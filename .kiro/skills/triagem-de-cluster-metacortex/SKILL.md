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
pelos eventos. Os dois caminhos funcionam em parte dos chamados e falham no resto — medido,
não suposto.

> **Não leia as `references/` para triar.** Elas não são passo do método: a de cobertura
> contém a **solução trabalhada** de três chamados específicos, com namespace, causa e valor.
> Lida antes de uma triagem desses mesmos casos, ela entrega a resposta e você para de
> investigar. Consulte-as quando alguém **contestar** o método, ou quando precisar da regra
> exata de leitura de um campo da API. O método do corpo é autossuficiente.

## O limite, antes do método

**Esta skill só lê o cluster.** Identificada a causa, a triagem acabou. Nenhuma correção é
aplicada, **nem quando a ferramenta permite** — e ela permite.

O servidor expõe **17 ferramentas** em modo não destrutivo. A lista abaixo classifica
**todas as 17** — se aparecer uma que não está aqui, o servidor mudou de versão e a lista
precisa ser revista antes de você usá-la.

| Permitidas (5) | Para quê |
|---|---|
| `kubectl_get` | o estado dos objetos |
| `kubectl_describe` | **eventos** do objeto e detalhe que o `get` não traz |
| `kubectl_logs` | saída da aplicação, inclusive a encarnação anterior |
| `list_api_resources` | descobrir que tipos existem neste cluster |
| `explain_resource` | o schema de um tipo |

| Proibidas (12) | Por quê |
|---|---|
| `kubectl_apply`, `kubectl_create`, `kubectl_patch`, `kubectl_scale`, `kubectl_rollout` | **escrevem no cluster** |
| `install_helm_chart`, `upgrade_helm_chart` | **escrevem no cluster** |
| `port_forward`, `stop_port_forward` | abrem túnel para dentro do cluster e não respondem nada que `get` e `describe` não respondam |
| `kubectl_context` | **troca o cluster-alvo.** Triagem no cluster errado é pior que nenhuma |
| `kubectl_reconnect` | muda estado do cliente; se a conexão caiu, isso é achado, não coisa a consertar |
| `ping` | retorna conteúdo vazio com código 0. Sucesso em branco é indistinguível de no-op — não informa nada |

O modo não destrutivo remove `kubectl_delete`, `kubectl_generic`, `exec_in_pod`,
`cleanup`, `node_management` e `uninstall_helm_chart`. **E deixa sete que escrevem.** Se
você sentir vontade de rodar `kubectl_patch` para subir um limite de memória, é sinal de que
a triagem já acabou: a causa está identificada e o conserto é de outra pessoa, com outro
contexto.

## Passo 1 — do sintoma para a camada

**Não comece por um comando. Comece pela frase do chamado.** Ela diz em que camada a causa
provavelmente está, e é o primeiro galho:

| O que o cliente ou o alerta diz | Camada | Vá para |
|---|---|---|
| "reinicia sozinho", "fica de pé e cai", `CrashLoopBackOff`, `OOMKilled` | **container** | passo 3 |
| "não sobe", "a versão nova não entrou", `ImagePullBackOff`, `Pending`, rollout travado | **imagem e agendamento** | passo 4 |
| "está de pé mas ninguém chega", 503, timeout, "subiu mas não responde" | **rede** | passo 5 |
| sintoma vago, "está fora do ar", ou nenhum dos acima | — | deixe o retrato do passo 2 decidir |

**O passo 2 é sempre o primeiro comando, qualquer que seja a camada.** A tabela acima diz
para onde ir *depois* dele, não que ele pode ser pulado — é do retrato que saem os nomes
dos objetos que os passos seguintes precisam.

## Regra de leitura do MCP, antes de qualquer comando

**`output: "json"` em modo LISTA devolve resumo, não o objeto da API.** Medido neste
servidor:

```
kubectl_get {"resourceType":"pods","namespace":"nyx-prod","output":"json"}
  -> cada item traz so: name, namespace, kind, status, createdAt

kubectl_get {"resourceType":"pod","name":"<nome>","namespace":"nyx-prod","output":"json"}
  -> objeto cru: apiVersion, kind, metadata, spec, status
     e e aqui que vive status.containerStatuses[].lastState
```

