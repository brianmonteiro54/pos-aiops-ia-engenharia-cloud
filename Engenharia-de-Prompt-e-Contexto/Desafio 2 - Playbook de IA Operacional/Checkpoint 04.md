# Checkpoint 04: Estratégia de backpressure no Relay

Quarto item do playbook, e o primeiro que não diagnostica nem transforma: **apoia decisão de arquitetura**.

O Relay é o barramento por onde todo o telemetry dos clientes passa antes de chegar ao resto da plataforma. Quando um cliente grande dispara muito mais dado que o normal, o Relay recebe mais do que consegue entregar, a fila acumula, e o atraso empurra o Sentinel junto: o alerta que deveria sair na hora atrasa. O Tony Stark quer uma estratégia para segurar esse excesso.

Não existe resposta única. Há vários caminhos defensáveis e cada um tem um preço, então o prompt tem que fazer a IA **comparar mais de um caminho antes de recomendar**, em vez de produzir uma recomendação única disfarçada de análise. Como a decisão é cara, o raciocínio vale tanto quanto a recomendação.

Saída aberta, como no Checkpoint 03: este prompt não entra nos testes determinísticos do Checkpoint 08.

---

## Prompt parametrizável

**Destino no registry:** `devops/estrategia-backpressure/prompt.md` · **versão:** 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{estado_atual}}` | sim | O que se sabe do componente hoje: capacidade, pico observado, retenção, consumidores |
| `{{restricoes}}` | sim | SLAs, limites de orçamento, requisitos não negociáveis, histórico que o time não quer repetir |
| `{{opcoes_candidatas}}` | não | Caminhos já em cima da mesa. Vazio faz o modelo derivar as opções; preenchido faz ele avaliar as recebidas e acrescentar pelo menos uma |

`````text
Você é um Engenheiro de Confiabilidade (SRE) e Arquiteto de Sistemas. Sua tarefa é atuar como um parceiro analítico em uma decisão arquitetural sob restrições em conflito (como backpressure, saturação ou gargalos), comparando caminhos possíveis e recomendando uma solução fundamentada.

EXECUTE AS SEGUINTES ETAPAS DE RACIOCÍNIO (não as imprima, use-as para estruturar a saída):

1. Dimensionamento Matemático: Calcule explicitamente, cada conta em uma linha separada, com as unidades visíveis:
   - Déficit = Taxa de chegada no pico - Capacidade de entrega.
   - Volume Acumulado = Déficit * Duração do pico.
   - Piso Físico de Drenagem = Volume Acumulado / Capacidade de entrega (assumindo dedicação total à drenagem e nenhuma chegada nova).
   Antes de usar qualquer resultado, confira a ordem de magnitude: um erro de fator 60 entre segundos e minutos, ou de fator mil entre unidade e milhar, invalida toda a análise seguinte.
   REGRA ABSOLUTA: Se o piso físico calculado já viola um SLA temporal exigido, nenhuma estratégia de priorização, particionamento, descarte ou reordenação resolverá aquele SLA isoladamente, apenas a alteração de capacidade resolve. Declare isso imediatamente se ocorrer.
   ASSIMETRIA DO PISO: o piso é limite inferior, não estimativa. Ele só serve para REPROVAR viabilidade, nunca para APROVAR. Piso acima do SLA prova inviabilidade. Piso abaixo do SLA não prova nada, porque na realidade eventos continuam chegando durante a drenagem e o tempo real é sempre maior. Se a taxa de chegada após o pico não estiver nos insumos, registre como lacuna e não use o piso como evidência de que o SLA é atingível.

2. Distinção de Relógios: Identifique o que cada restrição mede. "Latência de processamento de um evento novo" é um relógio diferente de "Tempo de drenagem de um volume já acumulado". Comparar um SLA de latência com um tempo de drenagem produz conclusão errada com aparência de rigor.

3. Checagem de Escopo de Capacidade: A capacidade declarada é do componente como um todo ou isolada por consumidor? Se o insumo não esclarecer, classifique isso como lacuna crítica e declare como essa distinção inverteria ou alteraria o efeito das opções avaliadas.

