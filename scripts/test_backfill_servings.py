#!/usr/bin/env python3
"""Tests for backfill_servings.py's parse_servings — recovering a serving *count*
from a recipe summary's prose. The tricky cases are the imported summaries that read
"3 to 4 servings. Total 30 min.": a naive "servings\\D*(\\d+)" skips past the keyword
and grabs the cook-time minutes, so the count must be read *adjacent* to the keyword.

Run:  python3 scripts/test_backfill_servings.py
"""

import unittest

import backfill_servings as bf


class ParseServings(unittest.TestCase):
    def test_keyword_before_number(self):
        self.assertEqual(bf.parse_servings("Serves 6. Prep 45 min. Adapted from X."), 6)
        self.assertEqual(bf.parse_servings("Makes 12 muffins."), 12)

    def test_number_before_keyword(self):
        self.assertEqual(bf.parse_servings("A sweet and salty treat.  16 Servings."), 16)
        self.assertEqual(bf.parse_servings("4 servings. Total 20 min. Adapted from X."), 4)

    def test_range_takes_low_end(self):
        # The number must bind to "servings", not the time that follows it.
        self.assertEqual(bf.parse_servings("3 to 4 servings. Prep 15 min."), 3)
        self.assertEqual(bf.parse_servings("3 to 4 servings. Total 30 min."), 3)
        self.assertEqual(bf.parse_servings("4-6 servings."), 4)

    def test_does_not_grab_an_unrelated_number(self):
        # No count adjacent to a serving word → nothing (not the prep/cook minutes).
        self.assertIsNone(bf.parse_servings("A summer pasta salad. Prep 30 min."))
        self.assertIsNone(bf.parse_servings("Bake at 350 degrees for 20 minutes."))

    def test_volume_yield_is_not_a_count(self):
        self.assertIsNone(bf.parse_servings("A clean stock. Makes about 3 liters."))
        self.assertIsNone(bf.parse_servings("Makes 3 liters."))

    def test_no_yield_and_empty(self):
        self.assertIsNone(bf.parse_servings("A sugar syrup used in many cocktails"))
        self.assertIsNone(bf.parse_servings(""))
        self.assertIsNone(bf.parse_servings(None))

    def test_out_of_range_rejected(self):
        self.assertIsNone(bf.parse_servings("Serves 0."))
        self.assertIsNone(bf.parse_servings("Makes 5000."))


if __name__ == "__main__":
    unittest.main()
