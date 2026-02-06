# =============================================================================
# S3 Module - Object Storage for Models and Data
# =============================================================================

terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  bucket_prefix = "${var.project}-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

# Raw data bucket (MIMIC data)
resource "aws_s3_bucket" "raw" {
  bucket = "${local.bucket_prefix}-raw"
  tags = merge(var.tags, { Name = "${var.project}-raw", Purpose = "Raw MIMIC data" })
}

# Processed data bucket (dbt outputs)
resource "aws_s3_bucket" "processed" {
  bucket = "${local.bucket_prefix}-processed"
  tags = merge(var.tags, { Name = "${var.project}-processed", Purpose = "Processed features" })
}

# Models bucket
resource "aws_s3_bucket" "models" {
  bucket = "${local.bucket_prefix}-models"
  tags = merge(var.tags, { Name = "${var.project}-models", Purpose = "ML model artifacts" })
}

# Versioning for models bucket (important for model rollback)
resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Encryption for all buckets
resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}

# Block public access
resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket                  = aws_s3_bucket.processed.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
