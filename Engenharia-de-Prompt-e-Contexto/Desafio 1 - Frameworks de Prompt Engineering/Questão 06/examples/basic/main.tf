# O bucket de logs deve existir e aceitar a entrega de logs de acesso do S3.
module "application_logs" {
  source = "../.."

  environment           = "prod"
  owner                 = "payments-platform"
  cost_center           = "CC-1234"
  bucket_name           = "application-logs"
  logging_target_bucket = "hvt-prod-central-access-logs"

  # SSE-S3 é aplicado por padrão; use aws:kms e kms_key_id quando necessário.
}
