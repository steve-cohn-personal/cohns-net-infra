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
# "Is there anything to deploy?" is answered by asking ECS what the service is
# running, NOT by reading container_image from tfvars. tfvars is gitignored,
# local-only, and rewritten by this script before the apply — so after an apply
# that failed or was aborted it names an image that was never deployed. Trusting
# it would report "nothing to deploy" and exit 0 while the environment runs
# something else: the same proxy-for-state mistake as #67. The script only skips
# the apply when ECS positively confirms the desired image; if ECS can't be
# queried it applies anyway, because a no-op apply is cheap and a false "nothing
# to deploy" is not.
#
# Schema changes: if migration files were added between the running image and
# the one being deployed, the script runs `db-migrate.sh <env> <sha>` — with the
# NEW image, since the running one doesn't contain them — before the apply rolls
# the service onto code that needs them. A failed migration stops the deploy.
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
sha_arg="$SHA"

REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-admin}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
stack="${repo_root}/terraform/live/compute"
tfvars="${stack}/env/${ENV}.tfvars"

[ -f "$tfvars" ] || { echo "no tfvars for '${ENV}' at ${tfvars}" >&2; exit 1; }

role_arn="$(sed -nE 's/^[[:space:]]*account_role_arn[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' "$tfvars")"

# --- AWS helpers --------------------------------------------------------------
# Print "AccessKeyId<TAB>SecretAccessKey<TAB>SessionToken" for the environment
# account's role, assumed from the SSO profile.
assume_env_role() {
  [ -n "$role_arn" ] || { echo "no account_role_arn in ${tfvars}" >&2; return 1; }
  aws sts assume-role --role-arn "$role_arn" --role-session-name "deploy-api-${ENV}" \
    --profile "$PROFILE" --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text
}

# Export the assumed-role credentials into the current shell. Only call this
# inside a subshell: static keys in the environment take precedence over
# AWS_PROFILE, so if they leaked into the terraform run they would replace the
# mgmt profile and break the provider's own assume-role.
use_env_role() {
  local creds
  creds="$(assume_env_role)" || return 1
  export AWS_ACCESS_KEY_ID="$(cut -f1 <<<"$creds")"
  export AWS_SECRET_ACCESS_KEY="$(cut -f2 <<<"$creds")"
  export AWS_SESSION_TOKEN="$(cut -f3 <<<"$creds")"
  unset AWS_PROFILE
}

# Print the image the ECS service is running right now. Prints nothing and fails
# if it can't be positively determined: no credentials, no service yet (first
# deploy), or an API error. Runs in a subshell so the credentials stay contained.
running_image() (
  use_env_role || exit 1
  local td image
  td="$(aws ecs describe-services --cluster "comments-${ENV}" --services "comments-${ENV}" \
    --region "$REGION" --query "services[?status=='ACTIVE'] | [0].taskDefinition" --output text)" || exit 1
  case "$td" in ""|None) exit 1 ;; esac
  image="$(aws ecs describe-task-definition --task-definition "$td" --region "$REGION" \
    --query 'taskDefinition.containerDefinitions[0].image' --output text)" || exit 1
  case "$image" in ""|None) exit 1 ;; esac
  echo "$image"
)

# tfvars is gitignored and local-only for this stack (compute is not CI-applied);
# it is the apply's input, not a record of what is deployed.
pin_tfvars() {
  local tmp
  tmp="$(mktemp)"
  sed -E "s|^([[:space:]]*container_image[[:space:]]*=[[:space:]]*).*|\1\"$1\"|" "$tfvars" > "$tmp"
  mv "$tmp" "$tfvars"
}

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
  [ "${#SHA}" -eq 40 ] || { echo "could not resolve '${sha_arg}' to a full commit sha" >&2; exit 1; }
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
running="$(running_image)" || running=""

echo
echo "environment : ${ENV}"
echo "tfvars      : ${current}"
echo "running     : ${running:-unknown (could not read the service from ECS)}"
echo "deploying   : ${desired}"
echo

