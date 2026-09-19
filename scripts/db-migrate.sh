#!/usr/bin/env bash
# Run the comments-api Alembic migrations against an environment's (private) Aurora,
# as a one-off Fargate task. No new infrastructure: it reuses the running service's
# task definition and network — the execution role pulls the image, the task role
# reads the DB secret — exactly as the service itself does. Aurora is not publicly
# reachable, so migrations must run from inside the VPC like this.
#
#   ./scripts/db-migrate.sh dev                 # with the image the service is running
#   ./scripts/db-migrate.sh prod <sha>          # with the image for <sha>, BEFORE deploying it
#   ./scripts/db-migrate.sh prod <sha> --dry-run  # show what would run; register/run nothing
#   ./scripts/db-migrate.sh prod --stamp 0002
#
# The plain form runs `alembic upgrade head`.
#
# Which image runs the migration matters. Images are pinned to commit shas (#67), so
# the service's task definition names the image that is DEPLOYED, not the one about
# to be. Migrating with it before a deploy runs the old code, which doesn't contain
# the new migration — and prod runs auto_create_tables=false, so once the new code
# rolls it 500s on the column it expects. With a <sha>, the task runs that commit's
# image instead. ECS run-task overrides can't change a container's image, so this
# registers a copy of the service's task definition with the image swapped, under a
# separate family (comments-<env>-migrate) that neither the service nor Terraform
# ever points at, and deregisters it on exit. deploy-api.sh does this for you when
# the release adds migrations.
#
# --stamp REV is a ONE-TIME bootstrap for a database first created by the app's
# auto_create_tables (create_all) rather than by Alembic: create_all makes the
# tables but no alembic_version row, so a bare `upgrade` would try to recreate
# existing objects. --stamp records the baseline revision matching the current
# schema, then upgrades only the newer migrations. Use it once per such database;
# afterwards the plain form is correct.
#
# Env: AWS_PROFILE (default admin, the mgmt SSO profile that can assume into the
# workload account named in the compute tfvars), AWS_REGION (default us-west-2).
# Needs `gh` authenticated when a sha is given.
set -euo pipefail

usage="usage: db-migrate.sh <dev|stage|prod> [sha] [--stamp REV] [--dry-run]"
ENV="${1:?$usage}"
shift
SHA=""
STAMP=""
DRY_RUN=""
while [ $# -gt 0 ]; do
  case "$1" in
    --stamp)   STAMP="${2:?--stamp needs a revision, e.g. 0002}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*)        echo "$usage" >&2; exit 1 ;;
    *)         SHA="$1"; shift ;;
  esac
done

REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-admin}"
CLUSTER="comments-${ENV}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

