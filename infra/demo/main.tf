# The whole podcast engine on one server, for a live demo, independent of the Mac. Docker Compose
# runs the same stack as on the Mac, with Caddy in front for HTTPS. The voice worker uses Gemini
# TTS on a regular server (voice_backend = "gemini"), or Chatterbox with the cloned voices on an
# NVIDIA GPU ("chatterbox-gpu"). No SSH: the server is managed and deployed through Systems Manager
# (SSM). Releases, and the optional copy of the Mac's data, go through a private S3 bucket.
# Secrets are SSM SecureString parameters written by deploy.sh, so they never enter this state.
#
# Stop the server between rehearsal and demo (make aws-demo-stop): a stopped server costs only its
# disk and IP. Destroy it afterwards (make aws-demo-destroy).

# Ubuntu 22.04 either way: AWS's GPU base image (NVIDIA driver, Docker, NVIDIA Container Toolkit)
# for Chatterbox on the GPU, else Canonical's standard image (the bootstrap installs Docker).
data "aws_ssm_parameter" "ami" {
  name = var.voice_backend == "chatterbox-gpu" ? (
    "/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id"
  ) : "/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id"
}

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Not every zone has every instance type: use a default subnet in a zone that offers this one.
data "aws_ec2_instance_type_offerings" "here" {
  location_type = "availability-zone"
  filter {
    name   = "instance-type"
    values = [var.instance_type]
  }
}

data "aws_subnet" "default" {
  for_each = toset(data.aws_subnets.default.ids)
  id       = each.value
}

data "aws_caller_identity" "current" {}

resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  gpu          = var.voice_backend == "chatterbox-gpu"
  volume_gb    = var.root_volume_gb > 0 ? var.root_volume_gb : (local.gpu ? 120 : 40)
  ssm_prefix   = "/${var.project}"
  site_address = var.domain_name != "" ? var.domain_name : "${replace(aws_eip.demo.public_ip, ".", "-")}.sslip.io"
  offering_subnets = sort([
    for id, subnet in data.aws_subnet.default : id
    if contains(data.aws_ec2_instance_type_offerings.here.locations, subnet.availability_zone)
  ])
}

# ---------------------------------------------------------------- releases and the data copy

resource "aws_s3_bucket" "demo" {
  bucket        = "${var.project}-${random_id.suffix.hex}"
  force_destroy = true # a demo bucket: destroying the demo removes its releases and data copy
}

resource "aws_s3_bucket_public_access_block" "demo" {
  bucket                  = aws_s3_bucket.demo.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "demo" {
  bucket = aws_s3_bucket.demo.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "demo" {
  bucket = aws_s3_bucket.demo.id
  rule {
    id     = "old-releases"
    status = "Enabled"
    filter {
      prefix = "releases/"
    }
    expiration {
      days = 14
    }
  }
}

resource "aws_s3_bucket_policy" "tls_only" {
  bucket = aws_s3_bucket.demo.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "DenyInsecureTransport"
      Effect    = "Deny"
      Principal = "*"
      Action    = "s3:*"
      Resource  = [aws_s3_bucket.demo.arn, "${aws_s3_bucket.demo.arn}/*"]
      Condition = { Bool = { "aws:SecureTransport" = "false" } }
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.demo]
}

# ---------------------------------------------------------------- the server's permissions

resource "aws_iam_role" "instance" {
  name = "${var.project}-instance"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "instance" {
  name = "${var.project}-releases-and-secrets"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ReadReleasesAndData"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.demo.arn}/releases/*", "${aws_s3_bucket.demo.arn}/data/*"]
      },
      {
        Sid      = "ListForTheDataCheck"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.demo.arn
      },
      {
        Sid      = "ReadDemoSettings"
        Effect   = "Allow"
        Action   = ["ssm:GetParameter", "ssm:GetParameters"]
        Resource = "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${local.ssm_prefix}/*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.project}-instance"
  role = aws_iam_role.instance.name
}

# ---------------------------------------------------------------- network and server

resource "aws_security_group" "demo" {
  name        = "${var.project}-web"
  description = "HTTP (certificate challenge and redirect) and HTTPS only; no SSH"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.http_cidrs
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.http_cidrs
  }
  egress {
    description = "Packages, model weights, Gemini, Lets Encrypt, S3 and SSM"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "demo" {
  ami                    = data.aws_ssm_parameter.ami.value
  instance_type          = var.instance_type
  subnet_id              = local.offering_subnets[0]
  vpc_security_group_ids = [aws_security_group.demo.id]
  iam_instance_profile   = aws_iam_instance_profile.instance.name

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    bucket     = aws_s3_bucket.demo.id
    region     = var.region
    ssm_prefix = local.ssm_prefix
    gpu        = local.gpu
  })

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 1          # containers cannot reach the server's credentials
  }

  # Burstable (t3) servers only: building the images needs more CPU than the baseline for a while.
  dynamic "credit_specification" {
    for_each = startswith(var.instance_type, "t") ? [1] : []
    content {
      cpu_credits = "unlimited"
    }
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = local.volume_gb
    encrypted             = true
    delete_on_termination = true
    tags = {
      Name = "${var.project}-root"
    }
  }

  tags = {
    Name = var.project
  }

  lifecycle {
    # A newer image or an edited bootstrap script must not replace the server (and its data).
    ignore_changes = [ami, user_data]
    precondition {
      condition     = length(local.offering_subnets) > 0
      error_message = "No default subnet is in a zone that offers ${var.instance_type}."
    }
    precondition {
      condition     = !local.gpu || startswith(var.instance_type, "g")
      error_message = "chatterbox-gpu needs a GPU instance type, such as g4dn.xlarge."
    }
  }
}

resource "aws_eip" "demo" {
  domain   = "vpc"
  instance = aws_instance.demo.id
  tags = {
    Name = var.project
  }
}

# Read by the server's deploy script for Caddy's address and the app's public URLs, and for how it
# voices episodes (not secrets).
resource "aws_ssm_parameter" "site_address" {
  name  = "${local.ssm_prefix}/site_address"
  type  = "String"
  value = local.site_address
}

resource "aws_ssm_parameter" "voice_backend" {
  name  = "${local.ssm_prefix}/voice_backend"
  type  = "String"
  value = var.voice_backend
}
