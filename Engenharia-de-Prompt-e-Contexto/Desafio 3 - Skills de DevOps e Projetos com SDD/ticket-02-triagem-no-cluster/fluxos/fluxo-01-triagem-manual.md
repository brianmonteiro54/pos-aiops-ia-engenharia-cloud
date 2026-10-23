# Fluxo executado: triagem manual dos três chamados

Registro do que eu fiz **antes** de existir skill, com `kubectl` na mão. É daqui que o
método da skill nasce: a ordem em que eu desci as camadas, onde eu precisei cruzar duas
fontes, e onde uma fonte me daria a resposta errada.

Cluster: k3d `metacortex`, k3s v1.31.5. Evidências brutas em `../evidencias/`.

Os três chamados têm o mesmo sintoma para o cliente ("está fora do ar") e causas em
camadas diferentes.

---

## O achado que organiza o método inteiro

Antes dos chamados, a conclusão que eles produziram juntos:

| Fonte | Chamado 1 (OOM) | Chamado 2 (imagem) | Chamado 3 (seletor) |
|---|---|---|---|
| `get pod` (STATUS) | `CrashLoopBackOff` | `ImagePullBackOff` | **`Running`, 1/1** |
| **status do container** | **OOMKilled, exit 137** | `ImagePullBackOff`, `lastState` vazio | ready=True |
| logs | **vazios** | **impossível** (BadRequest) | aplicação responde 200 |
| eventos | só `BackOff` | **`not found`, explícito** | nada relevante |
| `get endpoints` | em branco (pods não prontos) | em branco | **`subsets` AUSENTE** |

Nenhuma fonte resolve os três. **A fonte que resolve muda com a camada onde está a
causa**: e é por isso que a skill precisa de uma ordem, não de uma lista de comandos.

---

## Chamado 1: `nyx-prod`: a API reinicia sozinha

Relato: "a API do kube-news reinicia sozinha, depois de um corte de custos que mudou os
limites de recurso do namespace inteiro de uma vez."

### O que eu vi

```
deployment.apps/nyx-api   0/2   2   0
pod/nyx-api-...-777ht   0/1   CrashLoopBackOff   4 (61s ago)
pod/nyx-api-...-zrwbb   0/1   CrashLoopBackOff   4 (72s ago)
pod/nyx-postgres-...    1/1   Running            0
```

Primeira coisa que importa: **o banco está de pé**. A falha não é do namespace inteiro, é
de um componente.

### O erro que eu quase cometi: ler a fase do pod

```
phase do POD : Running
container    : api  ready=False  restartCount=4
state        : waiting -> reason=CrashLoopBackOff
lastState    : terminated -> reason=OOMKilled  exitCode=137
```

A **fase do pod é `Running`**. Um pod com container em `CrashLoopBackOff` continua
`Running`, porque o estado de falha vive no container e não no pod. Quem filtra por
`status.phase` para achar o que está quebrado **não encontra este caso**.

A causa está em `lastState.terminated.reason`: `OOMKilled`, `exitCode 137`. E está **só**
ali.

### Por que logs e eventos não resolvem

Rodei os dois, e é o achado mais útil do chamado:

```bash
kubectl -n nyx-prod logs -l app=nyx-api --tail=15            # vazio
kubectl -n nyx-prod logs <pod> --previous --tail=15          # vazio
```

**Vazios, nos dois.** `OOMKilled` é `SIGKILL` do kernel: a aplicação não tem chance de
escrever nada. Quem começa a triagem pelos logs (e é por onde metade do plantão começa)
não encontra absolutamente nada e conclui que "não tem erro".

Os eventos são melhores, mas não suficientes:

```
Warning  BackOff  Back-off restarting failed container api in pod nyx-api-...
```

**A palavra `OOMKilled` não aparece em nenhum evento.** `BackOff` é o sintoma de que o
container está reiniciando, não a causa de ele morrer. Quem começa pelos eventos tem o
sintoma e precisa de um segundo passo para chegar na causa.

### O cruzamento que fecha

Com `OOMKilled` na mão, a pergunta vira "quanto de memória ele tem?":

```json
"limits":   {"cpu": "200m", "memory": "24Mi"}
"requests": {"cpu": "50m",  "memory": "16Mi"}
```

24 MiB para um processo Node com Express, Sequelize e `prom-client` carregados. O
interpretador sozinho passa disso. **Causa identificada, e a triagem acabou**: o conserto
é decisão de quem opera, não da triagem.

O relato do cliente confirma o mecanismo: "um corte de custos que mudou os limites do
namespace inteiro de uma vez". Mudança em lote, sem medir consumo por workload.

### Ordem que funcionou

retrato do namespace → **status do container** → cruzar com `resources` → eventos como
confirmação. **Logs não entram neste caminho.**

