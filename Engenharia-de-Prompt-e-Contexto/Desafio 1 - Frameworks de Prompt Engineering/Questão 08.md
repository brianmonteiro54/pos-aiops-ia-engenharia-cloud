# Questão 08 — Postmortem técnico de incidente em produção

**Framework escolhido:** R-I-S-E (Role, Input, Steps, Expectation) — escolha livre entre os 5 do capítulo. A comparação com as alternativas está na Justificativa, que é o ponto central de avaliação desta questão.

---

## Prompt

````text
[ROLE]
Você é um SRE principal da Hill Valley Tech, especialista em análise de incidentes em produção sob pressão de tempo. Você é conhecido por separar com rigor o que a evidência sustenta do que é hipótese, e por recomendar uma decisão única e acionável mesmo com dados incompletos.

[INPUT]
Um incidente está em andamento agora, durante o pico de tráfego. Doc Brown (CTO) está em uma call e precisa, em 20 minutos, de um postmortem técnico para decidir entre duas opções mutuamente exclusivas:

- Opção A: rollback do deploy v2.48.0, que subiu ontem.
- Opção B: scaling emergencial, aumentando os limits do RDS e o pool de conexões.

Estes são todos os insumos disponíveis.

1) Changelog do deploy v2.47.0 -> v2.48.0, aplicado em 2026-08-16 às 18:42 UTC:

- Novo endpoint POST /v2/transactions/batch.
- Cliente do Ledger refatorado: pool de conexões migrado para nova biblioteca interna.
- Bump do psycopg 3.1.18 -> 3.2.0.
- Timeout do Ledger reduzido de 5s para 2s.

2) Série temporal do Beacon, últimos 30 minutos (2026-08-17):

```
horario_utc  p99_latencia_ms  requisicoes_por_s  taxa_erro_pct
20:05        420              1240               0,2
20:10        780              1410               0,4
20:15        1650             1520               1,1
20:20        3100             1580               3,4
20:25        5400             1610               6,8
20:30        7200             1490               9,5
20:35        8100             1320               11,7
```

3) Trecho de log do pod chronos-api:

```
2026-08-17T20:28:14.882Z WARN  [ledger-client]     connection pool exhausted (max=20, active=20, waiting=147)
2026-08-17T20:28:15.011Z ERROR [ledger-client]     query timeout after 2000ms
2026-08-17T20:28:15.014Z ERROR [chronos-api]       POST /v2/transactions/batch failed: LedgerTimeoutError
2026-08-17T20:28:17.402Z WARN  [ledger-client]     circuit breaker OPEN (failure rate 62% over last 30s)
2026-08-17T20:28:18.119Z ERROR [reactor-publisher] failed to publish event batch to SQS: upstream dependency unavailable
2026-08-17T20:28:19.550Z WARN  [ledger-client]     connection pool exhausted (max=20, active=20, waiting=163)
```

4) Estado do Reactor: fila com 50.127 mensagens acumuladas, crescendo cerca de 800 por minuto, consumer lag de 18 minutos e subindo.

5) Estado do cluster: Chronos em 12/12 pods, HPA no teto, CPU 62%, memória 71%, conexões ao Ledger em 240/250, que é o limite do RDS.

[STEPS]
Conduza a análise exatamente nesta sequência e mostre o raciocínio de cada etapa:

1. Monte a linha do tempo correlacionando o deploy de ontem 18:42 UTC com o início da degradação observada na série temporal, e diga o que essa defasagem sugere e o que ela não permite concluir.
2. Liste os sintomas objetivos extraídos dos insumos, separando causa de consequência: identifique qual sinal é gargalo primário e quais são efeitos em cascata (Reactor, circuit breaker, saturação de HPA).
3. Enumere as hipóteses de causa raiz, uma por item do changelog e demais candidatas plausíveis, e para cada uma indique a evidência que a sustenta, a evidência que a contradiz e o nível de confiança.
4. Escolha a causa raiz mais provável e explique por que ela explica melhor o conjunto de sinais do que as demais.
5. Avalie a Opção A e a Opção B lado a lado, cada uma com: efeito esperado sobre o gargalo primário, tempo até surtir efeito, risco de piorar a situação, restrições técnicas visíveis nos insumos (atenção ao limite de 250 conexões do RDS e ao HPA já no teto) e efeito sobre o backlog de 50.127 mensagens do Reactor.
6. Recomende uma decisão única, A ou B, ou a combinação e a ordem em que devem ser executadas, com os comandos ou ações concretas na ordem correta.
7. Defina como validar em até 10 minutos se a decisão funcionou, com métricas e valores-alvo, e defina o critério de reversão caso não funcione.
8. Trate o backlog do Reactor como item separado: como drenar sem provocar um segundo incidente.
9. Marque explicitamente toda lacuna de informação e, para cada lacuna, o comando ou consulta que a resolveria. Não preencha lacuna com suposição apresentada como fato.

[EXPECTATION]
O resultado esperado é um postmortem técnico que o Doc Brown consiga ler e usar para decidir em menos de 20 minutos, ainda com o incidente em andamento.

Formato obrigatório, em Markdown, nesta ordem:

