# A skill vale o custo?

Parte C do ticket. Dois chamados executados duas vezes: uma com a skill de triagem como
método, outra sem método nenhum. Mesmo cluster, mesmo transporte MCP, mesma restrição de
só-leitura, agentes diferentes e sem contato entre as execuções.

**Resposta curta: depende do eixo, e os eixos discordam.** Por número de chamadas a skill
saiu **mais barata** nesta medição (10 contra 15 e 10 contra 13). Por tokens ela saiu
**2,4x a 2,8x mais cara**, e essa parte não depende de sorte: 5.022 tokens entram no
contexto a cada ativação, antes de qualquer investigação.

A primeira versão deste documento media só chamadas e concluiu o oposto. **A correção está
registrada aqui**, com o motivo de cada parcela.

## Como foi medido

A primeira versão desta Parte C contou **chamadas** e declarou que tokens e tempo não
foram medidos, com um argumento que eu precisei abandonar: que chamada seria "o proxy
honesto de custo". **Não é**, e a medição de tokens é o que mostra por quê. Duas chamadas
podem diferir em uma ordem de grandeza no que devolvem.

A medição foi refeita por inteiro, com as skills carregadas de verdade.

### As quatro execuções

Quatro sub-agentes em sessão limpa, dois chamados, dois braços cada. Transporte **fixo e
igual nos quatro**: o cliente MCP de `ferramentas/mcp.py`, em modo não destrutivo. O braço
sem skill recebeu a instrução explícita de não ativar nada e não ler nada dentro de
`.kiro/skills/`; o braço com skill ativou sozinho, pela `description`, e registrou isso.

Cada executor instrumentou a própria execução: `date +%s` antes da primeira e depois da
última chamada ao cluster, mais a sequência exata de chamadas em ordem.

### A medição de tokens

As quatro sequências foram **transcritas do bloco de instrumentação de cada executor** e
repetidas por `ferramentas/medir-custo.py`, que mede cada resposta com `tiktoken`
(`o200k_base`). Reproduzível: `python3 ferramentas/medir-custo.py`.

Evidência bruta em `evidencias/custo-com-e-sem-skill.txt` e `.json`.

**O que esse número é, e o que não é.** É o custo de **entrada observável**: o que as
ferramentas devolveram, mais o corpo do `SKILL.md` quando houve ativação. **Não** é o total
faturado pelo provedor: tokens de raciocínio do modelo não são observáveis daqui, e eu não
tenho acesso a essa contabilidade. O tokenizador é o da OpenAI, não o da Anthropic; serve
porque mede os quatro braços com a mesma régua.

## O custo, nos três eixos

| Chamado | Braço | Chamadas | Tokens de resposta | Tokens de entrada | Tempo de ponta a ponta |
|---|---|---|---|---|---|
| **1** `nyx-prod`, OOMKilled | com skill | **10** | 8.202 | **13.224** | **269 s** |
| | sem skill | 15 | 5.409 | 5.409 | 503 s |
| **3** `nyx-stg`, sem endpoint | com skill | **10** | 4.591 | **9.613** | 277 s |
| | sem skill | 13 | 3.482 | 3.482 | 272 s |

Custo fixo da skill, por ativação: **5.022 tokens** (18.396 bytes de `SKILL.md`). As
`references/` estão fora do caminho de execução e não entram.

### Os eixos discordam, e essa é a descoberta

**Por chamadas, a skill é mais barata: 10 contra 15 e 10 contra 13.**

**Por tokens, a skill é mais cara: 2,44x e 2,76x.**

As duas coisas são verdade ao mesmo tempo, e a primeira versão deste documento,
medindo só chamadas, concluiu o oposto em ambos os eixos. Dois motivos compõem a inversão:

**1. O custo fixo de 5.022 tokens.** Ele é 38% da entrada no chamado 1 e 52% no chamado 3.
Num chamado curto, o método custa mais que a investigação.

**2. O método prescreve a leitura mais caras por objeto.** A skill manda `kubectl_get` no
singular com `output: json`, que devolve o objeto cru. O braço sem skill usou
`kubectl_describe`, que devolve um resumo formatado. Medido no **mesmo pod**:

| Leitura | Tokens |
|---|---|
| `kubectl_get pod <nome> output=json` | **1.849** |
| `kubectl_describe pod <nome>` | **835** |

**2,2x mais caro para responder a mesma pergunta.** A skill troca menos chamadas por
chamadas mais gordas, e no total de tokens isso não se paga.

### O que isso obriga a admitir sobre o método

O `describe` ganha nos dois eixos para inspeção de pod: menos chamadas (ele empacota
evento, spec e status) e menos tokens. A primeira versão já havia notado a vantagem em
chamadas e eu não mudei o método; a medição de tokens tira a desculpa.

A defesa da precisão de campo continua existindo, e é estreita: `describe` **formata**, e
formatar apaga a diferença entre chave ausente e chave nula. Num Service sem endpoint ele
imprime `Subsets: <none>` nos dois casos. Essa distinção é o que o Ticket 04 precisou para
escrever código contra a API, e é o que `0/0` contra `0/3` depende.

