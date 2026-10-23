# Checkpoint 03: Causa-raiz da degradação no Cerebro

Terceiro item do playbook. O Cerebro, sistema de indexação e busca da Aegis, começou a devolver buscas lentas e, em alguns casos, resultados incompletos. O plantão do Sam Wilson levantou três artefatos de fontes diferentes antes de escalar: a configuração do cluster versionada no repositório de infra, a série temporal de métricas do dashboard do Sentinel, e um trecho do log nativo do Elasticsearch de um nó.

A causa só aparece cruzando os três: nenhum deles isolado a revela. Este é o prompt que o time reusa toda vez que uma degradação assim aparece, trocando só o pacote de entrada.

Dois pontos marcam a diferença em relação aos checkpoints anteriores. A saída é **aberta**, não estruturada por regex, e por isso este é o prompt que vai para o LLM-as-judge no Checkpoint 09, com rubrica de 4 critérios e corte ≥ 6. E o enunciado exige decisão explícita de sanitização, registrada na curadoria.

---

## Prompt parametrizável

**Destino no registry:** `devops/causa-raiz/prompt.md` · **versão:** 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{config}}` | sim | Arquivo de configuração do serviço: capacidade, limites e agendamento de jobs. Diz o que o sistema **deveria** fazer |
| `{{metricas}}` | sim | Série temporal na janela do incidente. Diz **o que aconteceu** e em que ordem |
| `{{logs}}` | sim | Trecho de log do serviço ou do nó afetado, cobrindo a mesma janela das métricas. Diz **por que** aconteceu |

`````text
Você é um SRE investigador de incidentes. Sua tarefa é analisar três artefatos distintos de um serviço em produção que sofreu degradação, cruzar os dados e diagnosticar a causa-raiz.

Os artefatos representam três dimensões do sistema:
- CONFIG: O que o sistema DEVERIA fazer (parâmetros de capacidade, limites, agendamentos).
- MÉTRICAS: O que de fato ACONTECEU e em que ordem (comportamento no tempo).
- LOGS: O PORQUÊ de ter acontecido (eventos, erros, narrativas internas).

EXECUTE AS SEGUINTES ETAPAS DE RACIOCÍNIO (não as imprima, use-as para gerar a saída):

1. Avalie a Configuração vs. Realidade: Compare o comportamento e os horários observados nos logs e métricas contra o que a config declarava (ex: durações esperadas, horários de agendamento, limites de capacidade). Divergências são o ponto de partida.

1a. Faça a aritmética temporal explicitamente, antes de qualquer conclusão. Sempre que a config declarar horário de início e duração esperada de um processo, calcule o horário esperado de término e compare com o horário observado nos artefatos. Quantifique duas coisas: quanto tempo se passou além do esperado, e qual foi a taxa de progresso dentro da janela observada (quanto avançou entre o primeiro e o último registro disponível). Um processo que avança pouco em muito tempo é sinal diferente de um processo que apenas começou. Não trate um registro de progresso como evento isolado sem fazer essa conta. Se a config não declarar o fuso horário do agendamento e os artefatos usarem fuso explícito, a comparação depende de assumir que coincidem: declare essa premissa em vez de tratá-la como fato, e registre em LACUNAS.

2. Extração de Sinais: Isole eventos e variações anômalas, sempre atrelando-os ao seu valor exato e timestamp.

3. Cronologia: Ordene os sinais no tempo. O que satura ou altera primeiro restringe a direção causal. O que ocorre depois não pode ser causa do que já havia degradado antes.

4. Identificação do Gargalo: Identifique o recurso escasso primário (ex: memória, CPU, thread pool, disco, rede) que saturou.

5. Classificação: Separe CAUSA (o gatilho ou recurso escasso originário), EFEITO (métrica que degrada porque outra coisa saturou) e CONTEXTO (ruído de fundo ou estado normal). Métrica que degrada porque outra coisa saturou é efeito, mesmo que seja a métrica que mais chama atenção.

