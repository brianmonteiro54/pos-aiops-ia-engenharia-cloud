# Curadoria da skill `triagem-de-cluster-metacortex`

O que o método fixou, o que deixou a critério do agente, e como garanti que a skill não
escreve no cluster.

Skill em `.kiro/skills/triagem-de-cluster-metacortex/`.

## 0. Como a skill foi produzida

| | |
|---|---|
| **Agente** | Kiro (IDE), modo Autopilot |
| **Modelo** | Claude Opus 5 |
| **Acesso ao cluster** | `mcp-server-kubernetes` com `ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true` |
| **Cluster** | k3d `metacortex`, k3s v1.31.5, 2 nós |
| **Sub-agentes** | `general-task-execution` para executar a skill, para o roteamento e para a medição sem skill |

**O fluxo veio antes da skill:**

1. Apliquei os três chamados no k3d e esperei os defeitos se manifestarem.
2. **Triei os três à mão com `kubectl`**, registrando a ordem em que desci as camadas, onde
   cruzei duas fontes e onde uma fonte me daria a resposta errada —
   `fluxos/fluxo-01-triagem-manual.md`.
3. Medi o que o modo não destrutivo de fato remove, enumerando as ferramentas do servidor
   nos dois modos.
4. **Só então** escrevi o método.
5. Executei a skill nos três chamados pelo transporte MCP real, com um sub-agente que não
   tinha visto a triagem manual.

A regra do desafio — *skill escrita de cabeça não vale* — é o que produziu os achados. As
três distinções centrais do método saíram de **erros que eu quase cometi triando à mão**, não
de teoria.

## 1. O que o método fixou

Fixei o que, medido, **muda o resultado** quando não está fixo.

### A ordem das camadas, derivada do sintoma

Fixei que a camada vem **da frase do chamado**, não de um comando. A tabela do passo 1 é o
único galho obrigatório.

Por quê: os três chamados se resolvem em camadas diferentes, e nenhuma fonte resolve os
três.

| Fonte | Chamado 1 | Chamado 2 | Chamado 3 |
|---|---|---|---|
| logs | **vazios** | **impossíveis** | sem erro |
| eventos | só `BackOff` | **`not found`** | nada |
| status do container | **`OOMKilled`** | `lastState` vazio | `ready=True` |
| endpoints | — | — | **`subsets` ausente** |

"Sempre comece pelos logs" falha em 2 de 3. "Sempre pelos eventos" também. Deixar a ordem a
critério do agente é reintroduzir o problema que a SRE pediu para resolver: cada plantonista
começando por um lugar diferente.

### Três distinções de leitura

As três saíram de armadilhas que eu encontrei triando à mão:

| Fixado | Por que não pode ficar a critério |
|---|---|
| fase do pod **não é** estado do container | pod com container em `CrashLoopBackOff` tem `phase: Running`. Filtrar por fase perde o chamado 1 inteiro |
| `state` é falha viva, `lastState` é falha curada | no chamado 3 há 2 restarts com `exitCode 1` sem relação com o chamado. `lastState`, que resolveu o chamado 1, aqui engana |
| seletor do Deployment **não é** seletor do Service | no chamado 3 o `matchLabels` casa e só o Service está errado. Dois objetos, dois consertos |

### O gatilho de cruzar duas fontes

Fixei um critério em vez de "cruze quando fizer sentido": **cruze quando a primeira fonte
devolver sintoma em vez de causa.** `BackOff` não explica por que o container morre;
`Running` não explica o 503.

### Quando parar, e o teste

Fixei: **pare na causa**, e o teste é "se a próxima pergunta for *e por que isso?*, você
ainda está no sintoma".

### A lista branca de ferramentas

Fixei as cinco permitidas e as doze proibidas **por nome**, cobrindo as 17 que o servidor
expõe. Ver seção 3.

## 2. O que ficou a critério do agente

| A critério | Por quê |
|---|---|
| **quantas chamadas, e em que ordem dentro da camada** | o método diz a camada e a pergunta; o caminho depende do que a resposta anterior trouxe. Fixar a sequência produziria chamada inútil em 2 de 3 casos |
| **usar `get` ou `describe`** | `describe` empacota evento, spec e status numa chamada; `get` no singular dá o campo exato. A medição sem skill mostrou que `describe` é mais eficiente no caso simples, e `get` é o que acha causa em campo ausente |
| **quanto rigor de confirmação** | confirmar que o segundo pod do mesmo ReplicaSet tem a mesma causa custa uma chamada e troca inferência por evidência. Em plantão com fila, inferir é defensável |
| **a redação do relatório** | fixei as cinco partes e o que cada uma responde, não as frases |
| **o conserto recomendado** | a skill exige que seja recomendação e não ação. Qual é o conserto certo depende de contexto que a triagem não tem |