4. Classificação de Restrições:
   - Inviolável: Quebra SLAs de negócio, corrompe dados ou causa perda inaceitável. (Elimina opções).
   - Flexível com limite: Tolera degradação até um teto numérico. (Condiciona opções).
   - Econômica/Operacional: Orçamento, esforço, complexidade. (Penaliza opções, mas não as elimina).
   REGRA: Só elimine uma opção por violação de restrição inviolável, nunca por preferência pessoal.

5. Tratamento de Opções: Se as opções candidatas vierem vazias, derive caminhos viáveis a partir do cenário. Se vierem preenchidas, avalie-as E adicione obrigatoriamente pelo menos UMA nova opção técnica que não estava na lista original. Avalie no máximo cinco opções no total, priorizando as mais distintas entre si. Descreva o mecanismo mecânico de cada uma (o que passa, o que espera, o que descarta) antes de avaliá-las. Não presuma tecnologias: não assuma recursos específicos de um produto de fila ou stream a menos que o insumo os cite.

6. Avaliação Cruzada: Julgue todas as opções contra todas as restrições. Nenhuma opção recebe "passe livre".

7. Regra Anti-Espantalho: Para TODA opção, inclusive a recomendada, declare o que ela NÃO resolve e qual NOVO MODO DE FALHA ela introduz no ecossistema.
   LIMITE DESTA REGRA: se a opção genuinamente não introduz novo modo de falha, tipicamente provisionamento direto de capacidade, escreva "Nenhum novo modo de falha" e diga em troca qual recurso ela consome. Custo NÃO é modo de falha: não classifique gasto, orçamento ou esforço como falha técnica. Inventar pseudo-falha para preencher o campo é pior que declarar ausência, porque apaga a diferença entre opção que adiciona complexidade sistêmica e opção que é apenas força bruta segura.

8. Recomendação: Escolha um caminho. Se for uma combinação, limite a no máximo três partes justificando a ordem. REGRA ABSOLUTA: Uma combinação que inclui tudo que foi listado não é decisão, é abdicação de decisão (especialmente sob restrição econômica).

9. Sensibilidade: Defina qual dado incerto ou premissa, se provada falsa, mudaria a sua recomendação para outra opção específica.

REGRAS ESTRITAS DE SAÍDA:
- Responda em no máximo 90 linhas.
- As seções SENSIBILIDADE DA DECISAO e LACUNAS não podem ser omitidas nem encurtadas. Se faltar espaço, reduza os blocos de opções.
- Toda quantificação precisa mostrar a conta ou o número de origem. Não invente números, capacidades, custos ou SLAs que não estejam nos insumos.
- Onde houver premissa, escreva explicitamente "Premissa:".
- Não reproduza na resposta os marcadores entre colchetes do modelo abaixo: eles indicam onde entra o seu conteúdo.
- Use EXATAMENTE os 8 títulos abaixo, em maiúsculas, nesta ordem. Sem saudações ou preâmbulos.

DIMENSAO DO PROBLEMA
[Mostre a aritmética do passo 1, uma conta por linha. Declare o veredito sobre o piso físico vs. SLAs]

RELOGIOS E RESTRICOES
| Restrição | Tipo | Relógio Medido | Efeito (Elimina/Condiciona/Penaliza) |
|---|---|---|---|
[Uma linha por restrição recebida nos insumos]

OPCOES AVALIADAS
[Para cada opção, no máximo cinco:]
- [Nome]: [Mecanismo mecânico].
  Resolve: [X]. Não resolve: [Y].
  Novo modo de falha: [Z, ou "Nenhum novo modo de falha" com o recurso consumido]. Custo: [Infra/Complexidade].

MATRIZ OPCAO x RESTRICAO
| Opção | (uma coluna por restrição recebida) |
|---|---|
[Preencha com ATENDE, VIOLA ou CONDICIONAL, descrevendo a condição brevemente]

