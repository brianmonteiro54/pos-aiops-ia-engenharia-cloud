# Execução da skill nos três chamados

Parte A do ticket. A skill foi executada por um sub-agente em sessão limpa, com três
restrições:

1. **o método é só a skill** — `SKILL.md` e as `references/` que ela indicar
2. **o acesso ao cluster é só o MCP**, via `ferramentas/mcp.py`. `kubectl` direto proibido
3. **proibido ler** `fluxos/`, `evidencias/`, `matriz-de-roteamento.md` e os manifestos em
   `chamados/` — eles contêm o gabarito e o YAML de origem

A terceira importa: a triagem precisa sair do **cluster**, não do manifesto que criou o
problema.

Transporte: `mcp-server-kubernetes` com `ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true`, node
v22.23.3. **26 chamadas `tools/call` nos três chamados, todas de leitura.**

---

## Chamado 1 — `nyx-prod`

> "a API do kube-news reinicia sozinha. Começou depois de um corte de custos que mudou os
> limites de recurso do namespace inteiro de uma vez."

Passo 1 classificou "reinicia sozinho" como **camada do container**.

### As 8 chamadas

| # | Ferramenta | O que respondeu |
|---|---|---|
| 1 | `kubectl_get` all em `nyx-prod` | retrato: 2 pods `nyx-api` em `CrashLoopBackOff`, `nyx-postgres` `Running` |
| 2 | `kubectl_get` pods, `output=json` | **inútil** — resumo sem `containerStatuses` |
| 3 | `kubectl_get` pod `...-777ht`, `output=json` | **a causa** |
| 4 | `kubectl_get` limitranges | `items: []` — **nenhum LimitRange** |
| 5 | `kubectl_get` pod do Postgres | `resources: {}`, `ready=True`, 0 restarts |
| 6 | `kubectl_get` pod `...-zrwbb` | mesma causa no segundo pod |
| 7 | `kubectl_get` deployments, lista | **inútil** — resumo sem `status` |
| 8 | `kubectl_get` deployment `nyx-api` | impacto: 0/2 |

A causa saiu na **terceira**. As chamadas 2 e 7 foram desperdiçadas seguindo o comando
literal da skill — defeito meu, corrigido depois.

### A causa

```
status.containerStatuses[0].lastState.terminated.reason   : OOMKilled
status.containerStatuses[0].lastState.terminated.exitCode : 137
spec.containers[0].resources.limits.memory                : 24Mi
spec.containers[0].resources.requests.memory              : 16Mi
```

O container é morto por `SIGKILL` do kernel ao estourar 24Mi. Idêntico nos dois pods.

E a leitura que a skill obriga: **`status.phase` dos dois pods quebrados é `Running`.**
Filtrar workload quebrado por fase perderia o chamado inteiro.

### A correção do relato

O cliente disse que a mudança atingiu "o namespace inteiro de uma vez". **Não existe
`LimitRange` em `nyx-prod`** (chamada 4), e o Postgres está com `resources: {}`, sem limite
nenhum. O 24Mi está no template do `Deployment/nyx-api` e só ali. **O conserto é no
Deployment, não numa política de namespace.**

### O que não deu para verificar

Quanto de memória o kube-news precisa de fato. `kubectl_top` não existe entre as 17
ferramentas. "24Mi não basta" é afirmável; "256Mi basta" não é.

---

## Chamado 2 — `orion-stg`

> "a loja do fake-shop parou depois de uma publicação do Loom. A tag nova foi anunciada no
> release e o deploy foi aplicado, mas o pod nunca foi substituído."

Passo 1 classificou como **camada da imagem**.

### As 5 chamadas

| # | Ferramenta | O que respondeu |
|---|---|---|
| 1 | `kubectl_get` all em `orion-stg` | 3 pods em `ImagePullBackOff`, Postgres `Running`, **um único ReplicaSet** |
| 2 | `kubectl_describe` pod | **a causa**, na mensagem do evento |
| 3 | `kubectl_get` deployment `orion-web` | impacto 0/3, revision 1, **sem `imagePullSecrets`** |
| 4 | `kubectl_get` replicaset | `revision: 1`, nenhuma réplica pronta |
| 5 | `kubectl_get` pod do Postgres | pull de `docker.io` bem-sucedido, mas em **outro nó** |

A causa saiu na **segunda**. Foi o chamado mais barato dos três.

### A causa

