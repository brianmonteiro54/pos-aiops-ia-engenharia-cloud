# Checkpoint 05: Migração do Forge de lote para tempo real

Quinto item do playbook, e o primeiro que não é um prompt: é uma **cadeia** de três prompts encadeados, cada um recebendo a saída do anterior.

O Forge é o pipeline de dados da Aegis, o que transforma telemetry em tabela consultável. Hoje roda em lote: de hora em hora um job acorda, lê tudo que acumulou e processa de uma vez. O Bruce Banner quer migrar para modelo orientado a eventos, consumindo cada evento do Relay assim que chega.

A mudança é grande demais para um prompt só. Jogar "migre este sistema" em um prompt monolítico devolve plano genérico: o enunciado alerta para isso e a curadoria testa a afirmação. A entrega é a cadeia: um elo diagnostica o acoplamento, o próximo deriva as fases, o terceiro detalha uma fase ao nível de execução.

Saída aberta nos três elos: nenhum entra nos testes determinísticos do Checkpoint 08.

---

## Prompts parametrizáveis da cadeia

### Contratos de encaixe

O que transforma três prompts em cadeia é o contrato: a saída do elo N é exatamente o que o elo N+1 espera receber.

| Elo | Entra | Sai | Alimenta |
|---|---|---|---|
| 1: `diagnostico-de-acoplamento` | `{{estado_atual}}`, `{{requisitos}}` | Contrato por consumidor, etapas por incrementalidade, acoplamentos, riscos, lacunas | O parâmetro `{{diagnostico}}` do elo 2, integral |
| 2: `plano-de-migracao-faseado` | `{{diagnostico}}`, `{{requisitos}}` | Premissas herdadas, discordâncias, fases numeradas com critério de avanço e ponto de reversão, ordem, fora de escopo, lacunas | O parâmetro `{{plano}}` do elo 3, integral |
| 3: `detalhamento-de-fase` | `{{plano}}`, `{{fase_escolhida}}`, `{{requisitos}}` | Pré-condições, passos verificáveis, validação, reversão, critérios de aborto, lacunas | Execução |

Três regras de integridade atravessam os elos 2 e 3, e são elas que impedem a cadeia de degenerar em três prompts independentes rodando em sequência: **não refazer** o trabalho do elo anterior, **não contradizer em silêncio** (discordância vai em seção própria), e **declarar quando a entrada recebida é insuficiente** em vez de preencher com suposição.

### Elo 1: `devops/diagnostico-de-acoplamento/prompt.md` · versão 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{estado_atual}}` | sim | Descrição do pipeline atual: etapas, periodicidade, destino e consumidores |
| `{{requisitos}}` | sim | O que a migração precisa garantir |

`````text
Você é um SRE Arquiteto especializado em engenharia de dados e migração de sistemas. Sua tarefa é analisar o estado atual de um sistema orientado a lote e os requisitos de uma migração para modelo orientado a eventos (contínuo), mapeando o acoplamento e os riscos antes de qualquer plano de mudança.

EXECUTE AS SEGUINTES ETAPAS DE RACIOCÍNIO (não as imprima, use-as para estruturar a saída):
1. Análise de Consumidores: Para cada consumidor listado, identifique o que consome, periodicidade e garantia implícita. Pergunte-se: o que esse consumidor passa a ver de diferente quando a escrita deixa de ser em lote fechado e passa a ser contínua?
2. Classificação de Etapas: Classifique cada etapa de transformação em: INCREMENTAL (opera sobre fatia parcial e resultado é válido), EXIGE LOTE COMPLETO (precisa de todos os dados da janela para resultado correto, como agregações globais ou deduplicações) ou INDETERMINADO (insumos insuficientes).
3. Acoplamentos Críticos: Identifique onde o desenho amarra coisas que o modelo contínuo separa e onde oferece garantias que o modelo contínuo não dá de graça.
4. Ordenação de Riscos: Ordene os riscos da transição por raio de alcance (quantos consumidores atinge e se o efeito é visível ou silencioso). Riscos silenciosos vêm antes.
5. Declaração de Lacunas: Identifique o que os insumos não permitem concluir.

REGRAS ESTRITAS DE SAÍDA:
- Responda em no máximo 70 linhas.
- A seção LACUNAS nunca é omitida nem encurtada.
- Toda afirmação precisa estar ancorada no insumo recebido. Onde houver premissa, escreva "Premissa:".
- Não presuma tecnologia de destino que não esteja na entrada.
- Não reproduza na resposta os marcadores entre colchetes do modelo abaixo: eles indicam onde entra o seu conteúdo.
- Use EXATAMENTE os 5 títulos abaixo, em maiúsculas, nesta ordem. Sem saudações ou preâmbulos.

CONTRATO POR CONSUMIDOR
| Consumidor | O que consome | Periodicidade | Garantia implícita | O que muda no modelo contínuo |
|---|---|---|---|---|
[Uma linha por consumidor mapeado]

ETAPAS POR INCREMENTALIDADE
| Etapa ou Grupo | Classificação | Critério Usado |
|---|---|---|
[Uma linha por etapa ou grupo]

ACOPLAMENTOS CRITICOS
- [O que acopla]: [Por que importa na migração]

RISCOS DA TRANSICAO
| Risco | Consumidores atingidos | Visível ou Silencioso |
|---|---|---|
[Ordenado por raio de alcance e silêncio]

LACUNAS
- [Item faltante]: Necessário [Qual dado/consulta fecharia] (mínimo de 3 itens)

INSUMOS:
[ESTADO ATUAL]
{{estado_atual}}

[REQUISITOS]
{{requisitos}}
`````