**Mas nos dois chamados medidos ela não mudou a causa.** O braço sem skill chegou ao
`OOMKilled` com `describe` e ao seletor divergente com `describe`. Então:

> A precisão de campo vale quando alguém vai **escrever código** contra o campo. Para
> **relatar uma causa**, `describe` resolve mais barato nos dois eixos.

Melhoria conhecida e não aplicada: o passo 3 deveria abrir com `describe` e descer para
`get -o json` apenas nos campos que `describe` não distingue (`lastState` cru, `subsets`
ausente, `conditions.ready`). Não apliquei porque mudaria o método depois de medir, e a
medição seria de outra coisa.

### Tempo: o transporte domina, e é preciso dizer quanto

Medido com 3 repetições da mesma consulta:

| | Mediana |
|---|---|
| mesma consulta via MCP (`npx` por chamada) | **2,14 s** |
| mesma consulta via `kubectl` direto | **0,15 s** |
| spawn do `npx` por chamada | **1,99 s** |

**93% de cada chamada MCP é spawn do cliente**, não consulta ao apiserver. A primeira versão
usou isso para não medir tempo. O número agora está aqui, com a parcela separada, porque
medir e decompor é melhor que não medir.

No tempo de ponta a ponta das execuções reais, a skill **ganhou** no chamado 1 (269 s contra
503 s, 1,9x) e **empatou** no chamado 3 (277 s contra 272 s). Esse tempo inclui o raciocínio
do modelo, que é a parcela maior e a que eu não controlo.

A linha `tempo sem o spawn do npx` que o script imprime subtrai a mediana de overhead de
cada chamada, e **amplifica ruído**: ela produziu 1,5 s num braço de 13 chamadas, o que não
é crível. Está na evidência por honestidade de registro e eu não apoio conclusão nenhuma
nela.

### A inversão em relação à primeira medição

| | Primeira medição | Esta medição |
|---|---|---|
| chamado 1 | com skill **8**, sem skill 4 | com skill **10**, sem skill **15** |
| chamado 3 | com skill **12**, sem skill 8 | com skill **10**, sem skill **13** |
| veredito por chamadas | a skill custa 1,5x a 2x mais | a skill custa 0,67x a 0,77x |

Três coisas mudaram entre as duas, e as três empurram na mesma direção:

1. **A skill foi corrigida.** A regra "lista devolve resumo, use o singular com `name`"
   entrou depois da primeira medição, e era ela que desperdiçava duas chamadas.
2. **As `references/` saíram do caminho de execução.** O executor da primeira medição havia
   lido a solução trabalhada dos mesmos chamados. Essa contaminação, que o próprio executor
   denunciou, agora não existe, e mesmo assim o número melhorou.
3. **O braço sem skill variou muito.** Desta vez ele gastou 15 chamadas no chamado 1, com
   uma repetição por erro de parse local e um `describe` de nó que não era necessário. Na
   primeira medição ele gastou 4 e acertou rápido.

**O item 3 é o mais importante, e limita o que eu posso afirmar.** São execuções únicas de
um processo estocástico. Duas medições do mesmo par discordaram por fator de 2 a 3 em
chamadas. O que eu posso dizer com honestidade:

- **a afirmação "a skill custa mais em chamadas" não se reproduziu**, e eu a tinha publicado
- **a afirmação "a skill custa mais em tokens" se sustenta nos dois chamados**, e com margem
  grande, porque o custo fixo de 5.022 tokens não depende de sorte
- **n = 1 por célula**. Para falar de tendência seriam necessárias várias execuções por
  braço, e isso está fora do que eu fiz

### No que a skill gasta, e o que ela compra com isso

As chamadas que o método prescreve e que o executor sem skill não fez:

| Chamada | Para quê | Custo medido |
|---|---|---|
| segundo pod do mesmo ReplicaSet | confirmar que a causa é a mesma, em vez de inferir da posse do template | 1.854 tokens |
| pod do Postgres no singular | afirmar "o banco está de pé" com evidência, não por ausência na lista de problemas | 1.583 tokens |
| Deployment no singular | medir o impacto: `unavailableReplicas`, `conditions`, `generation` x `observedGeneration` | 1.087 tokens |
| `labelSelector` com o rótulo **certo** | controle. `items: []` é ambíguo entre "nenhum casa" e "o filtro foi ignorado" | 149 tokens |

A última custa 149 tokens e é a melhor da lista. O executor sem skill viu `items: []` e
concluiu "nenhum pod casa", provavelmente certo. O executor com skill gastou uma chamada
provando que o filtro estava ativo. **Uma afirmação que não depende de suposição, por 149
tokens**, é barato.

As três primeiras somam **4.524 tokens**, mais da metade do que o braço com skill consumiu
em respostas no chamado 1. Elas compram rigor: "o banco está de pé" com evidência em vez de
por omissão. **Caro, e não é o mesmo tipo de ganho da quarta.** A diferença é que a quarta
desarma uma ambiguidade concreta e as três primeiras confirmam algo que provavelmente já
era verdade.

