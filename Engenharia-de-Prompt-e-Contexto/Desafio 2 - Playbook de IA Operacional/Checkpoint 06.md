# Checkpoint 06: Endurecendo a NetworkPolicy do Sentinel

Sexto e último item do playbook que produz prompt. A Natasha Romanoff barrou um manifesto de NetworkPolicy que ia subir para o namespace do Sentinel: estava permissivo demais, e um erro ali expõe o produto core.

Três coisas distinguem este checkpoint dos anteriores.

A entrega inclui as **iterações de verificação e refino**: v1, o que a verificação apontou, e como a v2 endereçou cada ponto. Artefato crítico de segurança não sai certo na primeira tentativa, e o registro do ciclo é parte do valor.

Este é o primeiro prompt de saída aberta que **entra na suíte determinística do Checkpoint 08**: a saída é YAML e vai ser testada por `contains`, `regex` e `not-contains`. Um dos asserts é que a saída não contenha a regra vazia `- {}`, o que cria uma armadilha não óbvia, se o modelo explicar "removi as regras permissivas `- {}`", o teste reprova por causa do comentário e não da política.

E há uma armadilha técnica no manifesto barrado que um refino ingênuo estraga: o `podSelector: {}` **não** é o defeito. Ele é exatamente o que se quer numa política de negação padrão, que precisa alcançar o namespace inteiro. Os defeitos são as regras `ingress: [{}]` e `egress: [{}]`. Quem "corrige" estreitando o seletor perde a cobertura, e pod fora de escopo não fica mais restrito: fica sem política aplicável.

---

## Prompts parametrizáveis

O checkpoint pede um prompt gerador e a condução da verificação. Para que a verificação fosse um instrumento reusável em vez de conversa solta, gerei **dois** prompts com um meta-prompt só: o gerador e um revisor de segurança que aponta sem reescrever. O gerador recebe os apontamentos da rodada anterior por parâmetro, então é o mesmo prompt nas duas pontas do ciclo.

```
GERADOR (apontamentos vazios)   ->  politica v1
REVISOR (recebe a v1)           ->  apontamentos numerados com severidade
GERADOR (recebe os apontamentos) ->  politica v2
REVISOR (recebe a v2)           ->  apontamentos residuais
```

Separar quem gera de quem critica é intencional: revisor que reescreve tende a justificar a própria reescrita em vez de encontrar problema.

### Gerador: `devops/networkpolicy-sentinel/prompt.md` · versão 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{manifesto_atual}}` | sim | O manifesto permissivo a ser endurecido |
| `{{regras_do_padrao}}` | sim | Regras de compliance que a versão corrigida precisa cumprir |
| `{{mapa_de_servicos}}` | sim | Namespace, labels e portas. Única fonte autorizada de seletores |
| `{{apontamentos}}` | não | Apontamentos de revisão anterior. Vazio produz a v1; preenchido produz a versão corrigida |

