variable "domain_name" {
  description = "Canonical domain for the site, e.g. www.cohns.net."
  type        = string
}

variable "alternate_domain_names" {
  description = "Additional names served by the same distribution, e.g. [\"steve.cohns.net\"]."
  type        = list(string)
  default     = []
}

variable "hosted_zone_id" {
  description = "Route53 zone that owns these names. Passed in rather than looked up, so dev/stage can use delegated subzones."
  type        = string
}

variable "bucket_name" {
  description = "Override for the origin bucket name. Defaults to a name derived from domain_name."
  type        = string
  default     = null
}

variable "price_class" {
  description = "CloudFront price class. PriceClass_100 (US/EU) is plenty for a personal site."
  type        = string
  default     = "PriceClass_100"

  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "price_class must be PriceClass_100, PriceClass_200, or PriceClass_All."
  }
}

variable "versioning_enabled" {
  description = "Version objects in the origin bucket. Cheap insurance against a bad deploy."
  type        = bool
  default     = true
}

variable "content_security_policy" {
  description = "CSP header value. Deliberately strict by default; loosen it consciously."
  type        = string
  default     = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
}

variable "tags" {
  description = "Tags applied to every resource in this module."
  type        = map(string)
  default     = {}
}
