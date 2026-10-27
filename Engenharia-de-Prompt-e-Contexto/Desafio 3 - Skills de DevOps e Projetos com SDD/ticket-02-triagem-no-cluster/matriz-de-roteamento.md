# Matriz de roteamento: as duas skills disputando o mesmo território

Com as skills dos Tickets 01 e 02 instaladas, as duas falam de Kubernetes, YAML e coisa
quebrada. O agente escolhe qual carregar **apenas pela `description`** de cada uma: é o
único insumo que o roteamento tem, por desenho do Kiro: no startup só `name` e
`description` entram no contexto, e o corpo carrega depois.

## O teste tem duas fases, e a primeira não media o que prometia

**Fase 1, três rodadas de leitura de frontmatter.** Sub-agentes recebiam a instrução de ler
só o bloco de frontmatter dos dois `SKILL.md` e responder para qual skill a frase roteia,
com nível de confiança e o trecho que decidiu. Isso **não é** o mecanismo do Kiro: o
sub-agente lia as descriptions como documento e raciocinava sobre elas. O que a fase 1
mediu bem foi se o texto é **decidível**, e foi o que produziu os nove defeitos
documentados abaixo, que estão corrigidos nas descriptions de hoje.

**Fase 2, ativação real.** O que faltava era rodar as dez frases pelo mecanismo de verdade.
O obstáculo era estrutural: as skills viviam em `<repo>/.kiro/skills/`, e a raiz do
workspace da sessão não era a raiz do repositório, então nada carregava.

Resolvido instalando as duas no caminho global, que o Kiro **mescla** com o do workspace:

```
~/.kiro/skills/padrao-de-manifests-metacortex  -> <repo>/.kiro/skills/...
~/.kiro/skills/triagem-de-cluster-metacortex   -> <repo>/.kiro/skills/...
```

São symlinks para o repositório, então continua havendo uma fonte da verdade e nada
divergiu.

### Por que sub-agente serve como sessão limpa

Medido antes de usar, com uma sonda que não fazia nada além de responder:

> **ITENS_DISPONIVEIS:** `padrao-de-manifests-metacortex`, `triagem-de-cluster-metacortex`
> **`disclose_context` disponível:** sim

**Sub-agente faz descoberta própria.** Ele tem contexto novo, não herda a conversa, e vê as
duas skills com `name` e `description`, que é exatamente o insumo do roteamento. O que ele
**não** replica é a origem da mensagem: aqui ela vem do agente pai, não de uma pessoa
digitando no chat da IDE.

Cada uma das dez frases foi para um sub-agente que recebeu **só a frase**, sem nenhuma
menção a skills, mais um pedido de instrumentação no fim: quais itens estavam disponíveis,
quais foram ativados, em que momento, e o que na mensagem decidiu.

**O pedido de instrumentação é o risco deste método**, porque mencionar "itens disponíveis"
pode induzir a ativar. As frases 9 e 10 são o controle: se o pedido induzisse ativação, elas
também ativariam. Não ativaram.

## Resultado: as dez frases, ativação real

| # | Frase | Fase 1 previa | **Ativou de fato** | Momento |
|---|---|---|---|---|
| 1 | "o pod do nyx-prod não sobe" | triagem (alta) | **triagem** | antes de qualquer ação |
| 2 | "por que esse deployment está 0/3" | triagem (alta) | **triagem** | antes de qualquer ação |
| 3 | "o service do nyx-stg não tem endpoint" | triagem (alta) | **triagem** | antes de qualquer ação |
| 4 | "revisa esse deployment antes de eu subir" | manifests (alta) | **manifests** | antes de qualquer ação |
| 5 | "esse manifesto está no padrão da casa?" | manifests (alta) | **manifests** | antes de qualquer ação |
| 6 | "cria um Deployment novo do zero pra mim" | manifests (alta) | **manifests** | antes de qualquer ação |
| 7 | "esse manifesto não sobe no cluster" | AMBAS (baixa) | **NENHUMA, e pediu a mensagem de erro** | não ativou |
| 8 | "o Service do nyx não está entregando tráfego" | triagem (alta) | **triagem** | antes de qualquer ação |
| 9 | "o que é um DaemonSet?" | NENHUMA (alta) | **NENHUMA** | não ativou |
| 10 | "provisiona uma VM nova no Construct" | NENHUMA (alta) | **NENHUMA** | não ativou |

**Dez de dez com o comportamento desejado.** As duas skills apareceram em
`ITENS_DISPONIVEIS` nas dez execuções, então a descoberta é confiável.

Nas sete ativações, todas foram declaradas como **antes de qualquer outra ação**, que é o
comportamento esperado: o Kiro trata a ativação como requisito bloqueante quando a
`description` casa.