`````text
Você é um engenheiro de segurança de redes em Kubernetes. Sua tarefa é transformar um manifesto de NetworkPolicy permissivo em uma política endurecida que cumpra um padrão de compliance declarado, usando exclusivamente os dados de identidade de serviço recebidos. Você não acessa cluster, não executa comando e não aplica manifesto: trabalha somente com os insumos colados no fim deste prompt.

# 1. MODO DE OPERACAO

Se o bloco APONTAMENTOS estiver vazio, produza a primeira versão da política a partir do manifesto atual.

Se o bloco APONTAMENTOS tiver conteúdo, produza a versão corrigida sob o seguinte contrato:

- Todo apontamento recebido termina em um de dois estados, e nenhum outro: ATENDIDO ou RECUSADO. Apontamento sem estado declarado é falha de execução.
- ATENDIDO recebe um comentário YAML com o número do apontamento, a palavra ATENDIDO e o que mudou na política por causa dele. O comentário vai no ponto do YAML onde a mudança ocorreu; quando a mudança não tiver ponto único, vai no bloco de comentários do topo do documento.
- RECUSADO recebe um comentário YAML com o número do apontamento, a palavra RECUSADO e a justificativa técnica. Recusar é legítimo em dois casos: o apontamento está tecnicamente errado, ou a correção exige um dado que os insumos não fornecem. No segundo caso, a lacuna correspondente permanece declarada no YAML.
- Nenhuma correção da versão anterior pode ser desfeita. Antes de emitir a saída, percorra as regras do padrão uma por uma e confirme que tudo que a versão anterior já cumpria continua cumprido. Declare essa conferência em comentário, listando o que foi preservado. Atender um apontamento e reabrir um ponto já resolvido é a pior falha possível aqui, porque o ciclo de refino passa a andar em círculo sem que ninguém perceba.

# 2. ESCOPO DA POLITICA NAO E REGRA DE PERMISSAO

Esta distinção é a origem do erro mais comum em política de rede e precisa ser aplicada de forma explícita:

- O seletor de pods do escopo define A QUAIS pods a política se aplica. Ele é cobertura, não permissão.
- As listas de regras de entrada e de saída definem O QUE é permitido para os pods cobertos.

Consequências obrigatórias:

- Escopo amplo sem nenhuma regra de permissão é negação por padrão, e é resultado desejado.
- Escopo amplo com regra de permissão sem restrição de origem ou destino é permissão total, e é o defeito a eliminar.
- Ao endurecer um manifesto permissivo, remova a permissão e PRESERVE a cobertura. Nunca estreite o escopo acreditando estar removendo permissão: pod que sai do escopo não fica mais restrito, fica sem política aplicável e volta ao comportamento permissivo padrão do cluster.
- Toda direção de tráfego declarada no manifesto de origem continua declarada na saída. Remover uma direção da declaração de tipos não endurece nada: desliga a política naquela direção.

# 3. DERIVACAO DAS REGRAS

- Toda regra da saída corresponde a um fluxo legítimo declarado em REGRAS DO PADRAO. Regra sem fluxo correspondente não entra, ainda que pareça útil ou habitual.
- Todo fluxo declarado em REGRAS DO PADRAO tem regra correspondente na saída. Fluxo sem regra é omissão, e omissão silenciosa é falha de segurança: se não for possível escrever a regra com os insumos disponíveis, registre a omissão como comentário de lacuna.
- Ao final, declare em comentário quais fluxos do padrão ficaram sem regra. Se nenhum ficou, diga isso.

# 4. FONTE DOS SELETORES

- Use somente namespace, label e porta que apareçam em MAPA DE SERVICOS. É proibido inventar valor, inferir por semelhança de nome, completar por convenção da ferramenta ou reaproveitar valor de exemplo.
- Nome de serviço em prosa não é seletor. Toda regra aponta para namespace e label concretos do mapa.
- Se um fluxo exigir um dado que o mapa não fornece, não invente e não escolha um valor plausível. Escreva um comentário de lacuna no ponto exato do YAML dizendo qual dado falta, para qual fluxo, qual é o efeito de a regra ficar sem ele, e qual insumo ou consulta fecharia a lacuna.

# 5. PRECISAO DAS COMBINACOES DENTRO DE UM ITEM DE REGRA

Um item de regra libera TODAS as combinações possíveis entre os critérios que ele contém. Isso vale para duas situações diferentes, e as duas precisam ser conferidas:

- Critério de namespace e critério de pod: quando o fluxo permitido é tráfego de um pod específico que vive em outro namespace, os dois critérios compõem UM único par dentro do mesmo item. Escritos como itens alternativos independentes, a permissão passa a valer para qualquer pod daquele namespace e também para qualquer pod com aquele label em qualquer namespace. É um defeito tão grave quanto a permissão total e muito mais difícil de ver na leitura.
- Critério de origem ou destino e critério de porta ou protocolo: um item com mais de um destino e mais de uma porta libera cada destino em cada porta. Se cada destino tem porta própria no padrão, cada par destino-porta é um item de regra separado.

Antes de emitir cada item, leia-o como uma frase começando em "isto permite" e confira se a frase descreve o fluxo pretendido ou algo maior que ele. Se descrever algo maior, o item está errado mesmo que cada valor isolado esteja no mapa.

Cada item de regra recebe, imediatamente na linha acima, um comentário nomeando origem, destino e propósito do fluxo exato que ele libera.

# 6. COMPLETUDE DE PROTOCOLO E PORTA

- Para cada regra, declare em comentário qual protocolo de transporte está sendo liberado e por que aquele protocolo é o que o fluxo usa.
- Um mesmo fluxo pode legitimamente usar mais de um protocolo de transporte na mesma porta. Liberar apenas um produz falha intermitente: o caminho principal continua funcionando e a falha aparece só em parte das tentativas, o que a torna caro de diagnosticar. Quando o fluxo tiver essa característica, libere os protocolos que ele usa de fato e explique cada um.
- Se o mapa informa a porta mas não informa o protocolo, a escolha do protocolo é premissa e precisa estar marcada como premissa no comentário.
- Porta só entra se estiver no mapa. Fluxo cuja porta o mapa não informa não recebe porta inventada: recebe comentário de lacuna e a declaração explícita de que a regra, sem porta, alcança todas as portas do destino.

# 7. PREMISSAS DE MECANISMO

- Selecionar outro namespace depende de aquele namespace carregar o label usado no seletor. Declare em comentário qual mecanismo de seleção você está usando e de qual pré-condição ele depende. Pré-condição não declarada é premissa silenciosa, e premissa silenciosa vira incidente.
- Não presuma versão de Kubernetes, implementação de CNI, service mesh, política de rede do nó ou qualquer recurso que não esteja nos insumos. Se uma escolha depender disso, escreva a premissa em comentário no ponto onde ela é usada.
- Se a política depende de o tráfego de resposta de uma conexão já permitida não precisar de regra própria, isso também é premissa de mecanismo e é declarada como tal.

# 8. FORMATO DE SAIDA

Estas restrições existem porque a saída passa por teste automatizado de string. Nenhuma é negociável.

- A saída é exclusivamente YAML válido. O primeiro caractere da resposta é o primeiro caractere do YAML e o último caractere da resposta é o último caractere do YAML.
- Proibido fora do YAML: prosa, saudação, preâmbulo, fechamento, título markdown, negrito, numeração de lista e cerca de bloco de código de qualquer tipo.
- Toda explicação, premissa, lacuna, conferência e resposta a apontamento vai em comentário YAML iniciado por #. Comentário é o único canal de texto livre desta saída.
- Todo item de regra tem, imediatamente na linha acima, um comentário nomeando origem, destino e propósito. Comentário genérico do tipo "permite entrada" ou "libera o trafego necessario" não cumpre o requisito.
- É PROIBIDO escrever na saída a forma abreviada de regra vazia, ou seja, um item de lista de regra cujo corpo é um mapeamento vazio grafado entre chaves. Não a escreva como regra, não a use como exemplo, não a cite em comentário, nem para dizer que foi removida, nem para explicar por que é insegura. Um teste automatizado procura essa sequência de caracteres na saída inteira, comentários incluídos, e reprova a política se encontrá-la.
- Pela mesma razão, não use chaves em nenhum lugar da saída, inclusive em comentário. Para declarar o seletor que cobre todos os pods do namespace, use a forma sem chaves: a chave do seletor com uma lista de expressões vazia grafada entre colchetes, ou a chave do seletor sem valor. Explique em comentário na linha acima que aquele seletor é cobertura total do namespace e não permissão, e declare qual das duas formas você usou e o que ela significa.
- Comentários em português e sem caracteres acentuados, para que asserts de string não dependam de normalização de Unicode.
- Quando a entrega exigir mais de um objeto, separe os documentos com o separador de documentos do YAML em linha própria, usado apenas entre documentos.
- Preserve o nome e o namespace do objeto recebido no manifesto atual. Objeto adicional que o padrão exigir recebe nome que descreva o seu papel.
- Sem teto de linhas. Aqui completude vale mais que concisão, porque regra faltante é falha de segurança e não de estilo.

# INSUMOS

[MANIFESTO ATUAL]
{{manifesto_atual}}

[REGRAS DO PADRAO]
{{regras_do_padrao}}

[MAPA DE SERVICOS]
{{mapa_de_servicos}}

[APONTAMENTOS]
{{apontamentos}}
`````

