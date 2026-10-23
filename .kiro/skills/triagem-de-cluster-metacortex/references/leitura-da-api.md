# Leitura da API do Kubernetes — o que ela não devolve

Consulte ao interpretar JSON cru ou ao escrever código que lê o cluster. Tudo aqui foi
confirmado contra apiserver v1.31.5.

## Campo ausente não é campo vazio

O erro que mais gera bug e mais gera diagnóstico errado. **Quando a resposta é "nenhum", o
Kubernetes costuma omitir o campo em vez de devolver lista vazia ou zero.**

| Objeto | Campo | Quando não há nada |
|---|---|---|
| `Endpoints` | `subsets` | **a chave não aparece.** Não vem `[]` |
| `EndpointSlice` | `endpoints` | **a chave aparece com valor `null`** |
| `EndpointSlice` | `ports` | **a chave aparece com valor `null`** |
| `Deployment` | `status.readyReplicas` | **não aparece.** Não vem `0` |
| `Deployment` | `status.unavailableReplicas` | não aparece quando todas estão disponíveis |
| `Pod` | `status.containerStatuses` | não aparece enquanto o pod está `Pending` |
| container | `lastState` | vem como `{}` quando o container nunca morreu |

**Chave ausente e chave com `null` são dois jeitos diferentes de quebrar**, e `Endpoints` e
`EndpointSlice` fazem um cada. Medido no mesmo Service sem endpoint:

```
Endpoints      chaves de topo: ['apiVersion','kind','metadata']
                               -> 'subsets' NAO esta na lista

EndpointSlice  chaves de topo: ['addressType','apiVersion','endpoints','kind',
                                'metadata','ports']
                               -> 'endpoints' esta na lista, com valor None
```

Consequência prática — só uma das três formas abaixo sobrevive aos dois:

```python
len(ep["subsets"])                  # KeyError no Endpoints
len(sl.get("endpoints", []))         # TypeError no EndpointSlice: len(None)
len(x.get("endpoints") or [])        # certo nos dois

ready = dep["status"].get("readyReplicas") or 0   # certo
```

Cuidado com o `or` ao **rotular** em vez de contar: `valor or "AUSENTE"` imprime `AUSENTE`
tanto para chave ausente quanto para `[]` e para `None`, porque os três são falsy. Para
distinguir, teste a presença da chave:

```python
"endpoints" in sl                    # a chave existe?
sl.get("endpoints") is None          # existe e esta nula?
```

Este erro é documentado porque eu o cometi: o script que coletou a evidência deste ticket
usou `or "AUSENTE"` e rotulou o `EndpointSlice` como campo ausente quando a chave estava
presente e nula. A conclusão da triagem não mudou — zero endpoint nos dois casos —, mas a
regra que eu escrevi aqui estava errada até um teste cego medir de novo.

Na triagem, o efeito é pior que um erro: código que falha ao ler o caso quebrado faz a
ferramenta parecer que o cluster está bem.

## Fase do pod x estado do container

**São objetos diferentes com significados diferentes, e a fase mente.**

| Situação real | `status.phase` do pod | onde está a verdade |
|---|---|---|
| container em `CrashLoopBackOff` | **`Running`** | `containerStatuses[].state.waiting.reason` |
| container `OOMKilled` reiniciando | **`Running`** | `containerStatuses[].lastState.terminated.reason` |
| imagem não encontrada | `Pending` | `containerStatuses[].state.waiting.reason` |
| pod sem nó para agendar | `Pending` | `conditions[].reason` = `Unschedulable` |

As fases são `Pending`, `Running`, `Succeeded`, `Failed` e `Unknown`. **`Running` significa
"pelo menos um container iniciou", não "está funcionando".** Filtrar workload quebrado por
`phase != Running` perde todo pod em `CrashLoopBackOff`.

## `state` x `lastState`

| Campo | Responde |
|---|---|
| `state` | o que o container está fazendo **agora**: `running`, `waiting` ou `terminated` |
| `lastState` | como a encarnação **anterior** terminou |

**Regra de leitura: falha viva mora em `state`; falha curada mora em `lastState`.**

