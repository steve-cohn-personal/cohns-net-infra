#!/usr/bin/env python3
"""Load a class's "tools I used" list into the cohns.net content API.

The products used in a class — each an Amazon affiliate link — are structured data
(a design handoff, or curated by hand), not prose. This tool sets a class's `tools`
field from a canonical JSON data file, so importing the handoff list is one command
instead of hand-typing rows in the admin editor. Reusable across classes.

Data file shape (scripts/data/<class>-tools.json):

    { "slug": "cocktails-canapes",
      "tools": [ { "name": "...", "url": "https://amzn.to/…", "note": "..." }, … ] }

URLs are stored RAW (no `?tag=`); the site injects the Associates tag at render
(site/js/md.js). `note` is optional.

The class must already exist (create it in the admin editor first). This tool GETs
the class, preserves its other fields, and PUTs it back with the new `tools` — so
re-running just converges the list (idempotent). It does NOT create or delete classes.

Authoring is moderator-only (Cognito RS256), so this needs a moderator ID token:
pass --token or set COHNS_MODERATOR_TOKEN. Sign in on the site as a member of the
`moderators` group and copy the id_token.

Examples:
    ./scripts/load_class_tools.py --env prod --dry-run
    COHNS_MODERATOR_TOKEN=… ./scripts/load_class_tools.py --env prod
    COHNS_MODERATOR_TOKEN=… ./scripts/load_class_tools.py --env prod \
        --data scripts/data/cocktails-canapes-tools.json
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = REPO_ROOT / "scripts" / "data" / "cocktails-canapes-tools.json"

# Fields the moderator PUT (ClassWrite) accepts — everything but the server-owned
# id/sessions/timestamps. We carry these over from the existing class unchanged and
# only replace `tools`, so a load never clobbers the title, body, or publish state.
CLASS_WRITE_FIELDS = ["slug", "title", "summary", "description", "hero_image_url", "published", "sort_order"]


def api_base(env):
    """Match the site's api host derivation: dev -> api.dev.cohns.net, prod -> api.cohns.net."""
    return "https://api.cohns.net" if env == "prod" else f"https://api.{env}.cohns.net"


def load_data(path):
    data = json.loads(Path(path).read_text())
    slug = data.get("slug")
    tools = data.get("tools", [])
    if not slug:
        sys.exit(f"{path}: missing \"slug\".")
    for i, t in enumerate(tools):
        if not t.get("name") or not t.get("url"):
            sys.exit(f"{path}: tool #{i + 1} needs both \"name\" and \"url\".")
        if not str(t["url"]).startswith(("http://", "https://")):
            sys.exit(f"{path}: tool \"{t['name']}\" url must start with http:// or https:// "
                     f"(store the raw amzn.to link; the site adds the tag).")
    return slug, tools


def _check_token(token):
    """Fail early and clearly on a missing / placeholder / malformed token. A Cognito
    ID token is a long ASCII JWT (three dot-separated parts)."""
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
        sys.exit(f"could not reach {url}: {e.reason}\nIs the content API deployed and its DNS resolving?")


def find_class(base, token, slug):
    """Look the class up in the moderator listing (ClassAdmin carries id + all the
    ClassWrite fields we need to preserve)."""
    status, raw = _request("GET", f"{base}/admin/classes", token)
    if status == 401:
        sys.exit("401 unauthorized — the moderator token is expired or not in the `moderators` group.")
    if status != 200:
        sys.exit(f"could not list classes ({status}): {raw[:300].decode(errors='replace')}")
    for c in json.loads(raw):
        if c.get("slug") == slug:
            return c
    return None


def main():
    ap = argparse.ArgumentParser(description="Set a class's tools list from a JSON data file (moderator only).")
    ap.add_argument("--data", default=str(DEFAULT_DATA), help="Tools JSON ({slug, tools:[{name,url,note}]}).")
    ap.add_argument("--slug", help="Override the slug in the data file (target a different class).")
    ap.add_argument("--env", choices=["dev", "stage", "prod"], default="dev", help="Which content API to target.")
    ap.add_argument("--api-base", help="Override the API base URL (else derived from --env).")
    ap.add_argument("--token", default=os.environ.get("COHNS_MODERATOR_TOKEN"), help="Moderator Cognito ID token.")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be set; make no writes.")
    args = ap.parse_args()

    slug, tools = load_data(args.data)
    if args.slug:
        slug = args.slug
    base = args.api_base or api_base(args.env)

    print(f"{len(tools)} tool(s) for class '{slug}' from {args.data}")
    for t in tools:
        print(f"  • {t['name']}  {t['url']}")

    if args.dry_run:
        print(f"\nDry run — no API calls. Target: {base}")
        return

    token = _check_token(args.token)
    cls = find_class(base, token, slug)
    if cls is None:
        sys.exit(f"class '{slug}' not found on {base}. Create it in the admin editor first "
                 f"(this tool sets tools on an existing class; it does not create one).")

    payload = {k: cls.get(k) for k in CLASS_WRITE_FIELDS}
    payload["tools"] = tools
    status, raw = _request("PUT", f"{base}/admin/classes/{cls['id']}", token, payload)
    if status == 200:
        print(f"\nupdated '{slug}' → {len(tools)} tool(s)  ({base})")
    else:
        sys.exit(f"\nFAILED to update '{slug}' (PUT {status}): {raw[:400].decode(errors='replace')}")


if __name__ == "__main__":
    main()
