output "id" {
  description = "ID do bucket S3 criado."
  value       = aws_s3_bucket.this.id
}

output "arn" {
  description = "ARN do bucket S3 criado."
  value       = aws_s3_bucket.this.arn
}

output "bucket_domain_name" {
  description = "Nome de domínio regional do bucket S3 criado."
  value       = aws_s3_bucket.this.bucket_domain_name
}

output "tags" {
  description = "Mapa das tags aplicadas pelo módulo ao bucket."
  value       = aws_s3_bucket.this.tags
}
