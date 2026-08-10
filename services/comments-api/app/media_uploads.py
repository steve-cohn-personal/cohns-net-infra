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

# content-type -> file extension, per upload kind. These are also the allowlists:
# a content-type not present here is rejected.
IMAGE_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}
VIDEO_TYPES = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
}

_PRESIGN_TTL = 300  # seconds the PUT URL stays valid


class UploadError(Exception):
    """A bad request (unknown kind, disallowed content-type). Router → 400."""


def _slugify(s: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in (s or "").lower())
    out = "-".join(p for p in out.split("-") if p)  # collapse runs, trim ends
    return out[:60]


def build_key(kind: str, content_type: str, slug: str | None) -> str:
    """The S3 object key for an upload. Validates kind + content-type (→ UploadError).

    Images get a random suffix (images/<slug>-<rand>.<ext>) — many per recipe, never
    colliding. A video's key is deterministic on the slug (lessons/<slug>.<ext>): the
    transcode pipeline strips the extension to form the output prefix, which becomes
    recipe.video_key, so re-uploading a lesson replaces it in place."""
    if kind == "image":
        ext = IMAGE_TYPES.get(content_type)
        if not ext:
            raise UploadError(f"unsupported image content type: {content_type!r}")
        stem = _slugify(slug) or "img"
        return f"images/{stem}-{secrets.token_hex(4)}.{ext}"
    if kind == "video":
        ext = VIDEO_TYPES.get(content_type)
        if not ext:
            raise UploadError(f"unsupported video content type: {content_type!r}")
        stem = _slugify(slug)
        if not stem:
            raise UploadError("a recipe slug is required to name a video upload")
        return f"lessons/{stem}.{ext}"
    raise UploadError(f"unsupported upload kind: {kind!r}")


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
    from botocore.config import Config

    # Pin SigV4 + virtual-hosted addressing so the presigned URL host is the REGIONAL
    # bucket endpoint (<bucket>.s3.<region>.amazonaws.com) that the site CSP allows.
    # Left unpinned, botocore can emit the legacy GLOBAL host (<bucket>.s3.amazonaws.com)
    # with SigV2 — a different host that the browser's CSP connect-src blocks, so the
    # upload PUT dies as "Failed to fetch".
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )
    url = client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=_PRESIGN_TTL,
    )
    result = {
        "url": url,
        "key": key,
        # Content-Type is a signed header, so the browser must send exactly this.
        "headers": {"Content-Type": content_type},
        "public_url": None,
        "video_key": None,
    }
    if kind == "image":
        # Ready immediately; the CDN serves it. Goes into recipe.hero_image_url.
        result["public_url"] = f"{settings.media_cdn_base.rstrip('/')}/{key}"
    else:
        # The pipeline transcodes the source into <base>/, so recipe.video_key is the
        # key without its extension. The HLS manifest appears there minutes later.
        result["video_key"] = key.rsplit(".", 1)[0]
    return result
