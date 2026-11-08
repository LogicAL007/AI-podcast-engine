# Continuous deployment from GitHub Actions (.github/workflows/deploy-demo.yml), with no AWS keys
# stored in GitHub: the workflow signs in through GitHub's OpenID Connect provider and assumes
# this role, which only the main branch's `demo` environment of this repository may assume.
# The role can upload a release, run the server's deploy script through SSM, and start or stop
# this one server; nothing else.

variable "github_repository" {
  description = "owner/name of the GitHub repository whose workflow deploys the demo."
  type        = string
  default     = "LogicAL007/AI-podcast-engine"
}

variable "github_oidc_provider_arn" {
  description = "An account has one GitHub OIDC provider. Leave empty to create it; give its ARN if the account already has one."
  type        = string
  default     = ""
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  github_oidc_arn = var.github_oidc_provider_arn != "" ? var.github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  instance_arn    = "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/${aws_instance.demo.id}"
}

resource "aws_iam_role" "github" {
  name = "${var.project}-github-deploy"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_oidc_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          # Only jobs that run in the repository's `demo` environment (deploy-demo.yml).
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repository}:environment:demo"
        }
      }
    }]
  })
  max_session_duration = 7200 # a first deploy builds every image on the server
}

resource "aws_iam_role_policy" "github" {
  name = "${var.project}-github-deploy"
  role = aws_iam_role.github.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "UploadReleases"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.demo.arn}/releases/*"
      },
      {
        Sid      = "RunTheDeployScriptOnThisServer"
        Effect   = "Allow"
        Action   = ["ssm:SendCommand"]
        Resource = [local.instance_arn, "arn:aws:ssm:${var.region}::document/AWS-RunShellScript"]
      },
      {
        Sid      = "FollowTheDeploy"
        Effect   = "Allow"
        Action   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
        Resource = "*"
      },
      {
        Sid      = "StartAndStopThisServer"
        Effect   = "Allow"
        Action   = ["ec2:StartInstances", "ec2:StopInstances"]
        Resource = local.instance_arn
      },
      {
        Sid      = "SeeTheServerState"
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
        Resource = "*"
      }
    ]
  })
}

output "github_deploy_role_arn" {
  description = "Set as the DEMO_ROLE_ARN variable of the GitHub `demo` environment (make aws-demo-ci-vars)."
  value       = aws_iam_role.github.arn
}