# --- the image to migrate with --------------------------------------------------
# Same guard as deploy-api.sh: a sha with no successful container-build has no image.
if [ -n "$SHA" ]; then
  sha_arg="$SHA"
  [ "${#SHA}" -eq 40 ] || SHA="$(git -C "$repo_root" rev-parse --verify -q "${SHA}^{commit}" || true)"
  [ "${#SHA}" -eq 40 ] || { echo "could not resolve '${sha_arg}' to a full commit sha" >&2; exit 1; }
  build_status="$(gh run list --workflow=container-build --branch main --limit 50 \
    --json headSha,conclusion -q "[.[] | select(.headSha==\"${SHA}\")] | .[0].conclusion")"
  if [ "$build_status" != "success" ]; then
    echo "refusing to migrate with ${SHA}: no successful container-build for that commit (found: ${build_status:-none})" >&2
    exit 1
  fi
fi

role_arn="$(sed -nE 's/^[[:space:]]*account_role_arn[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' \
  "${repo_root}/terraform/live/compute/env/${ENV}.tfvars")"
[ -n "$role_arn" ] || { echo "no account_role_arn in compute ${ENV}.tfvars" >&2; exit 1; }

creds="$(aws sts assume-role --role-arn "$role_arn" --role-session-name "db-migrate-${ENV}" \
  --profile "$PROFILE" --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)"
export AWS_ACCESS_KEY_ID="$(echo "$creds" | cut -f1)"
export AWS_SECRET_ACCESS_KEY="$(echo "$creds" | cut -f2)"
export AWS_SESSION_TOKEN="$(echo "$creds" | cut -f3)"

svc="$(aws ecs describe-services --cluster "$CLUSTER" --services "$CLUSTER" --region "$REGION" \
  --query "services[?status=='ACTIVE'] | [0].{td: taskDefinition, net: networkConfiguration.awsvpcConfiguration}" \
  --output json)"
read -r service_td subnets sgs < <(echo "$svc" | python3 -c '
import json, sys
s = json.load(sys.stdin)
if not s or not s.get("td"):
    sys.exit("no ACTIVE service " + sys.argv[1] + " — the migration task borrows its network and task definition")
n = s["net"]
print(s["td"], ",".join(n["subnets"]), ",".join(n["securityGroups"]))
' "$CLUSTER")
[ -n "${service_td:-}" ] || exit 1

run_td="$service_td"
td_json="$(aws ecs describe-task-definition --task-definition "$service_td" --region "$REGION" \
  --query taskDefinition --output json)"
image="$(echo "$td_json" | python3 -c '
import json, sys
print(next(c["image"] for c in json.load(sys.stdin)["containerDefinitions"] if c["name"] == sys.argv[1]))
' "$CLUSTER")"

spec=""
if [ -n "$SHA" ] && [ "${image##*:}" != "$SHA" ]; then
  spec="$(echo "$td_json" | python3 -c '
import json, sys
td, name, sha = json.load(sys.stdin), sys.argv[1], sys.argv[2]
keep = ("taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions", "volumes",
        "placementConstraints", "requiresCompatibilities", "cpu", "memory", "runtimePlatform",
        "ephemeralStorage", "pidMode", "ipcMode", "proxyConfiguration")
spec = {k: td[k] for k in keep if td.get(k) not in (None, [], {})}
spec["family"] = name + "-migrate"
for c in spec["containerDefinitions"]:
    if c["name"] == name:
        c["image"] = c["image"].rsplit(":", 1)[0] + ":" + sha
print(json.dumps(spec))
' "$CLUSTER" "$SHA")"
  image="${image%:*}:${SHA}"
fi

cmd="alembic upgrade head"
[ -n "$STAMP" ] && cmd="alembic stamp ${STAMP} && ${cmd}"
overrides="$(python3 -c 'import json,sys; print(json.dumps({"containerOverrides":[{"name":sys.argv[1],"command":["sh","-c",sys.argv[2]]}]}))' "$CLUSTER" "$cmd")"
echo "→ ${CLUSTER}: ${cmd}"

if [ -n "$DRY_RUN" ]; then
  echo "  image: ${image##*/}"
  if [ -n "$spec" ]; then
    echo "  would register ${CLUSTER}-migrate (copy of ${service_td##*/}, image swapped), run it, deregister it:"
    echo "$spec"
  else
    echo "  would run ${service_td##*/} as-is (it already runs that image)"
  fi
  echo "dry run — nothing registered or run."
  exit 0
fi

if [ -n "$spec" ]; then
  run_td="$(aws ecs register-task-definition --region "$REGION" --cli-input-json "$spec" \
    --query 'taskDefinition.taskDefinitionArn' --output text)"
  trap 'aws ecs deregister-task-definition --region "$REGION" --task-definition "$run_td" >/dev/null \
    || echo "warning: could not deregister ${run_td##*/}" >&2' EXIT
fi
echo "  image: ${image##*/} (task definition ${run_td##*/})"

task="$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$run_td" --launch-type FARGATE --region "$REGION" \
  --network-configuration "awsvpcConfiguration={subnets=[${subnets}],securityGroups=[${sgs}],assignPublicIp=ENABLED}" \
  --overrides "$overrides" --query 'tasks[0].taskArn' --output text)"
echo "task: ${task##*/}"
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$task" --region "$REGION"

exit_code="$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$task" --region "$REGION" \
  --query 'tasks[0].containers[0].exitCode' --output text)"
stream="$(aws logs describe-log-streams --region "$REGION" --log-group-name "/ecs/${CLUSTER}" \
  --order-by LastEventTime --descending \
  --query "logStreams[?contains(logStreamName, '${task##*/}')].logStreamName | [0]" --output text)"
echo "--- migration logs ---"
aws logs get-log-events --region "$REGION" --log-group-name "/ecs/${CLUSTER}" \
  --log-stream-name "$stream" --query 'events[].message' --output text | tail -15
echo "exit code: ${exit_code}"
[ "$exit_code" = "0" ]