OPCOES ELIMINADAS
[Quais opções caem e por qual restrição inviolável. Se nenhuma, diga "Nenhuma"]

RECOMENDACAO
[Sua escolha ou combinação ordenada, no máximo 3 partes. Justificativa técnica e justificativa da ordem]

SENSIBILIDADE DA DECISAO
[Se a variável X mudar para Y, a recomendação muda para a Opção Z porque...]

LACUNAS
- [Item faltante]: Necessário [qual consulta ou dado fecharia] (mínimo de 3 itens)

INSUMOS DO CENÁRIO:

[ESTADO ATUAL]
{{estado_atual}}

[RESTRICOES]
{{restricoes}}

[OPCOES CANDIDATAS]
{{opcoes_candidatas}}
`````

**Frontmatter:**

```yaml
nome: estrategia-backpressure
descricao: Apoia decisões arquiteturais sob restrições em conflito comparando opções de contenção de carga, com aritmética de capacidade, matriz de restrições e análise de sensibilidade.
versao: 1.0.0
tags: [arquitetura, backpressure, capacity-planning, sre, decisao]
inputs:
  - nome: estado_atual
    descricao: Capacidade atual, taxa de pico observada, retenção e consumidores do componente.
  - nome: restricoes
    descricao: SLAs de negócio, restrições financeiras e requisitos não negociáveis.
  - nome: opcoes_candidatas
    descricao: (Opcional) Caminhos já mapeados pelo time. Se vazio, o prompt deriva as opções.
```

---

## Execução

**Modelo:** Gemini Pro, com raciocínio estendido.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Mesma justificativa do Checkpoint 03, por motivo análogo: a tarefa exige aritmética encadeada e avaliação cruzada de cinco opções contra quatro restrições, e não existe gate de latência sobre este prompt. Raciocínio longo aqui é o que a tarefa pede, não excesso.

> As tabelas perderam a estrutura de colunas na transcrição da interface. Reconstruí a formatação; nenhum veredito, número ou texto foi alterado.

### DIMENSAO DO PROBLEMA

```
Déficit = 320.000 msgs/s - 180.000 msgs/s = 140.000 msgs/s
Volume Acumulado = 140.000 msgs/s * 1.500 s (25 minutos) = 210.000.000 msgs
Piso Físico de Drenagem = 210.000.000 msgs / 180.000 msgs/s = 1.166,67 s = ~19,4 minutos

VEREDITO: O piso físico de drenagem (19,4 min) já VIOLA o SLA temporal do Forge (15 min).
Nenhuma estratégia de priorização, isolamento ou reordenação resolverá o SLA do Forge.
Apenas o aumento de capacidade resolverá o tempo de drenagem total.
```

### RELOGIOS E RESTRICOES

| Restrição | Tipo | Relógio Medido | Efeito |
|---|---|---|---|
| Sentinel não atrasar >60s | Inviolável | Latência de processamento de evento novo | Elimina opções que retêm a leitura geral |
| Forge pode atrasar 15min | Flexível c/ limite | Tempo de drenagem de volume acumulado | Condiciona a opção a drenar o déficit rápido |
| Orçamento 8% acima | Econômica | Esforço/Custo Financeiro | Penaliza Scale-Up, mas não o elimina |
| Sem perda de telemetry | Inviolável | Integridade de dados | Elimina qualquer descarte de eventos |

### OPCOES AVALIADAS

```
- Prioridade ao Sentinel: Altera o roteamento entregando os eventos ao Sentinel antes do Forge.
  Resolve: SLA do Sentinel. Não resolve: Atraso do Forge (piso de 19,4 min condena o SLA).
  Novo modo de falha: Starvation crônico do Forge. Custo: Complexidade lógica de roteamento.

- Fila secundária (DLQ/Fallback): Desvia o excesso (>180k) para storage frio (S3/blob) para reprocessar depois.
  Resolve: Protege o Relay contra OOM, evita descarte. Não resolve: Atraso na ingestão.
  Novo modo de falha: Out-of-order processing (eventos processados fora de ordem). Custo: Storage extra e lógica de retry.