```yaml
nome: diagnostico-de-acoplamento
descricao: Elo 1 de cadeia de migração. Mapeia consumidores, classifica etapas por incrementalidade, acoplamentos e riscos de transição.
versao: 1.0.0
tags: [arquitetura, migracao, sre, acoplamento, analise]
inputs:
  - nome: estado_atual
    descricao: Descrição estruturada do pipeline atual, etapas, periodicidade e consumidores dependentes.
  - nome: requisitos
    descricao: Restrições e objetivos não negociáveis da migração para o modelo contínuo.
```

### Elo 2: `devops/plano-de-migracao-faseado/prompt.md` · versão 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{diagnostico}}` | sim | Saída integral do elo 1 |
| `{{requisitos}}` | sim | O mesmo bloco de requisitos |

`````text
Você é um SRE Arquiteto especializado em migração de sistemas. Sua tarefa é receber o diagnóstico de acoplamento de um pipeline de dados e os requisitos de migração, transformando-os em um plano faseado seguro, sem viradas únicas (big-bang) e com pontos de reversão em cada etapa.

EXECUTE AS SEGUINTES ETAPAS DE RACIOCÍNIO (não as imprima, use-as para estruturar a saída):
1. Derivação Baseada no Diagnóstico: Derive as fases a partir dos riscos e acoplamentos listados no diagnóstico recebido, justificando a ordem.
2. Contrato de Integridade da Cadeia: Este prompt NÃO refaz o diagnóstico. Classificação de etapa, garantia implícita de consumidor e ordenação de risco já foram estabelecidas no diagnóstico recebido e são usadas como dadas. Você não reclassifica, não reordena e não reanalisa nada disso. Se discordar de algum ponto, declare expressamente na seção de discordâncias com justificativa, discordar é permitido, rediagnosticar em silêncio não é. Ao citar consumidores e etapas, use exatamente os mesmos nomes que aparecem no diagnóstico, sem abreviar nem renomear, para que a rastreabilidade entre os documentos não se perca.
3. Herança de Lacunas: Para cada fase, verifique se ela depende de alguma lacuna declarada no diagnóstico que ainda não foi resolvida. Fase que depende de lacuna não resolvida deve ser marcada como BLOQUEADA, com a lacuna nomeada e o dado que a desbloqueia. Planejar em cima de lacuna crítica como se ela estivesse resolvida é o modo de falha mais grave deste prompt: o plano parece sólido e se apoia em premissa que ninguém verificou.
4. Reversibilidade e Continuidade: Garanta que cada fase possua ponto de reversão independente de desfazer as anteriores e que cada consumidor saiba como continua operando.
5. Critérios Objetivos: Defina critérios numéricos/observáveis para avanço de fase. A FASE 1 deve focar em observabilidade/comparação sem alterar o caminho produtivo principal.
6. Escopo e Limites: Declare o que fica fora do escopo desta migração.

REGRAS ESTRITAS DE SAÍDA:
- Responda em no máximo 70 linhas.
- A seção LACUNAS nunca é omitida nem encurtada.
- Não presuma tecnologia de destino. Onde houver premissa, escreva "Premissa:".
- Não reproduza na resposta os marcadores entre colchetes do modelo abaixo.
- Use EXATAMENTE os 6 títulos abaixo, em maiúsculas, nesta ordem. Sem saudações ou preâmbulos.

PREMISSAS HERDADAS DO DIAGNOSTICO
- [Premissa ou acoplamento herdado do Elo 1]

DISCORDANCIAS DO DIAGNOSTICO
[Nenhuma, ou listagem justificada de discordâncias]

FASES
- Fase [N] - [Nome] [marcar BLOQUEADA quando aplicável]: Objetivo: [X]. O que muda: [Y]. O que permanece: [Z]. Continuidade por consumidor: [A]. Critério de avanço: [B]. Ponto de reversão: [C]. Depende de lacuna: [nome da lacuna ou "nenhuma"].

ORDEM E JUSTIFICATIVA
[Por que esta ordem de fases, ancorada nos riscos do diagnóstico]

FORA DE ESCOPO
- [O que esta migração não faz]

LACUNAS
- [Item faltante]: Necessário [Qual dado/consulta fecharia] (mínimo de 3 itens)

INSUMOS:
[DIAGNOSTICO]
{{diagnostico}}

[REQUISITOS]
{{requisitos}}
`````