1. DECISÃO — no máximo 3 linhas, no topo do documento: o que fazer agora, primeira ação e por quê.
2. Linha do tempo do incidente.
3. Causa raiz provável, com nível de confiança e as evidências que a sustentam.
4. Tabela comparando Opção A (rollback) e Opção B (scaling emergencial), com efeito, tempo, risco e limitação de cada uma.
5. Plano de ação numerado, com comandos e ordem de execução.
6. Critérios de validação e de reversão, com métricas e valores-alvo.
7. Plano para o backlog do Reactor.
8. Lacunas de informação e como fechá-las.
9. Follow-ups pós-incidente, separando o que é correção definitiva do que é mitigação temporária.

Restrições: baseie-se somente nos insumos fornecidos. Toda afirmação técnica deve apontar o insumo que a sustenta. Onde a evidência for insuficiente para afirmar, escreva "hipótese" e diga o que confirmaria. Não entregue duas recomendações em paralelo: escolha uma e assuma a escolha.
````

---

## Modelo

**Claude Opus 5 Max (Anthropic)**

Escolhido porque a tarefa é correlacionar cinco fontes heterogêneas (changelog, série temporal, log, estado de fila, estado de cluster) e sustentar uma recomendação única sob restrição de tempo, separando o que a evidência prova do que é hipótese. É raciocínio sobre evidência conflitante, não geração de artefato: o custo de errar a causa raiz aqui é decidir rollback quando o problema é capacidade, ou mexer no banco quando o problema é a aplicação.

---

## Output

### 1. DECISÃO

**Executar a Opção A (rollback de v2.48.0) agora. Não executar a Opção B neste momento.** Primeira ação: iniciar o rollback e, simultaneamente, congelar o consumer do Reactor para não competir por conexões. Motivo: o gargalo primário é capacidade de conexão ao Ledger (240/250, e 12 pods × pool 20 = 240 exatamente), e a Opção B tenta ampliar um teto que não se amplia com segurança em 20 minutos — elevar `max_connections` no PostgreSQL exige reinício da instância, ou seja, trocaria degradação por indisponibilidade total do Ledger em pico.

---

### 2. Linha do tempo do incidente

| Momento | Evento | Insumo |
|---|---|---|
| 2026-08-16 18:42 UTC | Deploy v2.47.0 → v2.48.0 aplicado | Changelog (insumo 1) |
| — | **Intervalo de ~25h30 sem degradação registrada** | Dedução da diferença entre insumo 1 e insumo 2 |
| 2026-08-17 20:05 | Estado ainda saudável: p99 420ms, 1240 rps, erro 0,2% | Série temporal (insumo 2) |
| 20:10 | Primeiro desvio claro: p99 780ms (1,9x), erro 0,4% | Insumo 2 |
| 20:15 | p99 1650ms, erro 1,1% — degradação já perceptível ao cliente | Insumo 2 |
| 20:20 | **Pico de goodput: 1526 req/s bem-sucedidas.** p99 3100ms, erro 3,4% | Cálculo sobre insumo 2 |
| 20:25 | Pico de tráfego total: 1610 rps. p99 5400ms, erro 6,8% | Insumo 2 |
| 20:28:14 | Log: pool esgotado, `max=20, active=20, waiting=147` | Log (insumo 3) |
| 20:28:15 | Log: `query timeout after 2000ms` e falha do `POST /v2/transactions/batch` | Insumo 3 |
| 20:28:17 | Log: circuit breaker do ledger-client **OPEN**, taxa de falha 62% em 30s | Insumo 3 |
| 20:28:18 | Log: `reactor-publisher` falha ao publicar no SQS | Insumo 3 |
| 20:28:19 | Log: `waiting` sobe de 147 para 163 em ~5 segundos | Insumo 3 |
| 20:30 | Tráfego total começa a **cair** (1490 rps) enquanto p99 e erro continuam subindo | Insumo 2 |
| 20:35 (agora) | p99 8100ms (19,3x), erro 11,7% (58,5x), tráfego 1320 rps, goodput 1166 req/s (−23,6% do pico) | Insumo 2 + cálculo |
| Estado atual | 12/12 pods (HPA no teto), CPU 62%, memória 71%, 240/250 conexões ao Ledger | Insumo 5 |
| Estado atual | Reactor: 50.127 mensagens, +800/min, lag 18min e subindo | Insumo 4 |

**O que a defasagem de ~25h30 sugere:** o deploy, por si só, não quebrou nada de forma imediata. Se v2.48.0 tivesse um erro determinístico, a degradação teria aparecido em 16/08, não 25 horas depois. O padrão é compatível com **regressão latente de capacidade**: uma mudança que só se manifesta quando a carga atinge o pico, ou cuja demanda cresce com a adoção do recurso novo.

**O que a defasagem NÃO permite concluir:**

- **Não permite absolver o deploy.** Regressão de capacidade é invisível fora do pico, por definição.
- **Não permite condenar o deploy.** A degradação coincide com o pico de tráfego, e a correlação temporal é com o pico, não com o deploy. Um teto de capacidade atingido por crescimento orgânico produziria exatamente a mesma curva.
- Para desempatar é preciso saber se v2.47.0 já sustentou ~1600 rps sem degradar. Essa é a **Lacuna 1** da seção 8, e é a única informação que muda o nível de confiança da causa raiz de média para alta.

