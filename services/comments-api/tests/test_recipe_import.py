import pytest

import app.recipe_import as ri
from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731

RECIPE_HTML = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Test Paella",
 "author":{"@type":"Person","name":"A. Chef"},
 "recipeYield":"4 servings","prepTime":"PT20M","cookTime":"PT40M",
 "description":"A LYRICAL COPYRIGHTED HEADNOTE about the coast.",
 "image":"https://src.example/hero.jpg",
 "recipeIngredient":["300g bomba rice","saffron"],
 "recipeInstructions":[{"@type":"HowToStep","text":"Saute."},{"@type":"HowToStep","text":"Simmer."}]}
</script></head><body></body></html>
"""


# --- import_from_url (fetch + robots patched, no network) -------------------

def test_import_parses_facts_and_regenerates_prose(monkeypatch):
    monkeypatch.setattr(ri, "robots_allows", lambda url: True)
    monkeypatch.setattr(ri, "fetch", lambda url: RECIPE_HTML)
    d = ri.import_from_url("https://src.example/recipe")
    assert d["title"] == "Test Paella" and d["slug"] == "test-paella"
    assert d["ingredients"] == ["300g bomba rice", "saffron"]
    assert d["steps"] == ["Saute.", "Simmer."]
    assert d["published"] is False and d["category"] is None and d["hero_image_url"] is None
    # copyright discipline: no headnote, no image; summary from facts + attribution
    assert "COPYRIGHTED" not in d["summary"]
    assert "4 servings" in d["summary"] and "Prep 20 min" in d["summary"] and "A. Chef" in d["summary"]


def test_import_no_jsonld_raises(monkeypatch):
    monkeypatch.setattr(ri, "robots_allows", lambda url: True)
    monkeypatch.setattr(ri, "fetch", lambda url: "<html><body>no structured data</body></html>")
    with pytest.raises(ri.RecipeImportError):
        ri.import_from_url("https://src.example/x")


def test_import_robots_blocked_raises(monkeypatch):
    monkeypatch.setattr(ri, "robots_allows", lambda url: False)
    with pytest.raises(ri.RecipeImportError):
        ri.import_from_url("https://src.example/x")


def test_import_bad_scheme_raises():
    with pytest.raises(ri.RecipeImportError):
        ri.import_from_url("not-a-url")


# --- POST /admin/recipes/import --------------------------------------------

async def test_import_endpoint_requires_moderator(client):
    body = {"url": "https://src.example/r"}
    assert (await client.post("/admin/recipes/import", json=body)).status_code == 401
    assert (await client.post("/admin/recipes/import", json=body, headers=auth(make_token()))).status_code == 403


async def test_import_endpoint_returns_unsaved_draft(client, monkeypatch):
    monkeypatch.setattr(ri, "robots_allows", lambda url: True)
    monkeypatch.setattr(ri, "fetch", lambda url: RECIPE_HTML)
    r = await client.post("/admin/recipes/import", json={"url": "https://src.example/r"}, headers=auth(MOD()))
    assert r.status_code == 200
    assert r.json()["title"] == "Test Paella" and r.json()["published"] is False
    assert (await client.get("/recipes/test-paella")).status_code == 404  # not saved


async def test_import_endpoint_422_when_no_recipe(client, monkeypatch):
    monkeypatch.setattr(ri, "robots_allows", lambda url: True)
    monkeypatch.setattr(ri, "fetch", lambda url: "<html></html>")
    r = await client.post("/admin/recipes/import", json={"url": "https://src.example/x"}, headers=auth(MOD()))
    assert r.status_code == 422


# --- DELETE /recipes/{slug} -------------------------------------------------

async def test_delete_recipe(client):
    recipe = {"slug": "gone", "title": "Gone", "ingredients": [], "steps": [], "published": True}
    await client.post("/recipes", json=recipe, headers=auth(MOD()))
    assert (await client.delete("/recipes/gone")).status_code == 401  # no token
    assert (await client.delete("/recipes/gone", headers=auth(make_token()))).status_code == 403  # not a mod
    assert (await client.delete("/recipes/gone", headers=auth(MOD()))).status_code == 204
    assert (await client.get("/recipes/gone")).status_code == 404
    assert (await client.delete("/recipes/nope", headers=auth(MOD()))).status_code == 404