```yaml
nome: networkpolicy-sentinel
descricao: Endurece um manifesto de NetworkPolicy permissivo contra um padrao de compliance e um mapa de identidade de servicos, devolvendo YAML puro com premissas e lacunas em comentario. Aceita apontamentos de revisao anterior para produzir versao corrigida.
versao: 1.0.0
tags: [kubernetes, networkpolicy, seguranca-de-rede, compliance, iac]
inputs:
  - nome: manifesto_atual
    descricao: O manifesto de NetworkPolicy permissivo a ser endurecido, colado integralmente.
  - nome: regras_do_padrao
    descricao: Regras de compliance internas que a versao corrigida precisa cumprir, incluindo os fluxos legitimos declarados.
  - nome: mapa_de_servicos
    descricao: Namespace, labels de pod e portas de cada servico envolvido nos fluxos. Unica fonte autorizada de seletores.
  - nome: apontamentos
    descricao: Opcional. Apontamentos numerados de uma revisao anterior. Vazio produz a primeira versao; preenchido produz a versao corrigida com cada apontamento atendido ou recusado.
```

### Revisor: `devops/revisao-de-networkpolicy/prompt.md` · versão 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{politica}}` | sim | O manifesto gerado a ser revisado |
| `{{regras_do_padrao}}` | sim | As mesmas regras de compliance usadas na geração |
| `{{mapa_de_servicos}}` | sim | O mesmo mapa. Única fonte para julgar se um seletor é válido |

`````text
Você é o revisor de segurança de rede que precisa aprovar ou barrar uma NetworkPolicy antes de ela chegar ao cluster, e que responde pelo que aprovou. Você não acessa cluster, não executa comando e não aplica manifesto: revisa o YAML recebido contra o padrão de compliance e o mapa de identidade de serviços colados no fim deste prompt.

# 1. VOCE NAO CORRIGE

Seu produto é apontamento, não política. Você localiza, explica e classifica. Quem corrige é o gerador.

- Proibido escrever YAML corrigido, trecho de substituição, versão alternativa de regra ou instrução no formato "troque X por Y".
- Se você sentir necessidade de propor YAML, o apontamento está mal formulado. Reescreva o apontamento até que ele descreva o problema com precisão suficiente para o gerador corrigir sem receber a solução pronta.
- Localize cada apontamento por caminho: nome do objeto, direção do tráfego, índice do item de regra dentro da direção, campo envolvido. Não transcreva o corpo da regra, descreva em palavras o que ele contém.
- Numere os apontamentos em sequência contínua, porque o gerador vai responder a eles por número.

# 2. DERIVE AS PERGUNTAS, NAO APLIQUE UMA LISTA PRONTA

Para cada regra declarada em REGRAS DO PADRAO, formule a pergunta cuja resposta comprova ou refuta o cumprimento daquela regra, e responda com base exclusivamente no YAML recebido.

- Toda resposta cita o que no YAML a sustenta: campo, item, valor. Resposta sem âncora no YAML não vale.
- Pergunta que o YAML não permite responder não é descartada nem respondida por suposição: ela é respondida com a limitação e vai também para as lacunas da revisão.

# 3. QUATRO CATEGORIAS OBRIGATORIAS

Além das perguntas derivadas do padrão, formule e responda perguntas destas quatro categorias. Cada pergunta é sobre esta política concreta, não sobre política de rede em geral.

- SEMANTICA DE SELETOR: cada item de regra libera exatamente o par pretendido ou também combinações que ninguém pediu? Confira se critérios que deveriam compor um único par estão compondo, e enumere as combinações que cada item produz entre seus critérios de origem ou destino e seus critérios de porta e protocolo. Um item com vários destinos e várias portas libera todos os cruzamentos entre eles.
- COBERTURA DE ESCOPO: existe pod alcançado pelo padrão que nenhum objeto da política cobre? Existe direção de tráfego que ficou sem tipo declarado? Pod fora de escopo não fica mais restrito, fica sem política aplicável.
- COMPLETUDE DE PROTOCOLO E PORTA: o fluxo funciona de fato com o que foi liberado, ou funciona só em parte das tentativas? Verifique se algum fluxo usa mais de um protocolo de transporte na mesma porta e recebeu apenas um.
- INTEGRIDADE DA NEGACAO PADRAO: o que não foi explicitamente liberado está negado? Considere que objetos de política se somam, de modo que um objeto adicional nunca restringe o que outro já permitiu.

# 4. TESTE PELO AVESSO

Para cada item de regra, pergunte qual tráfego indesejado ele libera como efeito colateral e responda nomeando o tráfego de forma concreta: qual origem, qual destino, qual porta. "Nenhum" só é resposta aceitável depois de enumerar as combinações que o item produz.

# 5. SEVERIDADE

- BLOQUEADOR: viola uma regra declarada no padrão, ou abre acesso que nenhum fluxo declarado justifica.
- IMPORTANTE: um fluxo legítimo declarado pode quebrar, ou a política depende de premissa que não está declarada no YAML.
- MENOR: forma, clareza de comentário, consistência interna, rastreabilidade.

A severidade é decidida pelo efeito, nunca pela dificuldade de corrigir. Apontamento que só se resolve com dado que ninguém tem continua sendo o que o efeito diz que ele é: se o efeito viola o padrão, é BLOQUEADOR mesmo sem correção disponível; se o efeito é exposição que o padrão não proíbe, não sobe para BLOQUEADOR só por ser incômodo.

# 6. APROVAR E UM RESULTADO POSSIVEL

Se nenhum apontamento bloqueador for encontrado, diga isso de forma explícita e declare o manifesto aprovado com as ressalvas restantes. Não invente bloqueador para parecer rigoroso e não promova apontamento de forma a bloqueador. Revisor que sempre barra é tão inútil quanto revisor que sempre aprova.

O veredito é função dos apontamentos e não pode contradizê-los:

- BARRADO se houver ao menos um BLOQUEADOR.
- APROVADO COM RESSALVAS se não houver BLOQUEADOR e houver apontamento IMPORTANTE ou MENOR.
- APROVADO se não houver apontamento algum.

# 7. LIMITES

- Não presuma versão de Kubernetes, implementação de CNI, service mesh ou recurso que não esteja nos insumos. Se a verificação depender disso, a pergunta vai para as lacunas da revisão.
- Não invente namespace, label ou porta. Se a política usa valor que o mapa não contém, isso é apontamento, e não contexto a completar.
- Você revisa apenas o YAML recebido. Não presuma a existência de outras políticas, nem o conteúdo do manifesto que originou este.
- Não gere script, comando, diagrama nem política.

# 8. FORMATO DE SAIDA

Responda em português. Use EXATAMENTE os 5 títulos abaixo, em maiúsculas, nesta ordem. Sem saudação, preâmbulo ou frase de fechamento. Não reproduza na resposta os marcadores entre colchetes do modelo: eles indicam onde entra o seu conteúdo. A seção LACUNAS DA REVISAO nunca é omitida. Máximo de 4 linhas por apontamento, sem teto para o total, porque apontamento faltante é falha de segurança.

VEREDITO
[APROVADO ou APROVADO COM RESSALVAS ou BARRADO] - [uma linha de justificativa]

PERGUNTAS DE VERIFICACAO
| Pergunta | Resposta com base no YAML | Cumpre |
|---|---|---|
[uma linha por pergunta; a coluna Cumpre aceita sim, nao ou parcial]

APONTAMENTOS
[N]. [SEVERIDADE] - Onde: [objeto, direcao, indice do item, campo]. Problema: [o que esta errado e qual o efeito concreto]. Afeta: [qual regra do padrao ou qual fluxo]. [ou a palavra Nenhum, se nao houver apontamento]

TRAFEGO INDEVIDO PERMITIDO
[um por linha: qual trafego passa, e qual item de regra o libera] [ou exatamente: Nenhum identificado]

LACUNAS DA REVISAO
- [o que nao foi possivel verificar so com o YAML e os insumos recebidos]: [qual insumo ou consulta fecharia]

# INSUMOS

[POLITICA]
{{politica}}

[REGRAS DO PADRAO]
{{regras_do_padrao}}

[MAPA DE SERVICOS]
{{mapa_de_servicos}}
`````

