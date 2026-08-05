#!/usr/bin/env python3
"""Import a recipe from another website into the cohns.net RecipeWrite shape.

Fetches a page, reads its schema.org/Recipe JSON-LD, and emits a recipe record that
`load_recipes.py` can load into the content API (or fold into a canonical data file).

Copyright, deliberately: a recipe's *functional facts* — the ingredient list and the
procedural steps — aren't copyrightable, but the creative expression around them is
(the headnote, narrative flourish, photography). So this tool takes the facts and
**regenerates** the prose: it copies ingredients and step actions, builds a fresh
factual summary from the yield/times, credits the source, and never lifts the
`description` headnote or the images (`hero_image_url` is left null for a human to
set to one of our own). Output defaults to `published: false` — a moderator reviews
and publishes.

It reads JSON-LD only (the `<script type="application/ld+json">` block most recipe
sites embed); that is where the clean structured facts live. A page without it is
reported, not scraped — HTML scraping would be the place creative prose leaks back in.

Examples:
    ./scripts/import_recipe.py https://example.com/recipe -o /tmp/imported.json
    ./scripts/import_recipe.py URL1 URL2 | ./scripts/load_recipes.py --data /dev/stdin --dry-run
    ./scripts/import_recipe.py URL --published        # trust the source, skip the draft step

Then load with the existing tool:
    ./scripts/load_recipes.py --data /tmp/imported.json --env prod
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.robotparser import RobotFileParser

USER_AGENT = "cohns-net-recipe-import/1.0 (+https://cohns.net; personal recipe archive)"
FETCH_TIMEOUT = 20


# --- fetching ---------------------------------------------------------------

def robots_allows(url, user_agent=USER_AGENT):
    """True if the site's robots.txt permits fetching url. Fails OPEN on a missing
    or unreadable robots.txt (the common case), CLOSED only on an explicit Disallow."""
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    rp = RobotFileParser()
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        return True  # no readable robots.txt → not disallowed
    return rp.can_fetch(user_agent, url)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        sys.exit(f"{url}: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        sys.exit(f"{url}: could not fetch — {e.reason}")


# --- JSON-LD extraction -----------------------------------------------------

class _JsonLdExtractor(HTMLParser):
    """Collect the text of every <script type="application/ld+json"> block."""

    def __init__(self):
        super().__init__()
        self._in_ld = False
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type", "").strip().lower() == "application/ld+json":
            self._in_ld = True
            self.blocks.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_ld:
            self.blocks[-1] += data


def extract_jsonld(html):
    """Return every JSON object found in the page's JSON-LD blocks, flattened out of
    any @graph wrappers and top-level arrays."""
    extractor = _JsonLdExtractor()
    extractor.feed(html)
    objects = []
    for block in extractor.blocks:
        block = block.strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue  # a malformed block shouldn't sink the others
        for obj in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            if isinstance(graph, list):
                objects.extend(g for g in graph if isinstance(g, dict))
            else:
                objects.append(obj)
    return objects


def _is_recipe(obj):
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.lower() == "recipe" for x in types)


def find_recipe(objects):
    return next((o for o in objects if _is_recipe(o)), None)


# --- field mapping ----------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value):
    """HTML → plain text: unescape entities, drop tags, collapse whitespace. Tags
    become spaces (so `a</p><p>b` doesn't fuse into `ab`), then any space left
    stranded before punctuation is pulled back (`gently </b>.` → `gently.`)."""
    if not isinstance(value, str):
        return ""
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(value))).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def slugify(title, max_len=200):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    s = s[:max_len].strip("-")
    return s or "recipe"


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def flatten_instructions(instructions):
    """schema.org recipeInstructions come in every shape: a single blob of text, a
    list of strings, HowToStep objects, or HowToSection groups of steps. Normalize
    them all to a flat list of step strings."""
    steps = []
    for item in _as_list(instructions):
        if isinstance(item, str):
            # A single string may pack multiple steps behind newlines.
            steps.extend(clean_text(line) for line in item.splitlines() if clean_text(line))
        elif isinstance(item, dict):
            itype = item.get("@type", "")
            itype = itype[0] if isinstance(itype, list) else itype
            if itype == "HowToSection":
                steps.extend(flatten_instructions(item.get("itemListElement")))
            else:  # HowToStep / HowToDirection / bare {text|name}
                text = clean_text(item.get("text") or item.get("name") or "")
                if text:
                    steps.append(text)
    return steps


def _iso_duration_to_human(value):
    """PT1H30M → '1 hr 30 min'. Returns None on anything it can't read."""
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value.strip())
    if not m:
        return None
    days, hours, minutes, _ = (int(x) if x else 0 for x in m.groups())
    hours += days * 24
    parts = []
    if hours:
        parts.append(f"{hours} hr")
    if minutes:
        parts.append(f"{minutes} min")
    return " ".join(parts) or None


