# ---------------------------------------------------------------------------
# A minimal private VPC.
#
# Just enough for a database: private subnets across two AZs, no internet
# gateway and no NAT — Aurora is reached only from inside the VPC, so it needs
# neither, and NAT is the expensive part of a VPC ($/hour). Public subnets and
# egress get added when the compute platform (EKS/Fargate) lands here.
# ---------------------------------------------------------------------------

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, { Name = var.name })
}

resource "aws_subnet" "private" {
  count = var.az_count

  vpc_id            = aws_vpc.this.id
  cidr_block        = cidrsubnet(var.cidr, 4, count.index)
  availability_zone = local.azs[count.index]

  tags = merge(var.tags, {
    Name = "${var.name}-private-${local.azs[count.index]}"
    Tier = "private"
  })
}