```yaml
nome: plano-de-migracao-faseado
descricao: Elo 2 de cadeia de migração. Transforma o diagnóstico em fases sequenciais, seguras, reversíveis e com critérios de avanço.
versao: 1.0.0
tags: [arquitetura, migracao, sre, planejamento, reversibilidade]
inputs:
  - nome: diagnostico
    descricao: Saída integral gerada pelo Elo 1 (diagnostico-de-acoplamento).
  - nome: requisitos
    descricao: Restrições e objetivos não negociáveis da migração.
```

### Elo 3: `devops/detalhamento-de-fase/prompt.md` · versão 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{plano}}` | sim | Saída integral do elo 2 |
| `{{fase_escolhida}}` | sim | Número ou nome exato da fase a detalhar |
| `{{requisitos}}` | sim | O mesmo bloco de requisitos |

`````text
Você é um SRE Arquiteto de Sistemas. Sua tarefa é detalhar uma única fase específica de um plano de migração de pipeline de dados ao nível de execução técnica, assegurando verificabilidade e reversibilidade real.

EXECUTE AS SEGUINTES ETAPAS DE RACIOCÍNIO (não as imprima, use-as para estruturar a saída):
1. Validação de Existência: Localize a fase escolhida no plano recebido. Se ela não existir no plano, recuse a tarefa explicitamente e diga quais fases existem.
2. Contrato de Integridade: Este prompt NÃO refaz o plano nem o diagnóstico que o originou. Escopo da fase, critério de avanço e ponto de reversão já foram decididos e são usados como dados. Você detalha a execução, não redesenha a estratégia. Se o plano herdado for inconsistente ou omisso nos detalhes necessários para o passo a passo, declare isso como lacuna e recuse preencher com suposições. Se a fase estiver marcada como BLOQUEADA no plano, diga isso na primeira seção e detalhe apenas os passos de desbloqueio.
3. Conferência do Critério: Compare o critério de conclusão que você vai propor com o critério de avanço que o plano declarou para esta fase. Os dois precisam ser a mesma coisa. Se divergirem, declare a divergência explicitamente em vez de substituir silenciosamente o critério do plano pelo seu.
4. Granularidade de Execução: Estruture pré-condições, passos sequenciais verificáveis, critérios de reversão com perda explícita e condições numéricas de aborto imediato. Cada passo declara se é reversível isoladamente ou apenas em conjunto com outros, porque isso define até onde é possível voltar sem desfazer a fase inteira.
5. Honestidade da Reversão: Toda reversão perde algo, tempo, dado processado no intervalo, estado intermediário ou trabalho de configuração. Reversão descrita sem declarar o que se perde é reversão fantasiosa e não é aceitável nesta saída.

REGRAS ESTRITAS DE SAÍDA:
- Responda em no máximo 70 linhas.
- A seção LACUNAS nunca é omitida nem encurtada.
- Toda afirmação técnica precisa de âncora nos insumos. Onde houver premissa, escreva "Premissa:".
- Não reproduza na resposta os marcadores entre colchetes do modelo abaixo.
- Use EXATAMENTE os 7 títulos abaixo, em maiúsculas, nesta ordem. Sem saudações ou preâmbulos.

FASE DETALHADA
Fase escolhida: [Número/Nome]. Critério de avanço definido no plano: [Texto copiado do plano]. Divergência com o critério de conclusão proposto: [Nenhuma, ou qual].

PRE-CONDICOES
- [Pré-condição verificável externa ou interna]

PASSOS
1. Ação: [X]. O que observar: [Y]. Critério de verificação: [Z]. Reversível sozinho (Sim/Não): [W].

VALIDACAO DA FASE
[Critério objetivo de conclusão da fase]

REVERSAO
Procedimento: [Passos de volta]. Janela de reversão: [Tempo limite]. O que se perde: [Consequência concreta da reversão].

CRITERIOS DE ABORTO
- [Condição numérica observável para interromper a execução]

LACUNAS
- [Item faltante]: Necessário [Qual dado/consulta fecharia] (mínimo de 2 itens)

INSUMOS:
[PLANO]
{{plano}}

[FASE ESCOLHIDA]
{{fase_escolhida}}

[REQUISITOS]
{{requisitos}}
`````

```yaml
nome: detalhamento-de-fase
descricao: Elo 3 de cadeia de migração. Detalha uma fase específica do plano em passos executáveis, critérios de aborto e reversão com perda declarada.
versao: 1.0.0
tags: [arquitetura, migracao, sre, runbook, execucao]
inputs:
  - nome: plano
    descricao: Saída integral gerada pelo Elo 2 (plano-de-migracao-faseado).
  - nome: fase_escolhida
    descricao: Identificador ou número exato da fase do plano que será detalhada.
  - nome: requisitos
    descricao: Restrições operacionais e de negócio aplicáveis.
```

