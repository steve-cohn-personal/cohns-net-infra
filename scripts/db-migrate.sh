#!/usr/bin/env bash
# Run the comments-api Alembic migrations against an environment's (private) Aurora,
# as a one-off Fargate task. No new infrastructure: it reuses the running service's
# task definition and network — the execution role pulls the image, the task role
# reads the DB secret — exactly as the service itself does. Aurora is not publicly
# reachable, so migrations must run from inside the VPC like this.
#
#   ./scripts/db-migrate.sh dev
#   ./scripts/db-migrate.sh prod --stamp 0002
#
# The plain form runs `alembic upgrade head`.
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
set -euo pipefail

ENV="${1:?usage: db-migrate.sh <dev|stage|prod> [--stamp REV]}"
STAMP=""
[ "${2:-}" = "--stamp" ] && STAMP="${3:?--stamp needs a revision, e.g. 0002}"

REGION="${AWS_REGION:-us-west-2}"
PROFILE="${AWS_PROFILE:-admin}"
CLUSTER="comments-${ENV}"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

role_arn="$(sed -nE 's/^[[:space:]]*account_role_arn[[:space:]]*=[[:space:]]*"(.*)".*/\1/p' \
  "${repo_root}/terraform/live/compute/env/${ENV}.tfvars")"
[ -n "$role_arn" ] || { echo "no account_role_arn in compute ${ENV}.tfvars" >&2; exit 1; }

creds="$(aws sts assume-role --role-arn "$role_arn" --role-session-name "db-migrate-${ENV}" \
  --profile "$PROFILE" --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text)"
export AWS_ACCESS_KEY_ID="$(echo "$creds" | cut -f1)"
export AWS_SECRET_ACCESS_KEY="$(echo "$creds" | cut -f2)"
export AWS_SESSION_TOKEN="$(echo "$creds" | cut -f3)"

net="$(aws ecs describe-services --cluster "$CLUSTER" --services "$CLUSTER" --region "$REGION" \
  --query 'services[0].networkConfiguration.awsvpcConfiguration' --output json)"
subnets="$(echo "$net" | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)["subnets"]))')"
sgs="$(echo "$net" | python3 -c 'import json,sys; print(",".join(json.load(sys.stdin)["securityGroups"]))')"

cmd="alembic upgrade head"
[ -n "$STAMP" ] && cmd="alembic stamp ${STAMP} && ${cmd}"
overrides="$(python3 -c 'import json,sys; print(json.dumps({"containerOverrides":[{"name":sys.argv[1],"command":["sh","-c",sys.argv[2]]}]}))' "$CLUSTER" "$cmd")"
echo "→ ${CLUSTER}: ${cmd}"

task="$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$CLUSTER" --launch-type FARGATE --region "$REGION" \
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