6. Teste de Hipóteses: Formule hipóteses concorrentes e invalide as que entrarem em contradição temporal ou factual com qualquer um dos três artefatos. Hipótese que nenhum artefato sustenta nem contradiz é indeterminada, não confirmada.

7. Causa-raiz: Escolha a hipótese sobrevivente que explica a maior parte dos sinais.

8. Plano de Ação: Defina contenção (para estancar o sangramento imediato) e correção de fundo (para evitar reincidência), avaliando o risco de produção de cada uma. A correção de fundo precisa estar ancorada na divergência encontrada na etapa 1: nomeie qual parâmetro da config seria alterado, ou qual processo seria reagendado, redimensionado ou isolado. Se a correção correta depender de informação que não está nos artefatos, diga isso e registre como LACUNA em vez de propor um ajuste genérico de recurso.

9. Lacunas: Identifique o limite da certeza. O que o recorte atual de artefatos não permite provar?

REGRAS ESTRITAS DE SAÍDA:
- Use EXATAMENTE as seis seções abaixo, nesta ordem, com títulos literais em maiúsculas.
- Toda afirmação técnica precisa de âncora: cite o artefato de origem, o valor e o horário. Afirmação sem âncora é proibida.
- Não invente parâmetros, métricas ou logs. O que não está no texto é LACUNA.
- Onde a evidência não sustentar uma afirmação, escreva que é hipótese e diga o que a confirmaria.
- Qualificar um comportamento como "natural", "normal", "esperado", "de rotina" ou "sazonal" exige um baseline presente nos artefatos que sustente a comparação. Sem baseline, essa qualificação é hipótese e precisa estar marcada como tal.
- A classificação de risco em produção precisa nomear quem é afetado pela ação (qual consumidor, qual fluxo, qual dado fica indisponível ou defasado). Se os artefatos não informam as dependências do serviço, escreva que a classificação é provisória por ausência do mapa de dependências e registre isso em LACUNAS.
- Responda em no máximo 60 linhas no total. Seja conciso e telegráfico.
- A tabela de SINAIS OBSERVADOS traz no máximo 8 linhas, priorizando os sinais que sustentam a cadeia causal.
- A seção LACUNAS nunca é omitida nem encurtada para caber no limite de linhas. Se faltar espaço, reduza a tabela de sinais. Ela traz no mínimo 3 itens e obrigatoriamente um deles é a limitação de escopo dos próprios artefatos: quantos nós ou instâncias estão visíveis, que janela de tempo foi coberta, e quais métricas relevantes não existem no pacote recebido.
- Não reproduza na resposta os marcadores entre colchetes do modelo abaixo: eles indicam onde entra o seu conteúdo.
- Sem saudações, preâmbulos ou fechamentos. Comece no primeiro título.

CAUSA RAIZ
[2 a 4 períodos explicando a causa]
Confiança: [ALTA | MEDIA | BAIXA] - Motivo: [explicação da confiança baseada na consistência ou falta de dados]

CADEIA CAUSAL
[Evento A (horário)] -> [Saturação B (horário)] -> [Sintoma C percebido (horário)]

SINAIS OBSERVADOS
| Origem | Sinal (valor e horário) | Papel (CAUSA, EFEITO, CONTEXTO) |
|---|---|---|
| [Métrica/Log/Config] | [descrição breve] | [papel e justificativa curta] |

HIPOTESES CONCORRENTES
- [Hipótese 1]: Evidência Pró: [X]. Evidência Contra: [Y]. Veredito: [Sustentada | Descartada | Indeterminada].
- [Hipótese 2]: Evidência Pró: [X]. Evidência Contra: [Y]. Veredito: [Sustentada | Descartada | Indeterminada].

ACAO
- Contenção imediata: [ação]. Risco em produção: [Baixo/Médio/Alto - por quê].
- Correção de fundo: [ação, ancorada em parâmetro da config]. Risco em produção: [Baixo/Médio/Alto - por quê].

