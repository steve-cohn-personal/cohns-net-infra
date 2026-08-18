#!/usr/bin/env python3
"""Backfill the recipes' new `servings` field from the yield text buried in each
summary, and report the recipes that have no recoverable count (forced to 1) so they
can be reviewed and set by hand.

Migration 0008 adds `servings` NOT NULL default 1, so after it runs every recipe is 1.
Many summaries already state a yield in prose ("Serves 2", "Makes 12 muffins"); this
recovers that count into the structured field. A summary with only a volume/weight
yield ("Makes about 3 liters") or no yield at all has no serving count — those stay at
1 and land on the review list.

Reads the admin list (drafts included), so it needs a moderator Cognito ID token:
pass --token or set COHNS_MODERATOR_TOKEN (same as load_recipes.py). Only recipes
still at the default 1 are touched; a recipe already set to >1 is left alone, so
re-running is safe and idempotent.

Examples:
    # See what would change and which recipes need manual review — no writes:
    COHNS_MODERATOR_TOKEN=… ./scripts/backfill_servings.py --env prod --dry-run
    # Apply the recovered counts:
    COHNS_MODERATOR_TOKEN=… ./scripts/backfill_servings.py --env prod
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request

# Fields the API accepts on a write (RecipeWrite). We echo the recipe back unchanged
# except for `servings`, so the PUT is a no-op on everything else.
WRITE_FIELDS = [
    "slug", "title", "category", "cuisine", "difficulty", "summary", "notes",
    "servings", "ingredients", "steps", "hero_image_url", "video_key", "published",
]

# The number must sit *adjacent* to a serving keyword, or the parse grabs an
# unrelated number — imported summaries read "3 to 4 servings. Total 30 min.", and a
# loose "servings\D*(\d+)" would skip past "servings" and pick up the 30 in the time.
# Patterns, in priority order (low end of a range wins):
#   "3 to 4 servings" -> 3      "4 servings" / "16 Servings" -> N
#   "Serves 6" / "Makes 12" -> N
_RANGE_BEFORE = re.compile(r"(\d+)\s*(?:to|or|[-–—])\s*\d+\s+servings?\b", re.I)
_NUM_BEFORE = re.compile(r"(\d+)\s+servings?\b", re.I)
_KW_BEFORE = re.compile(r"\b(?:serves?|makes|yields?)\s*:?\s*(\d+)", re.I)
# A volume/weight yield is a size, not a count ("Makes 3 liters") — don't read a
# serving number from it unless the text also literally says "serves"/"servings".
_VOLUME_RE = re.compile(
    r"\b(?:l|ml|liters?|litres?|g|kg|oz|lb|lbs|cups?|quarts?|pints?|gallons?)\b", re.I
)


def parse_servings(summary: str | None) -> int | None:
    """Recover a serving count from summary prose, or None when there is only a
    volume/weight yield or no yield at all."""
    text = (summary or "").strip()
    if not text:
        return None
    if _VOLUME_RE.search(text) and not re.search(r"\bservings?\b|\bserves?\b", text, re.I):
        return None
    for rx in (_RANGE_BEFORE, _NUM_BEFORE, _KW_BEFORE):
        m = rx.search(text)
        if m:
            n = int(m.group(1))
            return n if 1 <= n <= 1000 else None
    return None


def api_base(env: str) -> str:
    return "https://api.cohns.net" if env == "prod" else f"https://api.{env}.cohns.net"


def _check_token(token: str | None) -> str:
    if not token:
        sys.exit("no moderator token: pass --token or set COHNS_MODERATOR_TOKEN.")
    token = token.strip()
    if not token.isascii() or token.count(".") != 2:
        sys.exit("token doesn't look like a moderator Cognito id_token (expected a JWT).")
    return token


def _request(method: str, url: str, token: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        sys.exit(f"could not reach {url}: {e.reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill recipe servings from summary text; report the rest.")
    ap.add_argument("--env", choices=["dev", "stage", "prod"], default="prod")
    ap.add_argument("--api-base", help="Override the API base URL (else derived from --env).")
    ap.add_argument("--token", default=os.environ.get("COHNS_MODERATOR_TOKEN"))
    ap.add_argument("--dry-run", action="store_true", help="Report only; make no writes.")
    args = ap.parse_args()

    base = args.api_base or api_base(args.env)
    token = _check_token(args.token)

    status, raw = _request("GET", f"{base}/admin/recipes", token)
    if status != 200:
        sys.exit(f"could not list recipes (HTTP {status}): {raw[:300].decode(errors='replace')}")
    recipes = json.loads(raw)
    print(f"{len(recipes)} recipe(s) from {base}\n")

    to_set: list[tuple[str, int]] = []   # (slug, servings) recovered from the summary
    already: list[tuple[str, int]] = []  # already set to >1 — left alone
    review: list[dict] = []              # no recoverable count — forced to 1, needs review

    for r in recipes:
        current = int(r.get("servings") or 1)
        if current > 1:
            already.append((r["slug"], current))
            continue
        n = parse_servings(r.get("summary"))
        if n and n > 1:
            to_set.append((r["slug"], n))
        else:
            review.append(r)

    # Apply the recovered counts.
    updated = failed = 0
    if not args.dry_run:
        by_slug = {r["slug"]: r for r in recipes}
        for slug, n in to_set:
            payload = {k: by_slug[slug].get(k) for k in WRITE_FIELDS}
            payload["servings"] = n
            st, body = _request("PUT", f"{base}/recipes/{slug}", token, payload)
            if st == 200:
                updated += 1
            else:
                failed += 1
                print(f"  FAILED {slug} (PUT {st}): {body[:200].decode(errors='replace')}")

    # --- report ---
    verb = "Would set" if args.dry_run else "Set"
    print(f"{verb} servings from summary ({len(to_set)}):")
    for slug, n in to_set:
        print(f"  {slug} → {n}")
    if already:
        print(f"\nAlready set, left alone ({len(already)}):")
        for slug, n in already:
            print(f"  {slug} = {n}")

    print(f"\n*** Review these — no serving count found, defaulted to 1 ({len(review)}): ***")
    for r in review:
        summ = (r.get("summary") or "").strip().replace("\n", " ")
        snippet = (summ[:80] + "…") if len(summ) > 80 else summ
        state = "published" if r.get("published") else "draft"
        print(f"  {r['slug']}  [{state}]  {snippet}")

    if not args.dry_run:
        print(f"\nupdated {updated}, failed {failed}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