- Dividir por cliente: Cria partições dedicadas por tenant para isolamento.
  Resolve: Efeito "noisy neighbor". Não resolve: Déficit global de infra se o pico for generalizado.
  Novo modo de falha: Hotspots em partições específicas. Custo: Alta complexidade operacional de rebalanceamento.

- Auto-scaling de consumidores: Aumenta o número de instâncias do Forge/Sentinel dinamicamente.
  Resolve: Gargalo na ponta consumidora. Não resolve: Gargalo se o limite de 180k for de I/O do Relay.
  Novo modo de falha: Nenhum novo modo de falha (consome CPU/Memória adicionais). Custo: Piora orçamento (financeiro).

- Scale-up do Barramento Relay (Nova): Escala a infraestrutura de rede/discos/nós do próprio barramento durante o pico.
  Resolve: Déficit matemático de capacidade, derrubando o piso de drenagem. Não resolve: Custos.
  Novo modo de falha: Nenhum novo modo de falha (consome Orçamento extra). Custo: Piora orçamento fortemente (financeiro).
```

### MATRIZ OPCAO x RESTRICAO

| Opção | SLA Sentinel (<60s) | SLA Forge (<15m) | Orçamento (+8%) | Sem Perda |
|---|---|---|---|---|
| Prioridade ao Sentinel | ATENDE | VIOLA (19,4 min no melhor caso) | ATENDE | ATENDE |
| Fila de Fallback (DLQ) | ATENDE | VIOLA (processamento postergado) | PENALIZA | ATENDE |
| Dividir por cliente | CONDICIONAL (só se pico for isolado) | CONDICIONAL | PENALIZA | ATENDE |
| Auto-scaling Consumidores | CONDICIONAL (se gargalo nos workers) | CONDICIONAL | PENALIZA | ATENDE |
| Scale-up do Barramento | ATENDE | ATENDE | PENALIZA | ATENDE |

### OPCOES ELIMINADAS

```
Nenhuma. Nenhuma das opções propõe descarte (o que violaria a restrição inviolável "Sem Perda"),
e as falhas nos SLAs do Forge configuram violação de limite flexível para opções isoladas,
mas não eliminação sumária se combinadas.
```

### RECOMENDACAO

```
Combinação: 1. Prioridade ao Sentinel + 2. Auto-scaling de consumidores e Scale-up do Barramento
atrelados a métricas de pico.

Justificativa: A matemática prova que priorização isolada sacrifica inevitavelmente o Forge
(19,4 min de piso de drenagem). O Scale-up temporário é a única resposta que respeita as leis da
física para atender aos 15 minutos do Forge. A Prioridade atua como escudo de latência protegendo
o SLA inviolável do Sentinel (<60s) durante os minutos iniciais enquanto a infraestrutura faz
spin-up, justificando o impacto orçamentário (que é restrição apenas econômica, sobrepujada por SLAs).
```

### SENSIBILIDADE DA DECISAO

```
Premissa: Assumimos que a punição por estourar os 15 minutos do Forge é maior que a punição de
exceder ainda mais o orçamento. Se a diretoria financeira considerar que "nenhum centavo a mais
pode ser gasto", a recomendação muda para OPÇÃO 1 (Prioridade ao Sentinel isolada), forçando o
sacrifício consciente do SLA de 15 minutos do Forge.
```

### LACUNAS

```
- Escopo da capacidade informada: Necessário consultar os dashboards de infraestrutura para saber
  se os 180k msgs/s representam o limite I/O do cluster Relay ou se são o gargalo dos pods
  consumidores do Sentinel/Forge.
- Taxa de chegada pós-pico: Necessário medir a média de volume de entrada nos minutos seguintes ao
  pico; o tempo real de drenagem sempre será consideravelmente maior que os 19,4 minutos baseados
  em fluxo zero.
- Projeção financeira: Necessário calcular qual o impacto exato em dólares (e não apenas "aumento")
  do auto-scaling durante 25 minutos para embasar o tradeoff contra os 8% de estouro do trimestre.