---

## Execução

**Modelo de criação da cadeia:** Gemini Pro, com raciocínio estendido: um único meta-prompt gerou os três elos.
**Modelo de execução:** Gemini Pro, com raciocínio estendido, nos três elos.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Mesmo modelo nos três de propósito: se cada elo rodasse em um modelo diferente, uma quebra no encaixe seria indistinguível de diferença de comportamento entre modelos. Com modelo constante, o que sobra para explicar uma falha de encaixe é o contrato.

> As tabelas perderam a estrutura de colunas na transcrição da interface. Reconstruí a formatação; nenhum valor, classificação ou texto foi alterado. Mantive inclusive os erros de digitação do modelo, sinalizados adiante.

### Rodada 1: elo 1, diagnóstico

**CONTRATO POR CONSUMIDOR**

| Consumidor | O que consome | Periodicidade | Garantia implícita | O que muda no modelo contínuo |
|---|---|---|---|---|
| Sentinel | Tabelas agregadas do Forge | A cada 60min (após o job batch) | Completude e atomicidade por partição horária | Passa a receber atualizações parciais contínuas, perdendo a garantia de janela fechada |
| Cerebro | Eventos transformados | A cada 60min (após o job batch) | Ordem e fechamento de lote para reindexação | Recebe eventos fragmentados no tempo, impactando a lógica de indexação em lote |
| Pepper | Relatórios de billing | De madrugada (diário/lote) | Fechamento contábil consolidado da janela | Deixa de encontrar uma base estática e passa a lidar com fluxo contínuo de registros |

**ETAPAS POR INCREMENTALIDADE**

| Etapa ou Grupo | Classificação | Critério Usado |
|---|---|---|
| Ingestão (forge-batch-ingest) | EXIGE LOTE COMPLETO | Depende de agendamento cron e leitura fechada de intervalo |
| Transformação Spark (14 etapas) | INDETERMINADO | Insumos não detalham se há operações de agregação global ou janela móvel |
| Gravação no DW | EXIGE LOTE COMPLETO | Particionamento por hora exige escrita atômica por janela fechada |

**ACOPLAMENTOS CRITICOS**

```
- Acoplamento temporal entre o job de 60min e a leitura dos consumidores: O DW assume janelas
  horárias fechadas; o modelo contínuo quebra essa barreira de tempo.
- Acoplamento de resiliência por acumulação: Falhas no lote acumulam o dobro de volume no ciclo
  seguinte, comportamento que precisa ser repensado com backpressure no streaming.
```

**RISCOS DA TRANSICAO**

| Risco | Consumidores atingidos | Visível ou Silencioso |
|---|---|---|
| Divergência de dados contábeis por leitura prematura | Pepper | Silencioso |
| Alertas falsos por estado parcial de agregação | Sentinel | Visível |
| Falhas de indexação por quebra de ordenação temporal | Cerebro | Visível |

**LACUNAS**

```
- Granularidade das 14 etapas do Spark: Necessário listar o código ou spec das transformações para
  confirmar quais etapas exigem janelas globais (ex: distinct, join).
- SLA de entrega dos consumidores: Necessário consultar contratos de tolerância a atraso para
  Sentinel, Cerebro e Pepper.
- Mecanismo de reprocessamento atual: Necessário insumo sobre como o pipeline lida hoje com
  reprocessamento de dias anteriores.
```

**O que funcionou.** O achado central apareceu no lugar certo: os relatórios de billing dependem de "fechamento contábil consolidado da janela", e o risco de divergência contábil por leitura prematura veio **primeiro** na tabela, classificado como **silencioso**. Era exatamente isso que a regra de ordenar risco silencioso antes de risco ruidoso existia para produzir, dado errado que ninguém percebe é pior que alerta falso que todos veem.

As 14 etapas do Spark foram marcadas como INDETERMINADO com o critério honesto de que o insumo não as descreve individualmente, e a lacuna correspondente virou a primeira da lista. O enunciado genuinamente não descreve as etapas, então chutar uma classificação teria sido pior.

**O erro que eu encontrei e decidi não corrigir.** A ingestão e a gravação no DW foram classificadas como EXIGE LOTE COMPLETO com critérios que descrevem a implementação atual, não uma restrição inerente: "depende de agendamento cron" e "particionamento por hora exige escrita atômica". Rodar em cron hoje é escolha de desenho; a ingestão é na verdade a parte mais incrementável do pipeline, e consumir continuamente do Relay é o requisito número um da migração. Na gravação o problema se repete com um agravante: o acoplamento real é a suposição de completude do consumidor, que já estava corretamente capturada na primeira tabela, então o mesmo acoplamento foi contado duas vezes, uma no lugar certo e uma como se fosse limitação do pipeline.

