import uuid

from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731
SEED = ["American", "Italian", "Spanish", "Mexican", "French"]


async def _cuisine(client, name):
    cuisines = (await client.get("/admin/cuisines", headers=auth(MOD()))).json()
    return next(c for c in cuisines if c["name"] == name)


async def test_public_cuisines_ordered(client):
    assert (await client.get("/recipes/cuisines")).json() == SEED


async def test_admin_list_gated(client):
    assert (await client.get("/admin/cuisines")).status_code == 401
    assert (await client.get("/admin/cuisines", headers=auth(make_token()))).status_code == 403
    ok = await client.get("/admin/cuisines", headers=auth(MOD()))
    assert ok.status_code == 200 and [c["name"] for c in ok.json()] == SEED


async def test_create_cuisine_appears_public(client):
    r = await client.post("/admin/cuisines", json={"name": "Thai", "sort_order": 5}, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["name"] == "Thai"
    assert "Thai" in (await client.get("/recipes/cuisines")).json()


async def test_create_gated_and_duplicate(client):
    assert (await client.post("/admin/cuisines", json={"name": "X"})).status_code == 401
    assert (await client.post("/admin/cuisines", json={"name": "X"}, headers=auth(make_token()))).status_code == 403
    assert (await client.post("/admin/cuisines", json={"name": "Italian"}, headers=auth(MOD()))).status_code == 409


async def test_new_cuisine_usable_on_recipe(client):
    await client.post("/admin/cuisines", json={"name": "Thai", "sort_order": 5}, headers=auth(MOD()))
    recipe = {"slug": "pad-thai", "title": "Pad Thai", "cuisine": "Thai",
              "ingredients": ["noodles"], "steps": ["stir-fry"], "published": True}
    r = await client.post("/recipes", json=recipe, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["cuisine"] == "Thai"


async def test_unknown_cuisine_on_recipe_rejected(client):
    recipe = {"slug": "x", "title": "X", "cuisine": "Klingon", "ingredients": [], "steps": []}
    assert (await client.post("/recipes", json=recipe, headers=auth(MOD()))).status_code == 422


async def test_rename_cascades_to_recipes(client):
    it = await _cuisine(client, "Italian")
    await client.post("/recipes", json={"slug": "carbonara", "title": "Carbonara", "cuisine": "Italian",
                                        "ingredients": [], "steps": [], "published": True}, headers=auth(MOD()))
    r = await client.put(f"/admin/cuisines/{it['id']}",
                         json={"name": "Italiano", "sort_order": it["sort_order"]}, headers=auth(MOD()))
    assert r.status_code == 200
    assert (await client.get("/recipes/carbonara")).json()["cuisine"] == "Italiano"


async def test_delete_in_use_blocked(client):
    sp = await _cuisine(client, "Spanish")
    await client.post("/recipes", json={"slug": "paella", "title": "Paella", "cuisine": "Spanish",
                                        "ingredients": [], "steps": [], "published": True}, headers=auth(MOD()))
    assert (await client.delete(f"/admin/cuisines/{sp['id']}", headers=auth(MOD()))).status_code == 409


async def test_delete_unused_and_missing(client):
    fr = await _cuisine(client, "French")
    assert (await client.delete(f"/admin/cuisines/{fr['id']}", headers=auth(MOD()))).status_code == 204
    assert "French" not in (await client.get("/recipes/cuisines")).json()
    assert (await client.delete(f"/admin/cuisines/{uuid.uuid4()}", headers=auth(MOD()))).status_code == 404
