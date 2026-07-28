variable "name" {
  description = "Service name / identifier prefix."
  type        = string
}

variable "region" {
  description = "Region (for the awslogs driver)."
  type        = string
  default     = "us-west-2"
}

variable "vpc_id" {
  description = "VPC the service and ALB live in."
  type        = string
}

variable "public_subnet_ids" {
  description = "Public subnets for the internet-facing ALB and the (public-IP, no-NAT) tasks."
  type        = list(string)
}

variable "image" {
  description = "Full container image reference, e.g. <ecr>/cohns/comments-api:<tag>."
  type        = string
}

variable "container_port" {
  description = "Port the container listens on."
  type        = number
  default     = 8000
}

variable "cpu" {
  description = "Task CPU units (256 = 0.25 vCPU, the Fargate minimum)."
  type        = number
  default     = 256
}

variable "memory" {
  description = "Task memory (MiB). 512 is the minimum for 256 CPU."
  type        = number
  default     = 512
}

variable "cpu_architecture" {
  description = "X86_64 or ARM64 (Graviton, ~20% cheaper)."
  type        = string
  default     = "X86_64"
}

variable "desired_count" {
  description = "Number of tasks."
  type        = number
  default     = 1
}

variable "environment" {
  description = "Plain (non-secret) environment variables for the container."
  type        = map(string)
  default     = {}
}

variable "secrets" {
  description = "Secret env vars: env-var name => Secrets Manager ARN (whole-string secret). Injected via ECS valueFrom; the execution role is granted GetSecretValue on them."
  type        = map(string)
  default     = {}
}

variable "task_policy_arns" {
  description = "IAM policy ARNs to attach to the task role (e.g. the DB-secret read policy)."
  type        = list(string)
  default     = []
}

variable "enable_https" {
  description = "Add the HTTPS listener. A static flag (not derived from certificate_arn, which is often an apply-time value) so resource count is known at plan."
  type        = bool
  default     = false
}

variable "certificate_arn" {
  description = "ACM certificate ARN (regional) for the HTTPS listener. Required when enable_https is true."
  type        = string
  default     = null
}

variable "health_check_path" {
  description = "ALB target-group health check path."
  type        = string
  default     = "/healthz"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