---

### 3. Causa raiz provável

#### 3.1 Sintomas objetivos, separando causa de consequência

**Gargalo primário (a causa):** esgotamento da capacidade de conexão ao Ledger.

Duas evidências independentes convergem no mesmo ponto:

- **Por pod:** `max=20, active=20, waiting=147` e, cinco segundos depois, `waiting=163` (insumo 3). O pool está 100% ocupado com uma fila de espera 7 a 8 vezes maior que o próprio pool, e crescendo ~16 esperas a cada 5 segundos.
- **Agregado:** 240 de 250 conexões em uso (insumo 5). E **12 pods × max=20 por pod = 240**. A coincidência exata entre o teto do RDS e o produto pods × pool não é acidental: o cluster inteiro está encostado no limite do banco, com folga de 10 conexões.

**Consequências em cascata (não são a causa, e tratá-las não resolve):**

| Sintoma | Por que é consequência |
|---|---|
| `query timeout after 2000ms` | Requisição espera conexão, não sobra tempo dentro do orçamento de 2s (insumo 1 confirma que 2s é o valor novo) |
| `POST /v2/transactions/batch failed: LedgerTimeoutError` | Endpoint falha porque não obtém conexão em tempo, não por defeito próprio observável nos insumos |
| Circuit breaker OPEN com 62% de falha | Reação correta e esperada do ledger-client à taxa de erro; é sintoma de saúde do mecanismo, não da causa |
| `reactor-publisher` falhando no SQS | Segunda ordem: o publisher depende do fluxo que morreu no Ledger. Mensagem "upstream dependency unavailable" descreve o Ledger, não o SQS |
| Backlog de 50.127 no Reactor, lag 18min | Terceira ordem: consequência da falha de publicação e do consumo interrompido |
| HPA em 12/12 | **Não é sintoma de falta de capacidade computacional.** CPU 62% e memória 71% (insumo 5) mostram que os pods não estão saturados de recurso próprio |

**A observação mais importante da série temporal:** o tráfego total cai de 1610 rps (20:25) para 1320 rps (20:35), mas a latência e o erro continuam subindo. Calculando o goodput (requisições bem-sucedidas por segundo = rps × (1 − taxa de erro)):

| Hora | p99 | rps total | erro | **goodput** |
|---|---:|---:|---:|---:|
| 20:05 | 420 | 1240 | 0,2% | **1238** |
| 20:10 | 780 | 1410 | 0,4% | **1404** |
| 20:15 | 1650 | 1520 | 1,1% | **1503** |
| 20:20 | 3100 | 1580 | 3,4% | **1526** ← pico |
| 20:25 | 5400 | 1610 | 6,8% | **1501** |
| 20:30 | 7200 | 1490 | 9,5% | **1348** |
| 20:35 | 8100 | 1320 | 11,7% | **1166** |

O goodput atingiu o máximo às 20:20 e caiu 23,6% desde então, enquanto o p99 subiu 2,6x no mesmo intervalo. Essa é a assinatura clássica de **colapso por saturação**: o sistema passou do ponto em que mais carga produz mais trabalho útil e entrou na região em que mais carga produz menos. A queda de rps no fim da série provavelmente **não** é demanda diminuindo, é o sistema deixando de aceitar trabalho. *Hipótese*, e a Lacuna 8 diz como confirmar.

#### 3.2 Hipóteses de causa raiz

| # | Hipótese | Evidência que sustenta | Evidência que contradiz | Confiança |
|---|---|---|---|---|
| **H1** | O novo endpoint `POST /v2/transactions/batch` tem custo de conexão desproporcional (operação em lote consumindo conexão por mais tempo, ou várias por requisição) | É o único endpoint nomeado no log de falha (insumo 3); é novo em v2.48.0 (insumo 1); adoção de endpoint novo cresce ao longo de horas, o que explica a defasagem de 25h | Há apenas uma linha de log citando o endpoint; não existe recorte por rota mostrando sua participação no tráfego ou nas conexões | **Média-alta** como contribuinte |
| **H2** | A refatoração do pool para a nova biblioteca interna mudou o comportamento efetivo do pool (tamanho, semântica de aquisição/liberação, ou vazamento de conexão) | `max=20` por pod × 12 pods = 240 = exatamente o consumo observado contra o teto de 250 (insumos 3 e 5); a fila de espera de 147→163 indica que a demanda por conexão excede em muito a oferta configurada | Não há o valor de `max` anterior a v2.48.0 nos insumos, portanto não é possível provar que mudou | **Média-alta** como mecanismo |
| **H3** | O bump do psycopg 3.1.18 → 3.2.0 alterou comportamento de conexão | Está no conjunto de mudanças (insumo 1); driver novo pode alterar pooling, prepared statements ou pipeline | Nenhum sinal nos logs aponta para camada de driver: os erros são de pool e de timeout, uma camada acima | **Baixa** |
| **H4** | A redução do timeout de 5s para 2s é a causa do erro | O log traz literalmente `query timeout after 2000ms`, casando com o valor novo (insumos 1 e 3); com 2s, requisições que antes completavam lentas passam a virar erro, e erro pode gerar retry, que multiplica a demanda | Timeout menor **libera** conexão mais rápido, o que alivia o pool em vez de piorar. Só piora se houver retry automático, e a política de retry não está nos insumos | **Média** como amplificador da taxa de erro, **baixa** como causa da saturação |
| **H5** | Crescimento puro de tráfego atingiu o teto de capacidade; o deploy é irrelevante | Degradação começa junto com o pico; rps sobe 1240→1610 (+29,8%) antes do colapso; HPA no teto e conexões em 240/250 são tetos duros (insumos 2 e 5) | +29,8% de carga produzindo 19,3x de p99 e 58,5x de erro é desproporcional para limite linear — mas é exatamente o que um **teto duro** de recurso produz, então esta contradição é fraca | **Média** — é a hipótese concorrente que mais importa |
| **H6** | O Ledger degradou por conta própria (lock, vacuum, plano de query ruim, saturação de IO) e o Chronos é vítima | `query timeout after 2000ms` é compatível com banco genuinamente lento | Não há **nenhuma** métrica do lado do Ledger nos insumos: sem CPU, IOPS, locks ou `pg_stat_activity` não há como sustentar nem descartar | **Indeterminada** — maior ponto cego do diagnóstico |

