# ---------------------------------------------------------------------------
# shared-services — the apex DNS zone.
#
# The public hosted zone for cohns.net. This is the critical-path long pole: its
# nameservers must be registered at the domain registrar before ACM can validate
# any certificate, and NS propagation can take up to 48 hours. Create it early,
# update the registrar, and let propagation run while the rest is built.
#
# Subzone delegation (dev/stage) and the prod DNS-writer role come later, once
# those accounts have zones to delegate to.
# ---------------------------------------------------------------------------

resource "aws_route53_zone" "apex" {
  name    = var.domain_name
  comment = "Apex public zone for ${var.domain_name}. Managed by terraform (live/shared-services)."

  tags = local.tags
}