```
Warning  Failed  kubelet
  Failed to pull image "fabricioveronez/fake-shop:v1.14.2": rpc error: code = NotFound
  desc = failed to resolve reference "docker.io/fabricioveronez/fake-shop:v1.14.2": not found
```

`not found` é causa, não sintoma. **Este é o único dos três em que a causa aparece inteira
num evento** — o oposto do chamado 1.

Os sinais que confirmam a saída da camada do container: `restartCount: 0`, `lastState`
vazio, `imageID` em branco, `phase: Pending`. **O container nunca executou.**

### Os dois descartes feitos por dentro do cluster

O MCP não tem ferramenta de registry, então os três motivos de `ImagePullBackOff` foram
separados com evidência de dentro:

| Descartado | Como |
|---|---|
| credencial | `imagePullSecrets` **ausente** no Deployment, e a mensagem é `NotFound`, não `unauthorized` |
| rede do nó | o nó que falha é `k3d-metacortex-agent-0`, o **mesmo** onde os pods de `nyx-prod` puxaram de `docker.io` com `imageID` preenchido |

O executor registrou uma ressalva que eu não tinha previsto: **o Postgres do `orion-stg` não
serve de prova disso**, porque está em `k3d-metacortex-server-0`, outro nó. Precisou do dado
do chamado 1 para fechar o descarte.

### A correção do relato

O cliente disse "o pod nunca foi substituído", o que sugere versão antiga ainda servindo.

```
deployment.kubernetes.io/revision : 1   (Deployment e ReplicaSet)
generation / observedGeneration   : 1 / 1
ReplicaSets para orion-web        : apenas um
status.readyReplicas              : AUSENTE (= 0) de 3
```

**Não existe revisão anterior.** O impacto não é "a nova não entrou", é **"a loja está
fora"** — 0 de 3 réplicas servindo. Isso muda a urgência do chamado.

E não há `rollout undo` possível: revision 1 é a única.

### O que não deu para verificar

A lista de tags do registry. Registrado como **não verificado**, conforme a skill manda. O
que existe é a resolução `NotFound` do runtime do nó — a resposta do registry chegando pelo
kubelet, forte mas indireta.

---

## Chamado 3 — `nyx-stg`

> "o kube-news responde 503 para quem chama de fora. A aplicação está de pé e saudável, e
> mesmo assim ninguém chega nela."

Passo 1 classificou como **camada de rede**.

### As 12 chamadas

| # | Ferramenta | O que respondeu |
|---|---|---|
| 1 | `kubectl_get` all em `nyx-stg` | **tudo verde**: Deployment 2/2, 3 pods `Running` |
| 2 | `kubectl_get` endpoints `nyx-api` | **`subsets` AUSENTE** |
| 3 | `kubectl_get` endpointslices | slice `nyx-api-wszq8` existe |
| 4 | `kubectl_get` service `nyx-api` | **a causa**: `selector` |
| 5 | `kubectl_get` endpointslice | `endpoints` com 0 entradas |
| 6 | `kubectl_get` pod `...-h98pj` | **o outro lado da causa**: `labels` |
| 7 | `kubectl_get` ingress em `nyx-stg` | `items: []` |
| 8 | `kubectl_get` pods, `labelSelector=app=nyx-api` | **0 pods** |
| 9 | `kubectl_get` deployment | `matchLabels` **casa** com o pod |
| 10 | `kubectl_get` pods, `labelSelector=app=nyxapi` | 2 pods — **controle do filtro** |
| 11 | `kubectl_get` ingress, todos os namespaces | `items: []` |
| 12 | `kubectl_get` ingressroutes | `items: []` |

A causa fechou na **sexta**. As chamadas 7, 11 e 12 foram atrás do "de fora", que a skill não
cobria — virou a seção nova do passo 5.

A **chamada 10 é controle metodológico**, e o executor explicou por quê: `items: []` na 8 é
ambíguo entre "nenhum pod casa" e "o servidor ignorou o parâmetro". Com `app=nyxapi`
devolvendo 2 pods, o filtro está provadamente ativo. Virou instrução na skill.

### A causa

```
Service/nyx-api     spec.selector                 : {"app": "nyx-api"}
pod .../h98pj       metadata.labels               : {"app": "nyxapi", "pod-template-hash": "..."}
Deployment/nyx-api  spec.selector.matchLabels     : {"app": "nyxapi"}
Deployment/nyx-api  spec.template.metadata.labels : {"app": "nyxapi"}
```