Repassei o diagnóstico ao elo 2 **sem corrigir**, deliberadamente. A seção `DISCORDANCIAS DO DIAGNOSTICO` existe para esse caso, e agora ela tinha um erro real para pegar. Os três desfechos possíveis diziam coisas diferentes: declarar a discordância provaria que a cadeia se autocorrige com rastro; herdar em silêncio materializaria a cascata de erro; corrigir sem declarar seria o pior, porque daria a resposta certa e perderia a rastreabilidade, que é a única vantagem da cadeia sobre um prompt monolítico.

### Rodada 2: elo 2, plano faseado

```
PREMISSAS HERDADAS DO DIAGNOSTICO
- Consumo atual de Sentinel, Cerebro e Pepper baseado em lotes fechados horários com garantias de
  completude e atomicidade.
- Classificação do Elo 1 de que ingestão e gravação no DW exigem lote completo.

DISCORDANCIAS DO DIAGNOSTICO
O diagnóstico do Elo 1 classificou a ingestão e a gravação no DW como "EXIGE LOTE COMPLETO" com base
no fato de que hoje rodam em cron e partição horária. Discordamos dessa classificação: rodar em lote
hoje é escolha de implementação atual, não propriedade inerente. A ingestão contínua do Relay e a
escrita incremental em partições são tecnicamente viáveis. O verdadeiro desafio não é o pipeline
recusar blocos menores, mas sim a garantia de completude exigida pelos consumidores (Sentinel,
Cerebro e Pepper) que dependem de janelas fechadas. Ajustamos o plano considerando a ingestão
contínua como meta viável nas primeiras fases.

FASES
- Fase 1 - Observabilidade e Dupla Gravação Paralela: Objetivo: Estabelecer baseline sem alterar o
  tráfego produtivo principal. O que muda: Criação de um pipeline paralelo consumindo continuamente
  do Relay para um destino de teste/sombra. O que permanece: O job em cron e o pipeline original do
  Forge rodando inalterados. Continuidade por consumidor: 100% idêntica à atual. Critério de avanço:
  Paridade de dados verificada entre a saída sombra e o batch tradicional por 48 horas contínuas.
  Ponto de reversão: Desligar o consumer sombra sem impacto algum no produtivo. Depende de lacuna:
  nenhuma.

- Fase 2 - Ingestão Contínua com Consumidores em Modo Duplo: Objetivo: Migrar a ingestão para o
  modelo contínuo mantendo compatibilidade para os consumidores legados. O que muda: O Forge passa a
  consumir continuamente do Relay em pequenos blocos. O que permanece: Geração de visões horárias
  simuladas para não quebrar a garantia implícita dos consumidores. Continuidade por consumidor:
  Sentinel, Cerebro e Pepper continuam operando através de adaptadores de janela horária. Critério de
  avanço: Estabilidade da ingestão contínua por 5 dias sem acumulo de backlog ou picos de latência.
  Ponto de reversão: Chaveamento rápido de volta para o acionamento em cron do job original
  (utilizando o backlog do Relay). Depende de lacuna: Granularidade das 14 etapas do Spark.

- Fase 3 - Transição dos Consumidores e Desativação do Legado: Objetivo: Remover o modelo de lote e
  liberar os consumidores para o consumo direto do fluxo contínuo. O que muda: Atualização de
  Sentinel, Cerebro e Pepper para consumirem os blocos incrementais. O que permanece: Infraestrutura
  do Relay e core do Forge modernizado. Continuidade por consumidor: Adaptação final dos contratos de
  garantia implícita dos consumidores. Critério de avanço: Todos os consumidores migrados sem estouro
  de SLA de entrega. Ponto de reversão: Reversão restrita ao consumidor que falhar, religando o
  adaptador de lote para ele. Depende de lacuna: SLA de entrega dos consumidores.

ORDEM E JUSTIFICATIVA
A ordem prioriza a segurança estrutural exigida pelos requisitos. A Fase 1 foca em criar paridade e
observabilidade sem tocar na produção, mitigando os riscos silenciosos (como o da Pepper). A Fase 2
ataca diretamente o requisito principal (consumo contínuo do Relay) mas protege os consumidores
legados através de visões simuladas. A Fase 3 conclui a virada dos consumidores. Esta sequência evita
o big-bang e garante pontos de reversão independentes.

FORA DE ESCOPO
- Redesenho completo da lógica interna das 14 etapas de transformação do Spark além do necessário
  para aceitar blocos contínuos.
- Alteração nos contratos de negócio dos relatórios de billing da Pepper.

LACUNAS
- Granularidade das 14 etapas do Spark: Necessário detalhar o código ou spec para confirmar se alguma
  transformação interna exige estado global irrecuperável em micro-lotes.
- SLA de entrega dos consumidores: Necessário confirmar os limites exatos de tolerância a atraso para
  Sentinel, Cerebro e Pepper.
- Mecanismo de reprocessamento em lote: Necessário insumo sobre como lidar com reprocessamentos
  retroativos no modelo orientado a eventos.
```

