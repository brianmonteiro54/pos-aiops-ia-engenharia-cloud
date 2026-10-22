---
name: triagem-de-cluster-metacortex
description: >-
  Triagem de cluster Kubernetes na Metacortex, via MCP em modo não destrutivo. O limite é a
  fonte da verdade: esta skill lê o ESTADO DO CLUSTER, nunca decide por arquivo YAML. Use
  quando algo está quebrado agora: pod que não sobe, não subiu ou reinicia sozinho,
  CrashLoopBackOff, OOMKilled, ImagePullBackOff, Deployment 0/3 ou que não fica pronto,
  Service sem endpoint, 503 ou timeout de fora, "subiu mas não responde", "está fora do
  ar", rollout travado, alerta de plantão. Cobre o apply que falha por motivo de cluster:
  RBAC, quota, contexto errado, cluster inalcançável. NÃO use para revisar nem escrever
  manifesto, nem para "está no padrão da casa?" — é o padrão de manifests, outra skill. Nem
  para explicar conceito de Kubernetes. Se o erro do apply for desconhecido, peça a
  mensagem antes de rotear. A triagem SÓ LÊ: identifica a causa e para, nunca aplica
  correção, nem quando a ferramenta permite.
compatibility: >-
  Requer o mcp-server-kubernetes com ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true e um kubeconfig
  apontando para o cluster a investigar. ATENÇÃO: o modo não destrutivo NÃO é somente
  leitura — ele mantém kubectl_apply, create, patch, scale, rollout e os Helm
  install/upgrade disponíveis. A garantia de só leitura é desta skill, não da ferramenta.
metadata:
  autor: brian-monteiro
  versao: "1.0"
  mcp: mcp-server-kubernetes
---

# Triagem de cluster — método da Metacortex

Antes deste método, cada plantonista começava por um lugar diferente: um pelos logs, outro
pelos eventos. Os dois caminhos funcionam em parte dos chamados e falham no resto —
medido, não suposto. Ver `references/por-que-a-ordem-importa.md`.

## O limite, antes do método

**Esta skill só lê o cluster.** Identificada a causa, a triagem acabou. Nenhuma correção é
aplicada, **nem quando a ferramenta permite** — e ela permite.

As únicas ferramentas que você pode usar:

| Permitida | Para quê |
|---|---|
| `kubectl_get` | o estado dos objetos |
| `kubectl_describe` | eventos do objeto e detalhe que o `get` não traz |
| `kubectl_logs` | saída da aplicação, inclusive `--previous` |
| `list_api_resources`, `explain_resource` | descobrir o que existe no cluster |
| `ping` | confirmar que há conexão |

**Proibidas, mesmo estando disponíveis no servidor MCP:** `kubectl_apply`,
`kubectl_create`, `kubectl_patch`, `kubectl_scale`, `kubectl_rollout`,
`install_helm_chart`, `upgrade_helm_chart`, `port_forward`.

O modo não destrutivo remove `kubectl_delete`, `kubectl_generic`, `exec_in_pod`,
`cleanup`, `node_management` e `uninstall_helm_chart` — e deixa as sete primeiras da lista
acima, que **escrevem no cluster**. Se você sentir vontade de rodar `kubectl_patch` para
subir um limite de memória, é sinal de que a triagem já acabou: a causa está identificada e
o conserto é de outra pessoa, com outro contexto.

Também não use `port_forward`: ele não altera objeto, mas abre túnel para dentro do cluster
e não responde nenhuma pergunta de triagem que `get` e `describe` não respondam.

## Passo 1 — do sintoma para a camada

**Não comece por um comando. Comece pela frase do chamado.** Ela diz em que camada a causa
provavelmente está, e é o primeiro galho:

| O que o cliente ou o alerta diz | Camada | Vá para |
|---|---|---|
| "reinicia sozinho", "fica de pé e cai", `CrashLoopBackOff`, `OOMKilled` | **container** | passo 3 |
| "não sobe", "a versão nova não entrou", `ImagePullBackOff`, `Pending`, rollout travado | **imagem e agendamento** | passo 4 |
| "está de pé mas ninguém chega", 503, timeout, "subiu mas não responde" | **rede** | passo 5 |
| sintoma vago, "está fora do ar", ou nenhum dos acima | — | passo 2 e deixe o retrato decidir |

Se o sintoma não disser a camada, o passo 2 diz.

## Passo 2 — o retrato do namespace, sempre

```
kubectl_get  resourceType=all  namespace=<ns>
```

Uma chamada, e ela responde três coisas:

1. **O que está quebrado e o que não está.** Em todo chamado real há componente saudável ao
   lado do quebrado. Relatório que diz "o namespace está com problema" é inútil; o que
   serve é "o `orion-web` não sobe e o `orion-postgres` está de pé".
2. **A camada**, quando o sintoma não disse.
3. **O recorte do resto da triagem** — qual workload investigar.

Se o namespace não foi informado, `kubectl_get resourceType=namespaces` primeiro. Namespace
da Metacortex é `<cliente>-<ambiente>`, então "o nyx de produção" é `nyx-prod`.

## Passo 3 — camada do container

```
kubectl_get  resourceType=pods  namespace=<ns>  output=json
```

E leia **o status do container**, não a fase do pod. Três distinções que decidem o caso:

### Fase do pod não é estado do container

Um pod com container em `CrashLoopBackOff` tem `status.phase: Running`. **Filtrar por fase
perde o caso inteiro.** O que vale é `status.containerStatuses[].state` e `.lastState`.

### `state` é a falha viva; `lastState` é a falha que já passou

| Onde olhar | O que significa |
|---|---|
| `state.waiting.reason` | por que o container **não está rodando agora** |
| `state.running` + `lastState.terminated` | está rodando, e **já morreu antes** — pode não ter relação com o chamado |
| `lastState.terminated.reason` | por que a encarnação anterior morreu. `OOMKilled`, `Error`, `Completed` |
| `lastState.terminated.exitCode` | `137` = SIGKILL (típico de OOM), `1` = erro da aplicação |

**Container `ready=True` com `restartCount` alto é armadilha.** A falha pode ter sido
curada — aplicação que subiu antes do banco, morreu duas vezes e recuperou. Se o `state`
atual é `running`, o `lastState` é história e provavelmente não é o seu chamado.

### `lastState` vazio com `restartCount: 0` significa que o container nunca rodou

Aí não é problema de container — é imagem ou agendamento. Vá para o passo 4.

### Então cruze

Com o `reason` na mão, a próxima fonte depende dele:

| `reason` | Cruze com | Por quê |
|---|---|---|
| `OOMKilled` | `resources.limits.memory` do workload | é a comparação que fecha o caso |
| `Error` com exitCode da aplicação | **logs**, inclusive `--previous` | aqui o log serve |
| `CreateContainerConfigError` | `env`, `envFrom`, Secret e ConfigMap referenciados | referência a objeto que não existe |

**`OOMKilled` não aparece no log nem no evento.** O log fica vazio, porque `SIGKILL` não dá
chance de escrever; o evento diz `BackOff`, que é o sintoma de reiniciar e não a causa de
morrer. Não perca tempo procurando ali.

## Passo 4 — camada da imagem e do agendamento

Sinal: `state.waiting.reason` em `ImagePullBackOff`, `ErrImagePull` ou `CreateContainerError`,
ou pod em `Pending` sem container nenhum iniciado.

```
kubectl_describe  resourceType=pod  name=<pod>  namespace=<ns>
```

**Aqui o evento é a melhor fonte, e normalmente a única que traz a causa inteira.** O
kubelet escreve a mensagem crua do runtime:

```
Failed to pull image "...:v1.14.2": rpc error: code = NotFound
  desc = failed to resolve reference ... : not found
```

`not found` é causa, não sintoma. Separe os três motivos que produzem o mesmo
`ImagePullBackOff`:

| Mensagem do evento | Causa |
|---|---|
| `not found`, `manifest unknown` | **a tag não existe** no registry |
| `unauthorized`, `authentication required` | credencial de registry ausente ou errada |
| `dial tcp`, `i/o timeout` | rede do nó até o registry |

Para o primeiro caso, confirme fora do cluster: a tag existe no registry? Na Metacortex
toda imagem vem de `registry.metacortex.io`, publicada pelo **Loom** — uma tag anunciada
num release e nunca publicada é causa recorrente.

**Pod `Pending` sem evento de imagem** é agendamento, não imagem. Aí o `describe` traz
`FailedScheduling` com o motivo: recurso insuficiente, `nodeSelector` sem nó, taint sem
toleration.

### Rollout travado

Quando o relato é "a versão nova não entrou", meça **quanto o cliente está sendo afetado**:

```
kubectl_get  resourceType=deployments  namespace=<ns>  output=json
kubectl_get  resourceType=replicasets  namespace=<ns>
```

- `spec.replicas` x `status.readyReplicas` — quantas servem de fato
- `status.unavailableReplicas` e `conditions[].reason` (`MinimumReplicasUnavailable`,
  `ProgressDeadlineExceeded`)
