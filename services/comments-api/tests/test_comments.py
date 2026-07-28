from tests.conftest import auth, make_token

READER = "http://test"


async def _post(client, token, slug="blog/hello", body="Nice post!"):
    return await client.post("/comments", json={"page_slug": slug, "body": body}, headers=auth(token))


async def test_health_and_ready(client):
    assert (await client.get("/healthz")).status_code == 200
    assert (await client.get("/readyz")).status_code == 200


async def test_post_requires_auth(client):
    r = await client.post("/comments", json={"page_slug": "blog/hello", "body": "hi"})
    assert r.status_code == 401  # missing bearer credential


async def test_invalid_token_rejected(client):
    r = await _post(client, "not-a-jwt")
    assert r.status_code == 401


async def test_post_is_held_pending_and_hidden(client):
    r = await _post(client, make_token())
    assert r.status_code == 201
    assert r.json()["status"] == "pending"

    # The public read path shows nothing until moderation.
    listed = await client.get("/comments", params={"page_slug": "blog/hello"})
    assert listed.status_code == 200
    assert listed.json() == []


async def test_moderation_requires_moderator_role(client):
    r = await client.get("/admin/comments", headers=auth(make_token()))
    assert r.status_code == 403


async def test_moderator_approves_and_it_publishes(client):
    posted = (await _post(client, make_token(sub="u1", name="Alice"))).json()
    mod = make_token(sub="mod", name="Mod", groups=["moderators"])

    queue = await client.get("/admin/comments", headers=auth(mod))
    assert queue.status_code == 200
    assert len(queue.json()) == 1

    approve = await client.post(
        f"/comments/{posted['id']}/moderate".replace("/comments", "/admin/comments"),
        json={"decision": "approved"},
        headers=auth(mod),
    )
    assert approve.status_code == 200
    assert approve.json()["moderated_by"] == "mod"

    public = await client.get("/comments", params={"page_slug": "blog/hello"})
    assert [c["author_name"] for c in public.json()] == ["Alice"]
    # The public shape never leaks the author's subject id.
    assert "author_sub" not in public.json()[0]


async def test_rejected_stays_hidden(client):
    posted = (await _post(client, make_token())).json()
    mod = make_token(sub="mod", groups=["moderators"])
    await client.post(f"/admin/comments/{posted['id']}/moderate", json={"decision": "rejected"}, headers=auth(mod))

    public = await client.get("/comments", params={"page_slug": "blog/hello"})
    assert public.json() == []


async def test_body_validation(client):
    r = await client.post("/comments", json={"page_slug": "blog/hello", "body": ""}, headers=auth(make_token()))
    assert r.status_code == 422


async def test_rate_limit_blocks_bursts(client):
    from app.ratelimit import limiter

    limiter.enabled = True  # default is 5/minute; storage is fresh (others ran disabled)
    try:
        codes = [(await _post(client, make_token(), body=f"c{i}")).status_code for i in range(6)]
    finally:
        limiter.enabled = False
    assert codes.count(201) == 5
    assert codes[-1] == 429