LACUNAS
- [o que não se pode concluir]: Necessário [qual consulta ou dado exato resolveria isso].

ARTEFATOS:

[CONFIG]
{{config}}

[METRICAS]
{{metricas}}

[LOGS]
{{logs}}
`````

**Frontmatter:**

```yaml
nome: causa-raiz
descricao: Conduz uma investigação cruzada de configuração, métricas e logs para diagnosticar a causa-raiz de degradações de serviço, separando causa de consequência e declarando limitações dos dados.
versao: 1.0.0
tags: [rca, incidentes, sre, troubleshooting, correlacao]
inputs:
  - nome: config
    descricao: Arquivo de configuração do serviço cobrindo capacidade, limites e agendamento de jobs.
  - nome: metricas
    descricao: Série temporal em texto com as métricas principais do serviço na janela do incidente.
  - nome: logs
    descricao: Trecho de log do serviço ou do nó afetado, cobrindo a mesma janela de tempo das métricas.
```

---

## Execução

**Modelo:** Gemini Pro, com raciocínio estendido.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Este é o checkpoint em que raciocínio estendido é a escolha tecnicamente correta, e não apenas a conveniente. Nos itens de saída estruturada (CP01 e CP02) ele é excesso: transformação de texto com formato rígido não depende de cadeia longa, e no Checkpoint 08 o gate de 5 segundos vai até penalizá-lo. Aqui a tarefa é correlacionar três fontes heterogêneas, estabelecer direção de causalidade a partir de ordem temporal e fazer aritmética de horário; e não existe gate de latência, porque o Checkpoint 09 avalia qualidade de julgamento, não velocidade.

Registro duas execuções do mesmo pacote de artefatos, com o prompt em dois estágios de refino. O par é deliberado: ele serve de referência calibrada para o juiz do Checkpoint 09, porque um juiz que atribuir a mesma nota aos dois não está calibrado, está sendo generoso.

> As tabelas de `SINAIS OBSERVADOS` perderam a estrutura de colunas na transcrição da interface para cá. Reconstruí a formatação; nenhum valor, papel ou justificativa foi alterado.

### Execução 1: prompt antes do refino de honestidade epistêmica

```
CAUSA RAIZ
O job de reindexação agendado na config para 02:00 com duração de 90min falhou em concluir, estendendo-se por mais de 4.5h além do previsto (log 08:02 atesta progresso de apenas 38%). Ao colidir com o aumento natural da taxa de indexação a partir das 09:00 (métrica: 9800 docs/s), a retenção de memória do job esgotou a JVM. Isso disparou o Circuit Breaker (log 09:58 a 96%), expulsou o query cache (0.29) e gerou timeout na busca.
Confiança: ALTA - Motivo: Consistência cronológica exata entre o atraso do job apontado nos logs, o esgotamento progressivo do JVM Heap nas métricas e o posterior disparo do disjuntor de memória.