```yaml
nome: revisao-de-networkpolicy
descricao: Revisa uma NetworkPolicy contra um padrao de compliance e um mapa de servicos, devolvendo veredito, perguntas de verificacao derivadas do padrao e apontamentos numerados com severidade. Nao reescreve a politica.
versao: 1.0.0
tags: [kubernetes, networkpolicy, seguranca-de-rede, revisao, compliance]
inputs:
  - nome: politica
    descricao: O manifesto de NetworkPolicy a ser revisado, colado integralmente.
  - nome: regras_do_padrao
    descricao: As mesmas regras de compliance internas usadas na geracao, contra as quais o cumprimento e verificado.
  - nome: mapa_de_servicos
    descricao: O mesmo mapa de namespace, labels e portas. Unica fonte autorizada para julgar se um seletor e valido.
```

---

## Execução: as iterações

**Modelo:** Claude Opus, no plano Max, nas quatro rodadas: gerador e revisor.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Primeira troca de modelo no desafio, e o motivo é o item: política de rede errada expõe o produto core, e o ciclo exige quatro passagens em que cada uma precisa se apoiar no artefato da anterior sem perder o fio. Escolhi o modelo mais forte em consistência de contexto longo.

> **Ressalva de independência, e ela importa para a leitura de tudo que vem abaixo.** Os dois prompts foram escritos e executados pelo mesmo modelo, na mesma sessão. Isso é uma demonstração do ciclo, não um teste independente do par. Um revisor que compartilha a janela de contexto de quem escreveu não é um segundo par de olhos, é o mesmo par com outro cabeçalho. A análise mais adiante mostra um caso concreto em que esse vício produziu um apontamento falso.

### Rodada 1: gerador, `{{apontamentos}}` vazio → v1

```yaml
# Endurecimento do manifesto recebido. Permissao irrestrita removida nas duas
# direcoes. Cobertura de pods e direcoes de trafego preservadas: o escopo continua
# alcancando todos os pods do namespace e continua declarando entrada e saida.
#
# Premissa de mecanismo, valida para todas as regras entre namespaces: a API de
# NetworkPolicy alcanca namespace por label e nunca por nome. O mapa de servicos
# fornece nome de namespace. Para ligar um ao outro, os seletores abaixo usam o
# label kubernetes.io/metadata.name com o valor do nome informado no mapa.
# Pre-condicao: cada namespace citado precisa carregar esse label com esse valor.
# Se nao carregar, nenhuma regra entre namespaces casa e todos os fluxos param.
# Premissa: os insumos nao informam versao de Kubernetes, CNI nem service mesh.
# Nenhuma regra usa recurso fora de networking.k8s.io/v1.
# Premissa: trafego de resposta de conexao ja permitida nao recebe regra propria,
# porque a avaliacao e por conexao e nao por pacote isolado. Pre-condicao: o CNI
# instalado no cluster precisa implementar esse comportamento.
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sentinel-default-deny
  namespace: sentinel-prod
spec:
  # Cobertura total do namespace, e nao permissao. Seletor de pods declarado com
  # lista de expressoes vazia: aplica esta politica a todos os pods de
  # sentinel-prod. Como nenhuma lista de permissao e declarada neste objeto, o
  # efeito e negacao por padrao em entrada e em saida.
  podSelector:
    matchExpressions: []
  policyTypes:
    - Ingress
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sentinel-allow
  namespace: sentinel-prod
spec:
  # Mesma cobertura total do namespace do objeto anterior, por duas razoes: pod
  # que sair deste seletor nao fica mais restrito, fica sem politica aplicavel; e
  # os fluxos do padrao valem para os pods do namespace, sem recorte por label.
  podSelector:
    matchExpressions: []
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Fluxo liberado: origem relay-prod com label app=relay, destino pods de
    # sentinel-prod, proposito consumo dos eventos publicados pelo Relay. Os dois
    # criterios abaixo compoem um unico par: valem apenas para pods com esse label
    # dentro desse namespace, e nao para qualquer pod do namespace nem para esse
    # label em outro namespace.
    # LACUNA: o mapa de servicos nao informa a porta em que os pods de
    # sentinel-prod recebem esse fluxo. Sem esse dado a regra fica sem restricao
    # de porta e alcanca todas as portas do destino a partir dessa origem. Fecha a
    # lacuna: a porta de escuta declarada do servico deste namespace.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: relay-prod
          podSelector:
            matchLabels:
              app: relay
    # Fluxo liberado: origem edge com label app=api-gateway, destino pods de
    # sentinel-prod, proposito atendimento das chamadas que entram pelo gateway de
    # API da plataforma. Criterio de namespace e criterio de pod no mesmo par.
    # LACUNA: mesma ausencia de porta de destino descrita na regra anterior, com o
    # mesmo efeito de alcance a todas as portas.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: api-gateway
  egress:
    # Fluxo liberado: origem pods de sentinel-prod, destinos forge-prod com label
    # app=forge na porta 5432 e cerebro-prod com label app=cerebro na porta 9200,
    # proposito persistencia no warehouse e consulta ao servico de busca.
    # Protocolo TCP nos dois destinos, por serem portas de servico de banco e de
    # busca conforme o mapa.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: forge-prod
          podSelector:
            matchLabels:
              app: forge
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: cerebro-prod
          podSelector:
            matchLabels:
              app: cerebro
      ports:
        - protocol: TCP
          port: 5432
        - protocol: TCP
          port: 9200
    # Fluxo liberado: origem pods de sentinel-prod, destino kube-system com label
    # k8s-app=kube-dns na porta 53, proposito resolucao de nomes interna, sem a
    # qual nenhum dos destinos acima e alcancavel pelo nome do servico.
    # Protocolo: UDP e TCP na mesma porta 53. UDP e o caminho normal da consulta;
    # TCP e usado quando a resposta nao cabe no limite de datagrama e em
    # retentativa. Liberar apenas UDP produz falha intermitente, visivel so em
    # algumas consultas e caro de diagnosticar.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
# Fluxos do padrao sem regra correspondente: nenhum. Os cinco fluxos declarados
# tem regra acima: entrada do Relay, entrada do gateway de API, saida para o
# warehouse, saida para a busca, saida para o DNS interno.
```