#### 3.3 Causa raiz escolhida e por que ela explica melhor

**Causa raiz provável: v2.48.0 elevou o custo de conexão por requisição (H1 combinada com H2), levando o pool agregado ao teto de 250 conexões do RDS no pico de hoje; a redução de timeout para 2s (H4) converteu a espera em erro e acelerou a percepção da falha. Nível de confiança: MÉDIA.**

Por que explica melhor que as concorrentes:

- **Explica a defasagem de 25h**, que H5 não explica bem sozinha: a demanda do endpoint novo cresce com a adoção, e o teto só é atingido no pico.
- **Explica a aritmética exata** 12 × 20 = 240 contra 250, que nenhuma outra hipótese explica: é um teto de projeto, não um acidente de carga.
- **Explica por que HPA e recursos de pod são irrelevantes** (CPU 62%, memória 71%): o recurso escasso está fora do pod.
- **Explica a ordem dos eventos no log** (pool esgotado → timeout → falha do endpoint → circuit breaker → falha do publisher) como uma cadeia única, em vez de falhas independentes.

Por que a confiança é **média** e não alta: H5 e H6 continuam vivas. Se v2.47.0 nunca sustentou 1600 rps (Lacuna 1), boa parte do peso migra para H5, e o rollback devolve o sistema ao mesmo teto. Se o Ledger estiver degradado por conta própria (Lacuna 5), nem A nem B resolvem, e B piora. **Duas informações elevariam a confiança para alta: o baseline de v2.47.0 no mesmo horário e as métricas do lado do RDS.**

---

### 4. Opção A (rollback) contra Opção B (scaling emergencial)

| Critério | **Opção A — rollback de v2.48.0** | **Opção B — aumentar limits do RDS e o pool** |
|---|---|---|
| **Efeito no gargalo primário** | Reduz a **demanda** por conexão: remove o endpoint em lote e devolve o pool à implementação anterior. Ataca o lado que dá para mover em 20 minutos | Tenta ampliar a **oferta** de conexão. Seria o ataque direto ao gargalo, se fosse executável com segurança agora |
| **Tempo até surtir efeito** | Minutos. Rollout dos 12 pods; o alívio começa nos primeiros pods a subir | **Não é rápido.** `max_connections` no PostgreSQL é parâmetro estático: exige **reinício da instância** para valer (*hipótese*; Lacuna 6 traz o comando que confirma). Subir a classe da instância também exige reboot/failover. Alterar o pool exige redeploy dos 12 pods |
| **Risco de piorar** | Médio. O timeout volta a 5s, o que faz cada conexão ficar retida por mais tempo. Com fila de 163 esperas, isso pode não aliviar de imediato. O próprio rollout agita os 12 pods em pico e causa churn de conexão. Reversível em um comando | **Alto.** Elevar o pool sem elevar o teto do RDS empurra o agregado além de 250 e troca timeout por recusa de conexão, o que pode derrubar **outros** consumidores do Ledger e até o acesso administrativo. Reiniciar o RDS em pico troca degradação de 11,7% por indisponibilidade total. Se H6 for verdadeira, mais concorrência num banco já saturado piora todo mundo |
| **Restrições visíveis nos insumos** | Não remove o teto de 250 conexões. Se H5 dominar, o sistema volta ao mesmo limite com menos carga do endpoint novo | O teto de 250 é explicitamente "o limite do RDS" (insumo 5): a folga é de 10 conexões, ou seja, **0,8 conexão por pod**. HPA já em 12/12 significa que não há caminho por mais réplicas — e mais réplicas piorariam, porque cada uma abre mais 20 conexões |
| **Efeito no backlog do Reactor** | Indireto e positivo: restabelecido o fluxo no Ledger, o `reactor-publisher` volta a publicar e o crescimento de +800/min tende a parar. O backlog acumulado ainda precisa ser drenado (seção 7) | Nenhum efeito direto. Mais conexões poderiam acelerar a drenagem, mas competindo com o tráfego vivo pelas mesmas conexões |
| **Reversibilidade** | Alta: redeploy de v2.48.0 | Baixa no curto prazo: reinício de banco não se desfaz, e alteração de parameter group exige novo reboot para voltar |

