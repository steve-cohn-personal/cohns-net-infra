# ---------------------------------------------------------------------------
# Aurora PostgreSQL Serverless v2.
#
# Serverless v2 is provisioned-mode Aurora with a `db.serverless` instance and a
# scaling range. With min_capacity = 0 the cluster pauses when idle, so a database
# nobody is using costs only storage — which is what keeps this affordable to leave
# running while the rest of Phase 2 comes together.
#
# The master password is never in Terraform state or a tfvars file: AWS generates
# it, stores it in Secrets Manager, and rotates it (manage_master_user_password).
# The app reads the secret at runtime.
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "this" {
  name        = "${var.name}-db"
  description = "Aurora ${var.name} — Postgres access"
  vpc_id      = var.vpc_id
  tags        = merge(var.tags, { Name = "${var.name}-db" })
}

resource "aws_vpc_security_group_ingress_rule" "postgres" {
  for_each = toset(var.allowed_ingress_cidrs)

  security_group_id = aws_security_group.this.id
  description       = "Postgres from ${each.value}"
  cidr_ipv4         = each.value
  from_port         = 5432
  to_port           = 5432
  ip_protocol       = "tcp"
}

# The engine's default version in this region — a valid, Serverless-v2-capable
# Aurora PostgreSQL version, chosen without hardcoding a patch level.
data "aws_rds_engine_version" "postgres" {
  engine       = "aurora-postgresql"
  default_only = true
}

resource "aws_rds_cluster" "this" {
  cluster_identifier = var.name
  engine             = "aurora-postgresql"
  engine_version     = data.aws_rds_engine_version.postgres.version

  database_name               = var.database_name
  master_username             = var.master_username
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [aws_security_group.this.id]

  storage_encrypted         = true
  backup_retention_period   = var.backup_retention_days
  skip_final_snapshot       = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : "${var.name}-final"
  deletion_protection       = var.deletion_protection
  apply_immediately         = true

  serverlessv2_scaling_configuration {
    min_capacity             = var.min_acu
    max_capacity             = var.max_acu
    seconds_until_auto_pause = var.min_acu == 0 ? var.seconds_until_auto_pause : null
  }

  tags = var.tags
}

resource "aws_rds_cluster_instance" "this" {
  identifier         = "${var.name}-1"
  cluster_identifier = aws_rds_cluster.this.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.this.engine
  engine_version     = aws_rds_cluster.this.engine_version

  db_subnet_group_name = aws_db_subnet_group.this.name
  publicly_accessible  = false

  tags = var.tags
}