---

## Chamado 2: `orion-stg`: a loja parou depois de uma publicação

Relato: "a tag nova foi anunciada no release e o deploy foi aplicado, mas o pod nunca foi
substituído."

### O que eu vi

```
deployment.apps/orion-web       0/3   3   0
pod/orion-web-...   0/1   ImagePullBackOff   0
pod/orion-postgres-...   1/1   Running   0
```

De novo o banco de pé. E uma diferença do chamado 1 que importa:

```
phase=Pending                      <- nao Running
container web ready=False restartCount=0
state: waiting -> reason=ImagePullBackOff
lastState: vazio, o container NUNCA rodou
imageID real: (vazio)
```

`restartCount=0` e `lastState` vazio. **O container nunca executou.** No chamado 1 ele
executou quatro vezes e morreu; aqui ele nunca chegou a existir. São camadas diferentes, e
o `lastState` é o que distingue as duas em um olhar.

### Aqui os logs nem são vazios: são impossíveis

```
Error from server (BadRequest): container "web" in pod "orion-web-..." is waiting
to start: trying and failing to pull image
```

Não é "nenhuma linha": é o apiserver dizendo que não existe container de onde ler. Mais
informativo que o vazio do chamado 1, e ainda assim não é a causa.

### Aqui os eventos resolvem, e são a melhor fonte

```
Warning  Failed  Failed to pull image "fabricioveronez/fake-shop:v1.14.2":
   rpc error: code = NotFound desc = ... : not found
```

`not found`, explícito, vindo do kubelet. **Esta é a única das três causas que aparece
inteira num evento.** É o oposto do chamado 1, e é o que prova que a ordem não pode ser
"sempre comece pelos eventos" nem "sempre comece pelo status".

### A confirmação que eu fiz fora do cluster

O evento diz que a tag não foi encontrada. Isso pode ser tag inexistente, credencial de
registry ausente ou rede. Fui conferir no registry:

```bash
curl -s "https://hub.docker.com/v2/repositories/fabricioveronez/fake-shop/tags?page_size=50"
```

18 tags publicadas: `1`, `latest`, `v1`, `v2`, `v6`…`v26`. **Nenhuma com ponto, e
`v1.14.2` não existe.** O registry é público, então não é credencial.

Causa: a tag anunciada no release nunca foi publicada. O deploy referenciou uma imagem que
não existe, e por isso o pod novo nunca subiu, e, no incidente real, o ReplicaSet antigo é
que seguia servindo.

### Limitação honesta da reprodução

No laboratório o Deployment foi **criado** já na tag ruim: `generation 1`,
`observedGeneration 1`, um único ReplicaSet, `rollout history` com uma revisão. Não existe
ReplicaSet antigo.

No incidente descrito existiria, e o sintoma seria diferente: a loja continuaria servindo
a versão velha, e o chamado seria "a versão nova não entrou". Aqui são 0 de 3 pods prontos
e a loja está de fato fora. **O ambiente reproduz o estado final, não a história.** Para a
triagem isso muda um passo: num rollout travado de verdade, `rollout status` e
`get rs` dizem quantas réplicas de cada versão existem, e é por ali que se mede o quanto o
cliente está sendo afetado.

### Ordem que funcionou

retrato → status do container (`lastState` vazio distingue de crash) → **eventos** →
confirmação fora do cluster, no registry.

---

## Chamado 3: `nyx-stg`: 503 de fora, aplicação de pé

Relato: "o kube-news responde 503 para quem chama de fora. A aplicação está de pé e
saudável, e mesmo assim ninguém chega nela."

### O que eu vi, e por que é o mais perigoso dos três

```
deployment.apps/nyx-api   2/2   2   2
pod/nyx-api-...-h98pj   1/1   Running   2 (5m8s ago)
pod/nyx-api-...-rl2d2   1/1   Running   2 (5m7s ago)
```

**Tudo verde.** 2/2 prontas, `Running`, `ready=True`. Nenhuma das fontes dos chamados 1 e 2
aponta nada: o status do container está são, os logs não têm erro, e os eventos não trazem
nada relevante.

Uma triagem que só desce na camada do pod **conclui que não há problema**: e o cliente
está recebendo 503.

### A armadilha de verdade: um restart já curado

```
nyx-api-...-h98pj: ready=True restarts=2
   lastState: terminated reason=Error exitCode=1
```

Dois restarts, com `exitCode 1`. Isso é real e **não tem nada a ver com o chamado**: a
aplicação subiu antes do Postgres aceitar conexão, morreu duas vezes e recuperou. O
`lastState` guarda uma falha que **já passou**.

