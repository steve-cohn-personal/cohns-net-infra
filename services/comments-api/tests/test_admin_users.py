"""Admin user-management endpoints. The AWS layer (app.aws_admin) is monkeypatched
— these cover authorization, validation, and wiring, not real Cognito calls."""

import pytest

from app import aws_admin
from tests.conftest import auth, make_token

pytestmark = pytest.mark.asyncio

FAKE_USERS = [
    {"username": "u-1", "email": "a@x.com", "name": "Alice", "status": "CONFIRMED", "enabled": True, "groups": ["family"]},
    {"username": "u-2", "email": "b@x.com", "name": "Bob", "status": "CONFIRMED", "enabled": True, "groups": []},
]


async def test_list_requires_moderator(client):
    # No token at all -> 401 unauthenticated.
    assert (await client.get("/admin/users")).status_code == 401
    # Signed in, but not a moderator -> 403 forbidden.
    r = await client.get("/admin/users", headers=auth(make_token(groups=[])))
    assert r.status_code == 403


async def test_list_unconfigured_returns_503(client):
    # No cognito pool/role configured in tests -> aws_admin returns None -> 503.
    r = await client.get("/admin/users", headers=auth(make_token(groups=["moderators"])))
    assert r.status_code == 503


async def test_list_ok(client, monkeypatch):
    monkeypatch.setattr(aws_admin, "list_users", lambda settings: FAKE_USERS)
    r = await client.get("/admin/users", headers=auth(make_token(groups=["moderators"])))
    assert r.status_code == 200
    body = r.json()
    assert [u["email"] for u in body] == ["a@x.com", "b@x.com"]
    assert body[0]["groups"] == ["family"]


async def test_grant_and_revoke(client, monkeypatch):
    calls = []
    monkeypatch.setattr(aws_admin, "set_group", lambda s, u, g, member: calls.append((u, g, member)) or True)
    mod = auth(make_token(groups=["moderators"]))

    assert (await client.put("/admin/users/u-2/groups/family", headers=mod)).status_code == 204
    assert (await client.delete("/admin/users/u-1/groups/family", headers=mod)).status_code == 204
    assert calls == [("u-2", "family", True), ("u-1", "family", False)]


async def test_grant_rejects_unknown_group(client):
    r = await client.put("/admin/users/u-2/groups/superadmin", headers=auth(make_token(groups=["moderators"])))
    assert r.status_code == 422


async def test_access_request_any_signed_in_user(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        aws_admin, "notify_access_request",
        lambda s, **kw: seen.update(kw) or True,
    )
    # A plain signed-in user (no groups) can request access.
    r = await client.post("/access-requests", json={"group": "family"}, headers=auth(make_token(sub="u-9", name="Carol", groups=[])))
    assert r.status_code == 202
    assert r.json()["notified"] is True
    assert seen["sub"] == "u-9" and seen["group"] == "family"


async def test_access_request_requires_auth(client):
    assert (await client.post("/access-requests", json={"group": "family"})).status_code == 401