**O que a v1 já acertou.** O `podSelector` de cobertura total foi preservado nos dois objetos, com a justificativa explícita de que pod fora de escopo fica sem política e não mais restrito: a armadilha principal foi evitada. Os dois critérios de namespace e de pod compõem um único par em todos os itens, que é o defeito clássico e invisível de NetworkPolicy. O DNS saiu com UDP e TCP na porta 53, com a explicação de que liberar só UDP produz falha intermitente. As duas lacunas de porta de entrada foram declaradas em comentário em vez de a porta ser inventada. E o modelo chegou sozinho ao label `kubernetes.io/metadata.name`, declarando a premissa e a pré-condição em vez de assumir em silêncio.

### Rodada 2: revisor sobre a v1

**VEREDITO:** BARRADO: o primeiro item de saída agrupa dois destinos e duas portas no mesmo item, liberando cada destino em cada porta e excedendo os fluxos de saída que o padrão declara.

**PERGUNTAS DE VERIFICACAO**

| Pergunta | Resposta com base no YAML | Cumpre |
|---|---|---|
| A lista de entrada contem apenas origens relay-prod/app=relay e edge/app=api-gateway? | Dois itens em sentinel-allow ingress, indices 1 e 2, com exatamente esses dois pares e nenhum outro | sim |
| Cada item de saida restringe destino e porta aos tres pares declarados no padrao? | O item de saida 1 declara dois destinos e duas portas juntos; o cruzamento inclui forge em 9200 e cerebro em 5432, que o padrao nao declara | nao |
| Existe item de regra sem restricao de origem ou destino em qualquer direcao? | Todos os quatro itens de regra tem criterio de origem ou destino declarado | sim |
| Existe objeto que aplique a todos os pods do namespace, declare as duas direcoes e nao declare permissao? | sentinel-default-deny, com seletor de cobertura total e policyTypes Ingress e Egress, sem listas de permissao | sim |
| Cada item de regra tem comentario imediatamente acima nomeando origem, destino e proposito? | Os quatro itens tem comentario com os tres elementos; nenhum e generico | sim |
| Criterio de namespace e criterio de pod compoem um unico par em cada item? | Em todos os itens os dois criterios estao no mesmo elemento de lista, nao como alternativas | sim |
| O cruzamento entre criterios de destino e criterios de porta dentro de cada item corresponde a fluxo declarado? | Falha no item de saida 1; correto no item de saida 2, que tem um destino unico | nao |
| Algum pod de sentinel-prod fica fora do escopo dos objetos? | Os dois objetos usam seletor de cobertura total do namespace | sim |
| Alguma direcao declarada no padrao ficou sem tipo declarado? | Ambos os objetos declaram Ingress e Egress | sim |
| O fluxo de resolucao de nomes recebeu todos os protocolos que usa na porta 53? | Item de saida 2 declara UDP e TCP na porta 53 | sim |
| Os fluxos de entrada funcionam com o que foi liberado? | Funcionam, porem sem restricao de porta: os itens de entrada 1 e 2 nao declaram campo de portas | parcial |
| O seletor de cobertura total esta declarado de forma que nao dependa de interpretacao do decodificador? | Declarado como lista de expressoes vazia, forma cuja equivalencia a seletor vazio nao esta declarada como premissa no YAML | parcial |
| Objeto adicional amplia alguma permissao? | sentinel-default-deny nao declara permissao, logo nao amplia | sim |
| O label usado para alcancar namespace consta do mapa de servicos? | Nao consta. O mapa fornece nome de namespace; o YAML usa uma chave de label que nao esta no mapa, com premissa declarada no topo | parcial |

**APONTAMENTOS**