### A frase 7 saiu melhor do que o previsto, e isso inverte a ressalva antiga

A fase 1 deu `AMBAS (baixa confiança)` nas três rodadas, e eu publiquei que a medição era um
"limite superior otimista". **Na frase 7 ela foi pessimista.**

Na execução real o agente **não ativou nada** e fez exatamente o que a rodada 3 escreveu nas
duas descriptions: perguntou qual era a mensagem de erro antes de rotear. O registro dele:

> **MOTIVO:** sem a mensagem de erro não se distingue YAML recusado de falha de cluster, e a
> regra manda pedir a mensagem antes de rotear

A fase 1 não conseguia observar isso porque a pergunta era "para qual skill isto roteia?", o
que **força uma escolha**. O mecanismo real tem uma terceira saída que a simulação proibia:
não rotear e perguntar. O conserto da rodada 3 funcionou, e a simulação não tinha como
mostrar.

### Um defeito novo, que só a execução real revelou

As três frases de triagem fizeram a triagem completa contra o cluster, e acertaram as três
causas (limite de 24Mi, tag `v1.14.2` inexistente, `app: nyx-api` contra `app: nyxapi`).
Mas **nenhuma das sessões tinha o servidor MCP de Kubernetes**.

A skill de triagem prescreve chamadas no formato `kubectl_get {"resourceType":...}`, que é
a interface do MCP. Sem o servidor, os três executores caíram no `kubectl` do shell por
conta própria e se restringiram aos verbos de leitura. Um deles registrou:

> não há servidor MCP de Kubernetes instalado nesta sessão, então fiz a triagem com
> `kubectl` do shell, restrito aos verbos de leitura (`get`, `describe`, `logs`)

Duas leituras disso, e as duas importam:

- **é defeito de portabilidade da skill.** Ela assume um transporte que pode não existir, e
  não diz o que fazer quando não existe. O método sobreviveu pela competência do executor,
  não pelo texto
- **é a melhor evidência de que a garantia de só-leitura é da skill, e não da ferramenta.**
  Sem o servidor em modo não destrutivo, nada impedia um `kubectl delete`. O que segurou foi
  a instrução escrita. É a tese do ticket, confirmada pelo caminho que eu não planejei

Fica como correção pendente: a skill precisa de uma linha dizendo que, sem MCP, o
equivalente é `kubectl` restrito aos mesmos cinco verbos, e que a lista de proibidos
continua valendo.

### O que a frase 6 mostrou

A fase 1, rodada 2, tinha achado a frase 6 "sem dono": a description prometia gerar e
barrava pedido sem manifesto. O conserto foi "serve para gerar manifesto de um projeto que
ainda não tem nenhum: peça o repositório antes".

Na execução real o agente ativou a skill de manifests, **recusou escrever YAML sem ler o
projeto** e listou os cinco fatos que não têm default seguro (porta, probes e o que cada uma
toca, nomes das variáveis, caminhos de escrita, migração de schema). Depois procurou um
repositório no workspace, não achou, e pediu. O conserto da rodada 2 funcionou.

## Os nove defeitos que a fase 1 achou, e o que eu mudei por causa deles

Esta seção é o histórico das três rodadas de leitura de frontmatter. Ela continua valendo:
é o trabalho que produziu as descriptions que a fase 2 mediu, e cada defeito aqui é uma
alteração concreta de texto. **A fase 2 passou dez de dez com estas descriptions**, não com
as originais.

### Rodada 1: cinco defeitos nas descriptions

**1. O qualificador "em produção" contradizia o critério da própria skill.** A description do
padrão excluía "Service sem endpoint **em produção**". A frase 3 é sobre `nyx-stg`, que não
é produção: lido ao pé da letra, o caso de staging **não estava excluído** e virava empate.
Pior: o critério de fronteira que a própria skill declara é *arquivo versus cluster*, não
ambiente. O qualificador não tinha função nenhuma ali.
→ Removido.

**2. "não sobe" não existia na skill de triagem.** É provavelmente a forma mais frequente de
relatar o sintoma, e a description enumerava só os nomes técnicos (`CrashLoopBackOff`,
`OOMKilled`). A frase 1 roteou certo por pressuposição ("existe um Pod, logo houve apply")
e não por evidência no texto.
→ "pod que não sobe, não subiu ou reinicia sozinho" entrou na lista.

**3. Nenhuma das duas nomeava o evento "o apply foi recusado".** A frase 7 caiu em cima da
fronteira, e o padrão só a disputava se o usuário dissesse a palavra "Construct".
→ As duas ganharam vocabulário de apply, em polaridades distintas.

