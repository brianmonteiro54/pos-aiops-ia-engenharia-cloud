locals {
  name_prefix = "hvt-${var.environment}"

  common_tags = {
    Owner       = var.owner
    CostCenter  = var.cost_center
    Environment = var.environment
  }
}

resource "aws_s3_bucket" "this" {
  # O nome final segue o padrão hvt-<ambiente>-<sufixo>.
  bucket        = "${local.name_prefix}-${var.bucket_name}"
  force_destroy = var.force_destroy

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-${var.bucket_name}"
    }
  )
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = var.sse_algorithm
      kms_master_key_id = var.sse_algorithm == "aws:kms" ? var.kms_key_id : null
    }
  }

  lifecycle {
    precondition {
      # SSE-KMS requer uma chave explícita; SSE-S3 permanece o padrão seguro.
      condition = var.sse_algorithm != "aws:kms" ? true : (
        var.kms_key_id != null ? trimspace(var.kms_key_id) != "" : false
      )
      error_message = "kms_key_id deve ser informado quando sse_algorithm for aws:kms."
    }
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id

  versioning_configuration {
    # O versionamento não é opcional para buckets geridos por este módulo.
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket = aws_s3_bucket.this.id

  # Os quatro controles são necessários para bloquear acesso público completamente.
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_logging" "this" {
  bucket        = aws_s3_bucket.this.id
  target_bucket = var.logging_target_bucket
  target_prefix = var.logging_target_prefix
}
