output "site_url" {
  description = "The web app (HTTPS, once the first deploy has run)."
  value       = "https://${local.site_address}"
}

output "google_redirect_uri" {
  description = "Add this to the Google OAuth client's authorised redirect URIs for Sign in with Google."
  value       = "https://${local.site_address}/api/v1/auth/google/callback"
}

output "instance_id" {
  value = aws_instance.demo.id
}

output "public_ip" {
  value = aws_eip.demo.public_ip
}

output "bucket" {
  value = aws_s3_bucket.demo.id
}

output "region" {
  value = var.region
}

output "ssm_prefix" {
  value = local.ssm_prefix
}
