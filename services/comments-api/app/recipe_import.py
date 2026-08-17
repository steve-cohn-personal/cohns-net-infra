"""Import a recipe from another site's schema.org/Recipe JSON-LD into RecipeWrite
shape. The server-side twin of scripts/import_recipe.py (kept separate: that one is
a standalone CLI, this runs inside the API) — same copyright discipline: take the
functional facts (ingredients, steps), regenerate the summary from yield/times with
attribution, never lift the headnote or images. Imports arrive as unpublished,
uncategorized drafts for a moderator to review, categorize, and publish.

Reads JSON-LD only; a page without it raises rather than HTML-scraping (scraping is
where creative prose leaks back in). robots.txt is honored.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from html.parser import HTMLParser
from urllib.robotparser import RobotFileParser

USER_AGENT = "cohns-net-recipe-import/1.0 (+https://cohns.net; personal recipe archive)"
FETCH_TIMEOUT = 20


class RecipeImportError(Exception):
    """Anything that stops an import — bad URL, robots block, no Recipe JSON-LD.
    The router turns these into a 4xx with this message."""


# --- fetching ---------------------------------------------------------------

def robots_allows(url: str) -> bool:
    """True if robots.txt permits the fetch. Fails OPEN on a missing/unreadable
    robots.txt, CLOSED only on an explicit Disallow."""
    parts = urllib.parse.urlsplit(url)
    robots_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    rp = RobotFileParser()
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError):
        return True
    return rp.can_fetch(USER_AGENT, url)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as e:
        raise RecipeImportError(f"the page returned HTTP {e.code} {e.reason}") from None
    except urllib.error.URLError as e:
        raise RecipeImportError(f"could not fetch the page: {e.reason}") from None


# --- JSON-LD extraction -----------------------------------------------------

class _JsonLdExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._in_ld = False
        self.blocks: list[str] = []

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


def extract_jsonld(html: str) -> list[dict]:
    extractor = _JsonLdExtractor()
    extractor.feed(html)
    objects: list[dict] = []
    for block in extractor.blocks:
        block = block.strip()
        if not block:
            continue
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError:
            continue
        for obj in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(obj, dict):
                continue
            graph = obj.get("@graph")
            if isinstance(graph, list):
                objects.extend(g for g in graph if isinstance(g, dict))
            else:
                objects.append(obj)
    return objects


def _is_recipe(obj: dict) -> bool:
    t = obj.get("@type")
    types = t if isinstance(t, list) else [t]
    return any(isinstance(x, str) and x.lower() == "recipe" for x in types)


def find_recipe(objects: list[dict]) -> dict | None:
    return next((o for o in objects if _is_recipe(o)), None)


# --- field mapping ----------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value) -> str:
    if not isinstance(value, str):
        return ""
    text = _WS_RE.sub(" ", _TAG_RE.sub(" ", unescape(value))).strip()
    return re.sub(r"\s+([.,;:!?])", r"\1", text)


def slugify(title: str, max_len: int = 200) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:max_len].strip("-") or "recipe"


def _as_list(value) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def flatten_instructions(instructions) -> list[str]:
    steps: list[str] = []
    for item in _as_list(instructions):
        if isinstance(item, str):
            steps.extend(clean_text(line) for line in item.splitlines() if clean_text(line))
        elif isinstance(item, dict):
            itype = item.get("@type", "")
            itype = itype[0] if isinstance(itype, list) else itype
            if itype == "HowToSection":
                steps.extend(flatten_instructions(item.get("itemListElement")))
            else:
                text = clean_text(item.get("text") or item.get("name") or "")
                if text:
                    steps.append(text)
    return steps


def _iso_duration_to_human(value) -> str | None:
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


def _yield_text(value) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, (int, float)):
        return f"Serves {int(value)}"
    text = clean_text(value) if isinstance(value, str) else ""
    if not text:
        return None
    return text if re.search(r"[a-zA-Z]", text) else f"Serves {text}"


_SERVINGS_RE = re.compile(r"(?:serves?|servings?|makes|yields?)\D*(\d+)|^\s*(\d+)\b", re.I)


def parse_servings(value) -> int | None:
    """Recover a serving *count* from a schema.org recipeYield, or None when the yield
    is a volume/size rather than a count ("about 3 liters", "one 9-inch pie"). A bare
    number or a "Serves N"/"N servings"/"Makes N" phrase counts; anything else does not.
    Takes the low end of a range ("4 to 6" -> 4). Clamped to the schema's 1..1000."""
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = int(value)
        return n if 1 <= n <= 1000 else None
    if not isinstance(value, str):
        return None
    text = clean_text(value)
    # A volume/weight yield is not a serving count — leave those unset (default 1).
    if re.search(r"\b(?:l|ml|liters?|litres?|g|kg|oz|lb|lbs|cups?|quarts?|pints?|gallons?)\b", text, re.I):
        return None
    m = _SERVINGS_RE.search(text)
    if not m:
        return None
    n = int(m.group(1) or m.group(2))
    return n if 1 <= n <= 1000 else None


def _source_name(recipe: dict, source_url: str) -> str:
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


def build_summary(recipe: dict, source_url: str, max_len: int = 2000) -> str:
    facts = []
    recipe_yield = recipe.get("recipeYield")
    # When the yield is a serving *count* it goes in the structured `servings` field,
    # so keep it out of the summary prose. A volume/size yield ("3 liters") has no
    # count and still belongs in the summary.
    if parse_servings(recipe_yield) is None:
        y = _yield_text(recipe_yield)
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
    return (summary + f" Adapted from {_source_name(recipe, source_url)}: {source_url}").strip()[:max_len]


def to_recipe_write(recipe: dict, source_url: str) -> dict:
    title = clean_text(recipe.get("name") or "")
    if not title:
        raise RecipeImportError("the recipe on that page has no title")
    ingredients = [i for i in (clean_text(x) for x in _as_list(recipe.get("recipeIngredient") or recipe.get("ingredients"))) if i]
    steps = flatten_instructions(recipe.get("recipeInstructions"))
    if not ingredients and not steps:
        raise RecipeImportError("found a recipe on that page but no ingredients or instructions")
    return {
        "slug": slugify(title),
        "title": title[:200],
        "category": None,          # a moderator picks the category before publishing
        "summary": build_summary(recipe, source_url),
        "servings": parse_servings(recipe.get("recipeYield")) or 1,
        "ingredients": ingredients,
        "steps": steps,
        "hero_image_url": None,    # never lift the source's photo
        "video_key": None,
        "published": False,        # draft — reviewed before it goes public
    }


def import_from_url(url: str) -> dict:
    """Fetch, parse, and return a RecipeWrite-shaped draft. Raises RecipeImportError
    on any failure (bad URL, robots block, no Recipe JSON-LD)."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise RecipeImportError("please provide a full http(s) URL")
    if not robots_allows(url):
        raise RecipeImportError("that site's robots.txt disallows fetching this page")
    recipe = find_recipe(extract_jsonld(fetch(url)))
    if recipe is None:
        raise RecipeImportError(
            "no schema.org/Recipe data found on that page — this importer reads structured "
            "recipe data (JSON-LD), which that page doesn't publish"
        )
    return to_recipe_write(recipe, url)
