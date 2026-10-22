# A skill vale o custo?

Parte C do ticket. Dois chamados executados duas vezes: uma com a skill de triagem como
método, outra sem método nenhum. Mesmo cluster, mesmo transporte MCP, mesma restrição de
só-leitura, agentes diferentes e sem contato entre as execuções.

**Resposta curta: a skill custou mais e entregou mais. O "mais" de cada lado é de natureza
diferente, e é isso que decide quando ela vale.**

## O que foi medido, e o que não foi

| Medido | Como |
|---|---|
| **chamadas MCP** | contadas uma a uma, com a sequência registrada em ordem |
| **chamadas sem retorno útil** | declaradas pelo próprio executor |
| **caminhos errados** | hipóteses perseguidas e descartadas, com o custo de cada uma |
| **qualidade da saída** | causa correta, fronteira de incerteza declarada, correção do relato do cliente |

**Tempo de parede não foi medido, e não deveria.** Cada chamada do harness sobe um processo
`npx` novo, que leva mais tempo que a consulta ao apiserver. O número seria dominado por
uma escolha de implementação do cliente MCP, não pelo método. **Chamadas MCP é o proxy
honesto de custo aqui**: cada uma é uma ida ao apiserver e uma resposta entrando no contexto.

Também **não medi tokens de verdade.** Não tenho acesso à contabilidade de tokens de um
sub-agente. O que tenho é o número de chamadas e o volume do que elas devolvem, que é
proporcional — mas é proxy, e digo isso em vez de inventar um número.

## O custo

| Chamado | Com skill | Sem skill | Diferença |
|---|---|---|---|
| **1** — `nyx-prod`, OOMKilled | **8** chamadas | **4** chamadas | a skill custou **2x** |
| **3** — `nyx-stg`, sem endpoint | **12** chamadas | **8** chamadas | a skill custou **1,5x** |
| chamadas sem retorno útil | 2 e 1 | 2 e 3 | empate técnico |

Somando o corpo do `SKILL.md` que carrega a cada ativação — 248 linhas, ~2800 tokens — a
skill é claramente mais cara. **E ela chegou depois.**

### Por que custou mais, decomposto

**Metade da diferença foi defeito meu, e já está corrigido.** Duas das oito chamadas do
chamado 1 foram desperdiçadas porque a skill prescrevia
`kubectl_get resourceType=pods output=json` esperando `containerStatuses` — e neste servidor
MCP a lista devolve um resumo de cinco campos. Eu escrevi o método contra a saída do
`kubectl`, não contra a do MCP, que é o acesso que a própria skill determina. Hoje a skill
manda usar o singular com `name`, e tem uma seção sobre isso antes do passo 1.

**A outra metade é rigor, e é escolha.** As chamadas que a skill gastou e o executor sem
método não gastou:

| Chamada extra | Para quê |
|---|---|
| segundo pod do mesmo ReplicaSet | confirmar que a causa é a mesma, em vez de inferir da posse do template |
| pod do Postgres | afirmar "o banco está de pé" com evidência, não por ele não aparecer na lista de problemas |
| Deployment no singular | medir o impacto: `unavailableReplicas`, `conditions`, `generation` x `observedGeneration` |
| `labelSelector` com o rótulo **certo** | controle. `items: []` é ambíguo entre "nenhum casa" e "o filtro foi ignorado" |

A última é a que melhor ilustra a troca. O executor sem skill viu `items: []` e concluiu
"nenhum pod casa". Provavelmente certo. O executor com skill gastou uma chamada provando
que o filtro estava ativo. **Uma chamada por uma afirmação que não depende de suposição.**

### O achado de eficiência que veio do lado sem skill

O executor sem método usou `kubectl_describe` quase direto, e `describe` **empacota evento,
spec e status numa chamada só**. A causa do chamado 1 saiu na segunda chamada dele; na
quinta da versão com skill, que pedia `get` em JSON campo por campo.

É um ponto a favor do improviso que eu não tinha previsto: **para o caso simples, `describe`
é mais eficiente que `get -o json`.** A skill ficou mais precisa sobre *qual campo* ler e
pagou em número de chamadas.

Não mudei o método por causa disso, e o motivo é o chamado 3: ali `describe` do pod não
aponta nada, porque não há nada errado com o pod. A precisão de campo é o que faz a skill
achar causa em `subsets` ausente, que `describe` não destaca.

## O que a skill entregou a mais

Aqui a comparação inverte, e os dois relatórios são de categorias diferentes.

### As duas execuções acertaram as duas causas

Nenhuma vantagem da skill nisto. Com e sem método, `OOMKilled` com `limits.memory: 24Mi` e
`selector: app: nyx-api` contra `labels: app: nyxapi` foram identificados corretamente, com
o campo exato.

