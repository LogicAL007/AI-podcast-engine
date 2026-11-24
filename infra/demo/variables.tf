variable "region" {
  description = "AWS region. ca-central-1 (Montreal), like the study server."
  type        = string
  default     = "ca-central-1"
}

variable "project" {
  description = "Name of every resource and the SSM parameter prefix (/<project>/...). deployer-policy.json allows podcast-demo* only."
  type        = string
  default     = "podcast-demo"
}

variable "instance_type" {
  description = "m7i-flex.large (2 vCPUs, 8 GB) runs the stack (about 3 GB in use) and is allowed on AWS's free account plan; on a paid plan t3.xlarge builds faster."
  type        = string
  default     = "m7i-flex.large"
}

variable "root_volume_gb" {
  description = "Encrypted root disk, in GB."
  type        = number
  default     = 40
}

variable "domain_name" {
  description = "Optional domain pointing at the server's IP. Empty: <ip-with-dashes>.sslip.io, which needs no DNS setup."
  type        = string
  default     = ""
}

variable "http_cidrs" {
  description = "Who may reach the site (ports 80 and 443). Narrow it to the room's network for the demo if you like."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