**O resultado do teste: a cadeia se autocorrigiu com rastro.** O elo 2 pegou o erro do elo 1 e declarou a discordância, chegando ao mesmo raciocínio que eu havia feito, sem que nada tivesse sido dito a ele. É o melhor dos três desfechos, e é evidência em vez de afirmação: num prompt monolítico esse erro de classificação ficaria dentro de uma saída única e o plano sairia contradizendo o requisito principal da migração sem deixar marca.

O plano acertou também os outros dois pontos verificados. A fase 1 não toca produção: pipeline sombra, cron original intacto, reversão desligando o consumer, critério de paridade de 48 horas. E os nomes dos consumidores vieram literais do diagnóstico, preservando a rastreabilidade que a regra 2 exige. A solução de "visões horárias simuladas" na fase 2 é boa engenharia: mantém a garantia de completude dos consumidores enquanto a ingestão já é contínua, atacando exatamente o acoplamento que o diagnóstico identificou.

**Duas falhas de contabilidade.** A regra do BLOQUEADA foi cumprida pela metade: as fases 2 e 3 declaram `Depende de lacuna` com o nome da lacuna, mas nenhuma recebeu o marcador, e as duas lacunas seguem abertas na seção final. Fica uma indefinição para quem vai executar, ou a lacuna impede a fase, ou não impede e falta dizer por quê. E a seção de premissas herdadas lista "classificação do Elo 1 de que ingestão e gravação exigem lote completo" como premissa, sendo que essa classificação é rejeitada na seção seguinte: premissa herdada deveria listar o que foi usado como base, não o que foi descartado.

### Rodada 3: elo 3, detalhamento da Fase 1

```
FASE DETALHADA
Fase escolhida: Fase 1 - Observabilidade e Dupla Gravação Paralela. Critério de avanço definido no
plano: Paridade de dados verificada entre a saída sombra e o batch tradicional por 48 horas
contínuas. Divergência com o critério de conclusão proposto: Nenhuma.

PRE-CONDICOES
- Infraestrutura de consumo contínuo conectada ao Relay para o ambiente sombra.
- Acesso de leitura validado ao destino de teste/sombra e ao Data Warehouse produtivo.

PASSOS
1. Ação: Subir o pipeline sombra conectando ao Relay em modo de consumo contínuo isolado do DW de
   produção. O que observar: Logs de consumo do Relay e ausência de erros de conexão. Critério de
   verificação: 100% de leitura contínua por 1 hora sem queda. Reversível sozinho (Sim/Not): Sim.
2. Ação: Configurar rotina de comparação paralela (diff) entre as tabelas do pipeline sombra e o
   output do job cron legada. O que observar: Divergências de contagem de registros e schema.
   Critério de verificação: Estabilidade do diff por 48 horas consecutivas. Reversível sozinho
   (Sim/Not): Sim.

VALIDACAO DA FASE
Paridade de dados comprovada e estável entre a saída sombra e o batch tradicional por 48 horas
contínuas, sem interferir no pipeline produtivo original.

REVERSAO
Procedimento: Desligar o consumer sombra e apagar os recursos de teste alocados. Janela de reversão:
A qualquer momento durante ou após a fase. O que se perde: Apenas o histórico acumulado no ambiente
de testes/sombra (zero perda de dados produtivos).

CRITERIOS DE ABORTO
- Qualquer interrupção ou impacto observado no job em cron produtivo ou na base dos consumidores
  legados.
- Divergência persistente superior a 0,1% nos dados comparados do pipeline sombra após ajustes
  iniciais.

LACUNAS
- Granularidade das 14 etapas do Spark: Necessário validar o código interno para garantir que a
  paridade de 48 horas cubra todas as regras de negócio legadas.
- SLA de entrega dos consumidores: Necessário confirmar se a observabilidade sombra consegue coletar
  métricas em tempo real idênticas às exigidas pelos consumidores.
```

**A regra do cross-check funcionou limpa.** O critério de avanço veio copiado literalmente do plano e a divergência foi declarada como "Nenhuma". O elo 3 não substituiu silenciosamente o critério do plano pelo seu, que era o risco.

**A reversão foi meia-vitória, e a metade que falhou é a interessante.** Eu havia previsto que a fase 1 esconde uma armadilha: desligar um pipeline sombra não afeta produção nenhuma, então a resposta fácil é "não se perde nada", o que seria exatamente a reversão fantasiosa que a regra 5 proíbe. O output **não** caiu nisso: nomeou a perda do histórico acumulado. Mas tratou essa perda como irrelevante, com o parêntese "zero perda de dados produtivos", quando aquele histórico **é** a evidência que destrava a fase. O critério de avanço exige 48 horas contínuas de paridade, então reverter zera o relógio e a fase recomeça do zero. O custo real é dois dias de observação, não "apagar recursos de teste".

