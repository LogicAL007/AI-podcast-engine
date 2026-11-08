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

variable "voice_backend" {
  description = <<-EOT
    How the server voices episodes, on its own (no Mac needed):
      gemini          Gemini TTS, prebuilt voices, on a regular server (default; one request per
                      2-minute episode, 12 a day on the free tier)
      chatterbox-gpu  Chatterbox with the cloned voices on an NVIDIA GPU (needs the "Running
                      On-Demand G and VT instances" quota; set instance_type = "g4dn.xlarge")
  EOT
  type        = string
  default     = "gemini"
  validation {
    condition     = contains(["gemini", "chatterbox-gpu"], var.voice_backend)
    error_message = "voice_backend is gemini or chatterbox-gpu."
  }
}

variable "instance_type" {
  description = "m7i-flex.large (2 vCPUs, 8 GB) runs the stack (about 3 GB in use) and is allowed on AWS's free account plan; on a paid plan t3.xlarge builds faster, and g4dn.xlarge (NVIDIA T4) is for chatterbox-gpu."
  type        = string
  default     = "m7i-flex.large"
}

variable "root_volume_gb" {
  description = "Encrypted root disk; 0 picks 40 GB on a regular server and 120 GB with the GPU image (which needs 75 GB itself, and CUDA PyTorch is large)."
  type        = number
  default     = 0
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
