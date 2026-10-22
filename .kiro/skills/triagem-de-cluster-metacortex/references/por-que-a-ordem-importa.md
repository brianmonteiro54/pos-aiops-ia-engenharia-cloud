# Por que a ordem importa

Este arquivo existe para responder duas frases que aparecem em toda discussão de triagem:
**"sempre comece pelos logs"** e **"sempre comece pelos eventos"**. As duas falham em dois
de três chamados reais.

Medido contra três chamados reproduzidos num cluster k3d (k3s v1.31.5). Evidência bruta em
`ticket-02-triagem-no-cluster/evidencias/`.

## A tabela que decidiu o método

| Fonte | Chamado 1 — OOM | Chamado 2 — imagem | Chamado 3 — seletor |
|---|---|---|---|
| `get pod` coluna STATUS | `CrashLoopBackOff` | `ImagePullBackOff` | **`Running`, 1/1** |
| **status do container** | **`OOMKilled`, exit 137** | `ImagePullBackOff`, `lastState` vazio | `ready=True` |
| logs | **vazios** | **impossíveis** (BadRequest) | aplicação responde 200 |
| eventos | só `BackOff` | **`not found`, explícito** | nada relevante |
| endpoints | em branco (pods não prontos) | em branco | **`subsets` ausente** |

Nenhuma linha resolve as três colunas. **A fonte que resolve muda com a camada onde está a
causa** — e é por isso que o método deriva a camada do sintoma em vez de fixar uma ordem de
comandos.

## Chamado 1 — a camada do container

`nyx-prod`, kube-news com `limits: {memory: 24Mi}`. Dois pods em `CrashLoopBackOff`.

**Por que o log não serve.** Rodei nos dois containers, atual e anterior:

```
kubectl logs -l app=nyx-api --tail=15            # vazio
kubectl logs <pod> --previous --tail=15          # vazio
```

`OOMKilled` é `SIGKILL` vindo do kernel. A aplicação não recebe sinal tratável e não tem
chance de escrever nada. Quem começa pelos logs encontra zero linhas e conclui que "não tem
erro no log" — o que é verdade e é inútil.

**Por que o evento não serve.** O único evento relevante:

```
Warning  BackOff  Back-off restarting failed container api in pod nyx-api-...
```

**A palavra `OOMKilled` não aparece em evento nenhum.** `BackOff` descreve o container
reiniciando, que é o sintoma. Quem começa pelos eventos tem o sintoma e precisa de um
segundo passo.

**Onde a causa estava.** Em um lugar só:

```
phase do POD : Running
state        : waiting -> reason=CrashLoopBackOff
lastState    : terminated -> reason=OOMKilled  exitCode=137
```

E repare na primeira linha: **a fase do pod é `Running`**. Quem filtra workload quebrado por
`status.phase` não encontra este chamado.

## Chamado 2 — a camada da imagem

`orion-stg`, fake-shop na tag `v1.14.2`. Três pods em `ImagePullBackOff`.

**Aqui o evento é a melhor fonte e traz a causa inteira:**

```
Failed to pull image "fabricioveronez/fake-shop:v1.14.2": rpc error:
  code = NotFound desc = failed to resolve reference ... : not found
```

`not found` é causa. É o oposto do chamado 1, e é o que prova que nenhuma ordem fixa serve.

**Aqui o log não é vazio — é impossível:**

```
Error from server (BadRequest): container "web" in pod "orion-web-..." is
waiting to start: trying and failing to pull image
```

Não existe container de onde ler. Mais informativo que o vazio do chamado 1, e ainda assim
não é a causa.

**O que distingue esta camada da do container, num olhar:**

| | chamado 1 | chamado 2 |
|---|---|---|
| `phase` | `Running` | `Pending` |
| `restartCount` | 4 | **0** |
| `lastState` | `terminated` | **vazio** |
| `imageID` | preenchido | **vazio** |

`lastState` vazio com `restartCount: 0` significa que o container **nunca executou**. É o
sinal para sair da camada do container.

**A confirmação fora do cluster.** O evento diz `not found`, o que pode ser tag inexistente,
credencial ou rede. Consultei o registry:

```
tags publicadas (18): 1, latest, v1, v11, v12, v13, v14, v15, v16, v17,
                      v19, v2, v20, v26, v6, v7, v8, v9
v1.14.2 existe? NAO
```

Nenhuma tag com ponto. O registry é público, então não é credencial. A tag anunciada no
release nunca foi publicada.

## Chamado 3 — a camada de rede, e a armadilha

`nyx-stg`, kube-news com Service `selector: app: nyx-api` e pods com `app: nyxapi`.

**Tudo verde:**

```
deployment.apps/nyx-api   2/2   2   2
pod/nyx-api-...-h98pj   1/1   Running   2 (5m8s ago)
```

As fontes dos chamados 1 e 2 não apontam nada. Status do container são, logs sem erro,
eventos sem nada relevante. **Uma triagem que só desce na camada do pod conclui que não há
problema** — e o cliente está recebendo 503.

**A armadilha, e é a parte que mais ensina:**

```
nyx-api-...-h98pj: ready=True restarts=2
   lastState: terminated reason=Error exitCode=1
```

Dois restarts com `exitCode 1`. É real e **não tem relação com o chamado**: a aplicação
subiu antes do Postgres aceitar conexão, morreu duas vezes e recuperou. O `lastState`
guarda uma falha **já curada**.

Quem ancora no contador de restart vai investigar conexão de banco, que está funcionando.
**`lastState` — a fonte que resolveu o chamado 1 — aqui engana.**

A distinção que separa os dois casos: no chamado 1 o `state` **atual** é `waiting` com
`CrashLoopBackOff`. Aqui o `state` atual é `running`. **Falha viva mora em `state`; falha
curada mora em `lastState`.**

**Onde a causa estava:**

```
campo subsets: AUSENTE — o campo nao vem, nao vem vazio
slice nyx-api-wszq8: endpoints=AUSENTE

selector do Service  : {"app": "nyx-api"}
labels do pod        : {"app": "nyxapi", "pod-template-hash": "..."}
matchLabels do deploy: {"app": "nyxapi"}
```

Um hífen. E o detalhe que define o conserto: o `matchLabels` do Deployment **casa** com o
pod. O Deployment está correto; só o `selector` do Service está errado.

Confirmação pelos dois lados:

```
kubectl get pod -l app=nyx-api      -> No resources found
kubectl exec <pod> -- wget -qO- localhost:8080/health
                                    -> {"state":"up","machine":"nyx-api-..."}
```

## As quatro conclusões que viraram método

1. **A camada vem do sintoma relatado**, não de um comando. "Reinicia sozinho" é container;
   "não sobe" é imagem; "está de pé e ninguém chega" é rede.
2. **Cruzar duas fontes tem gatilho**: a primeira fonte deu **sintoma** em vez de causa.
   `BackOff` não explica por que morre; `Running` não explica o 503. Quando a resposta é
   sintoma, cruze. Quando é causa, pare.
3. **Três distinções decidem o caso**: fase do pod x estado do container; `state` x
   `lastState`; seletor do Deployment x seletor do Service.
4. **Parar é parte do método.** Nos três chamados o conserto exige contexto que a triagem
   não tem: orçamento do cliente para o limite de memória, o que o release pretendia
   entregar, qual dos dois lados do seletor é o certo.