CADEIA CAUSAL
Job de reindex estagnado (log 08:02) -> Saturação do JVM Heap e Circuit Breaker (log 09:58) -> Degradação de busca (métrica 10:00)
```

SINAIS OBSERVADOS

| Origem | Sinal (valor e horário) | Papel (CAUSA, EFEITO, CONTEXTO) |
|---|---|---|
| Config | reindex_job schedule 02:00, avg 90min | CONTEXTO: Baseline do comportamento esperado (término 03:30). |
| Log | 08:02: reindex task em 38% | CAUSA: Job atrasado em >4.5h retendo heap. |
| Métrica | 09:00: indexed_docs_per_s sobe a 9800 | CONTEXTO: Tráfego natural diurno aumentando. |
| Log | 09:31: circuit breaker usage 86% | EFEITO: Esgotamento do recurso primário (JVM Heap). |
| Log | 09:58: circuit breaker tripped (96%) | EFEITO: Proteção ativa rejeitando escritas (bulk). |
| Log | 09:58: cache eviction, hit_ratio 0.29 | EFEITO: Esvaziamento do cache para tentar salvar memória. |
| Métrica | 10:00: search_p99_ms em 6700ms | EFEITO: Sintoma final gerado pela falta de cache e GC thrashing. |

```
HIPOTESES CONCORRENTES
- Pico de acessos e leitura saturou a capacidade de busca: Evidência Pró: search_p99_ms sobe a 6700ms às 10:00. Evidência Contra: O gargalo rastreado afeta threads de escrita (write thread pool full às 09:58) e os logs mostram despejo do query cache (09:58), indicando que a leitura lenta é efeito da falta de memória, não a causa. Veredito: Descartada.
- Colisão do job de reindex com horário de pico estourou o Heap: Evidência Pró: Config prevê término 03:30, mas log 09:58 mostra job ativo (41%) rodando simultaneamente à carga diária de indexação, acionando o Circuit Breaker (96%). Veredito: Sustentada.

ACAO
- Contenção imediata: Cancelar ativamente a reindex task (88123) para aliviar o JVM Heap e estabilizar buscas. Risco em produção: Baixo - Adia a reindexação, mas restaura a saúde do cluster para clientes finais.
- Correção de fundo: Alterar a config do reindex_job implementando um timeout ou cancelamento automático caso ultrapasse a janela esperada de 90min. Risco em produção: Baixo - Altera apenas configuração de cronograma/comportamento preventivo.

LACUNAS
- Por que o reindex job avançou apenas 38% entre 02:00 e 08:00 e quase nada depois: Necessário extrair os logs do nó cerebro-node-3 e as métricas de latência de disco estritamente na janela das 02:00 às 08:00 para diagnosticar a estagnação silenciosa.
```

### Execução 2: prompt final (v1.0.0)

```
CAUSA RAIZ
O job de reindexação agendado na config para 02:00 estagnou, operando mais de 4,5 horas além de sua duração média esperada (log de 08:02 indica apenas 38% concluído). Partindo da premissa de que a config e as métricas utilizam o mesmo fuso horário, a sobreposição desse job retendo memória com uma alta taxa de indexação a partir das 09:00 esgotou o JVM Heap. Isso acionou o Circuit Breaker, expulsou o cache de busca e gerou timeouts e falhas nos shards.
Confiança: MEDIA - Motivo: Consistência cronológica interna forte entre métricas e logs, mas o nível de confiança cai porque a correlação depende de assumir fusos horários idênticos e o impacto real é indeterminado sem mapa de dependências.

CADEIA CAUSAL
Job de reindex estagnado (log 08:02) -> Saturação do JVM Heap e Circuit Breaker (log 09:58) -> Degradação de busca percebida (métrica 10:00)
```

SINAIS OBSERVADOS

| Origem | Sinal (valor e horário) | Papel (CAUSA, EFEITO, CONTEXTO) |
|---|---|---|
| Config | reindex_job schedule 02:00, avg 90min | CONTEXTO: Baseline de comportamento esperado (término projetado 03:30). |
| Log | 08:02: reindex task em 38% | CAUSA: Job severamente atrasado retendo recursos do heap. |
| Métrica | 09:00: indexed_docs_per_s vai a 9800 | HIPÓTESE: Aumento de carga. Sem baseline nos artefatos, assume-se tráfego sazonal concorrente. |
| Log | 09:31: circuit breaker usage 86% | EFEITO: Esgotamento progressivo do JVM Heap. |
| Log | 09:58: circuit breaker tripped (96%) | EFEITO: Proteção limitando escritas e operações intensivas. |
| Log | 09:58: cache eviction, hit_ratio 0.29 | EFEITO: Esvaziamento do cache de query como defesa da memória. |
| Métrica | 10:00: search_p99_ms em 6700ms | EFEITO: Sintoma final percebido devido ao cache vazio e saturação. |

```
HIPOTESES CONCORRENTES
- Pico de acessos de busca causou OOM: Evidência Pró: search_p99_ms sobe para 6700ms às 10:00. Evidência Contra: O log 09:58 revela "write thread pool queue full", indicando que o gargalo primário está na escrita/reindexação; hit_ratio caiu por eviction forçado. Veredito: Descartada.
- Colisão de job estagnado com carga de indexação externa esgotou o Heap: Evidência Pró: O log aponta job ativo (41%) às 09:58 simultâneo a 12.400 indexed_docs_per_s (métrica 10:00), culminando no Circuit Breaker (log 09:58). Veredito: Sustentada.

