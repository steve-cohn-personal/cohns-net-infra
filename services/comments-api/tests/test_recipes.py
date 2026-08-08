from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731

RECIPE = {
    "slug": "pan-con-tomate",
    "title": "Pan con Tomate",
    "summary": "The simplest good thing.",
    "ingredients": ["bread", "tomato", "olive oil", "salt"],
    "steps": ["Toast the bread", "Rub with tomato", "Oil and salt"],
    "published": True,
}


async def test_authoring_requires_moderator(client):
    assert (await client.post("/recipes", json=RECIPE)).status_code == 401  # no token
    assert (await client.post("/recipes", json=RECIPE, headers=auth(make_token()))).status_code == 403  # not a mod


async def test_create_publish_and_read(client):
    r = await client.post("/recipes", json=RECIPE, headers=auth(MOD()))
    assert r.status_code == 201
    body = r.json()
    assert body["published"] is True and body["ingredients"][1] == "tomato"

    # Public list + detail show it.
    assert [x["slug"] for x in (await client.get("/recipes")).json()] == ["pan-con-tomate"]
    got = await client.get("/recipes/pan-con-tomate")
    assert got.status_code == 200
    assert got.json()["steps"][0] == "Toast the bread"
    assert "published" not in got.json()  # public shape hides draft state


async def test_draft_is_hidden_from_public(client):
    draft = {**RECIPE, "slug": "secret-sauce", "published": False}
    await client.post("/recipes", json=draft, headers=auth(MOD()))

    assert (await client.get("/recipes")).json() == []
    assert (await client.get("/recipes/secret-sauce")).status_code == 404
    # but a moderator sees it in the admin list
    admin = await client.get("/admin/recipes", headers=auth(MOD()))
    assert [x["slug"] for x in admin.json()] == ["secret-sauce"]


async def test_update_recipe(client):
    await client.post("/recipes", json={**RECIPE, "published": False}, headers=auth(MOD()))
    upd = {**RECIPE, "title": "Pan con Tomate (v2)", "video_key": "lessons/pan-con-tomate", "published": True}
    r = await client.put("/recipes/pan-con-tomate", json=upd, headers=auth(MOD()))
    assert r.status_code == 200
    assert r.json()["title"] == "Pan con Tomate (v2)"
    assert (await client.get("/recipes/pan-con-tomate")).json()["video_key"] == "lessons/pan-con-tomate"


async def test_duplicate_slug_rejected(client):
    assert (await client.post("/recipes", json=RECIPE, headers=auth(MOD()))).status_code == 201
    assert (await client.post("/recipes", json=RECIPE, headers=auth(MOD()))).status_code == 409


async def test_slug_validation(client):
    bad = {**RECIPE, "slug": "Not a Slug!"}
    assert (await client.post("/recipes", json=bad, headers=auth(MOD()))).status_code == 422


async def test_notes_round_trips(client):
    story = "A **story** with a [link](https://example.com?tag=x&y=1).\n\n- one\n- two"
    r = await client.post("/recipes", json={**RECIPE, "notes": story}, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["notes"] == story  # raw Markdown stored; rendered client-side
    assert (await client.get("/recipes/pan-con-tomate")).json()["notes"] == story


async def test_categories_endpoint(client):
    cats = (await client.get("/recipes/categories")).json()
    assert cats == ["Breads", "Candy", "Quick Meals", "Appetizers", "Main Courses", "Desserts"]


async def test_category_round_trips_and_is_public(client):
    r = await client.post("/recipes", json={**RECIPE, "category": "Breads"}, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["category"] == "Breads"
    assert (await client.get("/recipes/pan-con-tomate")).json()["category"] == "Breads"


async def test_null_category_allowed(client):
    r = await client.post("/recipes", json={**RECIPE, "category": None}, headers=auth(MOD()))
    assert r.status_code == 201 and r.json()["category"] is None


async def test_unknown_category_rejected(client):
    bad = {**RECIPE, "category": "Breakfast"}
    assert (await client.post("/recipes", json=bad, headers=auth(MOD()))).status_code == 422


async def test_filter_by_category(client):
    await client.post("/recipes", json={**RECIPE, "slug": "sourdough", "category": "Breads"}, headers=auth(MOD()))
    await client.post("/recipes", json={**RECIPE, "slug": "fudge", "category": "Candy"}, headers=auth(MOD()))
    breads = (await client.get("/recipes", params={"category": "Breads"})).json()
    assert [x["slug"] for x in breads] == ["sourdough"]
    assert (await client.get("/recipes", params={"category": "Desserts"})).json() == []