- **os ReplicaSets dizem a história**: se o antigo ainda tem pods prontos, a versão velha
  segue servindo e o impacto é "não entrou"; se nenhum tem, o impacto é "está fora"
- `metadata.generation` x `status.observedGeneration`: divergente significa que o
  controlador ainda não processou a mudança

**`readyReplicas` não vem quando é zero.** O campo não aparece na resposta da API, não vem
como `0`. Tratar ausência como erro é bug; trate como zero.

## Passo 5 — camada de rede

Sinal: pods prontos, container são, e o cliente sem resposta. **É o caso mais perigoso,
porque as fontes dos passos 3 e 4 não apontam nada** e uma triagem que pare ali conclui que
não há problema.

A pergunta é uma só: **o Service tem endpoint?**

```
kubectl_get  resourceType=endpoints  name=<svc>  namespace=<ns>  output=json
```

**`subsets` ausente significa nenhum endpoint.** O campo não vem como lista vazia — ele não
aparece na resposta. Código que faz `len(ep["subsets"])` quebra com `KeyError` em vez de
reportar "sem endpoint". Confira também o `EndpointSlice`, que é o substituto:

```
kubectl_get  resourceType=endpointslices  namespace=<ns>
```

Sem endpoint, cruze seletor com rótulo — e **distinga os dois seletores**, porque são dois
objetos, dois erros e dois consertos:

| Objeto | Campo | Se estiver errado |
|---|---|---|
| Service | `spec.selector` | o Service sobe saudável e **nunca** entrega tráfego |
| Deployment | `spec.selector.matchLabels` | o controlador não governa os próprios pods |

```
kubectl_get  resourceType=services    name=<svc>  namespace=<ns>  output=json
kubectl_get  resourceType=pods        namespace=<ns>  output=json
```

Compare `service.spec.selector` com `pod.metadata.labels` **caractere por caractere**. Um
hífen de diferença é a causa mais comum do parque. Confirme pelos dois lados: um
`kubectl_get` de pods filtrando pelo seletor do Service deve devolver **nenhum** pod.

Se o seletor casa e ainda não há endpoint, desça para:

- **porta**: `service.spec.ports[].targetPort` x `containerPort` do pod. `port` é onde o
  Service escuta; `targetPort` é onde o container escuta, e normalmente são diferentes
- **readiness**: pod `ready=False` não entra no Endpoints mesmo com seletor correto. Aí o
  caso volta para o passo 3
- **NetworkPolicy**: `kubectl_get resourceType=networkpolicies` — seletor certo e endpoint
  presente, mas tráfego bloqueado

### O que você não pode fazer aqui

Na triagem manual eu confirmei que a aplicação respondia com `kubectl exec ... wget
localhost:8080/health`. **`exec_in_pod` não existe em modo não destrutivo**, e
`port_forward` é proibido por esta skill. Então a prova de que a aplicação responde é
indireta: `ready=True` significa que a readinessProbe passou, e a readinessProbe é uma
requisição HTTP real feita pelo kubelet. Diga isso no relatório em vez de afirmar que
testou o endpoint.

## Passo 6 — quando parar, e o que entregar

**Pare quando tiver a causa.** Causa é a afirmação que, se revertida, resolve o chamado:
"o limite de memória é 24Mi e o processo precisa de mais" é causa. "O container está em
`CrashLoopBackOff`" é sintoma — é o que o cliente já sabia.

Teste: se a próxima pergunta for "e por que isso?", você ainda está no sintoma.

O relatório tem cinco partes:

1. **O que está quebrado e o que não está**, por objeto. Nomeie os dois.
2. **A causa**, com o campo exato onde ela aparece — `lastState.terminated.reason`,
   `spec.selector`, a mensagem do evento.
3. **Como o sintoma do cliente se liga à causa.** É o que faz o relatório ser lido.
4. **O que você não conseguiu verificar**, e por quê. `exec_in_pod` indisponível conta.
5. **O conserto, como recomendação e não como ação.** Quem decide tem contexto que a
   triagem não tem — orçamento do cliente, o que o release pretendia entregar.

Nada de aplicar o conserto. Se perguntarem "pode arrumar?", a resposta é o comando que a
pessoa roda, não a execução dele.

## Referências

- `references/por-que-a-ordem-importa.md` — a medição dos três chamados que produziu esta
  ordem, com a tabela de qual fonte resolve e qual engana em cada camada. Consulte quando
  alguém propuser "sempre comece pelos logs".
- `references/leitura-da-api.md` — os campos que o Kubernetes **não devolve** quando são
  vazios, e os que mudam de lugar entre pod e container. Consulte ao escrever código ou ao
  interpretar JSON cru.
