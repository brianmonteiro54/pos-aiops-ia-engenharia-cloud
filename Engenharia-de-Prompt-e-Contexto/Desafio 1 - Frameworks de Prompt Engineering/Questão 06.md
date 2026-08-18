# Questão 06 — Módulo Terraform no padrão interno

**Framework:** C-A-R-E (Context, Action, Result, Example)

---

## Prompt

`````text
[CONTEXT]
Você é um engenheiro de plataforma sênior especializado em Terraform e IaC padronizada na Hill Valley Tech.

Strickland (head de segurança e compliance) publicou o padrão interno de IaC que todo módulo Terraform novo precisa seguir:

- Tags obrigatórias em todo recurso que suporte tags: Owner, CostCenter e Environment.
- Prefixo hvt- em todos os nomes de recursos.
- Toda variável em variables.tf precisa ter description e type declarados, sem exceção.

Regras específicas de compliance para bucket S3:

- Encryption habilitada, no mínimo SSE-S3.
- Versioning ativo.
- Block public access total.
- Logging configurado.

Doc Brown (CTO) pediu um módulo reutilizável para criar buckets S3 aderentes a esse padrão. O módulo será consumido por todos os times da empresa, então precisa ser genérico, parametrizável e seguro por padrão: um time que use o módulo sem configurar nada além do obrigatório já deve sair em conformidade.

Existe um módulo de VPC interno que é a referência de estilo da empresa, e o módulo novo precisa parecer escrito pela mesma pessoa que escreveu aquele.

[ACTION]
Escreva o módulo Terraform de S3 da Hill Valley Tech, fazendo o seguinte:

1. Criar o bucket S3 com nome composto pelo prefixo hvt- e pelos parâmetros do módulo, seguindo a mesma convenção de nomes do módulo de referência.
2. Aplicar as tags obrigatórias (Owner, CostCenter, Environment) via locals com common_tags e merge, exatamente no mesmo padrão do módulo de VPC.
3. Habilitar server-side encryption com no mínimo SSE-S3, permitindo opcionalmente SSE-KMS com chave informada por variável.
4. Habilitar versioning.
5. Aplicar block public access completo, nos quatro atributos.
6. Configurar logging de acesso, permitindo que o bucket de destino dos logs seja informado por variável.
7. Declarar todas as variáveis em variables.tf com description e type obrigatórios, defaults seguros apenas onde faz sentido, e validation nas variáveis que têm domínio restrito (por exemplo Environment).
8. Declarar outputs úteis para quem consome o módulo (id, arn, bucket domain name e o mapa de tags aplicadas).
9. Usar os recursos separados da AWS provider v5 (aws_s3_bucket_versioning, aws_s3_bucket_server_side_encryption_configuration, aws_s3_bucket_public_access_block, aws_s3_bucket_logging) em vez de argumentos inline depreciados no aws_s3_bucket.
10. Não usar valor hardcoded que devesse ser variável, e não deixar nenhuma configuração de compliance como opt-in: encryption, versioning e block public access são sempre aplicados.

[RESULT]
O resultado esperado é um módulo S3 completo, reutilizável e em conformidade, entregue arquivo por arquivo:

- main.tf com locals e recursos
- variables.tf com todas as variáveis documentadas e tipadas
- outputs.tf
- versions.tf com required_version e required_providers
- README.md curto com a tabela de inputs e outputs
- um exemplo de uso do módulo (examples/basic), mostrando como um time consumidor chama o módulo passando Owner, CostCenter e Environment

O módulo tem que passar em revisão do Strickland sem apontamento: cada regra do padrão interno visível no código. Ao final, inclua um checklist curto mapeando cada regra do padrão para o trecho do módulo que a implementa.

[EXAMPLE]
Use o trecho abaixo, extraído do módulo de VPC já existente, como modelo de estilo a seguir: mesma organização de variable, mesmo local common_tags, mesmo uso de name_prefix e mesma forma de aplicar merge de tags no recurso. Mantenha esse estilo de nomenclatura, indentação e alinhamento de atributos.

```hcl
variable "environment" {
  description = "Ambiente de deploy (dev, staging, prod)"
  type        = string
}

variable "owner" {
  description = "Time responsável pelo recurso"
  type        = string
}

variable "cost_center" {
  description = "Centro de custo para rateio da fatura"
  type        = string
}

locals {
  name_prefix = "hvt-${var.environment}"

  common_tags = {
    Owner       = var.owner
    CostCenter  = var.cost_center
    Environment = var.environment
  }
}

resource "aws_vpc" "this" {
  cidr_block           = var.cidr_block
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = merge(
    local.common_tags,
    {
      Name = "${local.name_prefix}-vpc"
    }
  )
}
```

Formato da resposta: um bloco de código por arquivo, cada um precedido apenas pelo caminho do arquivo como título. Comentários em português dentro do código. O checklist de conformidade vem por último.
`````

---

## Modelo

**GPT-5.6 Terra Max (OpenAI)**

Escolhido porque a questão pede um módulo multiarquivo internamente coerente (locals, variáveis, recursos, outputs, README e exemplo referenciando o mesmo contrato) e porque o modelo rodou em modo agente: ele buscou o módulo de VPC no repositório, verificou que a referência real não existe, decidiu seguir apenas o trecho fornecido e ainda executou `terraform fmt` sobre o próprio resultado.

---

## Output

