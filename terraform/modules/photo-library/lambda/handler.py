"""Family photo library — list endpoint.

The HTTP API's Cognito JWT authorizer has already validated the token (signature,
issuer, audience, expiry) before this runs, so here we only do *authorization*:
require the caller to be in the `family` group, then hand back short-lived S3
presigned URLs for each photo's thumbnail and full image. The bucket itself stays
entirely private — nothing is public, and the URLs expire.

boto3 is the only dependency (present in the Lambda runtime), so there is no native
crypto to bundle: token verification lives in the API Gateway authorizer, not here.
"""

import json
import os

import boto3
from botocore.config import Config

# Force SigV4 + the regional virtual-hosted endpoint. Without this, boto3 can emit a
# legacy SigV2 URL against the global s3.amazonaws.com endpoint, which then 307-
# redirects for a non-us-east-1 bucket — an <img> would be bounced to a different
# host (breaking CSP), and SigV2 is deprecated. Regional SigV4 URLs return 200.
_region = os.environ.get("AWS_REGION", "us-west-2")
s3 = boto3.client(
    "s3",
    region_name=_region,
    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

BUCKET = os.environ["PHOTO_BUCKET"]
MANIFEST_KEY = os.environ.get("MANIFEST_KEY", "manifest.json")
FAMILY_GROUP = os.environ.get("FAMILY_GROUP", "family")
URL_TTL = int(os.environ.get("URL_TTL_SECONDS", "7200"))
CORS_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o]


def _cors(origin):
    allow = origin if origin in CORS_ORIGINS else (CORS_ORIGINS[0] if CORS_ORIGINS else "*")
    return {
        "Access-Control-Allow-Origin": allow,
        "Access-Control-Allow-Headers": "authorization,content-type",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
        "Vary": "Origin",
    }


def _resp(status, body, origin):
    return {
        "statusCode": status,
        "headers": {**_cors(origin), "Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _groups(claims):
    """cognito:groups arrives from the JWT authorizer as a bracketed string
    (e.g. "[family moderators]") or, occasionally, a plain list. Normalize both."""
    raw = claims.get("cognito:groups", "")
    if isinstance(raw, list):
        return raw
    return [g for g in raw.strip("[]").replace(",", " ").split() if g]


def _sign(key):
    return s3.generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=URL_TTL
    )


def _load_manifest():
    """The curated manifest written at upload time: an ordered list of photos with
    caption/date and the thumb + full object keys. Absent = empty library."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=MANIFEST_KEY)
        return json.loads(obj["Body"].read())
    except s3.exceptions.NoSuchKey:
        return {"photos": []}


def handler(event, context):
    origin = (event.get("headers") or {}).get("origin", "")

    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    ) or {}

    if FAMILY_GROUP not in _groups(claims):
        # Authenticated, but not invited into the family library.
        return _resp(403, {"error": "not a member of the family group"}, origin)

    manifest = _load_manifest()
    photos = [
        {
            "id": p.get("id"),
            "caption": p.get("caption", ""),
            "date": p.get("date", ""),
            "thumb": _sign(p["thumb"]),
            "full": _sign(p["full"]),
        }
        for p in manifest.get("photos", [])
    ]
    return _resp(200, {"photos": photos, "expires_in": URL_TTL}, origin)
