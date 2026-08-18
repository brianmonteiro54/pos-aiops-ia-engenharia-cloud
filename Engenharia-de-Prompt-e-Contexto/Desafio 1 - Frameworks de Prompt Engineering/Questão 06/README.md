# Módulo S3 — Hill Valley Tech

Cria um bucket S3 no padrão `hvt-<environment>-<bucket_name>`, com criptografia, versionamento, bloqueio total de acesso público e logging de acesso sempre habilitados.

O bucket de destino de logs deve existir previamente e permitir a escrita do serviço de entrega de logs do S3.

## Inputs

| Nome | Descrição | Tipo | Padrão | Obrigatório |
|---|---|---|---|---|
| `environment` | Ambiente de deploy: `dev`, `staging` ou `prod`. | `string` | — | Sim |
| `owner` | Time responsável pelo recurso. | `string` | — | Sim |
| `cost_center` | Centro de custo para rateio da fatura. | `string` | — | Sim |
| `bucket_name` | Sufixo único usado no nome final do bucket. | `string` | — | Sim |
| `logging_target_bucket` | Bucket que receberá os logs de acesso. | `string` | — | Sim |
| `logging_target_prefix` | Prefixo dos logs no bucket de destino. | `string` | `s3-access-logs/` | Não |
| `sse_algorithm` | `AES256` (SSE-S3) ou `aws:kms` (SSE-KMS). | `string` | `AES256` | Não |
| `kms_key_id` | ARN ou ID da chave KMS quando `sse_algorithm = "aws:kms"`. | `string` | `null` | Não |
| `force_destroy` | Permite destruir o bucket mesmo com objetos ou versões. | `bool` | `false` | Não |

## Outputs

| Nome | Descrição |
|---|---|
| `id` | ID do bucket S3 criado. |
| `arn` | ARN do bucket S3 criado. |
| `bucket_domain_name` | Nome de domínio regional do bucket. |
| `tags` | Mapa das tags aplicadas pelo módulo. |

## Exemplo

Veja [`examples/basic`](examples/basic) para uma chamada mínima e aderente ao padrão da Hill Valley Tech.
