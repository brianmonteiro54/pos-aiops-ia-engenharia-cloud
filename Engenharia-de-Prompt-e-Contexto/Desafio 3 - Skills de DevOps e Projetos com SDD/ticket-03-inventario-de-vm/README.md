# Ticket 03: Inventário e drift de VM por SSH

Primeira peça do substituto do **Roster**: uma ferramenta de linha de comando que audita uma
VM por SSH, sem agente, e compara o que encontra com o baseline versionado do parque.

Projeto completo, com o arco de spec antes do código.

## Onde está cada item do `Entregue.`

| Item pedido | Onde está |
|---|---|
| **Os documentos de spec (PRD, TRD e ADRs)** | `docs/01-prd.md`, `docs/02-trd.md`, `docs/adr/` (quatro ADRs). O brainstorm que os antecede está em `docs/00-brainstorm.md` |
| **Artefatos do ciclo OpenSpec: proposta, tarefas, specs e o que foi arquivado** | `roster-inventario/openspec/changes/archive/2026-10-23-inventario-e-drift-de-vm/`: `proposal.md`, `design.md`, `tasks.md`, `specs/inventario-de-host/spec.md`. A spec principal resultante: `roster-inventario/openspec/specs/inventario-de-host/spec.md` |
| **O código** | `roster-inventario/roster_inventario.py`, mais os dois baselines |
| **Evidência: a saída nos dois formatos** | `evidencias/validacao.txt`, seções CA-01 a CA-03 |
| **Evidência: o código de retorno** | `evidencias/validacao.txt`, impresso após cada execução |
| **Evidência: host inalcançável** | `evidencias/validacao.txt`, seção CA-04, quatro casos |
| **Evidência: a segunda execução com o mesmo resultado** | `evidencias/validacao.txt`, seção CA-05 |
| **A curadoria** | `curadoria.md` |

## Os cinco critérios de pronto

Todos verificados por execução real contra host alcançável por SSH. `./validar.sh` reproduz.

| # | Critério | Resultado medido |
|---|---|---|
| **CA-01** | host conforme sai sem nenhum desvio | **0 desvios, `rc=0`** contra `baseline-laboratorio.yaml` |
| **CA-01b** | o mesmo host contra o baseline do parque | **exatamente 2 desvios**: `swap.habilitado` crítico e `kernel.versao_minima` médio, os dois previstos no ADR-004 |
| **CA-02** | cada desvio com a severidade do baseline | **7 desvios**: 4 críticos, 2 altos, 1 médio. `rc=1` |
| **CA-03** | regra não verificável, separada de conforme | `ssh.login_de_root` como `nao_verificado`, motivo `exige privilegio que o usuario da coleta nao tem`. No resumo: `conforme 3`, `desvio 7`, `nao_verificado 1`: **não somado em conforme** |
| **CA-04** | host inalcançável explica, sem stack trace | 4 casos, todos `rc=2` e sem bloco de conformidade: porta sem SSH, chave recusada, nome que não resolve, chave inexistente |
| **CA-05** | a segunda execução devolve o mesmo resultado | **mesmo veredito nas 11 regras**, documento idêntico, só o instante difere |
| **RE-03** | a chave privada não aparece em saída nenhuma | conteúdo, caminho, cabeçalho PEM e traceback: **todos ausentes** |

## As quatro decisões registradas

| ADR | Decisão | Descartados |
|---|---|---|
| **001** | `ssh` do sistema como subprocesso, com `ControlMaster` | biblioteca SSH na linguagem; transporte de orquestração |
| **002** | terceiro veredito `nao_verificado`, com motivo | abortar; reportar conforme; reportar desvio |
| **003** | Python 3, biblioteca padrão + PyYAML | Go; shell |
| **004** | containers com systemd, e as duas regras que eles não podem satisfazer | VM de verdade; localhost; mock do transporte |

O ADR-004 **não estava na lista** que o ticket manda registrar. Entrou porque limita o que
os critérios de aceite conseguem demonstrar, e deixar isso implícito seria apresentar como
provado algo que não foi.

## Como rodar

```bash
# 1. laboratorio: dois hosts com systemd, portas 2201 (conforme) e 2202 (desvios)
./laboratorio/subir.sh

# 2. auditar
cd roster-inventario
python3 roster_inventario.py \
    --host 127.0.0.1 --porta 2202 --usuario auditor \
    --chave ~/desafio03-lab/t03/chaves/auditor \
    --baseline baseline.yaml --formato ambos

# 3. validar os cinco critérios
cd .. && ./validar.sh
```

**Pré-requisitos:** `python3` ≥ 3.9 com PyYAML, `ssh` no PATH, `docker` para o laboratório.

**Códigos de saída:** `0` conforme · `1` há desvio · `2` inalcançável ou erro de uso.

## Por que há dois baselines

`baseline.yaml` é o do parque, como o ticket entrega. `baseline-laboratorio.yaml` é **o
mesmo menos duas regras**, e existe por um motivo registrado em ADR-004: container
compartilha o kernel e o namespace de swap do host, então `kernel.versao_minima` e
`swap.habilitado` são veredito do host e não do container auditado.

**Não é o padrão afrouxado para o teste passar.** A validação do CA-01 é em duas partes: o
host conforme sai com zero desvios contra o baseline do laboratório (provando a lógica)
e com **exatamente dois** contra o do parque, provando que os dois são os previstos e não um
defeito escondido. A diferença entre os arquivos é auditável por `diff`.

## Três coisas que a implementação me obrigou a consertar

**`dbus` não estava na spec**, e sem ele `systemctl` falha para usuário comum por SSH,
quatro regras saíram como `nao_verificado` na primeira validação. Eu havia validado o
laboratório com `docker exec`, que roda como **root**. A ferramenta estava certa; o
laboratório não exercitava o que devia.

**Host key de container recriado barrou a ferramenta**, e ela está certa:
`StrictHostKeyChecking=accept-new` recusa host cuja chave mudou. Não afrouxei: o
`subir.sh` limpa a entrada obsoleta, com o motivo escrito.

**Escrevi `## Por quê` onde o schema do OpenSpec espera `## Why`.** O `validate` passou e o
`archive` avisou. A regra estava no `config.yaml` que eu mesmo gerei, e eu não li.

Detalhe das três, e do que o agente entendeu diferente do que eu escrevi, em
`curadoria.md`.