**Granularidade de passo insuficiente.** O passo 2 tem como critério de verificação "estabilidade do diff por 48 horas consecutivas", que é o próprio critério de conclusão da fase. Um passo cuja verificação leva 48 horas não é passo executável, é a fase inteira com outro nome, e sem checkpoint intermediário não existe como detectar cedo que o diff foi configurado errado, o que é justamente o erro mais provável nessa etapa.

**Critérios de aborto: um de dois é numérico.** "Divergência persistente superior a 0,1%" é objetivo. "Qualquer interrupção ou impacto observado no job em cron produtivo" é observável mas não numérico, e deixa em aberto o que conta como impacto.

Também ficaram três erros de digitação do modelo, que mantive na transcrição: o rótulo `Reversível sozinho (Sim/Not)` com "Not" em lugar de "Não", "job cron legada", e "acumulo" sem acento no critério de avanço da fase 2.

**Uma quebra de rastreabilidade que a tabela de verificação deixou passar.** A terceira lacuna foi renomeada entre os elos: o diagnóstico escreveu "Mecanismo de reprocessamento **atual**" e o plano repassou como "Mecanismo de reprocessamento **em lote**". A regra 2 do elo 2 exige os mesmos nomes sem renomear, justamente para a rastreabilidade não se perder, e a verificação marcou "Sim" para nomes literais olhando só os consumidores. É renomeação pequena e de efeito real: quem procurar a lacuna pelo nome no documento anterior não acha.

### Verificação da cadeia

| Verificação | Resultado |
|---|---|
| Elo 1 identificou o acoplamento silencioso do billing | Sim, e ordenado primeiro por ser silencioso |
| Elo 1 tratou as 14 etapas honestamente | Sim, INDETERMINADO com lacuna correspondente |
| Elo 1 confundiu prática atual com propriedade inerente | Sim: erro deliberadamente repassado |
| Elo 2 pegou o erro e declarou discordância | **Sim**: mecanismo de integridade validado |
| Elo 2 usou nomes literais do diagnóstico | Sim |
| Fase 1 sem tocar no caminho de produção | Sim |
| Elo 2 marcou fase como BLOQUEADA quando depende de lacuna | Parcial: declarou a dependência, não aplicou o marcador |
| Elo 3 copiou o critério do plano e conferiu divergência | Sim, "Nenhuma" declarada |
| Elo 3 declarou o que se perde na reversão | Parcial: nomeou a perda, não reconheceu o relógio de 48h |
| Elo 3 com critérios de aborto numéricos | Parcial: 1 de 2 |
| Encaixe entre elos sem quebra de formato | Sim nas duas passagens |

---

## Curadoria

**Técnica de criação: meta-prompting, com uma decisão de arquitetura no próprio meta-prompt.** Usei **um único meta-prompt** para gerar os três elos, em vez de três separados. O motivo é o encaixe: o contrato de saída do elo 1 tem que ser exatamente o contrato de entrada do elo 2, e gerando separadamente o elo 2 pode esperar uma forma que o elo 1 não produz. Gerando junto, com a tabela de contratos declarada no meta-prompt, os três nascem consistentes por construção. Nas duas passagens da execução não houve quebra de formato, o que é evidência a favor dessa escolha.

**Framework: R-I-S-E nos três elos, com uma diferença importante.** Nos elos 2 e 3 o componente `Input` não é dado bruto, é **artefato produzido pelo elo anterior**: e isso muda o que o prompt precisa dizer sobre ele. Não basta descrever o parâmetro: é preciso declarar o que naquele artefato é autoridade estabelecida e não deve ser reaberto. Foi daí que saíram as três regras de integridade da cadeia. O `Steps` de cada elo é curto de propósito, porque a decomposição da tarefa já foi feita na cadeia: o que em um prompt monolítico seria um método de dezesseis etapas virou três métodos de cinco a seis.

**A divisão em três elos e não em dois ou cinco.** Dois elos deixariam o plano e o detalhamento no mesmo passo, e aí volta o problema da profundidade: detalhar todas as fases no mesmo output produz uma superficialidade por fase. Cinco elos fragmentariam demais e multiplicariam pontos de encaixe, que são os pontos frágeis. Três resolve porque cada elo tem uma pergunta própria e verificável: o que está acoplado, em que ordem mexer, e como executar um passo sem quebrar nada. O elo 3 recebendo **uma** fase por parâmetro é o que garante profundidade: ele é reusado uma vez por fase, em vez de tentar cobrir todas.

**O teste que dá valor a este checkpoint.** Encontrei um erro conceitual real na saída do elo 1: confundir "roda em lote hoje" com "exige lote completo por natureza", e escolhi repassá-lo sem corrigir. Isso transformou uma afirmação de projeto em experimento: a seção de discordâncias funciona ou não funciona? Funcionou. O elo 2 identificou o erro, explicou por que a classificação estava errada, e ajustou o plano mantendo a ingestão contínua como meta, que é o requisito principal que o erro do elo 1 teria sabotado.