def _yield_text(value):
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, (int, float)):
        return f"Serves {int(value)}"
    text = clean_text(value) if isinstance(value, str) else ""
    if not text:
        return None
    return text if re.search(r"[a-zA-Z]", text) else f"Serves {text}"


def _source_name(recipe, source_url):
    author = recipe.get("author")
    if isinstance(author, list):
        author = author[0] if author else None
    if isinstance(author, dict):
        name = clean_text(author.get("name") or "")
        if name:
            return name
    if isinstance(author, str) and clean_text(author):
        return clean_text(author)
    return urllib.parse.urlsplit(source_url).netloc.removeprefix("www.")


def build_summary(recipe, source_url, max_len=2000):
    """A fresh, factual summary from yield + times, with attribution — NOT the
    source's headnote (which is the copyrightable creative part)."""
    facts = []
    y = _yield_text(recipe.get("recipeYield"))
    if y:
        facts.append(y)
    prep = _iso_duration_to_human(recipe.get("prepTime"))
    cook = _iso_duration_to_human(recipe.get("cookTime"))
    total = _iso_duration_to_human(recipe.get("totalTime"))
    if prep:
        facts.append(f"Prep {prep}")
    if cook:
        facts.append(f"Cook {cook}")
    if total and not (prep or cook):
        facts.append(f"Total {total}")

    summary = ". ".join(facts)
    if summary:
        summary += "."
    summary = (summary + f" Adapted from {_source_name(recipe, source_url)}: {source_url}").strip()
    return summary[:max_len]


def to_recipe_write(recipe, source_url, published=False):
    title = clean_text(recipe.get("name") or "")
    if not title:
        sys.exit(f"{source_url}: recipe JSON-LD has no name/title")

    ingredients = [clean_text(i) for i in _as_list(recipe.get("recipeIngredient") or recipe.get("ingredients"))]
    ingredients = [i for i in ingredients if i]
    steps = flatten_instructions(recipe.get("recipeInstructions"))
    if not ingredients and not steps:
        sys.exit(f"{source_url}: found a Recipe but no ingredients or instructions to import")

    return {
        "slug": slugify(title),
        "title": title[:200],
        "summary": build_summary(recipe, source_url),
        "ingredients": ingredients,
        "steps": steps,
        "hero_image_url": None,  # never lift the source's photo; set one of ours later
        "video_key": None,
        "published": published,
    }


def import_url(url, published=False):
    if not robots_allows(url):
        sys.exit(f"{url}: robots.txt disallows fetching this page")
    recipe = find_recipe(extract_jsonld(fetch(url)))
    if recipe is None:
        sys.exit(f"{url}: no schema.org/Recipe JSON-LD found on the page "
                 f"(this importer reads JSON-LD only — see the module docstring)")
    return to_recipe_write(recipe, url, published)


def main():
    ap = argparse.ArgumentParser(description="Import recipes from other sites (JSON-LD) into RecipeWrite JSON.")
    ap.add_argument("urls", nargs="+", help="Recipe page URL(s).")
    ap.add_argument("-o", "--out", help="Write the JSON array here (default: stdout).")
    ap.add_argument("--published", action="store_true",
                    help="Mark imported recipes published (default: draft for moderator review).")
    args = ap.parse_args()

    records = []
    for url in args.urls:
        rec = import_url(url, published=args.published)
        print(f"imported {rec['slug']} "
              f"({len(rec['ingredients'])} ingredients, {len(rec['steps'])} steps)", file=sys.stderr)
        records.append(rec)

    output = json.dumps(records, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(output)
        print(f"wrote {len(records)} recipe(s) → {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(output)


if __name__ == "__main__":
    main()