**Se o critério for "acha a causa", a skill não se paga nestes dois casos.**

### A skill declarou a fronteira da própria ignorância

O relatório com skill registrou, por chamado, o que **não** conseguiu verificar:

- quanto de memória o kube-news precisa de fato — `kubectl_top` não existe entre as 17
  ferramentas, então "24Mi não basta" é afirmável e "256Mi basta" não é
- a lista de tags do registry — o MCP não tem ferramenta de registry
- **que a aplicação responde HTTP** — `exec_in_pod` não existe em modo não destrutivo, então
  a prova é indireta: `ready=True` significa que a readinessProbe passou, e ela é uma
  requisição real feita pelo kubelet. Não é o mesmo que ter recebido 200
- quem emite o 503 — sem Ingress no cluster, a borda está fora do alcance

O relatório sem skill não tem essa seção. Ele afirma "proxy/ingress devolve 503" como parte
da causa, tendo confirmado nas próprias chamadas que **não existe Ingress em namespace
nenhum**. É a diferença entre uma frase que o plantonista pode repassar ao cliente e uma que
alguém vai contestar.

### A skill corrigiu o relato do cliente

Os dois relatos têm afirmação falsa, e a skill as pegou de forma sistemática porque o passo
2 exige nomear o que está são:

| O cliente disse | O cluster diz |
|---|---|
| "mudou os limites do **namespace inteiro** de uma vez" | não existe `LimitRange` em `nyx-prod`, e o Postgres está com `resources: {}`. O 24Mi está no template do `Deployment/nyx-api` e só ali |
| "o pod nunca foi substituído" (chamado 2) | não existe ReplicaSet anterior. `revision: 1`, única. Não é "a nova não entrou", é **"a loja está fora"** — 0 de 3 |

A segunda muda a urgência do chamado. O executor sem skill também achou a questão do
`LimitRange`, gastando uma chamada que ele mesmo classificou como caminho errado — a skill
transforma isso em achado deliberado em vez de subproduto.

### A skill desarmou a armadilha, e sem ela o risco é concreto

No chamado 3 os pods têm `restartCount: 2` com `lastState.terminated.exitCode: 1` — falha
**já curada**, a aplicação subiu antes do Postgres aceitar conexão.

O executor **sem** skill registrou: *"distração do Terminated/Error/exit 1 no pod stg
(boot antes do Postgres, descartado sem custo)"*. Descartou, e sem gastar chamada. Mérito
dele.

O executor **com** skill tinha a regra escrita — `state: running` significa que `lastState`
é história — e também não caiu.

**Então a armadilha não pegou ninguém, e eu não posso usá-la como prova de valor da skill.**
O que posso dizer é o que o próprio executor com skill escreveu: `exitCode: 1` é o único
caso em que o log serve, e o reflexo de plantão com um 503 na mão é ler o log. Os dois
executores são modelos fortes, atentos e sem pressa. **Um plantonista humano às três da
manhã é o caso que a regra escrita protege, e isso este teste não mede.**

## Veredito, por cenário

| Cenário | A skill vale? |
|---|---|
| causa nomeada num campo (`OOMKilled`, `ImagePullBackOff`) | **não.** `describe` resolve em 2 chamadas, e o executor sem método chegou primeiro |
| tudo verde e o cliente reclamando | **sim.** É o caso em que as fontes óbvias não apontam nada, e o método diz onde olhar |
| relatório que vai para o cliente ou para o PR | **sim.** A fronteira de incerteza e a correção do relato não saem por acaso |
| plantonista novo, ou às três da manhã | **sim**, e é o cenário que este teste não consegue medir |
| agente forte, sem pressa, caso simples | **não.** O método é overhead |

## O que eu mudaria

**Primeiro, o que já mudei:** os comandos do método estavam escritos contra o `kubectl` e
não contra o MCP. Metade do custo extra era isso.

**O que eu faria diferente no teste:** medir um chamado que **nenhum** dos dois tenha visto
documentado. O executor com skill apontou, por conta própria, que
`references/por-que-a-ordem-importa.md` é a solução trabalhada destes mesmos três chamados —
com namespace, causa e valor — e que a skill mandava ler antes de triar. Ele leu, como
instruído, e registrou que isso contamina o julgamento de "o método me levou direto".

Está consertado na skill (as `references/` passaram a ser explicitamente fora do caminho de
execução, com aviso de que contêm solução trabalhada), **mas a medição com skill foi feita
antes do conserto.** Então o número de 8 e 12 chamadas é de um executor que já sabia as
respostas. Provavelmente **otimista** — ele pode ter ido direto a campos que não teria
adivinhado — e isso empurra o custo real da skill para cima, não para baixo.

É a limitação mais séria desta medição, e foi o executor que a apontou, não eu.