Se eu tivesse que cortar, cortaria o pod do Postgres no singular: `describe` responde "o
banco está de pé" por 313 tokens em vez de 1.583.

## O que a skill entregou a mais

Aqui a comparação inverte, e os dois relatórios são de categorias diferentes.

### As duas execuções acertaram as duas causas

Nenhuma vantagem da skill nisto. Com e sem método, `OOMKilled` com `limits.memory: 24Mi` e
`selector: app: nyx-api` contra `labels: app: nyxapi` foram identificados corretamente, com
o campo exato.

**Se o critério for "acha a causa", a skill não se paga nestes dois casos.**

### A skill declarou a fronteira da própria ignorância

O relatório com skill registrou, por chamado, o que **não** conseguiu verificar:

- quanto de memória o kube-news precisa de fato: `kubectl_top` não existe entre as 17
  ferramentas, então "24Mi não basta" é afirmável e "256Mi basta" não é
- a lista de tags do registry: o MCP não tem ferramenta de registry
- **que a aplicação responde HTTP**: `exec_in_pod` não existe em modo não destrutivo, então
  a prova é indireta: `ready=True` significa que a readinessProbe passou, e ela é uma
  requisição real feita pelo kubelet. Não é o mesmo que ter recebido 200
- quem emite o 503, sem Ingress no cluster, a borda está fora do alcance

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
| "o pod nunca foi substituído" (chamado 2) | não existe ReplicaSet anterior. `revision: 1`, única. Não é "a nova não entrou", é **"a loja está fora"**: 0 de 3 |

A segunda muda a urgência do chamado. O executor sem skill também achou a questão do
`LimitRange`, gastando uma chamada que ele mesmo classificou como caminho errado: a skill
transforma isso em achado deliberado em vez de subproduto.

### A skill desarmou a armadilha, e sem ela o risco é concreto

No chamado 3 os pods têm `restartCount: 2` com `lastState.terminated.exitCode: 1`: falha
**já curada**, a aplicação subiu antes do Postgres aceitar conexão.

O executor **sem** skill registrou: *"distração do Terminated/Error/exit 1 no pod stg
(boot antes do Postgres, descartado sem custo)"*. Descartou, e sem gastar chamada. Mérito
dele.

O executor **com** skill tinha a regra escrita (`state: running` significa que `lastState`
é história) e também não caiu.

**Então a armadilha não pegou ninguém, e eu não posso usá-la como prova de valor da skill.**
O que posso dizer é o que o próprio executor com skill escreveu: `exitCode: 1` é o único
caso em que o log serve, e o reflexo de plantão com um 503 na mão é ler o log. Os dois
executores são modelos fortes, atentos e sem pressa. **Um plantonista humano às três da
manhã é o caso que a regra escrita protege, e isso este teste não mede.**

## Veredito, por cenário

| Cenário | A skill vale? | Pelo quê |
|---|---|---|
| causa nomeada num campo (`OOMKilled`, `ImagePullBackOff`) | **não** | `describe` resolve com 2,2x menos tokens e o braço sem método chegou à mesma causa |
| tudo verde e o cliente reclamando | **sim** | as fontes óbvias não apontam nada e o método diz onde olhar. Custou 2,76x em tokens e chegou lá |
| relatório que vai para o cliente ou para o PR | **sim** | a fronteira de incerteza e a correção do relato não saem por acaso |
| contexto escasso, janela apertada | **não** | 5.022 tokens fixos por ativação, 38% a 52% da entrada nestes dois chamados |
| alguém vai escrever código contra o campo | **sim** | é a única situação em que `get -o json` cru se paga, porque `describe` apaga ausente contra nulo |
| plantonista novo, ou às três da manhã | **sim**, e este teste não mede | os dois executores são modelos fortes e sem pressa |

## O que eu mudaria

**O que a medição de tokens obriga a mudar no método, e eu não mudei ainda:** o passo 3
deveria abrir com `kubectl_describe` e descer para `get -o json` só nos campos que
`describe` não distingue. Isso cortaria algo em torno de 40% dos tokens de resposta do
braço com skill sem perder nenhuma das duas causas. Não apliquei porque mudar o método
depois de medir transformaria a evidência em medição de outra coisa. Fica como a próxima
alteração da skill, com o número que a justifica.

**O que eu faria diferente no teste:** rodar cada braço **várias vezes**. As duas medições
do mesmo par discordaram por fator de 2 a 3 em chamadas, e com n = 1 por célula eu não
distingo efeito do método de variação de execução. Foi a lição mais cara das duas rodadas:
publiquei "a skill custa mais em chamadas" com uma amostra de um, e não se reproduziu.

**O que já está consertado desde a primeira medição:** os comandos do método estavam
escritos contra a saída do `kubectl` e não contra a do MCP, onde a lista devolve um resumo
de cinco campos; e as `references/` entravam no caminho de execução carregando a solução
trabalhada dos próprios chamados. O executor da primeira rodada denunciou as duas, não eu.
Esta rodada foi feita depois dos dois consertos, e é por isso que ela serve de linha de base
para a próxima.