O que **não** deixei a critério e vale dizer: **a decisão de parar**. Um agente com acesso
de escrita e a causa na mão tende a consertar, e é exatamente o que o ticket proíbe.

## 3. Como garanti que a skill não escreve no cluster

**O modo não destrutivo não é somente-leitura, e isso é medição, não leitura de README.**

Enumerei as ferramentas do servidor nos dois modos, pelo protocolo:

| Modo | Ferramentas |
|---|---|
| default | **23** |
| `ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true` | **17** |

O modo remove 6: `kubectl_delete`, `kubectl_generic`, `exec_in_pod`, `cleanup`,
`node_management`, `uninstall_helm_chart`.

**E deixa sete que escrevem no cluster:**

```
kubectl_apply   kubectl_create   kubectl_patch   kubectl_scale   kubectl_rollout
install_helm_chart   upgrade_helm_chart
```

Um agente de triagem poderia "consertar" o OOM do chamado 1 com `kubectl_patch`, e o modo
não destrutivo **deixaria**. Então a garantia tem três camadas, e nenhuma sozinha basta:

### Camada 1 — o servidor, que bloqueia o irreversível

Verificado por chamada direta:

```
./mcp.py call kubectl_delete '{"resourceType":"pod","name":"nyx-api","namespace":"nyx-prod"}'
RECUSADA pelo servidor: MCP error -32600:
  Tool 'kubectl_delete' is not allowed under the current server configuration
```

Esta camada é a única que não depende de boa-fé. Ela cobre o que não tem volta — apagar
objeto, drenar nó, executar comando arbitrário dentro de pod.

### Camada 2 — a skill, que proíbe o que o servidor deixou

A lista branca de cinco, e as doze proibidas por nome, **cobrindo as 17 que o servidor
expõe**. Não é "evite escrever": é a enumeração completa, para que a regra *use apenas as
autorizadas* seja verificável.

Três que estavam fora das duas listas na primeira versão e entraram depois, apontadas pela
execução: `kubectl_context` (troca o cluster-alvo — triagem no cluster errado é pior que
nenhuma), `kubectl_reconnect` (muda estado do cliente; conexão caída é achado, não coisa a
consertar) e `stop_port_forward`.

`port_forward` entrou nas proibidas por decisão de escopo, não por risco de escrita: ele não
altera objeto, mas abre túnel para dentro do cluster e não responde pergunta que `get` e
`describe` não respondam.

### Camada 3 — o método, que remove o motivo de escrever

A skill define **parar na causa** e **entregar o conserto como recomendação**. A frase que
carrega isso:

> Se você sentir vontade de rodar `kubectl_patch` para subir um limite de memória, é sinal de
> que a triagem já acabou.

### Evidência de que funcionou

Na execução dos três chamados, o executor registrou por conta própria:

> Nenhuma ferramenta de escrita foi chamada — `kubectl_apply`, `create`, `patch`, `scale`,
> `rollout`, `install_helm_chart`, `upgrade_helm_chart`, `port_forward` e `stop_port_forward`
> **estavam disponíveis no servidor e não foram tocadas**.

26 chamadas `tools/call` nos três chamados, todas de leitura. E nos três ele entregou o
conserto como comando para outra pessoa rodar, incluindo o caso em que a correção era um
`patch` de um caractere no seletor.

### O que esta garantia não cobre

**Uma quarta camada que eu não implementei:** RBAC. Um contexto de kubeconfig com
ServiceAccount somente-leitura tornaria a escrita impossível **no apiserver**, independente
de skill e de servidor MCP. É a única camada que não depende de configuração do cliente.

Não fiz porque o k3d de laboratório usa o contexto de admin e montar RBAC restrito seria
trabalho fora do ticket. **Em produção seria a primeira camada, não a quarta** — e fica
registrado como lacuna conhecida, não como coisa resolvida.

## 4. Corpo x reference

