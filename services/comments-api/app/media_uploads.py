"""Presigned S3 uploads for recipe media.

Moderators upload images (and, later, lesson videos) directly to S3 from the
browser: the API mints a short-lived presigned PUT and the browser PUTs the bytes,
so large files never transit this service. The media buckets live in the same
(prod) account as this service, so the task role's own credentials sign the URL —
no assume-role. Everything is lazy and returns None/raises a clean error when
unconfigured (local, tests, dev), which the router turns into a 503.

Two upload kinds:
  - "image": PUT to the output bucket under images/ ; served immediately via the
    media CDN. The returned public_url goes into recipe.hero_image_url.
  - "video": (wired later) PUT the source to the ingest bucket under lessons/ ;
    the media pipeline transcodes it and recipe.video_key points at the output.
"""

import secrets

# content-type -> file extension, per upload kind. This is also the allowlist:
# a content-type not present here is rejected.
IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

# Prefix within the target bucket, per kind.
_PREFIX = {"image": "images", "video": "lessons"}

_PRESIGN_TTL = 300  # seconds the PUT URL stays valid


class UploadError(Exception):
    """A bad request (unknown kind, disallowed content-type). Router → 400."""


def _slugify(s: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in (s or "").lower())
    out = "-".join(p for p in out.split("-") if p)  # collapse runs, trim ends
    return out[:60]


def build_key(kind: str, content_type: str, slug: str | None) -> str:
    """Deterministic, collision-resistant object key for an upload. Validates the
    kind and content-type; raises UploadError otherwise."""
    if kind != "image":
        # video is added when the ingest bucket is wired; keep the surface honest.
        raise UploadError(f"unsupported upload kind: {kind!r}")
    ext = IMAGE_TYPES.get(content_type)
    if not ext:
        raise UploadError(f"unsupported content type: {content_type!r}")
    stem = _slugify(slug) or "img"
    return f"{_PREFIX[kind]}/{stem}-{secrets.token_hex(4)}.{ext}"


def _bucket_for(kind: str, settings) -> str | None:
    return settings.media_output_bucket if kind == "image" else settings.media_ingest_bucket


def presign_put(kind: str, content_type: str, slug: str | None, settings) -> dict | None:
    """Mint a presigned PUT for an upload. Returns {url, key, public_url, headers},
    or None when uploads aren't configured (→ router 503). Raises UploadError for a
    bad request. Blocking (boto3) — call via run_in_threadpool."""
    key = build_key(kind, content_type, slug)  # validate the request first (→ 400)

    bucket = _bucket_for(kind, settings)
    if not (bucket and settings.media_cdn_base):
        return None  # uploads not configured here (→ 503)

    import boto3

    client = boto3.client("s3", region_name=settings.aws_region)
    url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=_PRESIGN_TTL,
    )
    return {
        "url": url,
        "key": key,
        # Content-Type is a signed header, so the browser must send exactly this.
        "headers": {"Content-Type": content_type},
        "public_url": f"{settings.media_cdn_base.rstrip('/')}/{key}",
    }
