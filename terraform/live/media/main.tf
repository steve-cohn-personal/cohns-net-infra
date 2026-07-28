# ---------------------------------------------------------------------------
# live/media — the cooking-lesson video pipeline (Phase 3).
#
# One pipeline for the whole site's media. Upload a lesson video to the ingest
# bucket; it's transcoded to HLS + a thumbnail and served from CloudFront. A
# recipe's `video_key` (in the comments/content API) points at the output prefix.
#
# Cheap to leave running — see the module header; MediaConvert only bills while a
# job runs.
# ---------------------------------------------------------------------------

module "media" {
  source = "../../modules/media-pipeline"

  name         = var.name
  cors_origins = var.cors_origins

  tags = local.tags
}