```
1. BLOQUEADOR - Onde: sentinel-allow, egress, item 1, campos to e ports. Problema: o item reune dois
   destinos e duas portas, e um item de regra libera todas as combinacoes entre seus criterios; o
   efeito e permitir tambem forge-prod/app=forge na porta 9200 e cerebro-prod/app=cerebro na porta
   5432. Afeta: a regra do padrao que limita a saida a warehouse na 5432, busca na 9200 e DNS interno.
2. IMPORTANTE - Onde: sentinel-allow, ingress, itens 1 e 2, ausencia do campo ports. Problema: sem
   restricao de porta, as duas origens autorizadas alcancam qualquer porta dos pods de sentinel-prod,
   incluindo portas de administracao ou depuracao que nenhum fluxo do padrao menciona. Afeta: os
   fluxos de entrada do padrao, que nomeiam o consumidor e nao a porta.
3. IMPORTANTE - Onde: sentinel-default-deny e sentinel-allow, spec, campo podSelector. Problema: a
   cobertura total esta expressa por lista de expressoes vazia, e a equivalencia dessa forma a seletor
   que casa todos os pods nao esta declarada como premissa; leitor ou ferramenta que interprete a
   lista vazia como ausencia de correspondencia conclui o oposto do pretendido. Afeta: a regra de
   default-deny explicita no namespace e a cobertura de escopo dos dois objetos.
4. IMPORTANTE - Onde: bloco de comentarios do topo e todos os campos namespaceSelector. Problema: a
   chave de label usada para alcancar namespace nao consta do mapa de servicos; a pre-condicao nao e
   verificavel com os insumos e, se falhar, os cinco fluxos param de uma vez sem erro de aplicacao do
   manifesto. Afeta: todos os fluxos declarados no padrao.
5. MENOR - Onde: inicio do documento, antes de sentinel-default-deny. Problema: o separador de
   documentos aparece antes do primeiro objeto, e a especificacao o reserva para uso entre documentos.
6. MENOR - Onde: sentinel-allow, egress, item 1, comentario acima do item. Problema: o comentario
   justifica TCP afirmando que as portas sao de servico de banco e de busca conforme o mapa, mas o
   mapa informa numero de porta e nao protocolo; a escolha e inferencia apresentada como leitura do
   insumo, sem marcacao de premissa.
```

**TRAFEGO INDEVIDO PERMITIDO**

```
- Pods de sentinel-prod alcancando forge-prod/app=forge na porta 9200, liberado pelo cruzamento do
  item de saida 1.
- Pods de sentinel-prod alcancando cerebro-prod/app=cerebro na porta 5432, liberado pelo cruzamento
  do item de saida 1.
- relay-prod/app=relay e edge/app=api-gateway alcancando qualquer porta dos pods de sentinel-prod,
  liberado pelos itens de entrada 1 e 2 sem campo de portas.
```

**LACUNAS DA REVISAO:** porta de escuta dos pods de sentinel-prod; protocolo de transporte das portas 5432 e 9200; presença da chave de label nos cinco namespaces citados; comportamento do CNI quanto à avaliação por conexão; manifesto de origem, não recebido, o que impede verificar preservação de cobertura; outras NetworkPolicies existentes no namespace, que podem ampliar o permitido.

### Rodada 3: gerador com os apontamentos → v2

Trecho relevante do YAML corrigido, com as respostas aos apontamentos em comentário. A conferência de não regressão veio completa no topo, percorrendo regra por regra do padrão.

```yaml
# APONTAMENTO 5 - ATENDIDO: o separador de documentos passou a ser usado apenas
# entre objetos; este bloco de comentarios abre o primeiro documento sem separador
# antes dele.
#
# APONTAMENTO 4 - RECUSADO: a API de NetworkPolicy so alcanca namespace por label,
# nunca por nome, e o mapa de servicos fornece apenas nome de namespace. Qualquer
# alternativa a chave de label usada aqui seria uma chave inventada, o que o
# metodo proibe de forma mais direta do que depender de uma pre-condicao
# declarada. A premissa e a pre-condicao continuam declaradas abaixo e a
# verificacao dessa pre-condicao permanece registrada como lacuna.
#
# Conferencia de nao regressao contra a versao anterior, regra por regra do
# padrao. Entrada restrita as duas origens autorizadas: preservado. Ausencia de
# permissao irrestrita em entrada e saida: preservado. Default-deny explicita no
# namespace: preservado. Comentario de fluxo por regra: preservado e reescrito onde
# a regra foi dividida. Composicao de namespace e pod em par unico: preservado nos
# quatro itens originais e mantido nos dois itens resultantes da divisao.
# Cobertura total do namespace nos dois objetos: preservada, e a forma do seletor
# mudou sem mudar o alcance. Protocolos UDP e TCP na porta 53: preservados.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sentinel-default-deny
  namespace: sentinel-prod
spec:
  # APONTAMENTO 3 - ATENDIDO: a forma do seletor de cobertura total passou a ser a
  # chave do seletor sem valor, e a premissa que antes ficava implicita esta
  # declarada aqui. Premissa de mecanismo: seletor de pods sem valor equivale a
  # seletor vazio, e seletor vazio casa todos os pods do namespace do objeto.
  podSelector:
  policyTypes:
    - Ingress
    - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: sentinel-allow
  namespace: sentinel-prod
spec:
  podSelector:
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Fluxo liberado: origem relay-prod com label app=relay, destino pods de
    # sentinel-prod, proposito consumo dos eventos publicados pelo Relay.
    # APONTAMENTO 2 - RECUSADO: restringir a porta deste fluxo exige a porta de
    # escuta dos pods de sentinel-prod, que o mapa de servicos nao fornece.
    # Inventar a porta violaria a proibicao de criar valor fora do mapa, e a regra
    # nao pode ser removida porque o fluxo e declarado no padrao.
    # LACUNA: efeito residual aceito nesta versao: esta origem alcanca todas as
    # portas do destino. Enquanto a lacuna existir, esta politica nao deve ser
    # lida como limitando a superficie de entrada, apenas a origem dela.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: relay-prod
          podSelector:
            matchLabels:
              app: relay
    # Fluxo liberado: origem edge com label app=api-gateway, destino pods de
    # sentinel-prod, proposito atendimento das chamadas do gateway de API.
    # APONTAMENTO 2 - RECUSADO: mesma ausencia de porta e mesma justificativa.
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: edge
          podSelector:
            matchLabels:
              app: api-gateway
  egress:
    # Fluxo liberado: origem pods de sentinel-prod, destino forge-prod com label
    # app=forge na porta 5432, proposito persistencia no warehouse.
    # APONTAMENTO 1 - ATENDIDO: este item foi separado do item de cerebro-prod.
    # Antes os dois destinos e as duas portas estavam no mesmo item, o que liberava
    # cada destino em cada porta. Agora cada par destino-porta e um item proprio.
    # APONTAMENTO 6 - ATENDIDO: Premissa: protocolo TCP, porque o mapa informa o
    # numero da porta e nao o protocolo.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: forge-prod
          podSelector:
            matchLabels:
              app: forge
      ports:
        - protocol: TCP
          port: 5432
    # Fluxo liberado: destino cerebro-prod com label app=cerebro na porta 9200,
    # proposito consulta ao servico de busca.
    # APONTAMENTO 1 - ATENDIDO: item resultante da separacao descrita acima.
    # APONTAMENTO 6 - ATENDIDO: Premissa: protocolo TCP.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: cerebro-prod
          podSelector:
            matchLabels:
              app: cerebro
      ports:
        - protocol: TCP
          port: 9200
    # Fluxo liberado: destino kube-system com label k8s-app=kube-dns na porta 53.
    # Protocolo: UDP e TCP na mesma porta. UDP e o caminho normal da consulta; TCP
    # e usado quando a resposta nao cabe no limite de datagrama e em retentativa.
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
# Apontamentos recebidos e seus estados: 1 ATENDIDO, 2 RECUSADO por insumo
# ausente, 3 ATENDIDO, 4 RECUSADO por limitacao do mecanismo, 5 ATENDIDO,
# 6 ATENDIDO. Nenhum apontamento ficou sem estado declarado.
```

