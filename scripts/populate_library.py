#!/usr/bin/env python3
"""Populate the private family photo library (Phase 3) from the local macOS Photos app.

What it does
------------
1. Reads the chosen albums straight from the Photos SQLite catalog (read-only, on a
   copy — never the live DB) to enumerate the photos, their capture dates, and any
   caption you typed in Photos.
2. For each photo it picks the best JPEG *already on this Mac* — the original if it's
   local, otherwise Photos' full-res rendered derivative. RAW (.cr3) originals that
   live only in iCloud are never needed: the cached renders are far larger than the
   web needs. (Run with --require-original to skip anything whose original is remote.)
3. Downscales each to a web full-size (long edge <= --max-full) and a thumbnail
   (long edge <= --max-thumb) with `sips` — no third-party image libs required.
4. Writes manifest.json in the exact shape the list Lambda expects and uploads
   manifest + library/<id>.jpg + library/thumb/<id>.jpg to the private bucket.

Bucket and cross-account role are read from `terraform output` in live/family
(the account_role_arn output exists for exactly this), so nothing is hardcoded.

Credentials: uses the `admin` SSO profile to read Terraform state and to assume the
prod OrganizationAccountAccessRole for the upload. Run `aws sso login --profile admin`
first if the session has expired.

Typical use:
    ./scripts/populate_library.py --dry-run          # build + summarize, no upload
    ./scripts/populate_library.py --dry-run --limit 8 # smoke-test the pipeline
    ./scripts/populate_library.py                     # build + upload for real
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# Core Data reference date (2001-01-01 UTC) as a Unix timestamp; ZDATECREATED is
# stored as seconds since then.
CORE_DATA_EPOCH = 978307200

DEFAULT_ALBUMS = [
    "NYC Thanksgiving 2025",
    "2023 June Houston Trip",
    "2023 May UK Trip",
    "2023 NY October Unveiling",
    "Europe February 2023",
]

# Extensions we can hand to sips as an image source. RAW is excluded on purpose: the
# originals are in iCloud, and we prefer the rendered JPEG derivatives regardless.
IMAGE_EXTS = {".jpeg", ".jpg", ".heic", ".heif", ".png", ".tiff", ".tif"}

REPO_ROOT = Path(__file__).resolve().parent.parent
TF_DIR = REPO_ROOT / "terraform" / "live" / "family"
PHOTOS_LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"
AWS_PROFILE = os.environ.get("COHNS_AWS_PROFILE", "admin")


def run(cmd, **kw):
    """subprocess.run with check=True and captured text output."""
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


# --------------------------------------------------------------------------- AWS

def terraform_config():
    """bucket_name + account_role_arn from the live/family Terraform outputs."""
    env = {**os.environ, "AWS_PROFILE": AWS_PROFILE}
    try:
        out = run(["terraform", f"-chdir={TF_DIR}", "output", "-json"], env=env).stdout
    except subprocess.CalledProcessError as e:
        sys.exit(f"terraform output failed (is the family stack applied? SSO logged in?):\n{e.stderr}")
    outputs = json.loads(out)
    try:
        bucket = outputs["bucket_name"]["value"]
    except KeyError:
        sys.exit("missing Terraform output 'bucket_name'; is the family stack applied?")
    # Prefer the account_role_arn output, but fall back to family.auto.tfvars so the
    # script works even if that (infra-free) output hasn't been applied to state yet.
    role = outputs.get("account_role_arn", {}).get("value") or role_from_tfvars()
    if not role:
        sys.exit("no account_role_arn (output null and not found in family.auto.tfvars).")
    return bucket, role


def role_from_tfvars():
    tfvars = TF_DIR / "family.auto.tfvars"
    if not tfvars.exists():
        return None
    m = re.search(r'^\s*account_role_arn\s*=\s*"([^"]+)"', tfvars.read_text(), re.MULTILINE)
    return m.group(1) if m else None


def assume(role_arn):
    """Assume the prod role via the admin SSO profile; return an env dict with creds."""
    env = {**os.environ, "AWS_PROFILE": AWS_PROFILE}
    out = run(
        ["aws", "sts", "assume-role", "--role-arn", role_arn,
         "--role-session-name", "photo-populate", "--query", "Credentials", "--output", "json"],
        env=env,
    ).stdout
    c = json.loads(out)
    creds = {
        "AWS_ACCESS_KEY_ID": c["AccessKeyId"],
        "AWS_SECRET_ACCESS_KEY": c["SecretAccessKey"],
        "AWS_SESSION_TOKEN": c["SessionToken"],
    }
    # Drop any inherited profile so these explicit creds win.
    env = {k: v for k, v in os.environ.items() if k != "AWS_PROFILE"}
    env.update(creds)
    return env


# ------------------------------------------------------------------------ Photos

def open_catalog():
    """Copy the Photos SQLite catalog to a temp dir and open it read-only.

    We never touch the live DB: Photos keeps it in WAL mode and may hold a lock, so
    we snapshot the .sqlite (+ -wal/-shm if present) and query the copy.
    """
    src = PHOTOS_LIBRARY / "database" / "Photos.sqlite"
    if not src.exists():
        sys.exit(f"Photos catalog not found at {src} (Full Disk Access granted?).")
    tmp = Path(tempfile.mkdtemp(prefix="photodb-"))
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(src) + suffix)
        if f.exists():
            shutil.copy2(f, tmp / f.name)
    conn = sqlite3.connect(f"file:{tmp / 'Photos.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn, tmp


def album_join_table(conn):
    """The album<->asset join table is named Z_<n>ASSETS and <n> varies by macOS
    version, so discover it rather than hardcoding."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'Z_[0-9]*ASSETS'"
    ).fetchall()
    for r in rows:
        cols = [c["name"] for c in conn.execute(f"PRAGMA table_info({r['name']})")]
        if any(c.endswith("ALBUMS") for c in cols) and "Z_3ASSETS" in cols:
            albums_col = next(c for c in cols if c.endswith("ALBUMS"))
            return r["name"], albums_col
    sys.exit("could not locate the album/asset join table in the Photos catalog.")


