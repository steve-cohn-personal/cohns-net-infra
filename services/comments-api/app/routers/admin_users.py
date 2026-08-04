"""User administration (moderator only) + the access-request notification.

Grant/revoke a user's group membership so a moderator can approve people into the
family library from the site, instead of the AWS console. The heavy lifting (cross-
account Cognito) lives in app.aws_admin; here we just authorize and validate.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app import aws_admin
from app.auth import Principal, current_user, require_moderator
from app.config import Settings, get_settings
from app.schemas import AccessRequest, UserAdmin

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_moderator)])


def _require_configured(users_or_none):
    if users_or_none is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "user administration is not configured"
        )
    return users_or_none


@router.get("/users", response_model=list[UserAdmin])
async def list_users(settings: Settings = Depends(get_settings)):
    try:
        return _require_configured(aws_admin.list_users(settings))
    except HTTPException:
        raise
    except Exception as exc:  # boto/network errors -> 502, not a 500 stacktrace
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"cognito error: {exc}") from exc


def _check_group(group: str, settings: Settings):
    if group not in settings.grantable_groups:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"group must be one of {settings.grantable_groups}",
        )


@router.put("/users/{username}/groups/{group}", status_code=status.HTTP_204_NO_CONTENT)
async def grant_group(username: str, group: str, settings: Settings = Depends(get_settings)):
    """Add the user to the group (idempotent). The user must re-sign-in to pick it up."""
    _check_group(group, settings)
    try:
        _require_configured(aws_admin.set_group(settings, username, group, member=True))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"cognito error: {exc}") from exc


@router.delete("/users/{username}/groups/{group}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_group(username: str, group: str, settings: Settings = Depends(get_settings)):
    """Remove the user from the group."""
    _check_group(group, settings)
    try:
        _require_configured(aws_admin.set_group(settings, username, group, member=False))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"cognito error: {exc}") from exc


# --- Access requests (any signed-in user, not moderator) --------------------

requests_router = APIRouter(tags=["admin"])


@requests_router.post("/access-requests", status_code=status.HTTP_202_ACCEPTED)
async def request_access(
    payload: AccessRequest,
    user: Principal = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    """A signed-in user asks to be let into a gated area; emails the moderators.
    Always 202 — a missing notification topic is not the requester's problem."""
    _check_group(payload.group, settings)
    try:
        notified = aws_admin.notify_access_request(
            settings, name=user.name, email=user.email, sub=user.sub, group=payload.group
        )
    except Exception:
        notified = False
    return {"status": "received", "notified": notified}