ACAO
- Contenção imediata: Cancelar a reindex task (88123) em andamento para liberar a pressão imediata no JVM Heap. Risco em produção: Provisório (mapa de dependências ausente nos artefatos) - O cancelamento pode deixar consultas defasadas para clientes/consumidores finais não mapeados.
- Correção de fundo: Alterar a config do reindex_job, adicionando um parâmetro de timeout absoluto (ex: abortar se duração for > 120min). Risco em produção: Provisório (mapa de dependências ausente nos artefatos) - Falhas sistemáticas por timeout podem estagnar a versão dos índices consumida pela aplicação.

LACUNAS
- Fuso horário não declarado na config: Necessário confirmar se o schedule "0 2 * * *" opera em UTC (igual às métricas) ou horário local.
- Mapa de dependências do serviço: Necessário diagrama da arquitetura ou service catalog para identificar quais serviços ou tenants quebram caso a reindexação seja abortada na contenção.
- Limitação de escopo (apenas cerebro-node-3 e janela restrita): Necessário conferir logs dos demais 11 shards/nós para confirmar se o job enfileirou/travou em todo o cluster e checar métricas históricas de dias anteriores para confirmar se o pico das 09:00 é um tráfego de rotina ou um ataque/anomalia.
```

### Pontuação pela rubrica do Checkpoint 09

Pontuei manualmente as duas execuções com os quatro critérios da rubrica, escala 0 a 2, corte em 6 sem critério zerado. Esta é a referência humana que o juiz automatizado vai ter que reproduzir dentro de 1 ponto por critério.

| Critério | Exec 1 | Exec 2 | O que separa as duas |
|---|:---:|:---:|---|
| Causa-raiz correta | 2 | 2 | Ambas chegam à cadeia real: reindex estagnado → heap esgotado → circuit breaker → cache expulso → timeout de busca. A aritmética temporal apareceu nas duas ("4,5h além do previsto") |
| Correlação × causa | 2 | 2 | Ambas marcam `cache_hit` 0.29 como EFEITO, que é o item destacado na rubrica, e descartam a hipótese de pico de leitura pelo argumento certo: o gargalo está na fila de escrita |
| Ação proporcional | ~~2~~ **1** | 2 | Ambas cancelam o job em vez de aumentar memória. **Nota corrigida no Checkpoint 09**: ver nota abaixo. A exec 2 declara o risco das duas ações como provisório por ausência do mapa de dependências e nomeia o efeito colateral da própria correção de fundo; a exec 1 declara "Baixo, Altera apenas configuração de cronograma", sem nomear afetado e sem declarar provisoriedade |
| Honestidade epistêmica | **1** | **2** | Exec 1 afirmou "aumento natural da taxa de indexação" e "tráfego natural diurno" como fato, sem baseline nos artefatos, e trouxe uma única lacuna, sem registrar que só existe log de um nó. Exec 2 baixou a confiança de ALTA para MEDIA com motivo, marcou o salto de indexação como hipótese por ausência de baseline, e trouxe três lacunas incluindo a limitação de escopo |
| **Total** | ~~7/8~~ **6/8** | **8/8** | Ambas seguem aprovadas pelo corte; a diferença está nos critérios 3 e 4 |

> **Correção da nota de Ação proporcional da exec 1, feita no Checkpoint 09.**
>
> Eu havia dado 2 e registrado a ressalva sobre o risco otimista como observação que "não
> alterou a nota". Ao construir o juiz automatizado, ele apontou o mesmo ponto e atribuiu
> 1, e, relendo o nível 2 do critério, que exige que o risco de **cada** ação identifique
> quem é afetado ou se declare provisório, o juiz está certo e eu fui leniente. A exec 1
> não faz nenhuma das duas coisas na correção de fundo.
>
> A correção é do avaliador humano, não do juiz. Ela é registrada aqui em vez de aplicada
> em silêncio porque a nota original é o que estava valendo quando o Checkpoint 03 foi
> fechado, e a mudança de leitura é parte do resultado do Checkpoint 09: a referência
> humana também é hipótese até alguém conferir. O detalhamento está em
> [`devops/causa-raiz/rubrica.md`](./prompt-registry/devops/causa-raiz/rubrica.md) e a
> fonte única das notas em
> [`referencia-humana.json`](./prompt-registry/devops/causa-raiz/calibracao/referencia-humana.json).

**Observações que não alteraram a nota, mas ficam registradas:**

Na exec 1, classificar como "Baixo" o risco de cancelar uma reindexação de produção é otimista: perde-se o progresso de 41% e o índice fica em estado misto, o que o texto não menciona. A exec 2 corrigiu isso ao rotular o risco como provisório por ausência do mapa de dependências.

Na exec 2, a lacuna de escopo fala em "conferir logs dos demais 11 shards/nós", o que mistura shards com nós: a config declara 12 shards, e o log revela um nó chamado `cerebro-node-3`, o que implica pelo menos três nós, mas o número total não está em nenhum artefato. É imprecisão de vocabulário dentro da seção que trata justamente dos limites do conhecimento, não fabricação de evidência, por isso não descontei ponto, mas é o tipo de detalhe que um juiz rigoroso pode pegar.

A leitura de que o salto de `indexed_docs_per_s` é tráfego vivo e não a própria reindexação está correta e dá para confirmar pelos números: o job avançou de 4.0M para 4.1M docs entre 09:20 e 09:58, ou seja, cerca de 44 docs/s, longe dos 8 mil de aumento observados na métrica.

---

## Curadoria

**Técnica de criação: meta-prompting, com um cuidado específico deste checkpoint.** O meta-prompt trouxe os três artefatos reais, o método de raciocínio em nove etapas e as seções de saída. O cuidado foi com a rubrica do Checkpoint 09: o texto dela, como está no enunciado, **contém a resposta**: diz explicitamente que a causa é a reindexação travada saturando o heap. Se eu colasse a rubrica literal no meta-prompt, o modelo poderia escrever a conclusão dentro do prompt, e o item pararia de analisar para passar a recitar, ficando inútil para qualquer outro pacote de artefatos. Passei os quatro critérios pelo que eles medem, sem o parêntese que revela a causa, e incluí uma instrução explícita proibindo embutir a conclusão.

Pedi também que o modelo auditasse o próprio risco de overfitting, e essa foi a parte mais útil da resposta: ele nomeou três trechos onde quase embutiu a resposta e mostrou a generalização que usou. "Verifique se algum job agendado não terminou no horário" virou "compare os horários observados contra o que a config declarava"; "verifique saturação de memória ou JVM" virou "identifique o recurso escasso primário (memória, CPU, thread pool, disco, rede)"; e a lentidão de busca como efeito virou "métrica que degrada porque outra coisa saturou é efeito, mesmo que seja a métrica que mais chama atenção".

**Framework: R-I-S-E.** O componente que carrega o peso é o `Steps`, e é o que diferencia este prompt de um pedido genérico de análise. O modo de falha que este item existe para evitar é listar sintomas em vez de chegar à causa, e isso não se resolve pedindo "analise com profundidade": resolve-se impondo a ordem, conferir config contra realidade, fazer a aritmética temporal, ordenar no tempo, nomear o recurso escasso, classificar cada sinal, testar hipóteses concorrentes, e só então concluir. O `Expectation` fixou as seis seções, e aqui ele tem uma função extra: **cada seção existe para dar ao juiz do Checkpoint 09 um lugar onde procurar um critério da rubrica.** Sem `CADEIA CAUSAL` e a coluna de papel, o critério de correlação × causa não tem onde ser avaliado; sem `LACUNAS`, o de honestidade epistêmica é zerado por ausência de seção, e não por qualidade do raciocínio.

Descartei C-A-R-E, que foi a escolha certa no módulo Terraform, porque o componente `Example` seria o mais fraco aqui: não existe análise de causa-raiz anterior da Aegis para servir de referência, e um exemplo de postmortem encerrado ensinaria o modelo a escrever com a confiança retrospectiva de quem já sabe a resposta, exatamente o oposto do que o critério de honestidade epistêmica exige.

**O que refinei, em três rodadas.**

A primeira rodada de refino veio da autocrítica do modelo, antes de qualquer execução. Três pontos, todos aceitos:

1. **Cegueira temporal.** Ele apontou que LLM erra conta reversa de horário, e neste caso a conta *é* a causa-raiz: 02:00 mais 90 minutos dá término esperado às 03:30, e o log mostra 38% às 08:02. Sem esse cálculo o diagnóstico não fecha. Virou a etapa 1a, com exigência de quantificar o atraso e a taxa de progresso na janela observada. Foi a correção de maior impacto: a conta apareceu nas duas execuções.
2. **Teto de 45 linhas brigando com a tabela.** Ele calculou que uma tabela Markdown com cabeçalho e separador consome muitas linhas e espremeria as seções analíticas. O modo de falha concreto é o modelo cortar a última seção: LACUNAS, para caber, o que zeraria o critério 4 por acidente de formatação. Subi para 60 linhas, limitei a tabela a 8 sinais e escrevi que LACUNAS nunca é sacrificada: se faltar espaço, cortam-se linhas da tabela.
3. **Correção de fundo rasa.** "Aumentar memória" é o reflexo padrão de quem não tem contexto. Amarrei a correção de fundo à divergência encontrada na etapa 1, exigindo que ela nomeie qual parâmetro da config muda, ou declare que depende de informação ausente e vire lacuna. Nas duas execuções o resultado foi timeout no `reindex_job`, ancorado na config, e não pedido de mais heap.

A segunda rodada veio da **execução 1 pontuada pela rubrica**, que à época entregou 7 de 8 com a perda concentrada em honestidade epistêmica (nota depois corrigida para 6 de 8 no Checkpoint 09, ver a tabela acima). Duas regras novas:

4. **Proibição de adjetivo de normalidade sem baseline.** A exec 1 afirmou "tráfego natural diurno" como fato. Não há nos artefatos nenhum dado de dia anterior que sustente o "natural": é inferência plausível apresentada como evidência. A regra passou a exigir baseline presente nos artefatos para qualificar algo como natural, normal, esperado, de rotina ou sazonal; sem baseline, é hipótese e tem que estar marcada. Na exec 2 aquela linha da tabela veio marcada como hipótese.
5. **Piso de três lacunas, com uma delas obrigatoriamente sobre escopo.** A exec 1 trouxe uma única lacuna e não registrou que existe log de apenas um nó. Em vez de escrever uma regra específica sobre nós, que seria overfitting ao caso do Cerebro, a formulação ficou genérica: quantas instâncias estão visíveis, que janela foi coberta, quais métricas não existem no pacote. Isso funciona para pod de Kubernetes, instância de banco ou função serverless.

A terceira rodada veio da segunda autocrítica, e trouxe dois pontos que eu considerei válidos:

6. **Classificação de risco sem mapa de dependências.** O modelo reconheceu que chamou de "Baixo" o risco de cancelar a reindexação porque não sabe quem consome aquele índice: o mesmo ponto que eu havia registrado na pontuação. A regra passou a exigir que o risco nomeie o afetado ou declare que a classificação é provisória por ausência do mapa de dependências. Na exec 2 as duas ações vieram com risco provisório e com o efeito colateral nomeado.
7. **Fuso horário do agendamento.** A config traz `schedule: "0 2 * * *"` sem declarar fuso, e métricas e logs estão em UTC. Toda a aritmética temporal depende de assumir que coincidem, e essa premissa não estava escrita em lugar nenhum. A exec 2 declarou a premissa no corpo da causa-raiz, baixou a confiança por causa dela e registrou a lacuna.

**Uma tensão que eu criei e que o modelo resolveu por conta própria.** A tabela de sinais declara um vocabulário fechado de três valores para a coluna de papel: CAUSA, EFEITO, CONTEXTO, e outra regra exige marcar como hipótese o que não tem sustentação. Quando o papel de um sinal depende de uma premissa não sustentada, as duas regras colidem. Na exec 2 o modelo emitiu `HIPÓTESE` naquela coluna, que está fora do vocabulário declarado. A saída ficou mais honesta e o formato ficou menos previsível: um assert futuro sobre aquela coluna falharia. A correção fica como **v1.0.1**, permitindo sufixo em vez de valor novo, `CONTEXTO (hipótese)`, o que preserva o vocabulário fechado e carrega a incerteza. Não apliquei agora porque mudaria a saída e invalidaria as duas execuções que servem de referência calibrada para o Checkpoint 09.

**Limitação conhecida, aceita.** O piso de três lacunas pode induzir enchimento quando o pacote de artefatos for realmente completo: o modelo inventaria lacuna trivial para cumprir a cota. No caso do Cerebro o risco não se materializou, porque o recorte é genuinamente parcial: um nó, duas horas, quatro métricas. Fica registrado para reavaliação quando o playbook receber um pacote mais rico.

**Sanitização.** Este é o prompt que manda o maior volume de informação interna para um modelo externo, e por isso a decisão muda de patamar em relação aos dois primeiros itens.

O artefato mais sensível não é o log, é a **config**. O log mostra um estado transitório de duas horas; a `cerebro.yaml` revela o envelope de capacidade permanente do sistema de busca: 12 shards, 1 réplica, heap de 8g, cache de 512mb, janela de reindexação às 02:00. Combinado com a evidência de que o circuit breaker dispara a 96% de 8gb e que a reindexação diária ocupa o sistema em horário conhecido, isso é a receita de como induzir a degradação. E há um agravante de origem: esse arquivo é versionado no repositório de infra, então colá-lo num chat externo é exfiltrar conteúdo de repositório, não apenas compartilhar um sintoma.

A política que eu aplicaria é curta: **números ficam, identificadores saem.** A análise depende inteiramente dos valores (sem `02:00`, `90min` e `8g` não existe aritmética temporal nem comparação com o heap) mas não depende de nome nenhum. Concretamente: `cerebro-node-3` vira `node-3` sem o nome do serviço, o nome do índice `logs-2026.05` vira `indice-mensal`, e o identificador da task pode ficar porque é efêmero. Nome de serviço interno (`cerebro`) eu também substituiria por um rótulo genérico no cabeçalho da config, porque é o que amarra o pacote todo à empresa.

O que **não** sanitizaria: os valores de capacidade, a série temporal completa e os nomes de classe do log (`JvmGcMonitorService`, `HierarchyCircuitBreakerService`). Os nomes de classe revelam a tecnologia, e revelar que se usa Elasticsearch é informação de baixo valor para um atacante e de alto valor para o diagnóstico, é o que permite ao modelo interpretar corretamente o que é circuit breaker de heap e o que é throttle de indexing buffer.

Diferente do Checkpoint 02, aqui não há nome de tenant nos artefatos, então a pseudonimização de cliente não se aplica.