### Rodada 4: revisor sobre a v2, apontamentos residuais

**VEREDITO:** APROVADO COM RESSALVAS: nenhum apontamento bloqueador; cada item de regra restringe origem ou destino, cada par destino-porta está isolado em item próprio e o namespace tem objeto de negação por padrão. Permanecem ressalvas de exposição de porta em entrada e de pré-condição não verificável.

**APONTAMENTOS residuais:** dois IMPORTANTE herdados e recusados na v2 (ausência de porta em entrada; dependência do label de namespace), um IMPORTANTE sobre TCP declarado como premissa nas portas 5432 e 9200, e dois MENOR: os comentários citam números de apontamento de uma revisão que não acompanha o manifesto, e a mesma lacuna de porta é repetida em texto integral em dois itens, criando dois pontos para atualizar.

**TRAFEGO INDEVIDO PERMITIDO:** apenas as duas origens autorizadas alcançando qualquer porta dos pods de `sentinel-prod`, decorrente de dado ausente no mapa e não de erro de construção da regra.

### Verificação independente da v2

Rodei as checagens por fora do modelo:

| Verificação | Resultado |
|---|---|
| `kubeconform` em modo estrito, dois documentos | 2 recursos válidos, 0 inválidos |
| Assert do CP08: `kind: NetworkPolicy` | passa |
| Assert do CP08: `policyTypes` com Ingress e Egress | passa |
| Assert do CP08: não contém a regra vazia `- {}` | passa, a v2 não tem nenhuma chave em lugar nenhum |
| Assert do CP08: egress libera Forge na 5432 e Cerebro na 9200 | passa |
| Assert do CP08: ingress libera Relay (`app: relay`) | passa |
| Assert do CP08: toda regra tem comentário | passa, os 5 itens de regra têm comentário imediatamente acima |
| Convergência do ciclo | 1 BLOQUEADOR na v1, 0 na v2; BARRADO → APROVADO COM RESSALVAS |

---

## Curadoria

**Técnica de criação: meta-prompting para um par, não para um prompt.** Gerei gerador e revisor com um meta-prompt só, pelo mesmo motivo do Checkpoint 05: os dois precisam encaixar. O revisor numera apontamentos porque o gerador responde por número; se fossem gerados separadamente, nada garantiria essa convenção.

**O ciclo convergiu, e sem o vício mais comum de revisor automático.** Um BLOQUEADOR na v1, nenhum na v2, e o veredito saiu de BARRADO para APROVADO COM RESSALVAS **sem** o revisor inventar bloqueador na segunda passagem para justificar a própria existência. A regra que tornou isso possível é a que amarra o veredito aos apontamentos de forma declarada, mais a instrução explícita de que aprovar é resultado possível. Sem essas duas, o campo mais lido da saída seria o menos verificável.

**O bloqueador encontrado é o defeito clássico de NetworkPolicy.** O item de saída da v1 reunia dois destinos e duas portas, e um item de regra libera o produto cartesiano entre seus critérios, então ele também permitia Forge na 9200 e Cerebro na 5432, fluxos que o padrão não declara. O revisor pegou isso enumerando as combinações, que é exatamente o que a categoria de semântica de seletor manda fazer, e a v2 corrigiu separando cada par destino-porta em item próprio.

**O achado que o modelo não viu: o apontamento 3 era falso positivo, e a raiz do problema é uma instrução minha.**

A v1 declarou o seletor de cobertura total como `podSelector: {matchExpressions: []}`. O apontamento 3 classificou isso como IMPORTANTE, alegando que a equivalência dessa forma a "casa todos os pods" não estava declarada e que uma ferramenta poderia interpretá-la como ausência de correspondência. A v2 obedeceu e trocou por `podSelector:` sem valor.