**4. Nenhuma tinha cláusula negativa para pergunta conceitual.** As duas são densas em
vocabulário Kubernetes, então a frase 9 cai numa região de alta similaridade sem repulsão
explícita. O sub-agente acertou por leitura semântica; um roteador por embedding erraria.
→ "Nem para explicar conceito de Kubernetes" nas duas.

**5. "Construct" aparecia solto na description do padrão.** Na frase 10, sobre VM, essa era
a única âncora lexical disponível e apontava para a skill errada.
→ O termo saiu da description.

### Rodada 2: dois defeitos que eu introduzi consertando a rodada 1

**6. A frase 6 ficou sem dono.** A correção do defeito 4 adicionou "nem para pedido que não
tenha um manifesto ou um projeto concreto". Mas a description abre com "Confere e **gera**
manifests". Gerar do zero é exatamente um pedido sem manifesto: prometido na primeira frase
e barrado na última. A confiança caiu de alta para baixa.
→ Reescrito: "serve para gerar manifesto de um projeto que ainda não tem nenhum: peça o
repositório antes".

**7. Eu reivindiquei território que a própria skill nega.** A correção do defeito 3 colocou
"apply RECUSADO por schema, campo inválido ou **admission policy**" no padrão: numa skill
que declara "nunca o estado do cluster". **Recusa de admission policy é veredito que só
existe depois de falar com o cluster.** Contradição interna, apontada pela rodada 2.
→ `admission policy` saiu do padrão. Falha de ambiente: RBAC, quota, contexto errado,
cluster inalcançável: foi para a triagem, "porque aí a resposta está no cluster e não no
YAML".

### Rodada 3: dois últimos, um deles aritmético

**8. A triagem negava e prometia o mesmo momento.** Ela dizia "NÃO use **antes do apply**" e
em seguida reivindicava "o apply que falha por motivo de cluster: RBAC negado, cluster
inalcançável". Com RBAC negado não existe aplicação rodando e o apply não foi aceito: o veto
estava largo demais e cobria o caso que a própria frase seguinte reivindicava.
→ O veto virou "NÃO use para revisar nem escrever manifesto", que é a lista que ela mesma
enumera depois.

**9. `15 + 3 = 18`, não 19.** A `compatibility` do padrão dizia "sem ele o script confere 15
das 19 regras e avisa que as regras 2.1, 3.1 e 3.6 NÃO foram conferidas". Faltava uma. A
19ª é a **2.6**, que é manual com ou sem Trivy e não estava mencionada em lugar nenhum.
→ Reescrita com as três parcelas fechando em 19.

## As três frases que não roteiam, e o que fazer com cada uma

### Frase 7: a ambiguidade é da frase, e o conserto foi ensinar a perguntar

"esse manifesto não sobe no cluster" ficou em **AMBAS** nas três rodadas da fase 1. Na
execução real ficou em **NENHUMA**, com o agente pedindo a mensagem de erro.

O critério existe e está escrito nas duas descriptions:

| Natureza da falha | Skill | Por quê |
|---|---|---|
| conteúdo do YAML rejeitado (schema, campo inválido) | padrão de manifests | a resposta está no arquivo |
| falha de ambiente (RBAC, quota, contexto, cluster fora) | triagem | a resposta está no cluster |
| apply aceito e workload não fica pronto | triagem | é execução |

**O que falta não está na description: está na frase.** Ela não diz qual foi o erro, e o
critério depende exatamente disso. Nenhuma reescrita resolve: a informação não foi fornecida.

Foi o que a rodada 3 cobrou, e é o ajuste que eu fiz em vez de insistir no texto: as duas
descriptions passaram a instruir **"se o erro do apply não for conhecido, peça a mensagem
antes de decidir a rota"**.

**E a fase 2 provou que a instrução pega.** O agente não ativou nada, listou a bifurcação
com os dois ramos corretos, e esperou. Carregar a skill errada para descobrir depois é pior
que perguntar, e o texto conseguiu dizer isso.

Isto é o caso que o enunciado antecipa: *"nem todo disparo errado se corrige mexendo na
skill: às vezes a frase é que estava mal formulada."* A diferença é que a correção **não**
foi deixar a ambiguidade de pé: foi transformá-la numa pergunta.

### Frases 9 e 10: fora de escopo, e `NENHUMA` é resposta

"o que é um DaemonSet?" é pergunta didática: o agente responde com conhecimento geral e não
carrega skill nenhuma. "provisiona uma VM nova no Construct" é provisionamento de
infraestrutura, fora de Kubernetes.