if [ -n "$running" ] && [ "$running" = "$desired" ]; then
  if [ "$current" != "$desired" ]; then
    pin_tfvars "$desired"
    echo "ECS confirms ${ENV} is already running that image; tfvars disagreed, so rewrote it to match."
  else
    echo "ECS confirms ${ENV} is already running that image — nothing to deploy."
  fi
  exit 0
fi

if [ -z "$running" ]; then
  echo "note: couldn't confirm the running image (first deploy, or no credentials) — applying anyway."
elif [ "$current" != "$running" ]; then
  echo "note: tfvars and ECS disagree — a previous apply likely failed or was aborted."
fi

# --- schema changes ---------------------------------------------------------
# New code can read columns the database doesn't have yet (prod runs
# auto_create_tables=false, so that's a 500), so migrations added between the
# running image and this one must run BEFORE the apply rolls the service — with
# the image being deployed, since the running image doesn't contain them.
# Only ADDED migration files count: going back to an older sha removes files, and
# `alembic upgrade head` from older code fails outright when the database is ahead.
versions_dir="services/comments-api/migrations/versions"
MIGRATE=""
running_sha="${running##*:}"
if [ -z "$running" ]; then
  echo "note: migrations not run — no running image to compare against, and the migration"
  echo "      task borrows the service's network. If this release changes the schema, run"
  echo "      ./scripts/db-migrate.sh ${ENV} ${SHA} once the service exists."
elif ! [[ "$running_sha" =~ ^[0-9a-f]{40}$ ]] || ! git -C "$repo_root" cat-file -e "${running_sha}^{commit}" 2>/dev/null; then
  MIGRATE=1
  echo "migrations  : will run first — can't diff against the running image, and upgrade head is a no-op when current"
else
  added="$(git -C "$repo_root" diff --name-only --diff-filter=A "$running_sha" "$SHA" -- "$versions_dir")"
  removed="$(git -C "$repo_root" diff --name-only --diff-filter=D "$running_sha" "$SHA" -- "$versions_dir")"
  if [ -n "$added" ]; then
    MIGRATE=1
    echo "migrations  : will run first, with the image being deployed:"
    sed 's|^.*/|                |' <<<"$added"
  else
    echo "migrations  : none added since the running image"
  fi
  if [ -n "$removed" ]; then
    echo "note: this image predates migrations the database may already have (not downgraded):"
    sed 's|^.*/|      |' <<<"$removed"
  fi
fi

if [ "$ENV" = "prod" ] && [ -z "$ASSUME_YES" ]; then
  printf 'apply to PROD? [y/N] '
  read -r reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || { echo "aborted."; exit 1; }
fi

# --- apply ------------------------------------------------------------------
# A failed migration stops here, before tfvars is rewritten or anything rolls.
if [ -n "$MIGRATE" ]; then
  AWS_PROFILE="$PROFILE" AWS_REGION="$REGION" "${repo_root}/scripts/db-migrate.sh" "$ENV" "$SHA"
  echo
fi
pin_tfvars "$desired"

cd "$stack"
AWS_PROFILE="$PROFILE" terraform init -reconfigure -input=false \
  -backend-config="env/${ENV}.backend.hcl" >/dev/null
AWS_PROFILE="$PROFILE" terraform apply -input=false -var-file="env/${ENV}.tfvars" \
  ${ASSUME_YES:+-auto-approve}

# --- confirm it actually rolled ---------------------------------------------
echo
if [ -n "$role_arn" ]; then
  echo "waiting for the ECS deployment to stabilise..."
  (
    use_env_role
    aws ecs wait services-stable --cluster "comments-${ENV}" --services "comments-${ENV}" \
      --region "$REGION"
  )
  echo "service stable."
fi

api_host="api.cohns.net"
[ "$ENV" = "prod" ] || api_host="api.${ENV}.cohns.net"
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 30 "https://${api_host}/readyz" || true)"
echo "https://${api_host}/readyz -> ${code}"
[ "$code" = "200" ] || { echo "readiness check did not return 200 — investigate before walking away." >&2; exit 1; }

echo
echo "deployed ${SHA} to ${ENV}."
echo "NOTE: ${stack} is now initialised against the ${ENV} backend."