def query_assets(conn, albums):
    join, albums_col = album_join_table(conn)
    placeholders = ",".join("?" for _ in albums)
    sql = f"""
        SELECT s.ZUUID       AS uuid,
               s.ZDIRECTORY  AS dir,
               s.ZFILENAME   AS fname,
               s.ZDATECREATED AS created,
               TRIM(a.ZTITLE) AS album,
               COALESCE(NULLIF(aa.ZTITLE,''), NULLIF(aa.ZASSETDESCRIPTION,'')) AS caption
        FROM ZASSET s
        JOIN {join} za ON za.Z_3ASSETS = s.Z_PK
        JOIN ZGENERICALBUM a ON a.Z_PK = za.{albums_col}
        LEFT JOIN ZADDITIONALASSETATTRIBUTES aa ON aa.ZASSET = s.Z_PK
        WHERE TRIM(a.ZTITLE) IN ({placeholders})
          AND s.ZKIND = 0            -- images only, no video
          AND s.ZTRASHEDSTATE = 0    -- not in Recently Deleted
          AND s.ZHIDDEN = 0          -- not hidden
          AND s.ZVISIBILITYSTATE = 0 -- normal visibility
    """
    rows = conn.execute(sql, albums).fetchall()
    # Dedup by UUID (a photo can sit in more than one chosen album); keep the newest
    # entry's metadata deterministically.
    seen = {}
    for r in rows:
        if r["uuid"] not in seen:
            seen[r["uuid"]] = r
    return list(seen.values())


def best_source(uuid, dir_):
    """Largest local JPEG-able file for this asset: original if present, else the
    biggest rendered derivative. Returns a Path or None."""
    candidates = []
    orig_dir = PHOTOS_LIBRARY / "originals" / dir_
    if orig_dir.is_dir():
        candidates += [p for p in orig_dir.glob(f"{uuid}.*") if p.suffix.lower() in IMAGE_EXTS]
    for sub in ("derivatives", "derivatives/masters"):
        d = PHOTOS_LIBRARY / "resources" / sub / dir_
        if d.is_dir():
            candidates += [p for p in d.glob(f"{uuid}*") if p.suffix.lower() in IMAGE_EXTS]
    if not candidates:
        return None, False
    original_local = any((PHOTOS_LIBRARY / "originals" / dir_).glob(f"{uuid}.*"))
    # Byte size is a reliable proxy for resolution among JPEG renders of one photo.
    return max(candidates, key=lambda p: p.stat().st_size), original_local


# ------------------------------------------------------------------------- Images

def sips_resize(src, dst, max_edge, quality):
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["sips", "-Z", str(max_edge), "-s", "format", "jpeg",
         "-s", "formatOptions", str(quality), str(src), "--out", str(dst)])


# ---------------------------------------------------------------------------- Main

