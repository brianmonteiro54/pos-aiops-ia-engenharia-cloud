# Questão 02 — Script de backup do Ledger

**Framework:** R-T-F (Role, Task, Format)

---

## Prompt

````text
[ROLE]
Você é um SRE/DBA sênior especializado em automação bash de rotinas de backup PostgreSQL em AWS. Você escreve scripts defensivos, à prova de falha silenciosa e prontos para entrar em produção sem revisão adicional.

[TASK]
Escreva o script bash de backup diário do "Ledger", o data warehouse PostgreSQL da Hill Valley Tech, que hoje não possui nenhum backup automatizado. O script será agendado via cron e mantido pelo time de SRE.

Ambiente e insumos:

- Conexão: host ledger-db.internal.hvt.io, porta 5432, banco ledger_prod, usuário backup_user
- Senha: lida da variável de ambiente PGPASSWORD, populada pelo AWS Secrets Manager via IAM role. A senha nunca aparece no script, em log ou em linha de comando
- Região AWS: us-east-1
- Sistema operacional: Ubuntu 22.04 LTS
- Diretório de trabalho: /var/backups/ledger, com 80 GB livres
- Tamanho atual do dump compactado: aproximadamente 12 GB
- Bucket de destino: s3://hvt-ledger-backups

Requisitos técnicos que o script deve atender:

1. Pipeline obrigatório: pg_dump -> compactação com gzip -> upload para o S3 com `aws s3 cp`.
2. Nome do arquivo com timestamp, no padrão ledger_prod_YYYYMMDD_HHMMSS.sql.gz.
3. Retenção de 30 dias no S3, removendo os backups mais antigos que isso.
4. Remoção do arquivo local após o upload ser confirmado com sucesso.
5. Verificação de espaço livre em disco antes de iniciar o dump, considerando o tamanho esperado de ~12 GB.
6. Log de cada execução com timestamp em /var/log/ledger-backup.log, registrando início, fim, duração, tamanho do arquivo gerado e o resultado de cada etapa.
7. Tratamento de erro em todas as etapas críticas, com exit code adequado e distinto por tipo de falha. Falha no meio do pipeline não pode gerar um backup incompleto tratado como sucesso: trate explicitamente o status de cada comando do pipe.
8. Validação de pré-condições antes de começar: PGPASSWORD definida, binários pg_dump, gzip e aws disponíveis, diretório de trabalho existente e gravável.
9. Proteção contra execução concorrente, para o caso de uma execução anterior ainda estar rodando.
10. Compatível com execução não interativa via cron: PATH explícito e nenhuma dependência do ambiente do shell interativo.

[FORMAT]
Entregue a resposta em duas partes, nesta ordem, sem nenhum texto fora dos blocos de código:

1. Um único bloco de código com o script bash completo, começando por `#!/usr/bin/env bash`, comentado em português bloco a bloco, com um comentário de cabeçalho no topo informando propósito, dependências, variáveis esperadas e a tabela de exit codes usados.
2. Um bloco de código com a linha de crontab para execução diária às 02:00 e os comandos de instalação do script (caminho de destino, permissões e criação do arquivo de log).

Sem introdução, sem explicação em prosa, sem conclusão, sem comentários fora dos blocos de código.
````

---

## Modelo

**Gemini Flash (Google) — modo de raciocínio estendido**

Escolhido porque a tarefa é mecânica e totalmente especificada (10 requisitos verificáveis, formato de saída fechado): não exige o modelo mais caro, e o raciocínio estendido é suficiente para o único ponto que pede cuidado real, o tratamento do status de cada comando do pipe.

---

## Output