Então o padrão de uso é **dois passos**: a lista para descobrir os nomes, o singular com
`name` para ler o objeto. Pedir `output: json` numa lista e esperar `containerStatuses`
desperdiça uma chamada — foi o erro mais caro na primeira execução desta skill.

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
kubectl_get {"resourceType":"pod","name":"<pod-do-retrato>","namespace":"<ns>","output":"json"}
```

**No singular, com `name`** — a lista não traz `containerStatuses`. Os nomes dos pods saem
do retrato do passo 2.

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

**Você consegue descartar dois dos três sem sair do cluster**, e isso importa porque o MCP
não tem ferramenta de registry:

| Descartar | Como, por dentro |
|---|---|
| credencial | `spec.template.spec.imagePullSecrets` ausente **e** mensagem `NotFound` em vez de `unauthorized`. Repositório público não usa credencial |
| rede do nó | procure outro pod **no mesmo nó** que tenha puxado do **mesmo registry** com `imageID` preenchido. Se existe, o nó alcança o registry. Cuidado: pod em outro nó não prova nada |

Sobra a tag inexistente, e a mensagem `not found` do runtime **é a resposta do registry
chegando pelo kubelet** — evidência indireta, mas forte. Se puder confirmar a lista de tags
fora do cluster, confirme; se não, **declare como não verificado** em vez de afirmar.

Qual registry esperar: o padrão da casa é `registry.metacortex.io`, publicado pelo **Loom**.
Mas **confira o que o manifesto de fato usa** — `spec.containers[].image` — antes de
procurar num registry que este workload não consome. Imagem apontando para registry público
é, por si, violação da regra 3.7 do padrão de manifests, e vale registrar no relatório como
achado lateral.

**Pod `Pending` sem evento de imagem** é agendamento, não imagem. Aí o `describe` traz
`FailedScheduling` com o motivo: recurso insuficiente, `nodeSelector` sem nó, taint sem
toleration.

### Rollout travado

Quando o relato é "a versão nova não entrou", meça **quanto o cliente está sendo afetado**:

```
kubectl_get {"resourceType":"deployment","name":"<nome>","namespace":"<ns>","output":"json"}
kubectl_get {"resourceType":"replicasets","namespace":"<ns>"}
```

O Deployment **no singular**, senão `status` não vem.

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

A pergunta é **quantos endpoints prontos o Service tem** — não se ele tem endpoint.

```
kubectl_get {"resourceType":"endpoints","name":"<svc>","namespace":"<ns>","output":"json"}
kubectl_get {"resourceType":"endpointslices","namespace":"<ns>"}
```

> **Correção vinda do Ticket 04.** A versão anterior desta skill perguntava "o Service tem
> endpoint?". A pergunta de sim-ou-não acerta este passo e **erra os passos 3 e 4**, porque
> um Service cujos pods estão em `CrashLoopBackOff` ou `ImagePullBackOff` **tem** endpoints:
> eles existem e não servem. Medido nos quatro estados do cluster de laboratório:
>
> | Sintoma | `Endpoints` | `EndpointSlice` | `len()` responde |
> |---|---|---|---|
> | saudável | `subsets` com `addresses` | 1 endpoint `ready: true` | 1 — certo |
> | **selector não casa** | chave `subsets` **ausente** | chave presente, valor `null` | 0 — certo |
> | **`CrashLoopBackOff`** | `subsets` **presente**, 2 em `notReadyAddresses` | 2 endpoints `ready: false` | **2 — errado** |
> | **`ImagePullBackOff`** | `subsets` **presente**, 3 em `notReadyAddresses` | 3 endpoints `ready: false` | **3 — errado** |
>
> Conte prontos: `conditions.ready` no `EndpointSlice`, ou só `addresses` (nunca
> `notReadyAddresses`) no `Endpoints`. E note que `0/0` e `0/3` contam histórias
> diferentes: o primeiro é selector que não casa, o segundo é pod que existe e não sobe.

**Os dois sinalizam "nenhum endpoint" de formas diferentes**, e nenhuma delas é lista vazia:

| Objeto | Sem endpoint nenhum |
|---|---|
| `Endpoints` | a chave `subsets` **não aparece** na resposta |
| `EndpointSlice` | a chave `endpoints` **aparece com valor `null`** |

Não teste a presença da chave. `len(x.get("endpoints") or [])` funciona nos dois;
`len(x["subsets"])` dá `KeyError` e `len(x.get("endpoints", []))` dá `TypeError`. Detalhe em
`references/leitura-da-api.md`.

Sem endpoint, cruze seletor com rótulo — e **distinga os dois seletores**, porque são dois
objetos, dois erros e dois consertos:

| Objeto | Campo | Se estiver errado |
|---|---|---|
| Service | `spec.selector` | o Service sobe saudável e **nunca** entrega tráfego |
| Deployment | `spec.selector.matchLabels` | o controlador não governa os próprios pods |

```
kubectl_get {"resourceType":"service","name":"<svc>","namespace":"<ns>","output":"json"}
kubectl_get {"resourceType":"pod","name":"<pod>","namespace":"<ns>","output":"json"}
```

Compare `service.spec.selector` com `pod.metadata.labels` **caractere por caractere**. Um
hífen de diferença é a causa mais comum do parque.

Confirme pelos dois lados, com `labelSelector`:

```
kubectl_get {"resourceType":"pods","namespace":"<ns>","labelSelector":"<seletor do Service>"}
   -> deve devolver NENHUM pod

