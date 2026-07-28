variable "name" {
  description = "Cluster identifier / name prefix."
  type        = string
}

variable "vpc_id" {
  description = "VPC the cluster lives in."
  type        = string
}

variable "subnet_ids" {
  description = "Private subnet ids for the DB subnet group (>= 2 AZs)."
  type        = list(string)
}

variable "allowed_ingress_cidrs" {
  description = "CIDRs allowed to reach Postgres (5432). Defaults to the VPC; tighten to the app security group once compute exists."
  type        = list(string)
}

variable "database_name" {
  description = "Initial database created in the cluster. Avoid engine reserved words (e.g. 'comments' is reserved for aurora-postgresql)."
  type        = string
  default     = "commentsdb"
}

variable "master_username" {
  description = "Master user. The password is generated and stored in Secrets Manager (manage_master_user_password)."
  type        = string
  default     = "dbadmin"
}

# Serverless v2 scaling. min_capacity = 0 enables scale-to-zero (auto-pause), so an
# idle cluster costs only storage. Raise the floor to keep it warm.
variable "min_acu" {
  description = "Minimum Aurora Capacity Units. 0 = scale to zero when idle."
  type        = number
  default     = 0
}

variable "max_acu" {
  description = "Maximum Aurora Capacity Units."
  type        = number
  default     = 2
}

variable "seconds_until_auto_pause" {
  description = "Idle seconds before pausing to 0 ACU (300-86400). Only meaningful when min_acu = 0."
  type        = number
  default     = 3600
}

variable "backup_retention_days" {
  description = "Automated backup retention."
  type        = number
  default     = 1
}

variable "skip_final_snapshot" {
  description = "Skip the final snapshot on destroy. True for dev, false for prod."
  type        = bool
  default     = true
}

variable "deletion_protection" {
  description = "Block accidental deletion. False for dev, true for prod."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