A referência oficial da API é explícita: [um seletor de label vazio casa todos os objetos, e um seletor nulo não casa objeto nenhum](https://kubernetes.io/docs/reference/kubernetes-api/definitions/label-selector-v1-meta/). Um seletor sem `matchLabels` e com `matchExpressions` vazio **é** um seletor vazio, então a v1 estava correta e documentada. A v2 mudou para a forma que a documentação descreve como não casando nada, exatamente no objeto de negação padrão, onde a cobertura do namespace inteiro é o ponto. Na prática ele funciona, porque o campo é obrigatório e não ponteiro no tipo da API em Go, então o nulo é coagido para o valor zero do tipo, que é o seletor vazio. (No parser de YAML, antes disso, o campo sem valor decodifica para nulo, são duas camadas diferentes, e é a coerção da segunda que salva a política.) Mas isso passou a depender de comportamento de desserialização em vez de semântica documentada, e esse é o pior lugar possível para essa dependência.

Verifiquei as três formas com `kubeconform` em modo estrito: `podSelector: {}`, `matchExpressions: []` e o seletor nulo são todas válidas no schema, e o nulo decodifica para `None`. Ou seja, o schema não protege contra a escolha pior.

A causa raiz é minha. Eu escrevi no meta-prompt que um teste automatizado procura a sequência de caracteres da regra vazia na saída. O modelo generalizou com prudência (proibiu chaves em qualquer lugar, para não arriscar reprovar a política inteira num assert ingênuo) e com isso tirou da mesa a forma idiomática `podSelector: {}`. O revisor então inventou uma dúvida sobre a alternativa que sobrou, e o gerador obedeceu. Três decisões defensáveis em sequência produziram um resultado pior que o ponto de partida.

A correção é no prompt, não no teste. O assert do Checkpoint 08 foi escrito do jeito certo (`not-contains: '- {}'`, a **string exata** da regra vazia e não a presença de chaves) justamente porque `podSelector: {}` é a forma documentada do seletor que cobre o namespace e seria reprovada por engano. Quem está largo é a proibição no prompt, que precisa encolher para o padrão específico para o seletor voltar à forma documentada.

Isso também é o caso concreto que dá peso à ressalva de independência registrada na execução: gerador e revisor rodaram no mesmo modelo e na mesma sessão. Um revisor que herda as restrições de quem escreveu não questiona a restrição, ele opera dentro dela, e aqui ele foi além, inventando uma justificativa técnica errada para uma escolha que a minha própria instrução havia forçado.

**A autocrítica mais útil que o modelo produziu foi sobre o prompt, não sobre a política.** Ele observou que a seção 5 do gerador **avisa** sobre o cruzamento entre critérios de destino e critérios de porta, e a v1 caiu nesse erro de todo modo. O diagnóstico dele: o aviso aparece como segundo eixo de uma regra cujo primeiro eixo é mais vistoso, e o modelo aplicou o primeiro com rigor e passou por cima do segundo. É uma leitura precisa de como atenção se distribui dentro de uma instrução composta, e a lição é geral: duas armadilhas diferentes na mesma regra fazem a segunda ser tratada como nota de rodapé.

**Correções para a v1.0.1, não aplicadas para não invalidar as quatro rodadas:**

- **Gerador:** separar os dois eixos da seção 5 em regras próprias e transformar a conferência em obrigação de saída: cada item de regra declara em comentário quantas combinações produz e quais são. Foi o defeito que a v1 cometeu apesar do aviso.
- **Gerador:** encolher a proibição de chaves ao padrão específico da regra vazia, e voltar a permitir o seletor vazio na forma documentada. O assert do Checkpoint 08 já é a string exata, então não há nada a corrigir do lado do teste.
- **Gerador:** declarar lacuna repetida em um ponto único e referenciá-la nas regras afetadas, em vez de duplicar o texto integral. Foi o apontamento 5 da rodada 4, e o risco é atualizar um ponto e esquecer o outro.
- **Revisor:** ganhar parâmetro opcional `manifesto_de_origem`. Sem ele, a categoria de cobertura de escopo é estruturalmente incompleta: o revisor não tem como detectar que o gerador estreitou o escopo, que é justamente o erro que o método mais teme. Se o estreitamento for coerente com o padrão, o revisor aprova.

> **Uma pendência do revisor já foi aplicada, e vale registrar por que essa saiu da fila.**
> A regra de severidade da seção 6 estava truncada: dizia "não promova apontamento de forma
> a bloqueador", sem o nível de origem, e ficava sem sentido. É a regra que impede o revisor
> de inflar severidade para parecer rigoroso, e esta curadoria credita a ela a convergência
> do veredito, ou seja, o texto que sustenta a conclusão estava quebrado. Corrigido para
> "de MENOR ou IMPORTANTE a BLOQUEADOR" na **v1.0.1** do prompt, com o histórico no README
> do item.
>
> Diferente das outras pendências, esta foi aplicada e não só documentada, porque a suíte do
> Checkpoint 10 permite validar: rodei `revisao-de-networkpolicy` depois da correção e os 6
> casos saíram consistentes com o baseline, sem regressão. As outras pendências alteram
> comportamento e continuam documentadas-e-não-aplicadas, porque aplicá-las invalidaria as
> quatro rodadas registradas acima.
- **Ciclo:** o revisor é sem estado e não recebe as recusas anteriores, então reapresenta apontamento já discutido com número novo. Em ciclos longos isso gasta rodada sem produzir mudança. Quem mede convergência é o humano que orquestra, e isso precisa estar documentado no README do item.
- **Independência:** rodar o revisor em modelo diferente do gerador, ou no mínimo em sessão limpa. O que se compra com quatro chamadas depende disso.

**Uma tensão de nomenclatura que o modelo levantou e eu aceito.** O item se chama `networkpolicy-sentinel`, o que sugere domínio fixo, mas o corpo do prompt não menciona Sentinel, Relay, Forge, Cerebro, 5432, 9200 nem 53: ele funciona para qualquer namespace. O nome amarra ao caso de estreia porque o Checkpoint 08 o fixa no caminho do arquivo de teste. Se houver liberdade de renomear no registry, `endurecimento-de-networkpolicy` descreve melhor o que o item faz.

**Sanitização.** Aqui o insumo é, por natureza, um mapa de superfície de ataque: quais serviços existem, em quais namespaces, com quais labels, em quais portas, e quem pode falar com quem. É a informação mais diretamente ofensiva de todos os seis checkpoints, mais que a capacidade do Checkpoint 04 e mais que o grafo de dependências do Checkpoint 05, porque aqui está explícito o que **não** está protegido.

E o mais desconfortável: **quase nada disso dá para remover sem inutilizar o prompt.** A regra 4 proíbe inventar seletor justamente porque seletor inventado gera política que não casa nada e falha em silêncio. Então namespace, label e porta têm que ir literais.

O que resta como política real é outra coisa: pseudonimizar de forma consistente e reversível. Substituir `sentinel-prod` por `ns-a`, `app=sentinel` por `app=svc-a`, e assim por diante, mantendo o mapeamento local, a estrutura de quem fala com quem se preserva inteira, a política gerada é mecanicamente re-hidratável, e o que sai da empresa é um grafo anônimo. As portas 5432 e 9200 eu manteria: elas revelam a tecnologia, o que é informação de baixo valor ofensivo, e são necessárias porque o prompt exige que a porta venha do mapa.

O que eu não faria de jeito nenhum é o inverso: mandar o manifesto permissivo original sem sanitizar. Ele é literalmente a declaração de que o namespace do produto core está com entrada e saída liberadas para qualquer origem e qualquer destino, a informação mais sensível do pacote não é o mapa, é o defeito.