kubectl_get {"resourceType":"pods","namespace":"<ns>","labelSelector":"<rotulo do pod>"}
   -> deve devolver os pods
```

**A segunda chamada não é redundante, é controle.** `items: []` na primeira é ambíguo: pode
ser "nenhum pod casa" ou "o servidor ignorou o parâmetro". Só o contraste prova que o filtro
está ativo e que o vazio é resultado.

Se o seletor casa e ainda não há endpoint, desça para:

- **porta**: `service.spec.ports[].targetPort` x `containerPort` do pod. `port` é onde o
  Service escuta; `targetPort` é onde o container escuta, e normalmente são diferentes
- **readiness**: pod `ready=False` não entra no Endpoints mesmo com seletor correto. Aí o
  caso volta para o passo 3
- **NetworkPolicy**: `kubectl_get resourceType=networkpolicies` — seletor certo e endpoint
  presente, mas tráfego bloqueado

### A borda, quando o sintoma é 503

**Um `ClusterIP` sem endpoint não devolve 503** — ele recusa conexão ou estoura timeout. O
texto 503 vem de um proxy que procurou backend saudável e não achou. Então "503 de fora"
tem duas partes: a **condição** (zero endpoint, que você acabou de achar) e o **tradutor**
(a borda, que transformou isso em 503).

```
kubectl_get {"resourceType":"ingress","allNamespaces":true}
```

Se houver Ingress, o `spec.rules[].backend` diz qual Service a borda procura — e pode ser
outro que não o que você investigou. Se **não** houver nenhum, a borda está fora do alcance
do MCP: balanceador ou reverse proxy externo ao cluster.

Nos dois casos, zero endpoint explica inteiramente o "ninguém chega". **Diga no relatório
que o código 503 específico vem de uma camada que você não enxerga**, em vez de atribuí-lo
ao Service.

### O que você não pode fazer aqui

Na triagem manual que originou esta skill eu confirmei que a aplicação respondia com
`kubectl exec ... wget localhost:8080/health`. **`exec_in_pod` não existe em modo não
destrutivo**, e `port_forward` é proibido por esta skill.

Então a prova de que a aplicação responde é **indireta**: `ready=True` significa que a
readinessProbe passou, e a readinessProbe é uma requisição HTTP real feita pelo kubelet
contra a aplicação. Leia qual endpoint ela usa em
`spec.containers[].readinessProbe.httpGet.path` e cite no relatório.

Não é o mesmo que ter recebido 200 você mesmo. **Diga qual das duas coisas você tem.**

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
  alguém propuser "sempre comece pelos logs". **Contém solução trabalhada: não leia antes de
  triar um caso parecido.**
- `references/leitura-da-api.md` — os campos que o Kubernetes **não devolve** quando são
  vazios, e os que mudam de lugar entre pod e container. Consulte ao escrever código ou ao
  interpretar JSON cru.
