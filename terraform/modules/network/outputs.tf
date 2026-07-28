output "vpc_id" {
  description = "The VPC id."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "The VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "private_subnet_ids" {
  description = "Private subnet ids, one per AZ."
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "Public subnet ids, one per AZ (ALB + Fargate tasks)."
  value       = aws_subnet.public[*].id
}