A frase 10 merece um cuidado específico, e o sub-agente nomeou bem: **não se deve carregar a
triagem para "tentar fazer"**. A description promete não escrever, e o `compatibility` avisa
que a garantia é da skill e não da ferramenta: o MCP mantém `apply`, `create`, `patch`,
`scale` e Helm disponíveis. Carregar a skill de triagem para uma tarefa de escrita é
exatamente o cenário em que essa promessa quebra.

`NENHUMA` é resposta válida. Forçar rota para a skill menos errada é pior que não rotear.

## O achado estrutural sobre anti-gatilho

A observação mais útil das três rodadas, e ela não estava na minha lista de perguntas:

> Cada description **recita, literalmente, o vocabulário-gatilho da outra** dentro da sua
> cláusula de exclusão. Negação é semântica; busca por palavra-chave ou embedding vê os
> termos, não o "NÃO".

A description do padrão contém `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`,
`Service sem endpoint` e `503`: cinco sintomas de runtime no texto de uma skill que declara
"nunca o estado do cluster". E a description da triagem contém a frase 5 **palavra por
palavra, com as aspas**, que é o match lexical mais forte que existe para aquela frase nas
duas skills somadas.

Isso é faca de dois gumes, e os dois lados apareceram na medição:

- **O lado bom:** o apontamento cruzado nominal: "isso é triagem de cluster, outra skill" /
  "são do padrão de manifests, outra skill": é o que resolve 8 das 10 rotas. Sem ele,
  metade da tabela viraria `AMBAS`.
- **O lado ruim:** num roteador que não leia polaridade, o território fica 100% sobreposto
  nesses termos.

Mantive o anti-gatilho nominal, porque o matching do Kiro é semântico e o ganho medido é
grande. Mas a lição generaliza: **o que de fato roteia frase que não está em nenhuma
enumeração é o critério geral, não a lista.** A melhor linha das duas descriptions é

> "O limite é a fonte da verdade: esta skill lê arquivo YAML e código-fonte, nunca o estado
> do cluster."

É a única que entrega uma regra em vez de uma lista. A triagem tem a equivalente ("com o
estado do cluster como fonte da verdade") e a rodada 3 observou que ela está **diluída no
meio da enumeração**, e por isso menos operante. Fica como melhoria conhecida e não
aplicada: subir essa frase para o começo custaria caracteres que a description já não tem
(960 de 1024).

## O que esta medição prova, e o que ela não prova

**Prova:** com as descriptions de hoje e as duas skills descobertas pelo runtime, as dez
frases produziram o comportamento desejado em dez de dez, e as sete ativações aconteceram
antes de qualquer outra ação. A descoberta funcionou nas dez execuções. Os dois controles
negativos não ativaram, o que descarta a hipótese de que o pedido de instrumentação estivesse
induzindo ativação.

**Não prova, e vale listar:**

- **n = 1 por frase.** Ativação é decisão de modelo, não função determinística. Dez acertos
  em dez tentativas únicas não é o mesmo que dez de dez repetido.
- **a mensagem vem do agente pai, não de uma pessoa.** O mecanismo de descoberta e o insumo
  (`name` + `description`) são idênticos, verificados pela sonda. O enquadramento da
  mensagem não é.
- **só duas skills no conjunto.** O roteamento disputado é entre duas. Com vinte skills
  instaladas a sobreposição lexical descrita acima pesa mais, e nada aqui mede isso.
- **as frases são minhas.** Foram escritas por quem conhece as duas descriptions, o que é um
  viés estrutural que nenhuma rodada corrige. A frase 7 é a única que eu escrevi para
  quebrar o critério, e é a que rendeu mais.
- **as frases 4, 5, 6 e 7 não vinham com manifesto anexado.** Numa sessão real haveria um
  arquivo em contexto, e o arquivo é insumo de roteamento que este teste não ofereceu.

## O que a fase 1 errou, como método

Fica registrado porque é a correção que o retorno da avaliação cobrou, e ela é justa.

A fase 1 pedia ao sub-agente que **escolhesse** uma rota lendo o frontmatter. Isso tem dois
problemas que eu não vi na época:

1. **Mede leitura, não ativação.** Um modelo lendo "NÃO use para X" entende a negação. O
   mecanismo de ativação pode ser mais sensível à presença dos termos que à polaridade, e eu
   escrevi exatamente isso na seção de anti-gatilho sem perceber que a medição não podia
   verificá-lo.
2. **Proíbe a resposta certa.** Perguntar "para qual skill isto roteia?" elimina a saída
   "nenhuma, e eu pergunto antes". Era a resposta certa da frase 7, e a fase 1 a tornou
   impossível de observar.

O que a fase 1 entregou de real foram os **nove defeitos de texto**. Isso vale, e é o
trabalho que fez a fase 2 passar. O que não valia era a tabela de rotas, e ela foi
substituída.
