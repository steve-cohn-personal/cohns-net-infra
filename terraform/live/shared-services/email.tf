# ---------------------------------------------------------------------------
# Email DNS — Google Workspace.
#
# cohns.net uses Google for email. These records were read off the live GoDaddy
# zone on 2026-07-27 and replicated here EXACTLY, so that mail keeps flowing the
# moment Route53 becomes authoritative (the NS cutover). Get these in before
# changing the nameservers at the registrar.
#
# If a domain-verification TXT is ever needed at the apex, add it to
# aws_route53_record.spf below — Route53 allows only one TXT record set per name,
# holding multiple quoted strings.
# ---------------------------------------------------------------------------

locals {
  # DKIM public key from Google Admin (Gmail > Authenticate email), 2048-bit,
  # selector "google". Public by design — it lives in DNS for the world to read.
  # A 2048-bit key exceeds the 255-char TXT string limit, so it is emitted as
  # adjacent quoted strings within one record; resolvers concatenate them.
  dkim_value = "v=DKIM1; k=rsa; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArUZjiJo2B3e/tgQPWlAOpI0INmMXuneVrc6V8sGJXu10VvGqARObXbJio7d8hxZ5UeNGIyjLFUhD9uQroDEhCiboboygOWtZCN/Y9PnqskzNe8k/UmEEoF4lpFzSJ4+cmhwVXZqut8AkC+bea72MzkNzq4bYBMfDV8DK2ockVBwkm8k0vP2qNnb1pUxqYfMwgEXf7yDYf9EpMpSWwSuCVYQYNxE3uP+KFHBi9H6HJNvTYPwlnnzsYcwghT+WD0T3Z73cHpibSquyH9aKXxFW9KzevAIjgldm35FqyJbXc54rLcUIXImf44waUX0zWGLVzjog6s7ArcSl7Dv6mpSMUQIDAQAB"

  dkim_chunked = join("\"\"", [
    for i in range(0, length(local.dkim_value), 255) : substr(local.dkim_value, i, 255)
  ])
}

# DKIM. Selector google._domainkey. After this resolves, click "Start
# authentication" in the Google Admin console to activate signing.
resource "aws_route53_record" "dkim" {
  zone_id = aws_route53_zone.apex.zone_id
  name    = "google._domainkey.${var.domain_name}"
  type    = "TXT"
  ttl     = 3600

  records = [local.dkim_chunked]
}

resource "aws_route53_record" "mx" {
  zone_id = aws_route53_zone.apex.zone_id
  name    = var.domain_name
  type    = "MX"
  ttl     = 3600

  records = [
    "1 aspmx.l.google.com",
    "5 alt1.aspmx.l.google.com",
    "5 alt2.aspmx.l.google.com",
  ]
}

# SPF. Lives at the apex as a TXT record. If you later add a verification token,
# it joins this same record set as an additional string, not a second TXT record.
resource "aws_route53_record" "spf" {
  zone_id = aws_route53_zone.apex.zone_id
  name    = var.domain_name
  type    = "TXT"
  ttl     = 3600

  records = ["v=spf1 include:_spf.google.com ~all"]
}

# DMARC. Aggregate reports go to a mailbox we own (same domain, so no external
# _report._dmarc authorization record is needed). Still p=quarantine; move to
# p=reject once DKIM is live and the rua reports show clean SPF/DKIM alignment.
resource "aws_route53_record" "dmarc" {
  zone_id = aws_route53_zone.apex.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 3600

  records = ["v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:steve@${var.domain_name};"]
}
