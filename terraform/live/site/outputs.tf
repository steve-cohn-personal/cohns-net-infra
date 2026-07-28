output "site_url" {
  description = "Canonical URL for this environment."
  value       = module.site.site_url
}

output "bucket_name" {
  description = "Origin bucket the deploy pipeline syncs into."
  value       = module.site.bucket_name
}

output "distribution_id" {
  description = "CloudFront distribution the deploy pipeline invalidates."
  value       = module.site.distribution_id
}

output "distribution_domain_name" {
  description = "The *.cloudfront.net name, for testing ahead of DNS."
  value       = module.site.distribution_domain_name
}

output "deploy_role_arn" {
  description = "Role ARN for the GitHub Actions workflow. Not a secret — put it straight in the workflow file."
  value       = module.deploy_role.role_arn
}

output "subzone_name_servers" {
  description = "Nameservers of the delegated subzone (dev/stage). Empty for prod."
  value       = local.is_prod ? [] : aws_route53_zone.subzone[0].name_servers
}
