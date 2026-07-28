# ---------------------------------------------------------------------------
# Email DNS — Google Workspace.
#
# cohns.net uses Google for email. These records were read off the live GoDaddy
# zone on 2026-07-27 and replicated here EXACTLY, so that mail keeps flowing the
# moment Route53 becomes authoritative (the NS cutover). Get these in before
# changing the nameservers at the registrar.
#
# Not present in the source zone and therefore not here: DKIM (google._domainkey
# was empty — enable it in the Google Admin console for better deliverability,
# then add its TXT record). If a domain-verification TXT is ever needed at the
# apex, add it to aws_route53_record.spf below — Route53 allows only one TXT
# record set per name, holding multiple quoted strings.
# ---------------------------------------------------------------------------

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

# DMARC. Replicated as-is from GoDaddy; the rua address is GoDaddy's default
# aggregate-report mailbox. Consider pointing rua at a mailbox you control now
# that DNS is leaving GoDaddy.
resource "aws_route53_record" "dmarc" {
  zone_id = aws_route53_zone.apex.zone_id
  name    = "_dmarc.${var.domain_name}"
  type    = "TXT"
  ttl     = 3600

  records = ["v=DMARC1; p=quarantine; adkim=r; aspf=r; rua=mailto:dmarc_rua@onsecureserver.net;"]
}
