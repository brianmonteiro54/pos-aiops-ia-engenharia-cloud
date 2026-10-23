# Ticket 04 — Dashboard de leitura do cluster

`cluster-retrato`: aplicação local que lê o cluster corrente do kubeconfig e mostra o
retrato de um namespace numa tela. Encurta os primeiros minutos de um chamado. **Não
substitui o terminal.**

Somente leitura, e a garantia está no projeto: toda chamada ao cluster passa por uma função
única com lista branca de comandos, e um teste varre o próprio fonte procurando verbo de
escrita.

## Como subir

```bash
# 1. workload de laboratório: os quatro estados que a tela precisa mostrar
./laboratorio/subir-workload.sh

# 2. a aplicação (loopback por padrão, porta 8777)
python3 cluster-retrato/cluster_retrato.py
#   -> http://127.0.0.1:8777
```

Requisitos: `kubectl` no PATH, um kubeconfig com contexto corrente, Python 3.9+. **Nenhuma
dependência de pacote.**

Opções úteis:

```bash
python3 cluster-retrato/cluster_retrato.py --help
  --endereco          endereço de escuta (padrão 127.0.0.1)
  --porta             padrão 8777
  --teto-externo      segundos para o comando kubectl inteiro (padrão 20)
  --teto-requisicao   segundos por requisição, passado ao kubectl (padrão 8)
  --auditar           roda a varredura do CA-08 no próprio fonte e sai
  --uma-vez           coleta, imprime o HTML em stdout e sai
```

## Como validar

```bash
./laboratorio/subir-workload.sh            # os quatro estados no cluster
./laboratorio/preparar-cenarios-de-falha.sh # os kubeconfigs quebrados de propósito
./validar.sh
```

Última execução: **66 verificações, 0 falhas** — `evidencias/validacao.txt`.

> `preparar-cenarios-de-falha.sh` gera kubeconfigs com token e chave privada de verdade
> (descartáveis, de um cluster local) em `~/desafio03-lab/t04`, **fora do repositório**.
> Nada disso entra no git.

## Entregue

| O ticket pedia | Onde está |
|---|---|
| brainstorm do recorte | `docs/01-brainstorm-e-prd.md` |
| PRD com requisitos e critérios de aceite | `docs/01-brainstorm-e-prd.md` |
| TRD | `docs/02-trd.md` |
| decisão 1 — linguagem e stack | `docs/adr/ADR-001-linguagem-e-stack.md` |
| decisão 2 — como falar com a API | `docs/adr/ADR-002-acesso-a-api.md` |
| decisão 3 — como atualizar a tela | `docs/adr/ADR-003-atualizacao-da-tela.md` |
| decisão 4 — `Endpoints` ou `EndpointSlice` | `docs/adr/ADR-004-fonte-dos-endpoints.md` |
| decisão 5 — recorte da primeira fatia | `docs/adr/ADR-005-recorte-da-primeira-fatia.md` |
| ciclo OpenSpec | `cluster-retrato/openspec/` (arquivado) |
| implementação | `cluster-retrato/cluster_retrato.py` |
| validação com os 3 cenários de falha | `validar.sh`, `evidencias/` |
| registro do comportamento das skills | `docs/03-registro-das-skills.md` |
| curadoria | `curadoria.md` |

## Critérios de aceite

| # | Critério | Como é verificado |
|---|---|---|
| CA-01 | os seis itens do RF-02 contra o cluster real | `validar.sh`, + `GET /` por HTTP |
| CA-02 | `readyReplicas` ausente aparece como `0/N` | `nyx-prod/nyx-api` → `0/2` |
| CA-03 | Service por endpoints prontos/total | `nyx-stg` → `0/0`, `nyx-prod` → `0/2` |
| CA-04 | `CrashLoopBackOff` com `OOMKilled`, apesar de `phase: Running` | `nyx-prod` |
| CA-05 | cluster que não responde, sem stack trace | porta fechada **e** IP não roteável |
| CA-06 | credencial rejeitada, distinguível de cluster fora | 5 kubeconfigs (ver ressalva) |
| CA-07 | permissão negada em um tipo, os outros seguem | ServiceAccount sem `events` |
| CA-08 | nenhum caminho executa verbo de escrita | varredura por AST + portão em execução |

## Três coisas que a medição desmentiu

Detalhe em `curadoria.md`. O resumo:

**`--request-timeout` não limita o comando.** Contra um IP não roteável: sem teto, o
`kubectl` travou **além de 70s**; com `--request-timeout=5s`, levou **25s**. São dois tetos,
e o externo mata o grupo de processos.

**"Credencial expirada" não é afirmável.** Token inválido, JWT expirado e certificado de
cliente expirado assinado pela CA real do cluster devolvem a **mesma** linha
(`Unauthorized`, `exit 1`). A tela diz "expirada, inválida ou revogada". Só quando um `exec`
plugin informa a expiração é que ela é nomeada.

**Contar endpoints responde a pergunta errada.** Com pods em `CrashLoopBackOff` o objeto
`Endpoints` **tem** `subsets`, cheio de `notReadyAddresses`. A conta é `prontos/total`, e
`0/0` (selector não casa) conta história diferente de `0/3` (pods não sobem). Isto corrigiu
o PRD deste ticket **e** a skill do Ticket 02.

## Limitações conhecidas

- **sem autenticação.** Bind em loopback por padrão, aviso ao expor. Inadequado para uso
  compartilhado
- **RBAC somente-leitura não é usado como camada de garantia** — é a dívida que o Ticket 02
  registrou e que este ticket não pagou
- o caminho de `Endpoints` só roda por injeção no teste; este cluster tem
  `discovery.k8s.io/v1`
- a soma de N `EndpointSlice` por Service não é exercitada com N > 1 (o cluster tem 1)
- a classificação de falha casa texto do `kubectl` **v1.33.13**; outra versão cai no rótulo
  `nao_classificada`, que mostra o erro cru em vez de arriscar rótulo errado
- nada medido em cluster grande: os seis `LIST` são sequenciais e `get pods -A` não pagina

## Nota sobre o workload de laboratório

`registry.metacortex.io` não existe. `subir-workload.sh` aplica os manifests do Ticket 01 e
em seguida roda `kubectl set image` para imagens públicas. Efeito: a regra 3.7 do Padrão de
Manifests fica **satisfeita no artefato e insatisfeita no cluster**.

Isso não é descuido — é a diferença entre o que a skill do Ticket 01 julga (arquivo) e o que
a do Ticket 02 vê (estado). Está analisada em `docs/03-registro-das-skills.md`.

## Estrutura

```
ticket-04-dashboard-do-cluster/
├── docs/
│   ├── 01-brainstorm-e-prd.md
│   ├── 02-trd.md
│   ├── 03-registro-das-skills.md
│   └── adr/ADR-001 … ADR-005
├── cluster-retrato/
│   ├── cluster_retrato.py          # a aplicação, 1 arquivo, zero dependência
│   ├── testes/teste_normalizacao.py # 41 testes: normalização + portão + classificação
│   └── openspec/                    # ciclo arquivado
├── laboratorio/
│   ├── subir-workload.sh
│   └── preparar-cenarios-de-falha.sh
├── evidencias/
│   ├── validacao.txt                # 66 verificações
│   └── modos-de-falha.txt           # os nove modos medidos
├── validar.sh
├── curadoria.md
└── README.md
```
