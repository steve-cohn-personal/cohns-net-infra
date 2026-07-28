variable "region" {
  description = "Region for the state bucket. State should live where you can reach it, not where the workloads are."
  type        = string
  default     = "us-west-2"
}

variable "name_prefix" {
  description = "Prefix for globally-unique resource names."
  type        = string
  default     = "cohns"
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default = {
    Project   = "cohns.net"
    ManagedBy = "terraform"
    Component = "tf-backend"
    Repo      = "steve-cohn-personal/cohns-net-infra"
  }
}