**Conclusão da comparação:** a Opção B é a que ataca o gargalo de frente, e seria a escolha correta se o teto de conexões pudesse ser elevado sem reiniciar o Ledger. Como não pode (dentro de 20 minutos e em pico), ela deixa de ser mitigação e passa a ser um segundo incidente. A Opção A é a única alavanca que reduz demanda de conexão sem tocar no banco, e é reversível.

---

### 5. Plano de ação

Ordem obrigatória. Os passos 1 e 2 são simultâneos e vêm antes do rollback.

**1. Congelar o consumer do Reactor (evita competição por conexão durante o rollback).**

```bash
# O consumer do Reactor escreve no Ledger e disputa as mesmas 250 conexões.
# Zerar réplicas para o tempo do rollback. O backlog cresce, e isso é aceito: fila é durável, conexão não.
kubectl -n production scale deployment/reactor-consumer --replicas=0
kubectl -n production get deployment/reactor-consumer
```

> *Premissa a validar em 30 segundos:* o nome do Deployment do consumer não está nos insumos. Descubra com `kubectl -n production get deploy | grep -i reactor` antes de executar.

**2. Registrar o estado atual, para comparação pós-ação.**

```bash
date -u +"T_acao = %H:%M:%SZ"
kubectl -n production get pods -l app=chronos-api -o wide
kubectl -n production logs -l app=chronos-api --tail=200 | grep -E 'pool exhausted|timeout|circuit breaker' | tail -20
aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=ledger-prod \
  --start-time "$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --period 60 --statistics Maximum --output table
```

**3. Executar o rollback para v2.47.0.**

```bash
# Caminho principal, se o Chronos é entregue por Argo CD (premissa: pipeline não consta nos insumos desta questão)
argocd app history chronos-api | tail -5          # identificar o ID da revisão de v2.47.0
argocd app rollback chronos-api <ID_v2.47.0>
argocd app wait chronos-api --health --timeout 300

# Caminho alternativo, se o rollback for direto no cluster
kubectl -n production rollout undo deployment/chronos-api --to-revision=<REV_v2.47.0>
kubectl -n production rollout status deployment/chronos-api --timeout=5m
```

**4. Acompanhar a fila de espera do pool durante o rollout — este é o sinal que decide.**

```bash
watch -n 15 'kubectl -n production logs -l app=chronos-api --tail=50 | grep -o "waiting=[0-9]*" | tail -5'
```

**5. NÃO tocar no RDS. NÃO subir o pool. NÃO aumentar réplicas.** Cada réplica nova adiciona 20 conexões contra uma folga de 10, e o HPA já está em 12/12 (insumo 5).

**6. Só depois de validado (seção 6), religar o consumer do Reactor com concorrência limitada** (seção 7).

---

### 6. Critérios de validação e de reversão

Janela: **10 minutos** a partir do fim do rollout (T_ok). Medir em T_ok+5 e T_ok+10.

| Métrica | Valor agora (20:35) | Alvo em T_ok+10 | Fonte |
|---|---|---|---|
| `waiting` do pool nos logs | 163 e subindo | **< 20 e decrescente** entre duas medições | Log do ledger-client |
| Conexões no RDS | 240/250 | **≤ 200/250** | `DatabaseConnections` no CloudWatch |
| p99 de latência | 8100ms | **≤ 2000ms** | Beacon |
| Taxa de erro | 11,7% | **≤ 2%** | Beacon |
| Goodput | 1166 req/s | **≥ 1450 req/s** | Beacon (rps × (1 − erro)) |
| Circuit breaker | OPEN | **CLOSED**, sem reabrir por 5 min | Log do ledger-client |
| Crescimento da fila do Reactor | +800/min | **≤ +100/min** (indica publisher normalizado) | Métrica do SQS |

**Critério de sucesso:** todas as sete linhas atingidas em T_ok+10. Sem exceção — em especial `waiting` e goodput, que são os dois que distinguem alívio real de trégua momentânea.

**Critério de reversão, com gatilhos objetivos:**

| Gatilho | Leitura | Ação |
|---|---|---|
| **R1** | `waiting` continua acima de 100 em T_ok+5 | O rollback não reduziu a demanda de conexão: peso desloca para H5/H6. Pare de insistir na aplicação e vá para R4 |
| **R2** | p99 **piora** em relação a 8100ms em qualquer medição | Provável efeito do timeout de volta a 5s retendo conexão por mais tempo. Redeploy de v2.48.0 (que reintroduz o timeout de 2s) e vá para R4 |
| **R3** | Taxa de erro acima de 20%, ou goodput abaixo de 1000 req/s | Deterioração ativa. Acione a decisão de negócio: shed de tráfego do endpoint em lote na borda, com o Doc Brown na call |
| **R4** | Qualquer um dos acima, ou nada resolvido em T_ok+10 | **Aí sim a Opção B, de forma controlada e assumida como janela de indisponibilidade:** fechar a Lacuna 6 (parâmetro estático ou não), acionar o dono do Ledger, comunicar a janela de reboot e só então elevar `max_connections` **antes** de elevar o pool. Nunca a ordem inversa |