Quem ancora no contador de restart passa a investigar conexão de banco, que está
funcionando. É o caso em que `lastState` (a fonte que resolveu o chamado 1) **engana**.

A distinção que separa os dois casos: no chamado 1 o `state` **atual** é `waiting` com
`CrashLoopBackOff`; aqui o `state` atual é `running` e o `lastState` é histórico. Falha
viva mora em `state`; falha curada mora em `lastState`.

### A pergunta que resolve

Pods prontos e cliente sem resposta aponta para a camada de rede. A pergunta é "o Service
tem endpoint?":

```
campo subsets: AUSENTE, o campo nao vem, nao vem vazio
```

E no `EndpointSlice`, que é o substituto moderno:

```
slice nyx-api-wszq8: endpoints=AUSENTE
```

O objeto `Endpoints` existe e o campo `subsets` **não aparece na resposta da API**: não vem
como lista vazia. Código que faz `len(ep["subsets"])` quebra com `KeyError` em vez de
reportar "sem endpoint". Está no Bloco 4.6 do padrão de manifests, e eu confirmei aqui.

### O cruzamento que fecha

```
selector do Service  : {"app": "nyx-api"}
labels do pod        : {"app": "nyxapi", "pod-template-hash": "5cd5cdbf9d"}
matchLabels do deploy: {"app": "nyxapi"}
```

**Um hífen.** E o detalhe que importa para o conserto: o `matchLabels` do Deployment é
`app: nyxapi` e casa com o pod. **O Deployment está correto.** Quem está errado é só o
`selector` do Service.

Confirmação pelos dois lados:

```bash
kubectl -n nyx-stg get pod -l app=nyx-api
# No resources found in nyx-stg namespace.

kubectl -n nyx-stg exec <pod> -- wget -qO- http://localhost:8080/health
# {"state":"up","machine":"nyx-api-5cd5cdbf9d-h98pj"}
```

O seletor do Service não encontra pod nenhum, e a aplicação responde 200 quando falada
direto. Causa identificada.

### Ordem que funcionou

retrato → status do container (**descartar** a falha curada) → **camada de rede**:
endpoints → cruzar seletor do Service com rótulos do pod → confirmar pelos dois lados.

---

## O que este fluxo ensinou sobre a skill

### 1. A ordem precisa ser derivada do sintoma, não fixa

Três chamados, três fontes diferentes resolvendo:

| Chamado | Fonte que resolveu | Fonte que engana |
|---|---|---|
| 1 | status do container (`lastState`) | logs (vazios), eventos (só o sintoma) |
| 2 | eventos (`not found`) | logs (impossíveis) |
| 3 | endpoints + seletor | status do container (`lastState` de falha curada) |

Uma skill que diga "comece pelos logs" falha em dois de três. Uma que diga "comece pelos
eventos" falha em dois de três. O que funciona é **derivar a camada a partir do sintoma
relatado** e descer dali.

### 2. O sintoma do cliente mapeia para uma camada

- "reinicia sozinho", "fica de pé e cai" → camada do **container**
- "a versão nova não entrou", "não sobe" → camada da **imagem e do rollout**
- "está de pé mas ninguém chega" → camada de **rede**

É o primeiro galho da árvore, e vem da frase do chamado, não de um comando.

### 3. Três distinções que o relatório precisa fazer, e que eu quase errei

- **fase do pod x estado do container.** Pod `Running` com container morrendo. Filtrar por
  fase perde o chamado 1.
- **`state` x `lastState`.** Falha viva mora em `state`; falha curada mora em `lastState`.
  Confundir os dois faz perseguir problema que já passou: chamado 3.
- **seletor do Deployment x seletor do Service.** São dois objetos, dois erros, dois
  consertos. No chamado 3 só um dos dois estava errado.

### 4. "Cruzar duas fontes" tem um gatilho concreto

Não é "cruze sempre". Nos três casos o gatilho foi o mesmo: **a primeira fonte deu um
sintoma em vez de uma causa.** `BackOff` não explica por que o container morre; `Running`
não explica por que o cliente recebe 503. Quando a resposta é sintoma, cruze. Quando é
causa, pare.

### 5. Parar é parte do método

Nos três casos eu identifiquei a causa e **não consertei**. No chamado 1 o conserto é
medir consumo e subir o limite; no 2 é publicar a tag ou apontar para uma que existe; no 3
é trocar um caractere no seletor. Nenhum dos três é decisão da triagem, e dois deles
exigem saber coisas que a triagem não tem: o orçamento do cliente e o que o release
pretendia entregar.

### 6. Componente são ao lado do quebrado é a norma

Nos três chamados o Postgres estava `Running` e saudável. Um relatório que diz "o
namespace está com problema" é inútil; o que serve é "o `orion-web` não sobe e o
`orion-postgres` está de pé".