| `state` | `lastState` | Leitura |
|---|---|---|
| `waiting: CrashLoopBackOff` | `terminated: OOMKilled` | falha **viva**. `lastState` diz por quê |
| `running` | `terminated: Error` | **já recuperou.** Provavelmente não é o seu chamado |
| `waiting: ImagePullBackOff` | `{}` vazio | o container **nunca rodou** |

`restartCount` alto com `state: running` e `ready: true` é um pod que se recuperou. Comum em
aplicação que sobe antes do banco aceitar conexão.

## Códigos de saída que aparecem na triagem

| `exitCode` | Significa |
|---|---|
| `0` | terminou normalmente. Em `lastState` de workload de longa duração, costuma ser processo que não deveria sair |
| `1` | erro da aplicação. **Aqui o log serve** |
| `137` | `SIGKILL` (128+9). Com `reason: OOMKilled`, é o limite de memória. **O log fica vazio** |
| `143` | `SIGTERM` (128+15). Encerramento pedido pelo Kubernetes |
| `126` / `127` | comando não executável / não encontrado. `command` ou `args` errados |

## Eventos não ficam dentro do objeto

Evento é objeto próprio, com `involvedObject` apontando para o alvo. Dois efeitos:

- `kubectl_get resourceType=pod output=json` **não traz** os eventos do pod. Use
  `kubectl_describe`, que já faz a junção.
- Evento tem **retenção curta** — uma hora por padrão. Chamado de ontem pode não ter evento
  nenhum, e isso não significa que nada aconteceu.
- `count`, `firstTimestamp` e `lastTimestamp` dizem se é um evento repetido ou único. Um
  `BackOff` com `count: 21` é diferente de um com `count: 1`.

## Onde cada causa aparece, e onde não aparece

| Causa | Aparece em | **Não** aparece em |
|---|---|---|
| `OOMKilled` | `lastState.terminated.reason` | log (vazio), evento (só `BackOff`) |
| tag inexistente | evento do kubelet: `not found` | log (BadRequest, não há container) |
| Service sem endpoint **pronto** | `conditions.ready`, ou ausência de `subsets` | log, evento, status do container |
| erro da aplicação | **log**, `exitCode: 1` | evento |
| pod não agendável | `conditions[].reason`, evento `FailedScheduling` | log, `containerStatuses` |

## Endpoints x EndpointSlice

`Endpoints` está sendo descontinuado; a informação equivalente vive em `EndpointSlice`.
Durante a transição os dois existem, e o `Endpoints` continua sendo populado pelo
controlador.

Para triagem, consulte os dois: se divergirem, há problema no controlador de endpoints, o
que é causa em si. A ligação do slice com o Service é o rótulo
`kubernetes.io/service-name`, não o nome do objeto.

**Os dois sinalizam "sem endpoint" de formas diferentes** — ver a primeira seção. Não use a
presença da chave como teste; use o conteúdo normalizado com `or []`.

### Contar endpoints não é contar endpoints prontos

Correção vinda do Ticket 04. Endpoint **existir** e endpoint **servir** são coisas
diferentes, e só a segunda responde "por que não responde":

| Fonte | Prontos | Não prontos |
|---|---|---|
| `EndpointSlice` | `conditions.ready is True` | `ready: false`, e `terminating` separado |
| `Endpoints` | `subsets[].addresses` | `subsets[].notReadyAddresses` |

Num Service com 3 pods em `ImagePullBackOff`, `subsets` **está presente** e
`len(subsets)` devolve 1 — um subset, com 3 endereços não prontos. Quem conta subsets ou
conta endpoints conclui "tem endpoint" e segue adiante. A conta certa é
`0 de 3 prontos`.

`EndpointSlice` distingue `ready`, `serving` e `terminating`; `Endpoints` só separa pronto
de não-pronto, sem a noção de terminando. Durante um rollout essa é a diferença entre um
alarme e um não-evento.

## "Pronto" não significa "saudável"

`ready: true` significa que a readinessProbe passou. Se a aplicação **não tem** endpoint de
saúde, o Kubernetes marca o container como pronto assim que o processo sobe — é o caso do
fake-shop, que não expõe `/health` nem `/ready`.

Na Metacortex a regra 2.2 do padrão de manifests exige as duas probes, mas workload antigo
ou de terceiro pode não ter. **Diga no relatório o que você sabe e o que está inferindo:**
"a readinessProbe passou" é fato; "a aplicação está saudável" pode não ser.
