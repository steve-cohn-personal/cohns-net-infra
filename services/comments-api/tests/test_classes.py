from datetime import datetime, timedelta, timezone

from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731


def _future(days=30):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


async def _make_class(client, slug="paella", published=True):
    r = await client.post("/admin/classes", json={"slug": slug, "title": slug.title(),
                          "summary": "A class", "published": published}, headers=auth(MOD()))
    assert r.status_code == 201
    return r.json()


async def _add_session(client, class_id, **kw):
    body = {"starts_at": _future(), "location": "Niwot Library", "capacity": 8}
    body.update(kw)
    r = await client.post(f"/admin/classes/{class_id}/sessions", json=body, headers=auth(MOD()))
    assert r.status_code == 201
    return r.json()


async def test_admin_gated(client):
    assert (await client.get("/admin/classes")).status_code == 401
    assert (await client.get("/admin/classes", headers=auth(make_token()))).status_code == 403
    assert (await client.post("/admin/classes", json={"slug": "x", "title": "X"})).status_code == 401


async def test_published_class_is_public_draft_is_not(client):
    await _make_class(client, "paella", published=True)
    await _make_class(client, "secret", published=False)
    slugs = [c["slug"] for c in (await client.get("/classes")).json()]
    assert slugs == ["paella"]
    assert (await client.get("/classes/secret")).status_code == 404
    assert (await client.get("/classes/nope")).status_code == 404


async def test_upcoming_session_shown_with_spots(client):
    c = await _make_class(client)
    await _add_session(client, c["id"], capacity=8)
    detail = (await client.get("/classes/paella")).json()
    assert len(detail["sessions"]) == 1
    assert detail["sessions"][0]["spots_left"] == 8


async def test_past_session_hidden(client):
    c = await _make_class(client)
    await _add_session(client, c["id"], starts_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    assert (await client.get("/classes/paella")).json()["sessions"] == []


async def test_signup_registers_and_appears_on_roster(client):
    c = await _make_class(client)
    s = await _add_session(client, c["id"], capacity=8)
    r = await client.post(f"/classes/paella/sessions/{s['id']}/signup",
                          json={"name": "Ada", "email": "ada@example.com", "party_size": 2})
    assert r.status_code == 202 and r.json()["status"] == "registered"
    # spots_left drops by the party size
    assert (await client.get("/classes/paella")).json()["sessions"][0]["spots_left"] == 6
    roster = (await client.get(f"/admin/classes/{c['id']}/signups", headers=auth(MOD()))).json()
    assert len(roster) == 1 and roster[0]["email"] == "ada@example.com" and roster[0]["status"] == "registered"


async def test_full_session_waitlists(client):
    c = await _make_class(client)
    s = await _add_session(client, c["id"], capacity=2)
    await client.post(f"/classes/paella/sessions/{s['id']}/signup",
                      json={"name": "A", "email": "a@x.com", "party_size": 2})
    r = await client.post(f"/classes/paella/sessions/{s['id']}/signup",
                          json={"name": "B", "email": "b@x.com", "party_size": 1})
    assert r.status_code == 202 and r.json()["status"] == "waitlisted"


async def test_honeypot_silently_dropped(client):
    c = await _make_class(client)
    s = await _add_session(client, c["id"])
    r = await client.post(f"/classes/paella/sessions/{s['id']}/signup",
                          json={"name": "Bot", "email": "bot@x.com", "hp": "gotcha"})
    assert r.status_code == 202
    assert (await client.get(f"/admin/classes/{c['id']}/signups", headers=auth(MOD()))).json() == []


async def test_bad_email_rejected(client):
    c = await _make_class(client)
    s = await _add_session(client, c["id"])
    r = await client.post(f"/classes/paella/sessions/{s['id']}/signup",
                          json={"name": "X", "email": "not-an-email"})
    assert r.status_code == 422


async def test_request_persists_and_lists(client):
    c = await _make_class(client)
    r = await client.post("/classes/paella/request",
                          json={"name": "Sam", "email": "sam@x.com", "message": "Weekends?",
                                "preferred_timeframe": "December"})
    assert r.status_code == 202
    reqs = (await client.get("/admin/class-requests", headers=auth(MOD()))).json()
    assert len(reqs) == 1 and reqs[0]["name"] == "Sam" and reqs[0]["class_id"] == c["id"]


async def test_tools_round_trip_public(client):
    r = await client.post("/admin/classes", json={
        "slug": "cocktails", "title": "Cocktails", "published": True,
        "tools": [{"name": "Jigger", "url": "https://amzn.to/abc", "note": "measure from above"},
                  {"name": "Blender", "url": "https://amzn.to/def"}],
    }, headers=auth(MOD()))
    assert r.status_code == 201
    detail = (await client.get("/classes/cocktails")).json()
    assert [t["name"] for t in detail["tools"]] == ["Jigger", "Blender"]
    assert detail["tools"][0]["url"] == "https://amzn.to/abc"  # stored raw, untagged
    assert detail["tools"][0]["note"] == "measure from above"
    assert detail["tools"][1]["note"] is None


async def test_tools_default_empty(client):
    await _make_class(client, "paella")
    assert (await client.get("/classes/paella")).json()["tools"] == []


async def test_tool_url_must_be_http(client):
    r = await client.post("/admin/classes", json={
        "slug": "bad", "title": "Bad", "published": True,
        "tools": [{"name": "X", "url": "javascript:alert(1)"}],
    }, headers=auth(MOD()))
    assert r.status_code == 422


async def test_tools_updated_via_put(client):
    c = await _make_class(client, "paella")
    r = await client.put(f"/admin/classes/{c['id']}", json={
        "slug": "paella", "title": "Paella", "published": True,
        "tools": [{"name": "Paella pan", "url": "https://amzn.to/pan"}],
    }, headers=auth(MOD()))
    assert r.status_code == 200
    assert (await client.get("/classes/paella")).json()["tools"][0]["name"] == "Paella pan"


async def test_delete_class_cascades_sessions(client):
    c = await _make_class(client)
    await _add_session(client, c["id"])
    assert (await client.delete(f"/admin/classes/{c['id']}", headers=auth(MOD()))).status_code == 204
    assert (await client.get("/classes/paella")).status_code == 404
