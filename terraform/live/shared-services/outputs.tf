output "zone_id" {
  description = "Hosted zone id for the apex domain. Feed this into live/site as hosted_zone_id."
  value       = aws_route53_zone.apex.zone_id
}

output "name_servers" {
  description = "The four nameservers to set at the domain registrar. This is the manual next step."
  value       = aws_route53_zone.apex.name_servers
}

output "domain_name" {
  description = "The apex domain this zone serves."
  value       = aws_route53_zone.apex.name
}
