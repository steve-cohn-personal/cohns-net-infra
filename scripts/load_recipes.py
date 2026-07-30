#!/usr/bin/env python3
"""Load authored recipes into the cohns.net content API — and/or emit the static
sample the site falls back to when the API is unreachable.

One canonical data file (scripts/data/*.json) is the single source of truth, in the
comments-api RecipeWrite shape (slug/title/summary/ingredients/steps/hero_image_url/
video_key/published). From it this tool can:

  * --emit-sample PATH : write the public-shape array (drops `published`) to PATH,
                         e.g. site/recipes-sample.json — no API needed.
  * (default)          : POST each recipe to the content API; on a slug conflict it
                         PUTs instead, so re-running is idempotent.

Authoring is moderator-only (Cognito RS256), so the API load needs a moderator ID
token: pass --token or set COHNS_MODERATOR_TOKEN. Sign in on the site as a member of
the `moderators` group and copy the id_token, or use `aws cognito-idp` for a test user.

Examples:
    ./scripts/load_recipes.py --emit-sample site/recipes-sample.json
    ./scripts/load_recipes.py --env dev --dry-run
    COHNS_MODERATOR_TOKEN=… ./scripts/load_recipes.py --env dev
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "scripts" / "data" / "paella-club-recipes.json"

# Fields the public read path exposes (mirrors RecipePublic) — the sample drops
# `published`, since only published recipes ever reach the sample.
PUBLIC_FIELDS = ["slug", "title", "summary", "ingredients", "steps", "hero_image_url", "video_key"]


def api_base(env):
    """Match the site's api host derivation: dev -> api.dev.cohns.net, prod -> api.cohns.net."""
    return "https://api.cohns.net" if env == "prod" else f"https://api.{env}.cohns.net"


def load_data(path):
    recipes = json.loads(Path(path).read_text())
    slugs = [r["slug"] for r in recipes]
    dupes = {s for s in slugs if slugs.count(s) > 1}
    if dupes:
        sys.exit(f"duplicate slugs in {path}: {', '.join(sorted(dupes))}")
    return recipes


def emit_sample(recipes, out_path):
    """Write only published recipes, in the public shape, as pretty JSON."""
    public = [{k: r.get(k) for k in PUBLIC_FIELDS} for r in recipes if r.get("published", False)]
    Path(out_path).write_text(json.dumps(public, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(public)} published recipe(s) → {out_path}")


def _check_token(token):
    """Fail early and clearly on a missing / placeholder / malformed token, rather
    than deep in urllib. A Cognito ID token is a long ASCII JWT (three dot-separated
    parts)."""
    if not token:
        sys.exit("no moderator token: pass --token or set COHNS_MODERATOR_TOKEN.")
    token = token.strip()
    if not token.isascii():
        sys.exit("token contains non-ASCII characters — did you paste the '…' placeholder "
                 "instead of a real moderator id_token?")
    if token.count(".") != 2:
        sys.exit("token doesn't look like a JWT (expected three dot-separated parts). "
                 "Use a moderator Cognito id_token.")
    return token


def _request(method, url, token, body=None):
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
        sys.exit(f"could not reach {url}: {e.reason}\n"
                 f"Is the content API deployed and its DNS resolving? "
                 f"(api.dev.cohns.net was not provisioned as of this writing.)")


def load_to_api(recipes, base, token, dry_run):
    if dry_run:
        for r in recipes:
            print(f"  [dry-run] would upsert {r['slug']} ({'published' if r.get('published') else 'draft'})")
        print(f"\nDry run — {len(recipes)} recipe(s), no API calls. Target: {base}")
        return
    token = _check_token(token)

    created = updated = failed = 0
    for r in recipes:
        status, raw = _request("POST", f"{base}/recipes", token, r)
        if status == 201:
            created += 1
            print(f"  created {r['slug']}")
        elif status == 409:
            # Already exists — update it in place so re-runs converge.
            status, raw = _request("PUT", f"{base}/recipes/{r['slug']}", token, r)
            if status == 200:
                updated += 1
                print(f"  updated {r['slug']}")
            else:
                failed += 1
                print(f"  FAILED {r['slug']} (PUT {status}): {raw[:300].decode(errors='replace')}")
        else:
            failed += 1
            print(f"  FAILED {r['slug']} (POST {status}): {raw[:300].decode(errors='replace')}")

    print(f"\ncreated {created}, updated {updated}, failed {failed}  →  {base}")
    if failed:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Load recipes into the content API or emit the static sample.")
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="Canonical recipe JSON (RecipeWrite shape).")
    ap.add_argument("--emit-sample", metavar="PATH", help="Write the public-shape sample here and exit (no API).")
    ap.add_argument("--env", choices=["dev", "stage", "prod"], default="dev", help="Which content API to target.")
    ap.add_argument("--api-base", help="Override the API base URL (else derived from --env).")
    ap.add_argument("--token", default=os.environ.get("COHNS_MODERATOR_TOKEN"), help="Moderator Cognito ID token.")
    ap.add_argument("--dry-run", action="store_true", help="List what would be upserted; make no API calls.")
    args = ap.parse_args()

    recipes = load_data(args.data)
    print(f"Loaded {len(recipes)} recipe(s) from {args.data}")

    if args.emit_sample:
        emit_sample(recipes, args.emit_sample)
        return

    base = args.api_base or api_base(args.env)
    load_to_api(recipes, base, args.token, args.dry_run)


if __name__ == "__main__":
    main()