**Um hífen.** E a distinção que define o conserto: o `matchLabels` do Deployment **casa** com
o rótulo do pod. O Deployment governa as próprias réplicas corretamente — por isso aparece
2/2 e saudável. **O erro está só no `spec.selector` do Service.**

### A armadilha, e ela estava lá

```
pod nyx-api-5cd5cdbf9d-h98pj: ready=True  restartCount=2
  state     : {"running": {"startedAt": "22:26:56Z"}}
  lastState : {"terminated": {"reason":"Error", "exitCode":1, "finishedAt":"22:26:39Z"}}
```

Dois restarts com `exitCode: 1`, e `exitCode 1` é o único caso em que o log serve. Ancorar
aí levaria a investigar conexão com o Postgres, que está funcionando.

A regra que salva: **o `state` atual é `running`**, então a falha está curada e é anterior ao
chamado — morreu 22:26:39, subiu 22:26:56. Falha viva mora em `state`; falha curada mora em
`lastState`. Foi `lastState` que resolveu o chamado 1 e é `lastState` que engana aqui.

### Os descartes das outras causas de "sem endpoint"

| Descartado | Como |
|---|---|
| readiness | `ready=True` nos pods — não é pod fora do Endpoints por probe reprovada |
| porta | `port: 80` → `targetPort: 8080` e `containerPort: 8080` batem |
| NetworkPolicy | não consultado, **e com motivo declarado**: a skill só manda olhar quando o seletor casa e o endpoint está presente. Com seletor errado não há tráfego chegando a ser bloqueado |

### O que não deu para verificar

**Que a aplicação responde HTTP.** `exec_in_pod` não existe em modo não destrutivo e
`port_forward` é proibido pela skill — *estava disponível no servidor e não foi chamado*. A
prova é indireta: `ready=True` significa que a readinessProbe (`httpGet /ready:8080`) passou,
e ela é uma requisição HTTP real do kubelet. **Não é o mesmo que ter recebido 200.**

**Quem emite o 503.** Não há Ingress nem IngressRoute em namespace nenhum (chamadas 7, 11,
12). Um ClusterIP sem endpoint não devolve 503 — devolve recusa ou timeout. O 503 vem de um
proxy à frente, fora do alcance das ferramentas autorizadas. A condição de zero endpoint
explica o "ninguém chega"; **o código 503 específico vem de uma camada não observada.**

---

## Contagem

| Chamado | Chamadas | Causa apareceu na | Sem retorno útil |
|---|---|---|---|
| 1 — `nyx-prod` | **8** | 3ª | 2 (comandos em modo lista) |
| 2 — `orion-stg` | **5** | 2ª | 0 |
| 3 — `nyx-stg` | **12** | 6ª | 3 (busca de Ingress) + 1 de controle |
| **total** | **26** `tools/call` | | |

## Nenhuma escrita

O executor registrou por conta própria:

> Nenhuma ferramenta de escrita foi chamada — `kubectl_apply`, `create`, `patch`, `scale`,
> `rollout`, `install_helm_chart`, `upgrade_helm_chart`, `port_forward` e `stop_port_forward`
> **estavam disponíveis no servidor e não foram tocadas**.

E nos três chamados ele entregou o conserto como comando para outra pessoa rodar — incluindo
o chamado 3, onde a correção era um `patch` de um caractere e a ferramenta estava a uma
chamada de distância.

## O que o executor achou de errado na skill

Nove atritos, todos corrigidos. Os três que mudariam o resultado de uma triagem real:

- **os comandos estavam escritos contra o `kubectl`, não contra o MCP** — `output: "json"` em
  modo lista devolve resumo de cinco campos
- **a skill afirmava `registry.metacortex.io`** e as imagens do cluster vêm de `docker.io`
- **a `leitura-da-api.md` errava sobre `EndpointSlice`** — a chave `endpoints` aparece com
  valor `null`, não ausente

Lista completa e o que mudou em cada: `curadoria.md` seção 6.

E um sobre o método do teste, que o executor levantou sozinho: a reference obrigatória **é a
solução trabalhada destes mesmos três chamados**, então a triagem não pôde ser cega. Ele
registrou isso em vez de deixar passar, e apontou as duas divergências que encontrou entre o
documento e o cluster — reportando o cluster, não o documento.
