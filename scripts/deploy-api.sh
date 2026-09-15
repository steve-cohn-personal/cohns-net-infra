#!/usr/bin/env bash
# Deploy a comments-api image to an environment, pinned to its commit SHA.
#
#   ./scripts/deploy-api.sh dev             # newest built image
#   ./scripts/deploy-api.sh prod            # newest built image, with confirmation
#   ./scripts/deploy-api.sh prod <sha>      # a specific commit
#   ./scripts/deploy-api.sh prod --yes      # skip the confirmation prompt
#
# Why this exists (see issue #67). `container_image` used to be the constant
# "<ecr>/cohns/comments-api:latest" in every tfvars file. A constant never changes,
# so Terraform saw no diff, never made a new task-definition revision, and never
# deployed — the service only picked up a new image if something happened to
# restart it and re-pull the tag. On 2026-09-02 a deployment pulled :latest one
# minute BEFORE the image for #64 was built; the fix in that PR sat undeployed for
# a week until a rotated database secret took the API down. Pinning the tag to a
# commit makes each deploy a real Terraform diff and makes "what is prod running?"
# answerable from state instead of from image digests and build timestamps.
#
# The script refuses to deploy a SHA that has no successful container-build run.
# That is the exact race above: the tag would resolve to nothing, or worse, to a
# stale image under a moving tag.
#
# Env: AWS_PROFILE (default admin, the mgmt SSO profile the compute stack uses),
# AWS_REGION (default us-west-2). Needs `gh` authenticated for the build check.
set -euo pipefail

ENV="${1:?usage: deploy-api.sh <dev|stage|prod> [sha] [--yes]}"
shift

SHA=""
ASSUME_YES=""
for arg in "$@"; do
  case "$arg" in
    --yes) ASSUME_YES=1 ;;
    *)     SHA="$arg" ;;
  esac
done

REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-admin}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
stack="${repo_root}/terraform/live/compute"
tfvars="${stack}/env/${ENV}.tfvars"

[ -f "$tfvars" ] || { echo "no tfvars for '${ENV}' at ${tfvars}" >&2; exit 1; }

# --- resolve the commit to deploy ------------------------------------------
# container-build only runs on changes under services/comments-api, so most
# commits on main have NO image. "Newest image" is the newest successful build,
# which is usually older than origin/main — deploying `git rev-parse main` blindly
# would ask for a tag that was never pushed.
if [ -z "$SHA" ]; then
  SHA="$(gh run list --workflow=container-build --branch main --status success \
           --limit 1 --json headSha -q '.[0].headSha')"
  [ -n "$SHA" ] || { echo "could not find a successful container-build on main" >&2; exit 1; }
  echo "resolved newest built image: ${SHA}"
fi

# Accept a short SHA for convenience, but pin the full one: the image is tagged
# with github.sha, which is always 40 characters.
if [ "${#SHA}" -ne 40 ]; then
  SHA="$(git -C "$repo_root" rev-parse "$SHA" 2>/dev/null || true)"
  [ "${#SHA}" -eq 40 ] || { echo "could not resolve '${1:-}' to a full commit sha" >&2; exit 1; }
fi

# --- verify the image was actually built -----------------------------------
# ECR lives in the shared-services account, which the laptop SSO profiles cannot
# read, so confirm via the build that produced the tag rather than the registry.
build_status="$(gh run list --workflow=container-build --branch main --limit 50 \
  --json headSha,conclusion -q "[.[] | select(.headSha==\"${SHA}\")] | .[0].conclusion")"

if [ "$build_status" != "success" ]; then
  cat >&2 <<EOF
refusing to deploy ${SHA}: no successful container-build for that commit
  (found: ${build_status:-none})

The image tag would not exist in ECR. If the build is still running, wait for it.
If the commit did not touch services/comments-api, no image was built for it —
deploy the newest built commit instead by omitting the sha argument.
EOF
  exit 1
fi

# --- work out the change ----------------------------------------------------
current="$(sed -nE 's/^[[:space:]]*container_image[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' "$tfvars")"
[ -n "$current" ] || { echo "no container_image in ${tfvars}" >&2; exit 1; }

repo_uri="${current%:*}"
desired="${repo_uri}:${SHA}"

echo
echo "environment : ${ENV}"
echo "currently   : ${current}"
echo "deploying   : ${desired}"
echo

if [ "$current" = "$desired" ]; then
  echo "already pinned to that image — nothing to deploy."
  exit 0
fi

if [ "$ENV" = "prod" ] && [ -z "$ASSUME_YES" ]; then
  printf 'apply to PROD? [y/N] '
  read -r reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "aborted."; exit 1; }
fi

# --- apply ------------------------------------------------------------------
# tfvars is gitignored and local-only for this stack (compute is not CI-applied),
# so it doubles as the record of what each environment is pinned to.
tmp="$(mktemp)"
sed -E "s|^([[:space:]]*container_image[[:space:]]*=[[:space:]]*).*|\1\"${desired}\"|" "$tfvars" > "$tmp"
mv "$tmp" "$tfvars"

cd "$stack"
AWS_PROFILE="$PROFILE" terraform init -reconfigure -input=false \
  -backend-config="env/${ENV}.backend.hcl" >/dev/null
AWS_PROFILE="$PROFILE" terraform apply -input=false -var-file="env/${ENV}.tfvars" \
  ${ASSUME_YES:+-auto-approve}

# --- confirm it actually rolled ---------------------------------------------
echo
echo "waiting for the ECS deployment to stabilise..."
role_arn="$(sed -nE 's/^[[:space:]]*account_role_arn[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' "$tfvars")"
if [ -n "$role_arn" ]; then
  creds="$(aws sts assume-role --role-arn "$role_arn" --role-session-name "deploy-api-${ENV}" \
    --profile "$PROFILE" --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)"
  export AWS_ACCESS_KEY_ID="$(echo "$creds" | cut -f1)"
  export AWS_SECRET_ACCESS_KEY="$(echo "$creds" | cut -f2)"
  export AWS_SESSION_TOKEN="$(echo "$creds" | cut -f3)"
  unset AWS_PROFILE
  aws ecs wait services-stable --cluster "comments-${ENV}" --services "comments-${ENV}" \
    --region "$REGION" && echo "service stable."
fi

api_host="api.cohns.net"
[ "$ENV" = "prod" ] || api_host="api.${ENV}.cohns.net"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://${api_host}/readyz" || true)"
echo "https://${api_host}/readyz -> ${code}"
[ "$code" = "200" ] || { echo "readiness check did not return 200 — investigate before walking away." >&2; exit 1; }

echo
echo "deployed ${SHA} to ${ENV}."
echo "NOTE: ${stack} is now initialised against the ${ENV} backend."