Isso não é uma segunda recomendação em paralelo: a recomendação é A. R4 é o gatilho documentado que transfere a decisão para o caminho B **se e somente se** A falhar segundo números definidos.

---

### 7. Plano para o backlog do Reactor

Estado: 50.127 mensagens, crescendo ~800/min, consumer lag de 18 minutos e subindo (insumo 4).

**Princípio:** o backlog está numa fila **durável**. Ele é o único problema deste incidente que pode esperar sem perder dado, desde que a retenção da fila não expire (Lacuna 9). Conexão ao Ledger não espera. Portanto o backlog é explicitamente despriorizado até o gargalo primário estar resolvido.

**Aritmética da drenagem** (calculada sobre o insumo 4):

- Drenar em 30 min exige 1.671 msg/min de backlog + 800 msg/min de chegada = **2.471 msg/min ≈ 41 msg/s**.
- Drenar em 60 min exige **1.635 msg/min ≈ 27 msg/s**.

A opção de 60 minutos é a correta: metade da pressão sobre o Ledger, e a fila é durável.

**Sequência:**

1. **Manter o consumer em zero** até os sete critérios da seção 6 estarem atingidos. Enquanto o pool está esgotado, ligar o consumer é injetar concorrência no recurso escasso.
2. **Religar com concorrência limitada por orçamento de conexão, não por intuição.** Definir o orçamento antes: reservar no máximo 30 das 250 conexões para a drenagem (folga atual é de apenas 10). Com pool de 20 por réplica, isso significa **1 réplica de consumer com pool reduzido**, não 3 réplicas com pool padrão.
3. **Verificar antes de cada aumento de concorrência:** conexões no RDS abaixo de 200/250 e `waiting` do Chronos abaixo de 20. Se qualquer um dos dois piorar, voltar ao passo anterior.
4. **Acompanhar `ApproximateAgeOfOldestMessage`**, não apenas a contagem: a idade caindo é a prova de que a drenagem avança.
5. **Riscos a checar antes de drenar** (todos são lacunas, não fatos): mensagens cuja *visibility timeout* expirou durante o incidente podem ser reprocessadas — a drenagem só é segura se o consumer for idempotente; e se houver DLQ configurada, parte do backlog pode já ter sido desviada.

**Nunca fazer:** aumentar réplicas do consumer para "acompanhar" o crescimento de 800/min durante o incidente. Isso resolveria a métrica da fila consumindo justamente o recurso que causou o incidente.

---

### 8. Lacunas de informação e como fechá-las

Nenhuma delas foi preenchida com suposição no diagnóstico acima. As duas primeiras são as que mudam a confiança da causa raiz de média para alta.

| # | Lacuna | Por que importa | Como fechar |
|---|---|---|---|
| **1** | v2.47.0 já sustentou ~1600 rps sem degradar? | Desempata H1/H2 (regressão) contra H5 (teto de capacidade). Se v2.47.0 nunca viu esse volume, o rollback não resolve | Consultar no Beacon p99, rps e erro na mesma janela (20:00-20:40) dos 7 dias anteriores |
| **2** | Qual era o `max` do pool antes de v2.48.0? | Prova ou refuta H2. Se já era 20, a refatoração não mudou o tamanho e o peso vai para H1 | `git diff v2.47.0..v2.48.0 -- <config do ledger-client>` no repo `hvt/chronos-api` |
| **3** | Qual a participação de `/v2/transactions/batch` no tráfego e nas conexões? | Quantifica H1. Se for 2% do tráfego e 40% das conexões, a causa está isolada | Recorte por rota no `/metrics` ou no Beacon: latência, contagem e tempo de conexão por endpoint |
| **4** | Existe retry automático no timeout do ledger-client? Quantas tentativas? | Define se o timeout de 2s virou amplificador (H4). Retry sem orçamento multiplica a demanda por conexão | Ler a configuração de retry no mesmo diff da Lacuna 2 |
| **5** | Como está o Ledger por dentro: CPU, IOPS, locks, queries lentas? | **Maior ponto cego.** Se H6 for verdadeira, nem A nem B resolvem, e B piora | `aws cloudwatch get-metric-statistics` para `CPUUtilization`, `ReadLatency`, `WriteLatency`, `DiskQueueDepth`; e `SELECT state, wait_event_type, count(*) FROM pg_stat_activity GROUP BY 1,2;` |
| **6** | `max_connections` é parâmetro estático (exige reboot)? | É a restrição que inviabiliza a Opção B agora. Está declarada como **hipótese** na seção 4 | `aws rds describe-db-parameters --db-parameter-group-name <grupo> --query "Parameters[?ParameterName=='max_connections'].[ParameterValue,ApplyType]"` |
| **7** | O endpoint em lote gravou dados em formato que v2.47.0 não lê? Houve migração de schema? | Define se o rollback é seguro do ponto de vista de dados | Inspecionar migrações no diff v2.47.0..v2.48.0 e o schema atual do Ledger |
| **8** | A queda de rps (1610→1320) é demanda caindo ou requisição sendo rejeitada na borda? | Confirma o colapso por saturação. Está marcado como hipótese na seção 3.1 | Comparar requisições recebidas contra atendidas no ALB/ingress: `RequestCount` contra `HTTPCode_ELB_5XX_Count` e contagem de conexões rejeitadas |
| **9** | Retenção da fila SQS, existência de DLQ e idempotência do consumer | Define se o backlog pode esperar 60 min e se a drenagem pode duplicar efeitos | `aws sqs get-queue-attributes --queue-url <url> --attribute-names MessageRetentionPeriod RedrivePolicy VisibilityTimeout` |
| **10** | psycopg 3.2.0 alterou comportamento de pooling ou prepared statements? | Fecha H3, hoje em confiança baixa | Comparar o changelog das versões 3.1.18 e 3.2.0 |

