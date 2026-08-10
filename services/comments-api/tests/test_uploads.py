import re

import pytest

from app import media_uploads
from app.media_uploads import UploadError, build_key
from tests.conftest import auth, make_token

MOD = lambda: make_token(sub="mod", name="Mod", groups=["moderators"])  # noqa: E731


# --- build_key (pure) -------------------------------------------------------


def test_build_key_image():
    key = build_key("image", "image/jpeg", "Pan con Tomate!")
    assert re.fullmatch(r"images/pan-con-tomate-[0-9a-f]{8}\.jpg", key)


def test_build_key_defaults_stem_when_no_slug():
    assert build_key("image", "image/png", None).startswith("images/img-")


def test_build_key_rejects_bad_content_type():
    with pytest.raises(UploadError):
        build_key("image", "application/pdf", "x")


def test_build_key_video_is_deterministic_on_slug():
    # No random suffix: the key must match recipe.video_key so a re-upload replaces.
    assert build_key("video", "video/mp4", "Pan con Tomate") == "lessons/pan-con-tomate.mp4"


def test_build_key_video_requires_slug():
    with pytest.raises(UploadError):
        build_key("video", "video/mp4", None)


def test_build_key_rejects_bad_video_content_type():
    with pytest.raises(UploadError):
        build_key("video", "video/x-msvideo", "x")


def test_build_key_rejects_unknown_kind():
    with pytest.raises(UploadError):
        build_key("audio", "audio/mpeg", "x")


# --- presign_put (stubbed boto3) --------------------------------------------


class _StubSettings:
    aws_region = "us-west-2"
    media_output_bucket = "cohns-media-output-x"
    media_ingest_bucket = "cohns-media-ingest-x"
    media_cdn_base = "https://media.cohns.net/"


def test_presign_unconfigured_returns_none():
    class Bare:
        aws_region = "us-west-2"
        media_output_bucket = None
        media_ingest_bucket = None
        media_cdn_base = None

    assert media_uploads.presign_put("image", "image/png", "x", Bare()) is None


def test_presign_configured(monkeypatch):
    captured = {}
    client_kwargs = {}

    class _Client:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            captured.update(op=op, **Params, ttl=ExpiresIn)
            return "https://s3.example/put?sig=1"

    def _fake_client(*a, **k):
        client_kwargs.update(k)
        return _Client()

    monkeypatch.setattr("boto3.client", _fake_client)
    out = media_uploads.presign_put("image", "image/webp", "sourdough", _StubSettings())

    # The client MUST be pinned to SigV4 + virtual-hosted addressing so the presigned
    # host is the regional bucket endpoint the site CSP allows (else the browser PUT
    # is CSP-blocked as "Failed to fetch").
    cfg = client_kwargs["config"]
    assert cfg.signature_version == "s3v4"
    assert cfg.s3["addressing_style"] == "virtual"

    assert out["url"] == "https://s3.example/put?sig=1"
    assert out["key"].startswith("images/sourdough-") and out["key"].endswith(".webp")
    assert out["headers"] == {"Content-Type": "image/webp"}
    # public_url uses the CDN origin (no double slash from the trailing-slash base).
    assert out["public_url"] == "https://media.cohns.net/" + out["key"]
    assert out["video_key"] is None
    # the object key and content-type are signed into the URL.
    assert captured["op"] == "put_object" and captured["ContentType"] == "image/webp"
    assert captured["Bucket"] == "cohns-media-output-x" and captured["Key"] == out["key"]


def test_presign_video_targets_ingest_and_returns_video_key(monkeypatch):
    captured = {}

    class _Client:
        def generate_presigned_url(self, op, Params, ExpiresIn):
            captured.update(**Params)
            return "https://s3.example/put?sig=2"

    monkeypatch.setattr("boto3.client", lambda *a, **k: _Client())
    out = media_uploads.presign_put("video", "video/mp4", "pan-con-tomate", _StubSettings())

    assert captured["Bucket"] == "cohns-media-ingest-x"  # source goes to ingest
    assert out["key"] == "lessons/pan-con-tomate.mp4"
    # recipe.video_key is the key without extension (the transcode output prefix).
    assert out["video_key"] == "lessons/pan-con-tomate"
    assert out["public_url"] is None


# --- endpoint ---------------------------------------------------------------


async def test_presign_requires_moderator(client):
    body = {"kind": "image", "content_type": "image/png"}
    assert (await client.post("/admin/uploads/presign", json=body)).status_code == 401  # no token
    r = await client.post("/admin/uploads/presign", json=body, headers=auth(make_token()))
    assert r.status_code == 403  # signed in, not a moderator


async def test_presign_bad_content_type_is_400(client):
    # Request validation (400) precedes the unconfigured check (503).
    body = {"kind": "image", "content_type": "application/pdf"}
    r = await client.post("/admin/uploads/presign", json=body, headers=auth(MOD()))
    assert r.status_code == 400


async def test_presign_503_when_unconfigured(client):
    # Tests have no media buckets configured → the endpoint 503s cleanly.
    body = {"kind": "image", "content_type": "image/png", "slug": "x"}
    r = await client.post("/admin/uploads/presign", json=body, headers=auth(MOD()))
    assert r.status_code == 503
