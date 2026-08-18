variable "environment" {
  description = "Ambiente de deploy (dev, staging, prod)"
  type        = string
  nullable    = false

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment deve ser um dos valores: dev, staging ou prod."
  }
}

variable "owner" {
  description = "Time responsável pelo recurso"
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.owner)) > 0
    error_message = "owner deve ser informado e não pode conter somente espaços."
  }
}

variable "cost_center" {
  description = "Centro de custo para rateio da fatura"
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.cost_center)) > 0
    error_message = "cost_center deve ser informado e não pode conter somente espaços."
  }
}

variable "bucket_name" {
  description = "Sufixo único do bucket; o nome final será hvt-<environment>-<bucket_name>."
  type        = string
  nullable    = false

  validation {
    condition     = length(var.bucket_name) <= 51 && can(regex("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", var.bucket_name))
    error_message = "bucket_name deve ter até 51 caracteres, usar somente letras minúsculas, números e hífens, e não pode começar ou terminar com hífen."
  }
}

variable "logging_target_bucket" {
  description = "Nome do bucket de destino que receberá os logs de acesso."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", var.logging_target_bucket))
    error_message = "logging_target_bucket deve ser um nome de bucket S3 com 3 a 63 caracteres, iniciado e terminado por letra minúscula ou número."
  }
}

variable "logging_target_prefix" {
  description = "Prefixo usado para armazenar os logs de acesso no bucket de destino."
  type        = string
  default     = "s3-access-logs/"
}

variable "sse_algorithm" {
  description = "Algoritmo de criptografia padrão do bucket: AES256 para SSE-S3 ou aws:kms para SSE-KMS."
  type        = string
  default     = "AES256"

  validation {
    condition     = contains(["AES256", "aws:kms"], var.sse_algorithm)
    error_message = "sse_algorithm deve ser AES256 ou aws:kms."
  }
}

variable "kms_key_id" {
  description = "ARN ou ID da chave KMS usada quando sse_algorithm for aws:kms."
  type        = string
  default     = null
}

variable "force_destroy" {
  description = "Define se o bucket pode ser destruído mesmo quando contiver objetos ou versões."
  type        = bool
  default     = false
}