> O trace de tool calls, o painel de progresso e as chamadas de sub-agente da interface foram omitidos. Registro do que aconteceu nesse trace, porque é relevante para a avaliação: o modelo procurou o módulo de VPC no repositório com busca e histórico do git, não encontrou, e concluiu explicitamente "a referência real de VPC não está no repositório; vou seguir fielmente o trecho fornecido e criar o módulo no diretório da Questão 06, sem introduzir uma convenção global nova". Depois rodou `terraform fmt -check -recursive` (passou), tentou `terraform validate` (falhou por falta do provider AWS local), passou o resultado por uma revisão que apontou a possibilidade de string vazia nas variáveis obrigatórias e corrigiu `variables.tf` adicionando `nullable = false` e validações de `trimspace`.

Vou conferir a estrutura e a referência de estilo disponível antes de criar e validar o módulo Terraform completo.

### `main.tf`

```hcl
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
```

### `variables.tf`

```hcl
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
```

### `outputs.tf`

```hcl
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
```

### `versions.tf`

```hcl
terraform {
  required_version = ">= 1.5.0, < 2.0.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

### `README.md`

````markdown
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
````

### `examples/basic/main.tf`

```hcl
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
```

### Checklist de conformidade

- Prefixo `hvt-`: `local.name_prefix` e `aws_s3_bucket.this.bucket`.
- Tags Owner, CostCenter e Environment: `local.common_tags`, aplicadas com `merge`.
- Encryption obrigatória: `aws_s3_bucket_server_side_encryption_configuration`, com SSE-S3 como padrão e SSE-KMS parametrizável.
- Versioning obrigatório: `aws_s3_bucket_versioning` com `status = "Enabled"`.
- Bloqueio total de acesso público: os quatro atributos em `aws_s3_bucket_public_access_block`.
- Logging obrigatório e parametrizável: `aws_s3_bucket_logging` e `logging_target_bucket`.
- Variáveis documentadas, tipadas e validadas: `variables.tf`.
- Outputs, README e exemplo básico incluídos.
- `terraform fmt -check -recursive` passou. `terraform validate` permanece pendente de `terraform init`, pois o provider AWS não está instalado localmente.

---

## Justificativa

**Context:** o Context carregou o padrão do Strickland como regra de compliance, não como sugestão (tags obrigatórias, prefixo `hvt-`, description e type em toda variável, e as quatro exigências de S3), e acrescentou a restrição de produto que muda o desenho do módulo: será consumido por todos os times e precisa ser seguro por padrão. Isso aparece no resultado como compliance não negociável, `status = "Enabled"` fixo no versioning, os quatro atributos de public access block em `true` e `AES256` como default de criptografia.

**Action:** os 10 itens da Action funcionaram como especificação de implementação e evitaram os dois erros mais comuns nesse tipo de módulo: o item 9 forçou os recursos separados do provider v5 em vez dos argumentos inline depreciados do `aws_s3_bucket`, e o item 10 proibiu deixar compliance como opt-in. O item 7 puxou as `validation`, incluindo o domínio fechado de `environment` e o regex de nome de bucket, e o item 3 gerou a `precondition` que barra `aws:kms` sem `kms_key_id`.

**Result:** o Result definiu a entrega arquivo por arquivo e o critério de aceitação em uma frase útil ("passar em revisão do Strickland sem apontamento"), além de exigir o checklist mapeando regra para trecho de código. Por isso o output não é um `main.tf` solto: vieram os seis artefatos e o checklist final que um revisor usa para conferir sem ler o módulo inteiro.

**Example:** o Example foi o componente decisivo e o mais interessante de avaliar aqui. O modelo rodou em modo agente, procurou o módulo de VPC no repositório, não encontrou, e registrou a decisão de seguir estritamente o snippet do prompt sem inventar convenção nova. O estilo do snippet aparece replicado: `local.name_prefix` com o mesmo formato, `common_tags` com as mesmas três chaves na mesma ordem, `merge` com `Name` no segundo mapa, `resource "..." "this"` e alinhamento dos `=`. É o Example fazendo o trabalho que a Action não faria: sem ele o módulo estaria correto e fora do padrão visual da casa.

**Validação executada:** completei aqui a verificação que ficou pendente no output. `terraform fmt -check -recursive`: passou. `terraform init -backend=false`: instalou `hashicorp/aws v5.100.0`, coerente com o `~> 5.0` do `versions.tf`. `terraform validate`: **Success** no módulo raiz e **Success** em `examples/basic`. Ou seja, o último item do checklist do modelo ("validate pendente") já está resolvido: o módulo é válido de fato, não só bem formatado. Os diretórios `.terraform/` gerados nessa verificação (1,35 GB de provider) foram removidos e há um `.gitignore` no módulo para não voltarem ao repositório.

**Três pontos que eu ajustaria**

1. **`output "tags"` deveria usar `tags_all`.** `aws_s3_bucket.this.tags` devolve só as tags declaradas no recurso. Se o provider tiver `default_tags`, o mapa retornado não é o conjunto realmente aplicado, e o output promete exatamente isso.
2. **Falta `bucket_key_enabled` no caminho SSE-KMS.** Com S3 Bucket Keys ligado, o custo de KMS cai de forma expressiva em buckets com volume alto de objetos. Como o módulo será consumido por toda a empresa, esse default importa.
3. **`logging_target_prefix` ficou sem `nullable = false`.** As outras variáveis obrigatórias receberam a proteção na revisão, mas essa, mesmo tendo default, aceita `null` explícito e passaria um prefixo nulo ao `aws_s3_bucket_logging`.