```

### Verificação da execução

Recalculei a aritmética e conferi cada exigência do prompt:

| Verificação | Resultado |
|---|---|
| Déficit 320k − 180k | 140.000 msgs/s: correto |
| Volume acumulado 140k × 1.500s | 210.000.000 msgs: correto |
| Piso físico 210M ÷ 180k | 1.166,67s = 19,4min: correto |
| Veredito sobre o SLA do Forge | Correto e é a conclusão dura do cenário: o piso já viola os 15min, então só capacidade resolve |
| Relógios separados | Sim: Sentinel mapeado como latência de evento novo, Forge como tempo de drenagem. Não comparou os 60s com tempo de drenagem |
| Retenção de 4h usada na análise | **Não**: o dado não aparece em nenhuma seção. Ver defeito 3 adiante |
| Vocabulário da matriz restrito a ATENDE/VIOLA/CONDICIONAL | **Não**: quatro células usam PENALIZA. Ver defeito 2 adiante |
| Ambiguidade da capacidade levantada | Sim, e é a primeira lacuna listada |
| Taxa de chegada pós-pico como lacuna | Sim, com a observação correta de que o tempo real será maior que o piso |
| Quinta opção acrescentada | Sim: scale-up do próprio barramento |
| `Nenhum novo modo de falha` usado corretamente | **Parcial**: usado duas vezes; numa delas o recurso nomeado em troca é o orçamento, e o prompt proíbe classificar custo como falha. Ver defeito 4 adiante |
| Recomendação com ordem justificada | **Parcial**: a ordem entre priorização e scale-up tem fundamento temporal; o auto-scaling entra na combinação sem ordem nem papel justificados |
| Combinação dentro do teto de 3 partes | Sim, 3 partes |

**Um defeito encontrado, e é de rigor lógico.** Na matriz, a linha `Scale-up do Barramento` recebe **ATENDE** no SLA do Forge, sem nenhuma conta que sustente. O prompt exige que toda quantificação mostre a conta, e a própria regra da assimetria do piso, que o output aplicou corretamente à capacidade atual, diz que piso abaixo do SLA não prova nada. Ao avaliar a correção, ele afirmou viabilidade sem aritmética.

Calculando o que faltava: drenar 210M em 900s exige **233.333 msgs/s**, ou seja, um aumento de **29,6%** sobre os 180k, e isso no cenário utópico de zero chegada nova. Com chegada de 60k/s durante a drenagem seriam 293k/s, 1,63x a capacidade atual; com 100k/s, 333k/s, 1,85x. Ou seja, a opção pode ser válida, mas o "ATENDE" só se sustenta com um número que o output não produziu, e o tamanho do aumento necessário é exatamente o que decide se ela cabe num orçamento já 8% acima.

O padrão do defeito é instrutivo: o output **declarou duas lacunas críticas e depois preencheu células da matriz com ATENDE que dependem justamente dessas lacunas**. `Prioridade ao Sentinel → SLA Sentinel = ATENDE` tem o mesmo problema: se os 180k/s forem capacidade total do barramento, priorizar não faz o Sentinel acompanhar 320k/s de chegada, e a própria lacuna nº 1 admite não saber disso. Para as opções de particionamento e auto-scaling ele usou CONDICIONAL corretamente; para essas duas, não.

Correção como **v1.0.1**: nenhuma célula da matriz pode receber ATENDE quando o veredito depender de lacuna declarada, nesse caso é CONDICIONAL, com a lacuna nomeada na célula. Não apliquei agora porque mudaria a saída e invalidaria a execução registrada.

**Mais cinco defeitos que a minha verificação acima deixou passar.** Reli a saída depois de fechar a tabela e achei estes. Registro todos porque o padrão importa: a tabela de verificação é uma lista de perguntas que eu escolhi fazer, e o que ela não pergunta não aparece.

1. **A regra absoluta contradiz a própria matriz.** A seção `DIMENSAO DO PROBLEMA` declara que "nenhuma estratégia de priorização, isolamento ou reordenação resolverá o SLA do Forge, apenas o aumento de capacidade resolverá". Pelo próprio veredito, as células de `Dividir por cliente` e `Auto-scaling` na coluna do SLA do Forge deveriam ser **VIOLA**, e saíram **CONDICIONAL**. E eu afirmei acima que "para as opções de particionamento e auto-scaling ele usou CONDICIONAL corretamente", peguei o erro na direção oposta (ATENDE onde cabia CONDICIONAL) e passei batido neste.

2. **A matriz usa vocabulário que o prompt não permite.** Quatro células trazem **PENALIZA**, e o prompt fixa `ATENDE`, `VIOLA` ou `CONDICIONAL`. É o mesmo tipo de desvio que no Checkpoint 03 eu apontei e transformei em pendência v1.0.1: lá o `HIPÓTESE` na coluna de papel. Rigor desigual entre os dois checkpoints, e a inconsistência é minha.

3. **A retenção de 4h, um dos quatro dados do insumo, não entra em lugar nenhum da análise.** As cinco células da coluna de perda de mensagem recebem ATENDE sem comparar os 19,4 minutos de drenagem com a janela de retenção, que é precisamente a comparação que torna a garantia de "sem perda" verificável. Com 4h de retenção contra 19,4min de drenagem a conclusão até se sustenta, mas por sorte e não por argumento.

4. **Custo apresentado como modo de falha.** A opção de scale-up declara `Novo modo de falha: Nenhum novo modo de falha (consome Orçamento extra)`, e o prompt é explícito: "Custo NÃO é modo de falha: não classifique gasto, orçamento ou esforço como falha técnica". O recurso nomeado no campo tinha que ser técnico. Minha verificação afirmou o contrário na linha do `Nenhum novo modo de falha`.

5. **Rastreabilidade entre seções quebrada.** O nome das opções muda da lista para a matriz (`Fila secundária (DLQ/Fallback)` virou `Fila de Fallback (DLQ)`; `Scale-up do Barramento Relay (Nova)` virou `Scale-up do Barramento`), e a seção de sensibilidade aponta para a "OPÇÃO 1", número que não existe porque as opções saíram sem numeração. Quem lê a matriz não casa a linha com o bloco de origem.

Some-se a isso um sexto, menor: a opção de fila secundária menciona `storage frio (S3/blob)`, e o prompt proíbe presumir tecnologia que o insumo não cite.

Todos vão para a **v1.0.1** junto com a correção da matriz, e nenhum foi aplicado, pelo mesmo motivo: alterar o prompt agora invalidaria a execução registrada acima.

---

## Curadoria

**Técnica de criação: meta-prompting.** O meta-prompt trouxe o cenário real, o método em nove etapas e as oito seções de saída, com instrução explícita de não embutir a resposta, nem dizer qual opção vence, nem sugerir combinação vencedora. Pedi também, como nos checkpoints anteriores, a auditoria de overfitting e os pontos fracos; e desta vez incluí um pedido a mais: **um argumento contra uma regra que eu impus**. Foi a parte mais produtiva da resposta.

**Framework: R-I-S-E.** O `Input` importa mais aqui do que parece, porque são dois blocos de natureza diferente, estado e restrições, e confundi-los é o erro que produz recomendação violando requisito não negociável. O `Steps` carrega a disciplina de comparação, que é o coração deste item: sem ordem imposta, o modelo escreve um ensaio com quatro opções e uma favorita. O `Expectation` fixa a matriz, e é a matriz que torna o espantalho visível, opção avaliada célula por célula contra toda restrição não sobrevive como palha.

T-A-G foi a alternativa considerada e perde por um motivo concreto: o `Goal` casaria bem, porque as restrições *são* o objetivo, mas T-A-G não tem componente de entrada, então estado e restrições cairiam ambos dentro da Task e a distinção entre "o que é" e "o que não pode ser violado" se dilui. Essa distinção é o que sustenta a etapa de classificação de restrições, que é o que permite eliminar opção por regra em vez de por preferência.

**O que refinei, cinco correções. Três delas vieram da crítica do próprio modelo, e as duas mais importantes são essas:**

1. **A assimetria do piso físico.** Ele apontou que o piso assume zero chegada nova, o que é utópico, e que basear viabilidade nele aprova arquitetura que falha. Está certo, e a formulação correta é uma assimetria lógica: o piso só serve para **reprovar**, nunca para **aprovar**. Piso acima do SLA prova inviabilidade com certeza. Piso abaixo do SLA não prova nada, porque o tempo real é sempre maior. Escrevi isso como regra explícita, e o efeito apareceu no output: a lacuna sobre a taxa de chegada pós-pico veio com a observação de que o tempo real será consideravelmente maior que os 19,4 minutos. Ironia registrada acima: ele aplicou a regra à capacidade atual e a violou ao avaliar o scale-up.

2. **O limite da regra anti-espantalho.** Este foi o melhor argumento que recebi em quatro checkpoints. Ele mostrou que exigir "novo modo de falha" de toda opção faz o modelo fabricar pseudo-falhas quando a opção é força bruta segura: "aumentar servidores introduz o modo de falha de gastar dinheiro" é custo, não falha técnica, e que isso polui a análise apagando a diferença entre uma opção que adiciona complexidade sistêmica real, como DLQ gerando processamento fora de ordem, e uma que só consome orçamento. A correção manteve a regra e removeu a coerção: permitir explicitamente "Nenhum novo modo de falha" com o recurso consumido em troca, e proibir classificar gasto como falha. No output isso funcionou exatamente como projetado: duas opções usaram a saída honesta, e nenhuma pseudo-falha apareceu.

As outras três correções: exigir cada conta em linha separada com unidades e checagem de ordem de magnitude, porque ele tem razão de que LLM erra multiplicação longa e toda a análise pende dessa conta base; limitar a cinco opções e subir o teto de 80 para 90 linhas, porque ele calculou corretamente que as tabelas estouram o limite e o modo de falha seria cortar as últimas seções; e recolocar a regra que proíbe reproduzir os marcadores entre colchetes, que existia no Checkpoint 03 e ele deixou cair aqui.

**Sanitização: aqui o dado sensível é o próprio número, e ele dá para esconder sem perder nada.**

Este cenário não tem nome de cliente nem hostname. O que é sensível é o envelope de capacidade: 180k msgs/s sustentados, pico de 320k, retenção de 4h. Isso é a impressão digital de capacidade da plataforma de ingestão, e combinado com o SLA de 60s do alerting descreve exatamente onde e por quanto tempo o produto quebra sob carga.

A tentação é dizer que esses números não podem ser removidos, porque toda a análise é aritmética sobre eles. Mas isso é falso, e dá para demonstrar. O piso físico se reescreve como:

```
piso = backlog / capacidade = ((pico − capacidade) × duração) / capacidade = (pico/capacidade − 1) × duração
```

Ou seja, **o piso depende apenas da razão entre pico e capacidade, e da duração: não da escala absoluta.** Normalizando a capacidade para `1.0` e o pico para `1.78x`, com a duração de 25 minutos preservada, o resultado é idêntico: 1.167s, 19,4 minutos. Conferi com as três escalas (180k, 1.0 e 18k) e o piso não se move.

Então a política para este item é: **enviar razões e tempos, não taxas absolutas.** O throughput real nunca sai da empresa, os SLAs em segundos e minutos vão como estão porque são compromisso contratual e não revelam capacidade, e a análise sai idêntica. O custo é de leitura: a recomendação volta em unidades relativas e precisa ser reescalada localmente para virar plano de execução, o que é trabalho mecânico, não perda de informação.

O que eu não normalizaria: a retenção de 4h e os SLAs. A retenção é o prazo duro antes de perder mensagem e precisa ser comparável em unidade real com o tempo de drenagem; e os SLAs, sem eles não existe critério de decisão.