| Conteúdo | Onde | Por quê |
|---|---|---|
| a ordem das camadas e o mapa sintoma → camada | **corpo** | é o que define o comportamento |
| as três distinções de leitura | **corpo** | decidem o caso; precisam estar carregadas |
| a lista branca de ferramentas | **corpo** | é o limite; não pode depender de consulta |
| o formato do relatório | **corpo** | sem isso a saída muda a cada execução |
| a medição dos três chamados | `por-que-a-ordem-importa.md` | é argumento para quando alguém contestar o método |
| os campos que a API não devolve | `leitura-da-api.md` | consulta pontual, ao interpretar JSON |

Corpo: **~250 linhas, ~2800 tokens.** As duas references somam mais ~320 linhas que só
carregam quando o passo manda.

### Um erro de desenho que a execução revelou

A `por-que-a-ordem-importa.md` **é a solução trabalhada dos três chamados** — namespace,
causa e valor, nominalmente. E a abertura do corpo mandava lê-la.

O executor apontou:

> A skill manda ler, então li. O efeito é que a triagem não pode ser cega, e qualquer
> medição de "o método guia à descoberta?" fica comprometida.

Ele está certo, e isso contaminou a Parte C — ver `com-e-sem-skill.md`. Hoje a abertura do
corpo diz explicitamente que as references **não são passo do método** e que a de cobertura
contém solução trabalhada.

A tensão é estrutural e vale nomear: **a evidência que justifica um método é o conjunto de
casos resolvidos com ele, e esse conjunto é gabarito.** Não há como documentar a origem sem
criar o risco. O que dá é marcar o arquivo e tirá-lo do caminho de execução.

## 5. O que decidi não empacotar

| Fora | Por quê |
|---|---|
| **consertar qualquer coisa** | é o limite absoluto do ticket, e o método remove o motivo |
| **`kubectl_top` e métricas** | não existe entre as 17 ferramentas. A skill afirma "24Mi não basta" e **não** afirma qual valor basta |
| **ferramenta de registry** | o MCP não tem. A skill ensina a descartar credencial e rede **por dentro** do cluster e a declarar a tag como não verificada |
| **testar endpoint HTTP** | `exec_in_pod` não existe em modo não destrutivo e `port_forward` é proibido. A prova passa a ser indireta, via readinessProbe, e a skill manda dizer isso |
| **diagnóstico da borda** | sem Ingress no cluster, o proxy que emite o 503 está fora do alcance. A skill manda registrar que o código vem de camada não observada |
| **árvore de decisão completa** | fixaria a sequência de chamadas, e a medição mostrou que a sequência certa depende da resposta anterior |

## 6. Nove defeitos que a execução achou

A skill foi executada nos três chamados por um agente que não viu a triagem manual. As três
causas saíram corretas. O valor estava nos **nove atritos**, todos corrigidos:

1. **Os comandos estavam escritos contra o `kubectl`, não contra o MCP.** `output: "json"` em
   modo lista devolve resumo de cinco campos, sem `containerStatuses`. Duas chamadas
   desperdiçadas. Hoje há uma seção sobre isso antes do passo 1.
2. **Passo 1 e passo 2 se contradiziam** sobre o retrato ser obrigatório.
3. **O passo 4 exigia confirmar a tag no registry**, que o MCP não permite. Hoje ensina a
   descartar credencial e rede por dentro.
4. **A skill afirmava `registry.metacortex.io`** e as imagens do cluster vêm de `docker.io`.
   Mandaria o plantonista ao registry errado.
5. **A lista de ferramentas não cobria 3 das 17.**
6. **`ping` retorna conteúdo vazio** — sucesso em branco não informa nada. Saiu das
   permitidas.
7. **O passo 5 não mencionava Ingress**, e roteava justamente "503 de fora". Um ClusterIP sem
   endpoint não devolve 503: devolve recusa ou timeout.
8. **A `leitura-da-api.md` estava errada sobre `EndpointSlice`.** Eu escrevi que a chave
   `endpoints` não aparece. Medido: ela **aparece com valor `null`**. Só `Endpoints.subsets`
   some de verdade. O erro veio do meu script de coleta, que usou `or "AUSENTE"` — e `[]`,
   `None` e chave ausente são todos falsy. São dois jeitos diferentes de quebrar:
   `len(x["subsets"])` dá `KeyError`, `len(x.get("endpoints", []))` dá `TypeError`.
9. **A reference obrigatória entregava o gabarito** — seção 4.

Os defeitos 1, 4 e 8 mudariam o resultado de uma triagem real. O 8 é o mais incômodo: é uma
regra de leitura **errada** dentro do arquivo que existe para ensinar regras de leitura, e ela
sobreviveu a eu ter escrito o documento e revisado o script.