---

### 9. Follow-ups pós-incidente

**Correções definitivas**

1. **Multiplexação de conexão entre a aplicação e o Ledger** (RDS Proxy ou pgbouncer). É a correção estrutural: hoje o número de conexões é `pods × pool`, o que faz o teto do banco ser função da escala do Chronos. Com multiplexação, escalar pods deixa de consumir conexão proporcionalmente.
2. **Orçamento agregado de conexões, imposto por configuração.** O pool por pod deve ser derivado do teto do banco e do máximo de réplicas do HPA, com folga: hoje `12 × 20 = 240` contra 250 é um projeto que não tem margem para nenhuma réplica extra.
3. **Acoplar o `maxReplicas` do HPA ao orçamento de conexões.** Enquanto o HPA puder escalar sem consultar esse orçamento, escalar por CPU é um caminho para derrubar o banco.
4. **Bulkhead para o endpoint em lote:** pool e fila separados para `/v2/transactions/batch`, para que uma operação em lote não consuma a capacidade de conexão do tráfego transacional comum.
5. **Timeout e retry desenhados juntos**, com orçamento total por requisição, jitter e teto de tentativas. Reduzir timeout de 5s para 2s isoladamente, sem revisar retry, muda o perfil de falha do sistema.
6. **Alertas sobre os sinais que precedem o colapso:** fila de espera do pool (`waiting`) e conexões agregadas contra o limite do RDS. Ambos estavam disponíveis e nenhum alertou antes da queda de goodput.
7. **Teste de carga em rps equivalente ao pico antes de liberar mudanças no cliente do banco.** As quatro mudanças de v2.48.0 tocam o caminho crítico do Ledger e subiram juntas.
8. **Separar mudanças de risco em deploys distintos.** Endpoint novo, troca de biblioteca de pool, bump de driver e mudança de timeout no mesmo release tornam impossível atribuir causa em 20 minutos — o custo disso é exatamente este postmortem com confiança média em vez de alta.

**Mitigações temporárias (têm prazo de validade e precisam sair do ar)**

1. O rollback para v2.47.0 em si: bloqueia o endpoint novo, que é entrega de produto pendente.
2. Elevação de `max_connections` no RDS, caso o gatilho R4 seja acionado: alivia sem corrigir o modelo de conexão.
3. Consumer do Reactor em zero réplicas ou com concorrência reduzida.
4. Congelamento de novos deploys do Chronos até a causa raiz estar confirmada com as Lacunas 1 e 2 fechadas.
5. Qualquer shed de tráfego no endpoint em lote acionado por R3.

---

## Justificativa estendida

### Framework escolhido: R-I-S-E

**Role:** o papel não é decorativo aqui, ele define o comportamento exigido: "separar com rigor o que a evidência sustenta do que é hipótese" e "recomendar uma decisão única mesmo com dados incompletos". Essas duas frases são o que impede o output de virar uma lista de possibilidades. Elas aparecem no resultado como confiança declarada por hipótese (H1 a H6, de baixa a indeterminada), a palavra "hipótese" marcando as três afirmações que a evidência não sustenta (reboot do RDS, queda de rps por rejeição, causa raiz) e uma decisão assumida na primeira linha.

**Input:** cinco fontes heterogêneas em um único bloco: changelog com quatro mudanças simultâneas, série temporal de 7 pontos, trecho de log com 6 linhas, estado de fila e estado de cluster. Foi o Input que tornou possível a descoberta que decide o caso, e ela só existe cruzando dois insumos diferentes: `max=20` por pod (log) × 12 pods (cluster) = 240 = as conexões observadas contra o teto de 250. Nenhum insumo isolado revela isso.

**Steps** — os 9 passos impuseram a ordem do raciocínio, e essa ordem é o que evita o erro mais provável do cenário. Diagnosticar antes de escolher (passos 1-4) mostrou que HPA no teto, circuit breaker e backlog do Reactor são consequência, não causa; avaliar A e B com critérios fixos (passo 5) expôs que a opção aparentemente mais direta, mexer no banco, é a que exige reboot em pico; e o passo 9, exigindo lacuna com o comando que a fecha, é o que permitiu declarar confiança média com honestidade em vez de fabricar certeza.

