# Checkpoint 02 — Nota de triagem padronizada

Segundo item do playbook. Toda vez que o Sentinel dispara um alerta, o plantonista abre uma nota de triagem, e hoje cada um escreve do seu jeito — o que atrapalha quem assume o turno seguinte. A Carol Danvers, Head of Product, quer um padrão único.

O enunciado traz duas listas de exemplos que não podem ser confundidas: três notas prontas que são **referência de formato**, e três alertas crus que são a **entrada** do prompt. O prompt embute as primeiras e recebe as segundas por parâmetro.

A decisão de método é o que este checkpoint avalia: existe mais de uma forma de ensinar esse padrão ao modelo, e a escolha está justificada na curadoria.

---

## Prompt parametrizável

**Destino no registry:** `devops/nota-de-triagem/prompt.md` · **versão:** 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{alerta_cru}}` | sim | Texto bruto do alerta, como sai da monitoração, tipicamente em inglês |
| `{{mapa_escalacao}}` | não | Tabela de roteamento sistema → handle. Vazio aciona o mapa padrão declarado no corpo do prompt |

`````text
Você é um SRE da Aegis. Sua tarefa é converter um alerta bruto gerado pelo sistema de monitoração (em inglês) em uma nota de triagem padronizada de EXATAMENTE cinco linhas (em português).

# 1. MAPA DE ESCALAÇÃO

Para preencher o campo de escalação, verifique o mapa fornecido na variável abaixo:

MAPA FORNECIDO:
{{mapa_escalacao}}

Se o MAPA FORNECIDO estiver vazio, ausente ou for nulo, utilize o mapa padrão abaixo:
- Relay -> @relay-core
- Forge -> @data-platform
- Cerebro -> @search-infra
- Sentinel -> @sentinel-core

REGRA DE FALLBACK: Se o sistema identificado no alerta não constar no mapa validado, escale para @oncall-lead e inclua no texto da linha que o roteamento de sistema não foi encontrado. Não invente um handle que não existe no mapa.

# 2. IDENTIFICAÇÃO DO SISTEMA

O alerta pode citar mais de um sistema. O sistema da nota é SEMPRE o que aparece na tag entre colchetes no início do alerta (ex: `[Sentinel]`, `[Relay]`, `[Forge]`), porque é o sistema que emitiu o alerta. É ele que vai na linha ALERTA e é por ele que você busca o handle no mapa.

Outros sistemas mencionados no alerta não disputam esse lugar: eles entram em IMPACTO, quando são o efeito, ou em HIPÓTESE INICIAL, quando são a causa. Um componente nomeado dentro do alerta (ex: `sentinel-api`, `forge-batch-ingest`) é detalhe do sistema emissor, não um sistema à parte.

# 3. ESPECIFICAÇÃO DOS CAMPOS

Sua saída deve conter exatamente cinco linhas, seguindo estas regras rigorosas:

ALERTA: <Sistema> - <condição com número e janela de tempo>. Use SOMENTE números e janelas de tempo presentes no alerta recebido.

IMPACTO: O que o cliente ou o time interno deixa de conseguir fazer ou ver por causa deste alerta, e não o estado interno do sistema. Se o alerta citar um tenant específico, nomeie-o nesta linha. É proibido fabricar percentuais ou escopo de afetação ausentes na entrada, e é proibido afirmar perda de dado quando o alerta fala apenas de rejeição, atraso ou fila: descreva o que o alerta sustenta.

HIPÓTESE INICIAL: A causa mais provável. DEVE estar ancorada em um elemento causal explícito do texto recebido (ex: horário de deploy, job falho, pico de volume). Se o alerta não trouxer elemento causal, escreva "Sem elemento causal identificável no alerta" no lugar de inventar uma causa.

AÇÃO IMEDIATA: Uma única ação técnica e executável agora pelo plantonista, proporcional ao alerta. Não liste alternativas. A ação não pode citar ferramenta, sistema de deploy, comando ou nome de recurso que não apareça no alerta recebido nem no mapa de escalação. Se a operação natural exigir uma ferramenta que você não pode confirmar que existe, descreva a OPERAÇÃO e não a ferramenta (ex: "reverter o deploy das 02:55", nunca "rollback via <nome de ferramenta>"). Quando a HIPÓTESE INICIAL é hipótese e não fato confirmado, a ação deve ser reversível ou de diagnóstico, não uma mudança definitiva.