def human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.0f} TB"


def main():
    ap = argparse.ArgumentParser(description="Populate the family photo library from Photos.app")
    ap.add_argument("--albums", nargs="+", default=DEFAULT_ALBUMS, help="Album titles to include.")
    ap.add_argument("--max-full", type=int, default=2048, help="Long edge (px) for full images.")
    ap.add_argument("--max-thumb", type=int, default=500, help="Long edge (px) for thumbnails.")
    ap.add_argument("--full-quality", type=int, default=82, help="sips JPEG quality for full images.")
    ap.add_argument("--thumb-quality", type=int, default=70, help="sips JPEG quality for thumbnails.")
    ap.add_argument("--order", choices=["newest", "oldest"], default="newest", help="Manifest/display order.")
    ap.add_argument("--staging", default=None, help="Staging dir (default: a temp dir).")
    ap.add_argument("--limit", type=int, default=0, help="Only process the first N photos (smoke test).")
    ap.add_argument("--require-original", action="store_true",
                    help="Skip photos whose original isn't local (don't fall back to renders).")
    ap.add_argument("--dry-run", action="store_true", help="Build staging + manifest but don't upload.")
    args = ap.parse_args()

    bucket, role_arn = terraform_config()
    print(f"Target bucket : s3://{bucket}")
    print(f"Assume role   : {role_arn}")
    print(f"Albums        : {', '.join(args.albums)}")

    conn, tmpdb = open_catalog()
    try:
        assets = query_assets(conn, args.albums)
    finally:
        conn.close()
        shutil.rmtree(tmpdb, ignore_errors=True)

    reverse = args.order == "newest"
    assets.sort(key=lambda r: (r["created"] or 0), reverse=reverse)
    if args.limit:
        assets = assets[: args.limit]
    print(f"Photos        : {len(assets)}")

    staging = Path(args.staging) if args.staging else Path(tempfile.mkdtemp(prefix="library-staging-"))
    (staging / "library" / "thumb").mkdir(parents=True, exist_ok=True)

    manifest = {"photos": []}
    skipped, remote_used, total_bytes = [], 0, 0

    for i, r in enumerate(assets, 1):
        uuid, dir_ = r["uuid"], r["dir"]
        src, original_local = best_source(uuid, dir_)
        if src is None or (args.require_original and not original_local):
            skipped.append((uuid, r["album"]))
            continue
        if not original_local:
            remote_used += 1

        full = staging / "library" / f"{uuid}.jpg"
        thumb = staging / "library" / "thumb" / f"{uuid}.jpg"
        sips_resize(src, full, args.max_full, args.full_quality)
        # Thumbnail from the already-downscaled full image: faster, and identical crop.
        sips_resize(full, thumb, args.max_thumb, args.thumb_quality)
        total_bytes += full.stat().st_size + thumb.stat().st_size

        date = ""
        if r["created"] is not None:
            date = datetime.fromtimestamp(r["created"] + CORE_DATA_EPOCH, tz=timezone.utc).strftime("%Y-%m-%d")
        manifest["photos"].append({
            "id": uuid,
            "caption": (r["caption"] or "").strip(),
            "date": date,
            "thumb": f"library/thumb/{uuid}.jpg",
            "full": f"library/{uuid}.jpg",
        })
        if i % 100 == 0 or i == len(assets):
            print(f"  processed {i}/{len(assets)}", flush=True)

    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print("\n--- summary ---")
    print(f"Staging dir     : {staging}")
    print(f"Photos in manifest: {len(manifest['photos'])}")
    print(f"Served from iCloud render (no local original): {remote_used}")
    print(f"Skipped         : {len(skipped)}")
    for uuid, album in skipped[:20]:
        print(f"    skip {uuid}  ({album})")
    print(f"Generated JPEG bytes (full+thumb): {human(total_bytes)}")
    captioned = sum(1 for p in manifest["photos"] if p["caption"])
    print(f"Photos with a caption: {captioned}")

    if args.dry_run:
        print("\nDry run — nothing uploaded. Inspect the staging dir, then rerun without --dry-run.")
        return

    print("\nAssuming prod role and uploading …")
    env = assume(role_arn)
    run(["aws", "s3", "sync", f"{staging}/", f"s3://{bucket}/", "--delete", "--no-progress"], env=env)
    print(f"Uploaded to s3://{bucket}/  ({len(manifest['photos'])} photos)")


if __name__ == "__main__":
    main()
