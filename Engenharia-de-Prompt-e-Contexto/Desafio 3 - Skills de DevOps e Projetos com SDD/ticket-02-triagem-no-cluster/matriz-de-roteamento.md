# Matriz de roteamento: as duas skills disputando o mesmo território

Com as skills dos Tickets 01 e 02 instaladas, as duas falam de Kubernetes, YAML e coisa
quebrada. O agente escolhe qual carregar **apenas pela `description`** de cada uma: é o
único insumo que o roteamento tem, por desenho do Kiro: no startup só `name` e
`description` entram no contexto, e o corpo carrega depois.

## Método do teste

Despachei **sub-agentes em sessão limpa**, cada um com uma instrução dura: ler **só o bloco
de frontmatter** dos dois `SKILL.md`, e nada mais. Proibido ler o corpo, as `references/`,
os `scripts/` ou qualquer artefato dos tickets.

Isso importa. Se o sub-agente lesse o corpo da skill, ele acertaria o roteamento por
entender o conteúdo, e o roteamento real **não lê o corpo**. Medir com o corpo disponível
mediria a coisa errada.

Além da rota, pedi **confiança** e **o trecho exato da description que decidiu**. A
confiança é o que separa "acertou" de "acertou por sorte", e o trecho é o que permite
consertar o texto em vez de adivinhar.

Foram **três rodadas**: a inicial, uma depois das correções, e uma final.

## Resultado das três rodadas

| # | Frase | Rodada 1 | Rodada 2 | Rodada 3 (final) |
|---|---|---|---|---|
| 1 | "o pod do nyx-prod não sobe" | triagem (média) | triagem (alta) | **triagem (alta)** |
| 2 | "por que esse deployment está 0/3" | triagem (alta) | triagem (alta) | **triagem (alta)** |
| 3 | "o service do nyx-stg não tem endpoint" | triagem (média) | triagem (alta) | **triagem (alta)** |
| 4 | "revisa esse deployment antes de eu subir" | manifests (alta) | manifests (alta) | **manifests (alta)** |
| 5 | "esse manifesto está no padrão da casa?" | manifests (alta) | manifests (alta) | **manifests (alta)** |
| 6 | "cria um Deployment novo do zero pra mim" | manifests (alta) | manifests (**baixa**) | **manifests (alta)** |
| 7 | "esse manifesto não sobe no cluster" | **AMBAS** (baixa) | **AMBAS** (baixa) | **AMBAS (baixa)** |
| 8 | "o Service do nyx não está entregando tráfego" | triagem (alta) | triagem (alta) | **triagem (alta)** |
| 9 | "o que é um DaemonSet?" | NENHUMA (alta) | NENHUMA (alta) | **NENHUMA (alta)** |
| 10 | "provisiona uma VM nova no Construct" | NENHUMA (alta) | NENHUMA (alta) | **NENHUMA (alta)** |

**Confiança alta: 6 → 8 → 9 de 10.** Nenhuma rota mudou de destino entre as rodadas; o que
mudou foi a confiança, que é o sinal de que o texto ficou decidível em vez de adivinhável.

## O que errou, e o que eu mudei por causa disso

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

### Frase 7: ambiguidade real, e ela permanece

"esse manifesto não sobe no cluster" ficou em **AMBAS** nas três rodadas, e eu decidi
**deixar assim**.

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
antes de decidir a rota"**. Perguntar é a resposta certa, e carregar a skill errada para
descobrir depois é pior que perguntar.

Isto é o caso que o enunciado antecipa: *"nem todo disparo errado se corrige mexendo na
skill: às vezes a frase é que estava mal formulada."*

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

## Limitação honesta deste teste

Os sub-agentes **simularam** o roteamento lendo as descriptions e raciocinando sobre elas.
Não é o mecanismo real do Kiro, que faz o matching por conta própria no startup.

O que este método mede bem: se o texto é **decidível**: se existe no frontmatter informação
suficiente para escolher, e qual trecho carrega essa decisão. Foi o que produziu os nove
defeitos.

O que ele **não** mede: se o matcher real do Kiro, com o mesmo texto, escolhe igual. Um
roteador por embedding é mais sensível à sobreposição lexical descrita acima do que um
sub-agente que lê a palavra "NÃO". A medição é um limite superior otimista.