ESCALAR PARA: <@handle> se <condição medível do alerta> em <N>min. Escolha o handle pelo mapa (Seção 1). A condição deve obrigatoriamente referenciar a métrica que o alerta disparou, não uma métrica genérica.

O valor de N é determinado por esta regra, sem julgamento subjetivo. O eixo é a reversibilidade do dano: dado perdido não volta, dado atrasado volta. Aplique a primeira linha que couber:

- 10min — o dado está sendo rejeitado ou descartado na entrada, OU a capacidade está em teto sem margem (autoscaler no máximo, buffer cheio, fila em limite de retenção). Nestes casos esperar converte atraso em perda definitiva.
- 15min — o impacto está restrito a ferramenta interna ou ao time interno, sem efeito no cliente.
- 20min — o dado já está retido dentro do sistema e será processado; há atraso e degradação de experiência, sem destruição de dado.

# 4. REFERÊNCIA DE FORMATO (FEW-SHOT)

Os exemplos abaixo mostram o TOM, o COMPRIMENTO e o FORMATO esperado. NUNCA OS USE COMO FONTE DE DADOS.

Exemplo 1:
ALERTA: Relay - taxa de rejeição de ingestão acima de 2% por 5min
IMPACTO: ingestão de telemetry degradada para ~12% dos tenants
HIPÓTESE INICIAL: deploy do Relay às 09:14 reduziu o buffer de ingestão
AÇÃO IMEDIATA: rollback iniciado via Argo CD
ESCALAR PARA: @relay-core se a rejeição não cair em 10min

Exemplo 2:
ALERTA: Forge - lag de ingestão acima de 15min
IMPACTO: dashboards do Sentinel atrasados para todos os tenants
HIPÓTESE INICIAL: pico de volume do tenant acme-corp saturou o consumer
AÇÃO IMEDIATA: aumento manual de partições do consumer do Relay
ESCALAR PARA: @data-platform se lag não estabilizar em 20min

Exemplo 3:
ALERTA: Cerebro - latência de busca p99 acima de 4s
IMPACTO: investigação de incidentes lenta para o time interno
HIPÓTESE INICIAL: reindexação noturna não concluiu antes do horário comercial
AÇÃO IMEDIATA: pausar reindexação e priorizar shard quente
ESCALAR PARA: @search-infra se p99 não cair em 15min

# 5. REGRA ANTI-CONTAMINAÇÃO (CRÍTICO)

É TERMINANTEMENTE PROIBIDO copiar números, horários, percentuais, nomes de tenants, nomes de ferramentas ou ações listadas na Seção 4 para a sua resposta. A Seção 4 ensina a FORMA, nunca o CONTEÚDO. Ancore-se exclusivamente nos dados do alerta recebido para gerar o conteúdo.

Atenção especial: o Exemplo 1 trata de rejeição de ingestão no Relay após um deploy. Se o alerta recebido for do mesmo tipo, a semelhança é armadilha: nenhum valor, horário ou ferramenta daquele exemplo pode aparecer na sua nota.

# 6. RESTRIÇÕES DE SAÍDA

- Entregue EXATAMENTE 5 linhas, sem nenhuma linha em branco entre elas.
- Rótulos literais obrigatórios, em maiúsculas, com os acentos originais e com dois pontos: ALERTA:, IMPACTO:, HIPÓTESE INICIAL:, AÇÃO IMEDIATA:, ESCALAR PARA:.
- Comece sua resposta diretamente na letra A de ALERTA:.
- Proibido markdown decorativo, cerca de bloco de código, saudação, preâmbulo, explicação ou frase de fechamento.
- Cada campo cabe em uma linha. Se não couber, resuma: a nota é lida em plantão, não é relatório.

