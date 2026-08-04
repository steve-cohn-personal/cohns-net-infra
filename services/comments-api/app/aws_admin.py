"""Cross-account Cognito user administration + access-request notifications.

The Cognito user pool lives in the shared-services account; this service runs in
prod. So the task assumes a scoped role (settings.cognito_admin_role_arn) to call
the Cognito admin APIs. The SNS topic for access-request emails is in this account,
so it uses the task's own credentials — no assume-role.

Everything is lazy and returns None when unconfigured (local/tests), which the
router turns into a clean 503 rather than a crash.
"""

import time

_clients: dict = {}


def _assumed_cognito(settings):
    """A cognito-idp client using credentials assumed into the pool's account.
    Cached until the assumed credentials near expiry. None if unconfigured."""
    if not (settings.cognito_pool_id and settings.cognito_admin_role_arn):
        return None

    cached = _clients.get("cognito")
    if cached and cached["expires"] - 120 > time.time():
        return cached["client"]

    import boto3

    creds = boto3.client("sts", region_name=settings.aws_region).assume_role(
        RoleArn=settings.cognito_admin_role_arn, RoleSessionName="comments-admin"
    )["Credentials"]
    client = boto3.client(
        "cognito-idp",
        region_name=settings.aws_region,
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
    _clients["cognito"] = {"client": client, "expires": creds["Expiration"].timestamp()}
    return client


def _attr(attrs, name):
    return next((a["Value"] for a in attrs if a["Name"] == name), None)


def list_users(settings):
    """Every pool user with their grantable-group membership. None if unconfigured."""
    cog = _assumed_cognito(settings)
    if cog is None:
        return None
    pool = settings.cognito_pool_id

    # One list_users_in_group per grantable group (a handful), rather than an
    # admin_list_groups_for_user per user, so this scales with groups not users.
    members: dict[str, set[str]] = {g: set() for g in settings.grantable_groups}
    for group in settings.grantable_groups:
        token = None
        while True:
            kw = {"UserPoolId": pool, "GroupName": group, "Limit": 60}
            if token:
                kw["NextToken"] = token
            resp = cog.list_users_in_group(**kw)
            members[group].update(u["Username"] for u in resp.get("Users", []))
            token = resp.get("NextToken")
            if not token:
                break

    users = []
    pag = None
    while True:
        kw = {"UserPoolId": pool, "Limit": 60}
        if pag:
            kw["PaginationToken"] = pag
        resp = cog.list_users(**kw)
        for u in resp.get("Users", []):
            uname = u["Username"]
            attrs = u.get("Attributes", [])
            users.append(
                {
                    "username": uname,
                    "email": _attr(attrs, "email"),
                    "name": _attr(attrs, "name"),
                    "status": u.get("UserStatus"),
                    "enabled": u.get("Enabled", True),
                    "groups": sorted(g for g, m in members.items() if uname in m),
                }
            )
        pag = resp.get("PaginationToken")
        if not pag:
            break
    users.sort(key=lambda x: (x["email"] or x["username"]).lower())
    return users


def set_group(settings, username: str, group: str, member: bool):
    """Add (member=True) or remove the user from the group. None if unconfigured."""
    cog = _assumed_cognito(settings)
    if cog is None:
        return None
    fn = cog.admin_add_user_to_group if member else cog.admin_remove_user_from_group
    fn(UserPoolId=settings.cognito_pool_id, Username=username, GroupName=group)
    return True


def notify_access_request(settings, *, name: str, email: str | None, sub: str, group: str) -> bool:
    """Email the moderators (via SNS) that someone asked for access. Returns False
    if no topic is configured (request still succeeds, just silently)."""
    if not settings.access_request_topic_arn:
        return False

    import boto3

    who = f"{name} <{email}>" if email else name
    boto3.client("sns", region_name=settings.aws_region).publish(
        TopicArn=settings.access_request_topic_arn,
        Subject="cohns.net — access request",
        Message=(
            f"{who} requested access to the '{group}' area.\n\n"
            f"Cognito username (sub): {sub}\n\n"
            f"Approve them from the admin page, or:\n"
            f"  aws cognito-idp admin-add-user-to-group "
            f"--user-pool-id {settings.cognito_pool_id} --group-name {group} --username {sub}\n"
        ),
    )
    return True
