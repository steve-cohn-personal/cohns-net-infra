import uuid

from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731
SEED = ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"]


async def _cat(client, name):
    cats = (await client.get("/admin/categories", headers=auth(MOD()))).json()
    return next(c for c in cats if c["name"] == name)


async def test_public_categories_ordered(client):
    assert (await client.get("/recipes/categories")).json() == SEED


async def test_admin_list_gated(client):
    assert (await client.get("/admin/categories")).status_code == 401
    assert (await client.get("/admin/categories", headers=auth(make_token()))).status_code == 403
    ok = await client.get("/admin/categories", headers=auth(MOD()))
    assert ok.status_code == 200 and [c["name"] for c in ok.json()] == SEED


async def test_create_category_appears_public(client):
    r = await client.post("/admin/categories", json={"name": "Canning & Preserving", "sort_order": 6}, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["name"] == "Canning & Preserving"
    assert "Canning & Preserving" in (await client.get("/recipes/categories")).json()


async def test_create_gated_and_duplicate(client):
    assert (await client.post("/admin/categories", json={"name": "X"})).status_code == 401
    assert (await client.post("/admin/categories", json={"name": "X"}, headers=auth(make_token()))).status_code == 403
    assert (await client.post("/admin/categories", json={"name": "Breads"}, headers=auth(MOD()))).status_code == 409


async def test_new_category_is_usable_on_a_recipe(client):
    await client.post("/admin/categories", json={"name": "Canning & Preserving", "sort_order": 6}, headers=auth(MOD()))
    recipe = {"slug": "apple-butter", "title": "Apple Butter", "category": "Canning & Preserving",
              "ingredients": ["apples"], "steps": ["cook"], "published": True}
    r = await client.post("/recipes", json=recipe, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["category"] == "Canning & Preserving"


async def test_unknown_category_on_recipe_rejected(client):
    recipe = {"slug": "x", "title": "X", "category": "Nope", "ingredients": [], "steps": []}
    assert (await client.post("/recipes", json=recipe, headers=auth(MOD()))).status_code == 422


async def test_rename_cascades_to_recipes(client):
    bread = await _cat(client, "Breads")
    await client.post("/recipes", json={"slug": "sourdough", "title": "Sourdough", "category": "Breads",
                                        "ingredients": [], "steps": [], "published": True}, headers=auth(MOD()))
    r = await client.put(f"/admin/categories/{bread['id']}",
                         json={"name": "Breads & Rolls", "sort_order": bread["sort_order"]}, headers=auth(MOD()))
    assert r.status_code == 200
    assert (await client.get("/recipes/sourdough")).json()["category"] == "Breads & Rolls"
    assert "Breads & Rolls" in (await client.get("/recipes/categories")).json()


async def test_reorder_changes_public_order(client):
    desserts = await _cat(client, "Desserts")
    await client.put(f"/admin/categories/{desserts['id']}", json={"name": "Desserts", "sort_order": -1}, headers=auth(MOD()))
    assert (await client.get("/recipes/categories")).json()[0] == "Desserts"


async def test_delete_unused(client):
    candy = await _cat(client, "Candy")
    assert (await client.delete(f"/admin/categories/{candy['id']}", headers=auth(MOD()))).status_code == 204
    assert "Candy" not in (await client.get("/recipes/categories")).json()


async def test_delete_in_use_blocked(client):
    main = await _cat(client, "Main Courses")
    await client.post("/recipes", json={"slug": "paella", "title": "Paella", "category": "Main Courses",
                                        "ingredients": [], "steps": [], "published": True}, headers=auth(MOD()))
    assert (await client.delete(f"/admin/categories/{main['id']}", headers=auth(MOD()))).status_code == 409


async def test_delete_gated_and_missing(client):
    breads = await _cat(client, "Breads")
    assert (await client.delete(f"/admin/categories/{breads['id']}")).status_code == 401
    assert (await client.delete(f"/admin/categories/{uuid.uuid4()}", headers=auth(MOD()))).status_code == 404
