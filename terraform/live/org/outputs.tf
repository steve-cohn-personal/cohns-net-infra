output "organization_id" {
  description = "The AWS Organization id."
  value       = aws_organizations_organization.this.id
}

output "root_id" {
  description = "The Organization root id, for attaching root-level SCPs later."
  value       = aws_organizations_organization.this.roots[0].id
}

output "ou_ids" {
  description = "Organizational unit ids by name."
  value = {
    infrastructure = aws_organizations_organizational_unit.infrastructure.id
    workloads      = aws_organizations_organizational_unit.workloads.id
  }
}

output "account_ids" {
  description = "Member account ids by short name. Feed these into live/site backends and DNS delegation."
  value       = { for k, a in aws_organizations_account.member : k => a.id }
}

# The role to assume when running Terraform against a member account, e.g.:
#   provider "aws" { assume_role { role_arn = <this> } }
output "account_admin_role_arns" {
  description = "OrganizationAccountAccessRole ARN in each member account."
  value = {
    for k, a in aws_organizations_account.member :
    k => "arn:aws:iam::${a.id}:role/OrganizationAccountAccessRole"
  }
}

output "permission_set_arns" {
  description = "Identity Center permission set ARNs by name."
  value       = { for k, ps in aws_ssoadmin_permission_set.this : k => ps.arn }
}