```bash
#!/usr/bin/env bash
# ==============================================================================
# Script: ledger_backup.sh
# Propósito: Realiza o backup diário, compactação, transferência para AWS S3 e
#            gestão do ciclo de retenção do data warehouse PostgreSQL "Ledger".
#
# Dependências:
#   - bash (>= 4.0)
#   - coreutils (date, df, rm, awk, tee, etc.)
#   - util-linux (flock)
#   - postgresql-client-14+ (pg_dump)
#   - gzip
#   - aws-cli v2 (aws)
#
# Variáveis de Ambiente Esperadas:
#   - PGPASSWORD: Senha de autenticação do usuário do banco (injetada via AWS Secrets Manager).
#   - AWS_DEFAULT_REGION / AWS_REGION: (Opcional) Região AWS (padrão: us-east-1).
#
# Tabela de Códigos de Saída (Exit Codes):
#   0 - Sucesso na execução completa da rotina
#   1 - Execução concorrente detectada (lock ativo)
#   2 - Pré-condições ausentes (binários, variáveis obrigatórias)
#   3 - Diretório de trabalho inválido ou sem permissão de escrita
#   4 - Espaço insuficiente em disco local para geração do dump
#   5 - Falha no pipeline de geração/compactação (pg_dump | gzip)
#   6 - Falha no upload do artefato para o Amazon S3
#   7 - Falha na rotina de expurgo de retenção no S3
# ==============================================================================

# Ativação do modo defensivo estrito
set -Eeuo pipefail

# ------------------------------------------------------------------------------
# 1. AMBIENTE E CONSTANTES
# ------------------------------------------------------------------------------
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LC_ALL="C"

# Parâmetros de Conexão com o PostgreSQL
readonly DB_HOST="ledger-db.internal.hvt.io"
readonly DB_PORT="5432"
readonly DB_NAME="ledger_prod"
readonly DB_USER="backup_user"

# Parâmetros de Armazenamento e AWS
readonly AWS_REGION="us-east-1"
readonly S3_BUCKET="s3://hvt-ledger-backups"
readonly WORK_DIR="/var/backups/ledger"
readonly LOG_FILE="/var/log/ledger-backup.log"
readonly LOCK_FILE="${WORK_DIR}/.ledger_backup.lock"

# Regras de Negócio e Capacidade
readonly MIN_DISK_SPACE_GB=20
readonly RETENTION_DAYS=30

# ------------------------------------------------------------------------------
# 2. FUNÇÕES AUXILIARES
# ------------------------------------------------------------------------------

# Registra mensagens formatadas com timestamp no log e no canal stderr
log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo "${timestamp} [${level}] ${message}" | tee -a "${LOG_FILE}" >&2
}

# Trap de limpeza para remoção de arquivos residuais em caso de erro/interrupção
cleanup() {
    local exit_code=$?
    if [[ -n "${LOCAL_BACKUP_PATH:-}" && -f "${LOCAL_BACKUP_PATH}" ]]; then
        log "WARN" "Limpando artefato local temporário/incompleto devido à interrupção: ${LOCAL_BACKUP_PATH}"
        rm -f "${LOCAL_BACKUP_PATH}"
    fi
    exit "${exit_code}"
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# 3. VALIDAÇÃO DE PRÉ-CONDIÇÕES E PROTEÇÃO CONCORRENTE
# ------------------------------------------------------------------------------

# Validação do diretório de trabalho e permissões de escrita
if [[ ! -d "${WORK_DIR}" || ! -w "${WORK_DIR}" ]]; then
    log "FATAL" "Diretório de trabalho '${WORK_DIR}' não existe ou não possui permissão de escrita."
    exit 3
fi

# Proteção contra execução concorrente usando descritor de arquivo e flock
exec 200>"${LOCK_FILE}"
if ! flock -n 200; then
    log "ERROR" "Outra instância do backup já está em execução. Abortando execução."
    exit 1
fi

log "INFO" "=================== INÍCIO DA ROTINA DE BACKUP: ${DB_NAME} ==================="
SCRIPT_START_TIME=$(date +%s)

# Validação da variável de ambiente PGPASSWORD
if [[ -z "${PGPASSWORD:-}" ]]; then
    log "FATAL" "A variável de ambiente PGPASSWORD não está definida ou está vazia."
    exit 2
fi

# Validação de binários essenciais
readonly REQUIRED_BINARIES=("pg_dump" "gzip" "aws" "df" "awk" "date")
for bin in "${REQUIRED_BINARIES[@]}"; do
    if ! command -v "${bin}" >/dev/null 2>&1; then
        log "FATAL" "Dependência obrigatória ausente no PATH: ${bin}"
        exit 2
    fi
done

# ------------------------------------------------------------------------------
# 4. VERIFICAÇÃO DE ESPAÇO LIVRE EM DISCO LOCAL
# ------------------------------------------------------------------------------
AVAILABLE_KB=$(df -P "${WORK_DIR}" | awk 'NR==2 {print $4}')
AVAILABLE_GB=$(( AVAILABLE_KB / 1024 / 1024 ))

log "INFO" "Espaço livre disponível em '${WORK_DIR}': ${AVAILABLE_GB} GB (Mínimo exigido: ${MIN_DISK_SPACE_GB} GB)."

if (( AVAILABLE_GB < MIN_DISK_SPACE_GB )); then
    log "FATAL" "Espaço insuficiente em disco. Requerido: >= ${MIN_DISK_SPACE_GB} GB, Disponível: ${AVAILABLE_GB} GB."
    exit 4
fi

# ------------------------------------------------------------------------------
# 5. EXECUÇÃO DO PIPELINE DE DUMP E COMPACTAÇÃO
# ------------------------------------------------------------------------------
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
BACKUP_FILENAME="ledger_prod_${TIMESTAMP}.sql.gz"
LOCAL_BACKUP_PATH="${WORK_DIR}/${BACKUP_FILENAME}"
S3_TARGET_URI="${S3_BUCKET}/${BACKUP_FILENAME}"

log "INFO" "Iniciando geração do dump compactado: ${LOCAL_BACKUP_PATH}"
DUMP_START_TIME=$(date +%s)

# Desativa saída imediata para inspecionar explicitamente o PIPESTATUS
set +e
pg_dump \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${DB_USER}" \
    -d "${DB_NAME}" \
    --no-password \
    --format=plain \
    --no-owner \
    --no-privileges 2>> "${LOG_FILE}" | gzip -c > "${LOCAL_BACKUP_PATH}"
PIPE_STATUS=("${PIPESTATUS[@]}")
set -e

PG_DUMP_EXIT=${PIPE_STATUS[0]}
GZIP_EXIT=${PIPE_STATUS[1]}

# Validação do status de cada elemento do pipe
if [[ ${PG_DUMP_EXIT} -ne 0 || ${GZIP_EXIT} -ne 0 ]]; then
    log "FATAL" "Falha no pipeline de dump. pg_dump exit code: ${PG_DUMP_EXIT}, gzip exit code: ${GZIP_EXIT}."
    [[ -f "${LOCAL_BACKUP_PATH}" ]] && rm -f "${LOCAL_BACKUP_PATH}"
    exit 5
fi

# Validação da integridade física do arquivo gerado
if [[ ! -s "${LOCAL_BACKUP_PATH}" ]]; then
    log "FATAL" "O arquivo de backup gerado está vazio ou não foi encontrado: ${LOCAL_BACKUP_PATH}"
    [[ -f "${LOCAL_BACKUP_PATH}" ]] && rm -f "${LOCAL_BACKUP_PATH}"
    exit 5
fi

DUMP_END_TIME=$(date +%s)
DUMP_DURATION=$(( DUMP_END_TIME - DUMP_START_TIME ))
FILE_SIZE_HUMAN=$(du -h "${LOCAL_BACKUP_PATH}" | awk '{print $1}')
FILE_SIZE_BYTES=$(stat -c %s "${LOCAL_BACKUP_PATH}")

log "INFO" "Dump e compressão concluídos com sucesso. Tamanho: ${FILE_SIZE_HUMAN} (${FILE_SIZE_BYTES} bytes). Duração: ${DUMP_DURATION}s."

# ------------------------------------------------------------------------------
# 6. TRANSFERÊNCIA SEGURA PARA O AMAZON S3
# ------------------------------------------------------------------------------
log "INFO" "Iniciando upload para o S3: ${S3_TARGET_URI}"
UPLOAD_START_TIME=$(date +%s)

if ! aws s3 cp "${LOCAL_BACKUP_PATH}" "${S3_TARGET_URI}" --region "${AWS_REGION}" >> "${LOG_FILE}" 2>&1; then
    log "FATAL" "Falha no upload do arquivo para o Amazon S3."
    exit 6
fi

UPLOAD_END_TIME=$(date +%s)
UPLOAD_DURATION=$(( UPLOAD_END_TIME - UPLOAD_START_TIME ))
log "INFO" "Upload para o S3 concluído com sucesso. Duração: ${UPLOAD_DURATION}s."

# ------------------------------------------------------------------------------
# 7. REMOÇÃO DO ARQUIVO LOCAL
# ------------------------------------------------------------------------------
log "INFO" "Removendo arquivo local após confirmação de upload: ${LOCAL_BACKUP_PATH}"
rm -f "${LOCAL_BACKUP_PATH}"

# Desarma a exclusão do trap, pois a remoção regular foi concluída com sucesso
LOCAL_BACKUP_PATH=""

# ------------------------------------------------------------------------------
# 8. EXPURGO E POLÍTICA DE RETENÇÃO NO S3 (30 DIAS)
# ------------------------------------------------------------------------------
log "INFO" "Iniciando verificação da política de retenção no S3 (${RETENTION_DAYS} dias)..."

CUTOFF_TIMESTAMP=$(date -d "${RETENTION_DAYS} days ago" '+%Y%m%d%H%M%S')

# Listagem de backups gerenciados no padrão ledger_prod_YYYYMMDD_HHMMSS.sql.gz
S3_OBJECTS=$(aws s3 ls "${S3_BUCKET}/" --region "${AWS_REGION}" 2>> "${LOG_FILE}" | awk '{print $4}' | grep -E '^ledger_prod_[0-9]{8}_[0-9]{6}\.sql\.gz$' || true)

if [[ -n "${S3_OBJECTS}" ]]; then
    while read -r obj; do
        [[ -z "${obj}" ]] && continue

        # Extração do timestamp do próprio nome do arquivo para ordenação estrita
        obj_ts=$(echo "${obj}" | sed -E 's/^ledger_prod_([0-9]{8})_([0-9]{6})\.sql\.gz$/\1\2/')

        if [[ "${obj_ts}" < "${CUTOFF_TIMESTAMP}" ]]; then
            log "INFO" "Excluindo backup expirado do S3: ${S3_BUCKET}/${obj}"
            if ! aws s3 rm "${S3_BUCKET}/${obj}" --region "${AWS_REGION}" >> "${LOG_FILE}" 2>&1; then
                log "ERROR" "Falha ao remover o objeto expirado do S3: ${obj}"
                exit 7
            fi
        fi
    done <<< "${S3_OBJECTS}"
fi

log "INFO" "Processamento de retenção finalizado."

# ------------------------------------------------------------------------------
# 9. FINALIZAÇÃO E MÉTRICAS DA EXECUÇÃO
# ------------------------------------------------------------------------------
SCRIPT_END_TIME=$(date +%s)
TOTAL_DURATION=$(( SCRIPT_END_TIME - SCRIPT_START_TIME ))

log "INFO" "Backup diário concluído com êxito em ${TOTAL_DURATION}s. Artefato: ${S3_TARGET_URI}"
log "INFO" "=================== FIM DA ROTINA DE BACKUP: ${DB_NAME} ==================="

exit 0
```

