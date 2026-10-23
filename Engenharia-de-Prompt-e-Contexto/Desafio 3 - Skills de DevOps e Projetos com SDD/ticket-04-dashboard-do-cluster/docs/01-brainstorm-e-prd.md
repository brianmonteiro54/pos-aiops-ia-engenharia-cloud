# Brainstorm e PRD — dashboard do cluster

## Brainstorm: o recorte

### O problema, como ele chega

Toda triagem começa com a mesma sequência de seis a dez comandos no terminal para montar o
retrato de um namespace. O Ticket 02 mediu isso: a triagem dos três chamados consumiu 26
chamadas, e as primeiras de cada uma eram sempre o mesmo retrato.

**Isto não substitui o terminal.** Encurta os primeiros minutos de cada chamado.

### O que isto NÃO é

| Ideia levantada | Por que ficou fora |
|---|---|
| **painel de observabilidade** | métrica, série temporal e alerta são outro produto. Isto lê o estado atual da API do Kubernetes |
| **ferramenta de operação** | nada de `apply`, `delete`, `scale`. A garantia tem que estar **visível no projeto**, não na intenção |
| **multicluster** | explicitamente fora de escopo. Quem quer outro cluster troca o contexto **por fora**, como já faz |
| **substituto do `kubectl`** | o terminal continua. Isto é o retrato inicial |
| **logs e `exec`** | são o passo seguinte da triagem, não o retrato. E `exec` é escrita disfarçada |
| **editor de YAML** | implicaria escrita |

### As cinco decisões em aberto

O ticket as nomeia, e nenhuma tem resposta única. Cada uma virou ADR:

1. linguagem e stack, considerando que quem mantém é um time de **infraestrutura** → ADR-001
2. como falar com a API: cliente oficial, `kubectl` como subprocesso, ou HTTP direto → ADR-002
3. como manter a tela atualizada: sob demanda, intervalo fixo, ou `watch` → ADR-003
4. fonte dos endpoints: `Endpoints` ou `EndpointSlice` → ADR-004
5. recorte da primeira fatia → ADR-005

### Três fatos sobre os dados que mudam a implementação

O ticket os entrega, e o Ticket 02 já tinha medido dois deles contra o cluster:

**Campo ausente não é campo vazio.** `Endpoints.subsets` **não vem** quando não há endpoint.
`Deployment.status.readyReplicas` **não vem** quando é zero. Medido no Ticket 02, com um
detalhe a mais: `EndpointSlice.endpoints` **vem, com valor `null`**. São dois modos
diferentes de quebrar — `KeyError` num, `TypeError` no outro.

**`Endpoints` está sendo descontinuado**, e a informação equivalente vive em
`EndpointSlice` → ADR-004.

> **Correção a este PRD, vinda da medição do ADR-004.** Eu havia escrito que "ausência de
> endpoint é o que explica 'subiu mas não responde'". Medi os dois tipos contra os quatro
> estados do cluster e **está incompleto**: nos namespaces com `CrashLoopBackOff` e com
> `ImagePullBackOff`, o objeto `Endpoints` **tem** `subsets` — populado com
> `notReadyAddresses`. Contar endpoints acusa só o caso do selector que não casa e passa
> batido nos outros dois. A pergunta certa é **quantos endpoints prontos**, não se existem.
> O RF-02 e o CA-03 foram reescritos por causa disso.

**"Pronto" não significa "saudável".** O fake-shop não tem endpoint de saúde, então o
Kubernetes o marca pronto assim que o processo sobe. O dashboard precisa dizer **o que sabe
e o que está inferindo**.

## PRD

**Produto:** `cluster-retrato`, aplicação local de leitura do cluster.
**Consumidor:** quem está de plantão, nos primeiros minutos de um chamado.

### Requisitos funcionais

#### RF-01 — Lê apenas o contexto corrente do kubeconfig

No momento em que sobe. **Sem seletor de cluster, sem troca de contexto por dentro.**
Multicluster está fora de escopo.

#### RF-02 — O mínimo da tela

| O que mostrar | Detalhe que não é decoração |
|---|---|
| **namespaces** do cluster | com contagem do que está quebrado em cada um |
| **pods** com estado, reinícios e motivo na falha | o motivo vive em `state.waiting.reason` e `lastState.terminated.reason`, não em `status.phase` |
| **deployments** com réplicas prontas sobre desejadas | `readyReplicas` ausente é zero, não erro |
| **services** com **endpoints prontos sobre total** | ver a correção abaixo: ausência de endpoint é só **um** dos três modos de "subiu mas não responde" |
| **eventos recentes** do namespace selecionado | objeto próprio, com `count`, `firstTimestamp` e `lastTimestamp` |
| **filtro por namespace** e **busca por nome** | |

#### RF-03 — Distinguir o que sabe do que infere

`ready=true` significa que a readinessProbe passou. Se a aplicação **não tem** probe, isso
significa só que o processo subiu. O dashboard SHALL marcar pod pronto **sem probe
declarada** de forma diferente de pod pronto com probe.

#### RF-04 — Três cenários de falha de ambiente, sem tela branca nem stack trace

1. contexto corrente apontando para cluster que **não responde**
2. **credencial expirada**
3. **permissão negada** para um tipo de recurso enquanto os outros seguem acessíveis — é o
   caso de um contexto de leitura restrita

### Restrição

**RE-01 — Só leitura.** Nenhuma operação de escrita: nada de `apply`, `delete` ou `scale`.
**A garantia precisa estar visível no projeto** — código, configuração ou permissões — não
só na intenção de quem escreveu.

### Critérios de aceite

| # | Critério |
|---|---|
| **CA-01** | a tela mostra os seis itens do RF-02 contra o cluster real |
| **CA-02** | `readyReplicas` ausente aparece como `0/N`, não como erro |
| **CA-03** | Service aparece como `prontos/total`: `0/0` quando o selector não casa e `0/3` quando os pods existem e não estão prontos. A chave `subsets` ausente e a chave `endpoints` com `null` não quebram |
| **CA-04** | pod com `CrashLoopBackOff` mostra `OOMKilled` como motivo, mesmo com `phase: Running` |
| **CA-05** | cluster que não responde: mensagem que explica, sem stack trace |
| **CA-06** | credencial expirada: idem, e distinguível de cluster fora |
| **CA-07** | permissão negada em um tipo: os outros continuam na tela, e o negado aparece como negado |
| **CA-08** | nenhum caminho do código executa verbo de escrita |

### Fora de escopo

logs · `exec` · métricas · multicluster · edição de YAML · alerta · histórico
