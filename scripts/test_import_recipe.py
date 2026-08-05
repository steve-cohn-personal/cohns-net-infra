#!/usr/bin/env python3
"""Tests for import_recipe.py — the fiddly bits are the JSON-LD shapes and the
copyright discipline, so that's what's covered. Pure functions only; no network.

Run:  python3 scripts/test_import_recipe.py
"""

import json
import unittest

import import_recipe as ir


class Slugify(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(ir.slugify("Seafood Paella"), "seafood-paella")

    def test_punctuation_and_accents_collapse(self):
        self.assertEqual(ir.slugify("Mom's  Best!! Soup — v2"), "mom-s-best-soup-v2")

    def test_matches_the_api_pattern(self):
        import re
        for title in ["Grandma's Rösti", "  ...Weird??  ", "42 Clove Garlic"]:
            self.assertRegex(ir.slugify(title), r"^[a-z0-9][a-z0-9-]*$")

    def test_never_empty(self):
        self.assertEqual(ir.slugify("!!!"), "recipe")


class IsoDuration(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(ir._iso_duration_to_human("PT1H30M"), "1 hr 30 min")

    def test_minutes_only(self):
        self.assertEqual(ir._iso_duration_to_human("PT20M"), "20 min")

    def test_days_roll_into_hours(self):
        self.assertEqual(ir._iso_duration_to_human("P1DT2H"), "26 hr")

    def test_garbage_is_none(self):
        self.assertIsNone(ir._iso_duration_to_human("soon"))
        self.assertIsNone(ir._iso_duration_to_human(None))


class Instructions(unittest.TestCase):
    def test_plain_string_splits_on_newlines(self):
        self.assertEqual(ir.flatten_instructions("Chop.\nFry.\n\nSimmer."), ["Chop.", "Fry.", "Simmer."])

    def test_list_of_howtostep(self):
        data = [{"@type": "HowToStep", "text": "Boil water."}, {"@type": "HowToStep", "text": "Add pasta."}]
        self.assertEqual(ir.flatten_instructions(data), ["Boil water.", "Add pasta."])

    def test_howtosection_is_flattened(self):
        data = [{
            "@type": "HowToSection",
            "name": "Sauce",
            "itemListElement": [
                {"@type": "HowToStep", "text": "Sauté onion."},
                {"@type": "HowToStep", "text": "Add tomato."},
            ],
        }]
        self.assertEqual(ir.flatten_instructions(data), ["Sauté onion.", "Add tomato."])

    def test_html_is_stripped(self):
        self.assertEqual(ir.flatten_instructions([{"@type": "HowToStep", "text": "Stir <b>gently</b>."}]),
                         ["Stir gently."])


class ExtractAndFind(unittest.TestCase):
    def test_graph_wrapped_recipe(self):
        html = """
        <html><head>
        <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"WebSite","name":"Some Site"},
          {"@type":"Recipe","name":"Test Stew","recipeIngredient":["1 onion"],
           "recipeInstructions":"Cook it."}
        ]}
        </script></head><body></body></html>
        """
        recipe = ir.find_recipe(ir.extract_jsonld(html))
        self.assertIsNotNone(recipe)
        self.assertEqual(recipe["name"], "Test Stew")

    def test_type_as_list(self):
        objs = [{"@type": ["Thing", "Recipe"], "name": "R"}]
        self.assertIsNotNone(ir.find_recipe(objs))

    def test_malformed_block_is_skipped_not_fatal(self):
        html = ('<script type="application/ld+json">{ broken</script>'
                '<script type="application/ld+json">{"@type":"Recipe","name":"OK"}</script>')
        recipe = ir.find_recipe(ir.extract_jsonld(html))
        self.assertEqual(recipe["name"], "OK")

    def test_no_recipe_returns_none(self):
        self.assertIsNone(ir.find_recipe(ir.extract_jsonld('<script type="application/ld+json">{"@type":"Article"}</script>')))


class CopyrightDiscipline(unittest.TestCase):
    """The point of the tool: facts in, creative expression out."""

    RECIPE = {
        "@type": "Recipe",
        "name": "Wild Mushroom Paella",
        "description": "A LYRICAL, COPYRIGHTED HEADNOTE about autumn in Catalonia.",
        "image": "https://source.example/hero.jpg",
        "author": {"@type": "Person", "name": "A. Chef"},
        "recipeYield": "4 servings",
        "prepTime": "PT20M",
        "cookTime": "PT40M",
        "recipeIngredient": ["300g bomba rice", "200g wild mushrooms"],
        "recipeInstructions": [{"@type": "HowToStep", "text": "Sauté the mushrooms."}],
    }

    def setUp(self):
        self.rec = ir.to_recipe_write(self.RECIPE, "https://source.example/recipe", published=False)

    def test_headnote_is_not_copied(self):
        self.assertNotIn("LYRICAL", self.rec["summary"])
        self.assertNotIn("Catalonia", self.rec["summary"])

    def test_summary_is_regenerated_from_facts_with_attribution(self):
        self.assertIn("4 servings", self.rec["summary"])
        self.assertIn("Prep 20 min", self.rec["summary"])
        self.assertIn("Cook 40 min", self.rec["summary"])
        self.assertIn("A. Chef", self.rec["summary"])
        self.assertIn("https://source.example/recipe", self.rec["summary"])

    def test_source_image_is_not_lifted(self):
        self.assertIsNone(self.rec["hero_image_url"])

    def test_defaults_to_draft(self):
        self.assertFalse(self.rec["published"])

    def test_facts_are_kept(self):
        self.assertEqual(self.rec["ingredients"], ["300g bomba rice", "200g wild mushrooms"])
        self.assertEqual(self.rec["steps"], ["Sauté the mushrooms."])

    def test_output_matches_recipewrite_keys(self):
        self.assertEqual(set(self.rec), {"slug", "title", "summary", "ingredients",
                                         "steps", "hero_image_url", "video_key", "published"})
        # round-trips as JSON (what load_recipes.py consumes)
        json.loads(json.dumps(self.rec))


if __name__ == "__main__":
    unittest.main(verbosity=2)