```bash
# 1. Criação da estrutura de diretórios e arquivos de sistema
sudo mkdir -p /var/backups/ledger
sudo touch /var/log/ledger-backup.log

# 2. Configuração de proprietário e permissões restritivas
sudo chown -R backup_user:backup_user /var/backups/ledger /var/log/ledger-backup.log
sudo chmod 750 /var/backups/ledger
sudo chmod 640 /var/log/ledger-backup.log

# 3. Instalação do script no diretório padrão de binários do sistema
sudo cp ledger_backup.sh /usr/local/bin/ledger_backup.sh
sudo chown backup_user:backup_user /usr/local/bin/ledger_backup.sh
sudo chmod 700 /usr/local/bin/ledger_backup.sh

# 4. Linha de agendamento no crontab do usuário backup_user (execução diária às 02:00 UTC)
# Para instalar: sudo crontab -u backup_user -e
0 2 * * * PGPASSWORD=$(aws secretsmanager get-secret-value --secret-id "ledger/db/backup_user" --query SecretString --output text --region us-east-1) /usr/local/bin/ledger_backup.sh >/dev/null 2>&1
```

---

## Justificativa

**Role:** o prompt fixou o modelo como SRE/DBA sênior que escreve script defensivo e à prova de falha silenciosa, e é isso que explica o que veio além do pedido explícito: `set -Eeuo pipefail`, `trap cleanup EXIT INT TERM` removendo dump parcial, `LC_ALL=C`, `readonly` nas constantes e checagem extra de arquivo vazio com `[[ ! -s ]]` depois do dump.

**Task:** a tarefa trouxe o ambiente completo (host, porta, banco, usuário, região, SO, diretório, tamanho do dump e bucket) mais 10 requisitos verificáveis, então o modelo não precisou inventar parâmetro nenhum: o pipeline, o padrão de nome `ledger_prod_YYYYMMDD_HHMMSS.sql.gz`, a retenção de 30 dias, o `flock` de concorrência e o PATH explícito para cron saíram diretamente dos itens numerados.

**Format:** o formato exigia duas partes, só blocos de código, comentários em português bloco a bloco e cabeçalho com propósito, dependências, variáveis e tabela de exit codes; o retorno seguiu exatamente isso, com 8 exit codes distintos por tipo de falha (requisito 7) e sem uma linha de prosa fora dos blocos.

**O que eu faria diferente:** o requisito 7 pedia tratar o status de cada comando do pipe e o modelo resolveu com `set +e` + `PIPESTATUS`, o que funciona, mas eu pediria explicitamente para não desarmar o `set -e` no meio do script. Também revisaria a linha de crontab: ela resolve o segredo via `command substitution`, o que expõe a senha no ambiente do processo, e o próprio prompt dizia que a senha não deveria aparecer em linha de comando.