**Expectation:** a Expectation fixou o formato de consumo sob pressão: DECISÃO em 3 linhas no topo, porque o Doc Brown está numa call e pode ler só isso; tabela A contra B, porque ele precisa comparar, não ler prosa; e a proibição explícita de duas recomendações em paralelo, que foi resolvida com uma recomendação única (A) mais um gatilho documentado (R4) que transfere para B sob condição numérica. Sem essa restrição, o output natural teria sido "depende", que é inútil em 20 minutos.

### Comparação com alternativas

**Alternativa 1 — T-A-G (Task, Action, Goal). O que se ganharia e o que se perderia.**

*Ganho:* T-A-G é mais enxuto e o Goal casa bem com este cenário, porque existe um objetivo de negócio nítido e verificável, decidir entre A e B em 20 minutos. A Action carregaria a sequência analítica, e o prompt sairia mais curto e mais rápido de escrever.

*Perda:* T-A-G não tem componente de entrada. Este caso tem cinco insumos heterogêneos que precisam ser lidos como um conjunto e citados individualmente ("toda afirmação técnica deve apontar o insumo que a sustenta"). Em T-A-G esses dados seriam empilhados dentro da Task, e a distinção entre *o que analisar* e *como analisar* se dilui. A perda concreta e mensurável seria no rigor epistêmico: T-A-G não tem onde alojar naturalmente a exigência de marcar hipótese e declarar nível de confiança, porque isso é característica de **postura** do analista, que é papel do Role, e o Role não existe em T-A-G. O output mais provável seria um relatório correto no formato e otimista na conclusão, afirmando causa raiz com convicção que a evidência não dá. Em incidente, essa é a diferença entre reiniciar o banco por engano e não reiniciar.

**Alternativa 2 — C-A-R-E (Context, Action, Result, Example). O que se ganharia e o que se perderia.**

*Ganho:* C-A-R-E é o mais forte dos cinco quando existe um artefato de referência a imitar, e postmortem é um gênero com formato consagrado. O Example poderia trazer um postmortem anterior da Hill Valley Tech, garantindo aderência de estilo e seções, e o Result descreveria o entregável com precisão. Foi a escolha certa na Questão 06 exatamente por isso.

*Perda:* o Example é o componente mais caro e aqui ele seria o mais fraco. Postmortem exemplar é documento longo; incluí-lo consumiria uma fração significativa da janela de contexto competindo com os cinco insumos, que são o que realmente importa. Pior, um exemplo de postmortem **encerrado** ensinaria o modelo a escrever no passado, com causa raiz estabelecida — e este incidente está em andamento, com dados incompletos, precisando de recomendação no presente. Haveria risco real de o modelo imitar a confiança retrospectiva do exemplo e apresentar H1+H2 como fato. Além disso, C-A-R-E não tem componente de sequência: a ordem "diagnostique antes de escolher" ficaria dentro da Action como lista, sem a força que o Steps dá.

**Alternativa 3 — B-A-B, descartada rapidamente.** B-A-B pressupõe que se conhece o Before e o After e que a dúvida é a travessia. Aqui a incógnita é justamente o Before: não se sabe qual é a causa. Usar B-A-B obrigaria a assumir a causa raiz no próprio prompt, o que resolveria por decreto a pergunta que o Doc Brown está fazendo. Foi a escolha certa na Questão 05, onde o estado atual era um YAML conhecido e o estado desejado era o padrão da empresa.

**Alternativa 4 — R-T-F, descartada rapidamente.** R-T-F é ótimo para produzir artefato com formato rígido (Questões 01 e 02), mas não tem onde colocar cinco insumos nem como impor sequência de raciocínio. Sobrariam Role e Format, e o Task viraria um parágrafo gigante fazendo o trabalho de Input e Steps ao mesmo tempo.

### Por que R-I-S-E vence neste caso específico

O critério de escolha não é qual framework é melhor em geral, é qual tem componente para cada dificuldade **deste** cenário. As dificuldades são quatro, e o R-I-S-E cobre as quatro em componentes distintos:

| Dificuldade do cenário | Componente que resolve | O que faltaria nas alternativas |
|---|---|---|
| Cinco insumos heterogêneos que só fazem sentido cruzados | **Input** | T-A-G e R-T-F não têm componente de entrada |
| A análise precisa acontecer numa ordem específica, senão a conclusão vem antes da evidência | **Steps** | C-A-R-E e T-A-G tratam ordem como lista dentro da Action |
| Exigência de rigor: marcar hipótese, declarar confiança, não fabricar certeza | **Role** | T-A-G não tem Role; sem ele, o output tende ao excesso de confiança |
| Formato de consumo sob pressão, com decisão única obrigatória | **Expectation** | B-A-B não tem componente de formato de saída |

O que se perde ao escolher R-I-S-E é o Example: não há garantia de aderência ao formato de postmortem que a Hill Valley Tech já usa, e o output pode divergir do padrão interno de documento. Nesta questão isso é um preço aceitável, porque o formato foi especificado item a item na Expectation. Se a empresa tivesse um template obrigatório de postmortem, a resposta correta mudaria: seria R-I-S-E com o template anexado, ou C-A-R-E aceitando o custo de contexto do Example.
