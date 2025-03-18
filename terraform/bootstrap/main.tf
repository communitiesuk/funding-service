provider "aws" {
  region = "eu-west-2"
}

variable fs_tags {
  default = {
    team="funding-service"
  }
}
data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "fs_terraform_state_bucket" {
  bucket = "mhclg-fs-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
  tags = var.fs_tags
}

resource "aws_s3_bucket_versioning" "fs_terraform_state_bucket_versioning" {
    bucket = aws_s3_bucket.fs_terraform_state_bucket.id

    versioning_configuration {
      status = "Enabled"
    }
}

data "aws_iam_policy_document" "fs_terraform_state_policy_doc" {
  statement {
    principals {
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/terraform-developer"]
      type = "AWS"
    }
    actions = ["s3:*"]
    resources = ["arn:aws:s3:::${aws_s3_bucket.fs_terraform_state_bucket.bucket}/global/s3"]
    condition {
      test     = "Bool"
      values = ["true"]
      variable = "aws:SecureTransport"
    }
  }

}

resource "aws_s3_bucket_policy" "allow_bucket_access" {
  bucket = aws_s3_bucket.fs_terraform_state_bucket.id
  policy = data.aws_iam_policy_document.fs_terraform_state_policy_doc.json
}