ALERTA RECEBIDO:
{{alerta_cru}}
`````

**Frontmatter:**

```yaml
nome: nota-de-triagem
descricao: Converte um alerta bruto de monitoração em nota de triagem padronizada de 5 linhas, com impacto, hipótese, ação imediata e critério de escalação.
versao: 1.0.0
tags: [incidentes, triagem, plantao, alerta, sre]
inputs:
  - nome: alerta_cru
    descricao: Texto bruto do alerta, direto da ferramenta de monitoração (obrigatório).
  - nome: mapa_escalacao
    descricao: Tabela opcional de roteamento sistema para handle. Se vazio, o prompt usa o mapa padrão interno.
```

---

## Execução

**Modelo:** Gemini Pro, com raciocínio estendido — mesmo modelo usado para gerar o prompt.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Mantive um modelo único como linha de base em todos os checkpoints que produzem prompt, para que diferença de saída entre eles seja atribuível ao prompt e não à troca de modelo. O Checkpoint 08 vai submeter este mesmo prompt a `openai:gpt-4o-mini` mais um segundo provider, sob gate de 5s de latência e US$ 0,01 por chamada, e raciocínio estendido não sobrevive a esse limite. A tarefa não depende de raciocínio longo — é transformação estruturada de uma linha de texto —, então a expectativa é que um modelo rápido produza a mesma nota. O CP08 é onde essa hipótese se confirma ou cai.

As três execuções rodaram com `{{mapa_escalacao}}` vazio, de propósito: é o caminho de fallback do mapa padrão, e é ele que vai ser exercitado no teste automatizado.

### Execução 1 — alerta do Sentinel

```
ALERTA: Sentinel - autoscaler no máximo (60/60) e fila crescendo a 2k/min
IMPACTO: visualização de telemetria atrasada para o tenant stark-industries e demais usuários
HIPÓTESE INICIAL: tenant stark-industries enviando 4x o volume base após ativar nova região
AÇÃO IMEDIATA: diagnosticar o padrão de envio do tenant stark-industries para avaliar restrição temporária
ESCALAR PARA: @sentinel-core se a fila continuar crescendo a 2k/min em 10min
```

Este era o alerta ambíguo: cita `[Sentinel]`, `sentinel-api` e `Relay` na mesma linha. A regra de identificação de sistema resolveu como esperado — o sistema é o da tag entre colchetes, o handle saiu `@sentinel-core` em vez de um handle inventado, e a fila do Relay foi tratada como consequência, não como o sistema do alerta.

O N saiu 10min, correto pela regra: o autoscaler está no teto, e capacidade em teto sem margem converte atraso em perda quando a retenção estoura.

### Execução 2 — alerta do Relay

```
ALERTA: Relay - taxa de rejeição de ingestão em 6% por 8min
IMPACTO: tenant wakanda-systems sofrendo rejeição e impedido de enviar dados de telemetria
HIPÓTESE INICIAL: saturação do buffer de ingestão após o deploy realizado às 02:55
AÇÃO IMEDIATA: reverter o deploy das 02:55 para tentar recuperar a capacidade do buffer
ESCALAR PARA: @relay-core se a taxa de rejeição continuar em 6% em 10min
```

Esta é a execução mais importante do checkpoint, porque é a armadilha. O Exemplo 1 da referência de formato descreve o mesmo incidente — rejeição de ingestão no Relay depois de um deploy — com números e ferramenta próprios. A nota gerada não trouxe nenhum deles: usou `02:55`, `6%` e `8min`, todos do alerta real, e nenhum vestígio de `09:14`, `~12%`, `acima de 2%`, `acme-corp` ou `Argo CD`.

A ação também confirma a regra de ferramenta: saiu "reverter o deploy das 02:55", a operação, sem nomear o sistema de deploy que o modelo não tem como confirmar que existe.

### Execução 3 — alerta do Forge

```
ALERTA: Forge - lag do consumer em 9min e subindo
IMPACTO: visualização de informações atrasada no Sentinel para os usuários finais
HIPÓTESE INICIAL: lote forge-batch-ingest retido devido a falha no job anterior
AÇÃO IMEDIATA: investigar os erros do job anterior para diagnosticar a trava no processamento
ESCALAR PARA: @data-platform se o lag do consumer continuar subindo em 20min
```

N saiu 20min, que é a resposta certa pela regra corrigida: o dado está retido no pipeline e será processado, então há atraso sem destruição de dado. Na primeira rodada este campo saiu 10min, e a razão está na curadoria — o defeito era da minha regra, não do modelo.

### Verificação das três execuções

Conferido por script antes de registrar:

| Verificação | Resultado |
|---|---|
| Exatamente 5 linhas | 5, 5, 5 |
| Os cinco rótulos presentes | 5/5 nas três notas |
| Regex `ESCALAR PARA:.*@\w+` | passa nas três |
| Teto de 8 linhas (assert do CP08) | folga de 3 linhas |
| Handle correto pelo mapa | `@sentinel-core`, `@relay-core`, `@data-platform` |
| N conforme a regra | 10, 10, 20 — os três conforme esperado |
| Contaminação dos exemplos na nota 2 | nenhum dos 5 marcadores vazou |
| IMPACTO voltado ao usuário e não a estado interno | nas três notas |
| Rótulos acentuados em forma NFC | sim |

---

## Curadoria

**Técnica de criação: meta-prompting.** Escrevi um meta-prompt que descreve a tarefa, os parâmetros, as duas listas de exemplos com a distinção explícita entre elas, a especificação campo a campo e as restrições de formato decorrentes de o prompt vir a ser testado por assert depois. Rodei no Gemini Pro com raciocínio estendido. O meta-prompt pedia também que o modelo listasse os pontos fracos da própria saída e, deliberadamente, que ele **argumentasse contra o método que eu impus** — foi daí que saiu o material mais útil da revisão.

**Decisão de método: híbrido (few-shot de formato + especificação campo a campo + regra anti-contaminação).**

O que decidiu a escolha foi uma coincidência no enunciado: o Exemplo 1 da referência de formato e o alerta cru nº 2 descrevem o mesmo tipo de incidente no Relay, rejeição de ingestão após um deploy. Com few-shot puro, o modelo tem convite aberto para copiar as especificidades do exemplo — o horário `09:14`, o `~12% dos tenants`, o `rollback via Argo CD` — em vez de derivar do alerta recebido. Numa nota de plantão isso significa afirmar uma ação que ninguém tomou e um impacto que ninguém mediu.

Descartei as duas alternativas puras por razões diferentes. **Few-shot puro** é o mais curto de escrever, mas fica exposto à contaminação acima e não dá garantia nenhuma para tipo de alerta que não está nos três exemplos. **Especificação pura (zero-shot estruturado)** é imune à contaminação, mas joga fora os três exemplos que o time já consolidou como referência do que é bom — e o que está nesses exemplos não é só o rótulo, é o tom telegráfico, o comprimento de uma linha por campo e a escolha de não usar maiúscula depois do rótulo. Isso é difícil de transmitir em regra escrita e trivial de transmitir por exemplo.

**O contra-argumento e por que ele não se sustenta em números.** A crítica que pedi ao modelo foi boa e merecia resposta com conta, não com opinião: ele argumentou que o híbrido gasta tokens criando um risco (os exemplos) e depois gastando mais tokens para neutralizá-lo (a regra anti-contaminação), o que prejudicaria o limite de 5s e US$ 0,01 do Checkpoint 08.

Medindo: os três exemplos mais a regra anti-contaminação somam cerca de **1.700 caracteres**, o que em português dá na ordem de **400 a 470 tokens** — não os 225 que eu havia estimado de cabeça. Na faixa de preço do `gpt-4o-mini` isso custa cerca de **US$ 0,00007 por chamada, ou 0,7% do orçamento**. A chamada inteira, prompt completo mais as cinco linhas de saída, foi medida depois no Checkpoint 08 em **US$ 0,00018, ou 1,8% do orçamento — cerca de 55 vezes de folga**. (A contagem de tokens é estimada por caracteres, sem tokenizer; o custo da chamada inteira é medição real do `promptfoo`.) No gate de latência o efeito é menor ainda, porque latência é dominada pelo decode dos tokens de saída, e a saída tem cinco linhas nos dois métodos; os tokens extras são de entrada, processados em prefill. A crítica estava direcionalmente correta e quantitativamente errada por duas ordens de magnitude. Mantive o híbrido.

**O que refinei do v1 para o v1.0.0.** Cinco correções, três vindas da autocrítica do modelo e duas descobertas na execução:

1. **`<N>min` não-determinístico — e o erro era meu.** Eu havia especificado "escolha N entre 10 e 30 conforme a severidade", o que produz 15min hoje e 25min amanhã para o mesmo alerta. O modelo apontou isso corretamente. Ao substituir por faixas, errei de novo: a primeira versão usava "cliente já impactado agora" como critério da faixa de 10min, e isso **contradizia a nota de referência do Forge**, que tem cliente impactado ("dashboards atrasados para todos os tenants") e usa 20min. A execução expôs a contradição: o modelo aplicou minha regra como escrita e deu 10min nas três notas, o que era defensável. Reescrevi o eixo como **reversibilidade do dano** — dado rejeitado na entrada ou capacidade em teto vale 10min porque esperar converte atraso em perda; dado retido no pipeline vale 20min porque só está atrasado; impacto interno vale 15min. Com esse eixo, as três notas de referência passam a ser reproduzidas exatamente, e o alerta do Forge saiu 20min na re-execução.
2. **Ambiguidade de sistema.** O modelo apontou que o alerta nº 1 cita `[Sentinel]`, `sentinel-api` e `Relay`, e que o prompt não dizia qual usar para buscar o handle. Criei a regra da tag entre colchetes: o sistema da nota é o emissor do alerta, e os demais viram impacto ou causa.
3. **Alucinação de ferramenta na AÇÃO IMEDIATA.** O modelo alertou que ele não conhece a topologia da Aegis e ia inventar ações de senso comum. Resolvi com uma regra que fecha dois problemas de uma vez: a ação não pode citar ferramenta, comando ou recurso ausente do alerta e do mapa de escalação, e quando a operação natural exigir uma ferramenta não confirmável, descreve-se a operação. Isso também elimina a principal porta de contaminação, que era exatamente o `Argo CD` do Exemplo 1.
4. **IMPACTO descrevendo estado interno.** Na primeira execução o campo saiu como "processamento de telemetria sobrecarregado" e "atraso propagado para o sistema Sentinel a jusante" — estado do sistema, não o que o cliente perde, enquanto as três referências são todas voltadas ao usuário. Reescrevi a especificação do campo exigindo o que o cliente ou o time interno deixa de conseguir ver ou fazer.
5. **Afirmação de perda sem sustentação.** A nota do Relay dizia "perda e rejeição de dados". O alerta fala em taxa de rejeição, e rejeição pode ser retentada pelo cliente: afirmar perda é ir além do insumo. Incluí a proibição explícita de afirmar perda quando o alerta fala apenas de rejeição, atraso ou fila.

Também removi a tag `pagerduty` que o modelo havia colocado no frontmatter, porque PagerDuty não aparece em nenhum lugar do cenário — metadado inventado não entra em biblioteca versionada. E troquei a menção literal a cercas de bloco de código dentro do texto do prompt por descrição em palavras, senão o conteúdo quebra o próprio arquivo quando virar `prompt.md` no Checkpoint 07.

**Sanitização.** Aqui a decisão é obrigatória, diferente do Checkpoint 01: `stark-industries` e `wakanda-systems` são identificadores de cliente, e o prompt os manda para um modelo externo junto com informação de que aquele cliente está com volume anormal ou com ingestão rejeitada — ou seja, dado de negócio do cliente combinado com evidência de incidente.

O que eu faria antes de mandar para modelo externo: substituir o nome do tenant por um pseudônimo estável na entrada (`tenant-a1`, derivado de hash) e re-hidratar o nome real localmente, depois que a nota volta. O pseudônimo precisa ser estável para que duas notas do mesmo cliente continuem correlacionáveis. O custo dessa escolha é operacional: a nota que chega ao canal de plantão vem com o pseudônimo, e quem lê precisa da tabela de mapeamento — por isso a re-hidratação tem que ser automática, não manual.

O que **não** sanitizaria: nome de sistema interno (Relay, Forge, Sentinel, Cerebro), nome de job (`forge-batch-ingest`) e handles de escalação. São identificadores de arquitetura interna, não dado de cliente, e removê-los inutilizaria a nota — o roteamento da escalação depende exatamente deles.