Isso responde o argumento mais forte que o próprio modelo levantou contra a cadeia, o de propagação de erro: "se o Elo 1 classificar uma etapa de forma incorreta, o Elo 2 aceitará o erro como verdade absoluta". A resposta é uma inversão. A cadeia **não cria** o risco de propagação, num prompt monolítico o mesmo erro acontece dentro de uma saída única e ninguém vê. O que a cadeia faz é tornar o erro inspecionável: a classificação do elo 1 fica escrita em um artefato revisável antes de gastar o elo 2, e o próprio elo 2 tem um mecanismo formal para recusá-la. O custo real da divisão não é a propagação, é que o **ponto de revisão humana entre elos é opcional**: quem repassa a saída sem ler paga o preço de três execuções e não colhe o benefício da inspeção.

Os outros dois custos que ele apontou são reais e eu aceito: três execuções gastam mais tokens que uma, e a orquestração é manual enquanto não houver automação. O teto de 70 linhas por elo existe justamente para limitar o primeiro.

**O que refinei, cinco patches.** Três consertam regras que caíram na tradução do meta-prompt para os prompts, e dois vêm da crítica do modelo:

1. **"Não refaça o trabalho do elo anterior"** foi a regra mais importante e a que sumiu. O modelo implementou declarar discordância e declarar entrada insuficiente, mas não a proibição de reanalisar. Sem ela o elo 2 rediagnostica por conta própria e a cadeia degenera em três prompts independentes. Recolocada nos elos 2 e 3 com a lista do que é autoridade estabelecida: classificação de etapa, garantia de consumidor, ordenação de risco, escopo de fase, critério de avanço.
2. **Rastreabilidade por nome literal**, que vem da crítica dele sobre deriva de formato entre elos: se o elo 1 chama um consumidor de um jeito e o elo 2 de outro, a correlação se perde. Virou regra de copiar os nomes sem renomear, e funcionou na execução.
3. **Herança de lacuna com fase bloqueada**, que responde à crítica mais séria dele, a cascata de incerteza: se o elo 1 declara lacuna crítica e o texto é repassado de todo jeito, o elo 2 planeja sobre premissa não verificada e o plano parece sólido. A regra manda marcar BLOQUEADA a fase que depende de lacuna aberta. Na execução saiu pela metade, e o próximo patch corrige isso.
4. **Conferência do critério** no elo 3: comparar o critério de conclusão proposto com o critério de avanço que o plano declarou, e declarar divergência em vez de substituir em silêncio. Funcionou.
5. **Proibição da reversão fantasiosa** no elo 3: toda reversão perde algo, e reversão sem perda declarada não é aceitável. Funcionou pela metade, como analisado acima.

**Correções para a v1.0.1, não aplicadas para não invalidar as execuções registradas:**

- **Elo 1:** separar propriedade inerente de escolha de implementação no critério de classificação. "Hoje roda em lote" nunca basta para classificar como EXIGE LOTE COMPLETO; o critério é se o resultado fica incorreto quando calculado sobre uma fatia parcial.
- **Elo 2:** dependência de lacuna é binária, ou a fase vem marcada BLOQUEADA, ou explica por que aquela lacuna não bloqueia. E premissa herdada lista só o que foi usado como base, nunca o que foi rejeitado na seção de discordâncias.
- **Elo 3:** ao declarar o que se perde na reversão, verificar explicitamente se a perda inclui progresso em direção ao critério de avanço: janela de observação, tempo de estabilidade acumulado, ciclos de comparação. E nenhum passo pode ter critério de verificação igual ao critério de conclusão da fase: se a verificação de um passo demora tanto quanto a fase, o passo precisa ser subdividido com checkpoints intermediários.

**Sanitização: aqui o dado sensível é o grafo de dependências, não os valores.**

Diferente do Checkpoint 03, onde o risco era o envelope de capacidade, e do 04, onde era o throughput absoluto, neste o que vale proteger é **quem depende de quem, com que garantia e em que horário**. O insumo revela que os relatórios de billing rodam de madrugada e dependem de partição horária fechada. Isso é um mapa de onde e quando corromper dado financeiro sem que ninguém perceba na hora: o próprio diagnóstico classificou esse risco como silencioso.

A política: substituir nome de pessoa por papel, porque `Pepper` associa uma executiva nominalmente ao processo de faturamento e nada na análise depende disso, `relatórios de billing` basta e o diagnóstico fica idêntico. Substituir nome de sistema por rótulo funcional (`consumidor-de-agregados`, `indexador`, `faturamento`), porque o raciocínio da cadeia opera sobre a garantia implícita de cada consumidor, não sobre a identidade deles. Generalizar a janela horária do faturamento para "janela diária fora do horário comercial", que preserva a natureza do acoplamento e remove a precisão operacional.

O que **não** sanitizaria: a estrutura numérica, 14 etapas, ciclo de 60 minutos, particionamento por hora, os 40 minutos de processamento. Toda a classificação de incrementalidade e todo o desenho de fases dependem dessas quantidades, e elas não identificam a empresa nem o cliente.
