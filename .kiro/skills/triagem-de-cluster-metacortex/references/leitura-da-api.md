# Leitura da API do Kubernetes — o que ela não devolve

Consulte ao interpretar JSON cru ou ao escrever código que lê o cluster. Tudo aqui foi
confirmado contra apiserver v1.31.5.

## Campo ausente não é campo vazio

O erro que mais gera bug e mais gera diagnóstico errado. **Quando a resposta é "nenhum", o
Kubernetes costuma omitir o campo em vez de devolver lista vazia ou zero.**

| Objeto | Campo | Quando não há nada |
|---|---|---|
| `Endpoints` | `subsets` | **não aparece.** Não vem `[]` |
| `EndpointSlice` | `endpoints` | **não aparece** |
| `Deployment` | `status.readyReplicas` | **não aparece.** Não vem `0` |
| `Deployment` | `status.unavailableReplicas` | não aparece quando todas estão disponíveis |
| `Pod` | `status.containerStatuses` | não aparece enquanto o pod está `Pending` |
| container | `lastState` | vem como `{}` quando o container nunca morreu |

Consequência prática:

```python
# quebra com KeyError quando o Service nao tem endpoint —
# que e exatamente o caso que voce esta investigando
len(ep["subsets"])

# certo
len(ep.get("subsets") or [])

# o mesmo para replicas prontas
ready = dep["status"].get("readyReplicas", 0)
```

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
| Service sem endpoint | ausência de `subsets` | log, evento, status do container |
| erro da aplicação | **log**, `exitCode: 1` | evento |
| pod não agendável | `conditions[].reason`, evento `FailedScheduling` | log, `containerStatuses` |

## Endpoints x EndpointSlice

`Endpoints` está sendo descontinuado; a informação equivalente vive em `EndpointSlice`.
Durante a transição os dois existem, e o `Endpoints` continua sendo populado pelo
controlador.

Para triagem, consulte os dois: se divergirem, há problema no controlador de endpoints, o
que é causa em si. A ligação do slice com o Service é o rótulo
`kubernetes.io/service-name`, não o nome do objeto.

## "Pronto" não significa "saudável"

`ready: true` significa que a readinessProbe passou. Se a aplicação **não tem** endpoint de
saúde, o Kubernetes marca o container como pronto assim que o processo sobe — é o caso do
fake-shop, que não expõe `/health` nem `/ready`.

Na Metacortex a regra 2.2 do padrão de manifests exige as duas probes, mas workload antigo
ou de terceiro pode não ter. **Diga no relatório o que você sabe e o que está inferindo:**
"a readinessProbe passou" é fato; "a aplicação está saudável" pode não ser.
