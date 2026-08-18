# Questão 07 — Runbook para alerta recorrente

**Framework:** R-I-S-E (Role, Input, Steps, Expectation)

---

## Prompt

````text
[ROLE]
Você é o SRE líder de plantão da Hill Valley Tech e está escrevendo um runbook operacional.

O runbook atende o plantonista de sobreaviso: uma pessoa que pode estar às 3h da manhã, não conhece a arquitetura do Chronos, nunca tratou esse alerta antes e não tem ninguém acordado para consultar. Escreva para esse leitor. Nada pode depender de conhecimento prévio do sistema, de intuição ou de "perguntar para quem conhece".

[INPUT]
Alerta a ser tratado: `[CRITICAL] High memory usage on Chronos API pods (>85% for 10min)`

Situação atual: o Beacon dispara esse alerta em média 4 vezes por semana. Cada plantonista gasta de 30 a 40 minutos resolvendo, de forma diferente a cada vez, porque não existe procedimento documentado.

Contexto do sistema:

- Chronos: API gateway e plataforma core, ponto de entrada de todo o tráfego da empresa.
- Runtime: EKS, namespace production, 6 réplicas com HPA (min 4, max 12, CPU target 70%).
- Deploy: Argo CD, repositório hvt/chronos-api.
- Dependências diretas: Ledger (PostgreSQL) e Reactor (filas SQS).
- Observabilidade: métricas expostas em /metrics, logs no Beacon, dashboards no Grafana.
- Ferramentas disponíveis no plantão: kubectl, aws cli, argocd cli.
- Canal de plantão: #oncall-chronos. Escalação para @chronos-core, com SLA de 15 minutos em horário comercial e 30 minutos fora dele.

[STEPS]
Produza o runbook em passos numerados, sequenciais, do início ao fim do atendimento, seguindo esta estrutura em cada passo:

1. Título do passo, com o objetivo em uma linha.
2. Os comandos exatos a executar, prontos para copiar e colar, já com namespace, labels e nomes de recursos deste ambiente preenchidos. Sem placeholder genérico do tipo `<pod-name>` sem antes mostrar o comando que descobre esse valor.
3. O que observar na saída: qual valor, qual campo, qual ordem de grandeza.
4. A verificação esperada ao final do passo, ou seja, o critério objetivo que diz se o passo resolveu, não resolveu ou apenas coletou evidência.
5. A bifurcação explícita: se a verificação der A, vá para o passo X; se der B, vá para o passo Y ou escale.

O runbook deve cobrir, nesta ordem lógica:

- Triagem inicial e confirmação de que o alerta é real (memória por pod, comparação com os limits, quantas réplicas estão afetadas, estado do HPA).
- Avaliação de impacto no usuário antes de qualquer ação: latência, taxa de erro e se o tráfego está sendo atendido.
- Coleta de evidência que não se perde depois de reiniciar pod: logs, métricas, describe, eventos e, se aplicável, heap ou perfil de memória.
- Diferenciação entre as causas prováveis: memory leak progressivo, pico legítimo de tráfego, degradação de dependência (Ledger ou Reactor) causando acúmulo em memória, e regressão introduzida por deploy recente via Argo CD.
- Ações de mitigação, da menos invasiva para a mais invasiva, cada uma com o risco de executá-la em um serviço que recebe todo o tráfego da empresa.
- Rollback via Argo CD como caminho documentado: como identificar o último deploy, como comparar e como reverter.
- O que registrar no #oncall-chronos e em que momento.
- Critérios objetivos de escalação para @chronos-core, com números e prazos, não com julgamento subjetivo, considerando o SLA de 15 minutos em horário comercial e 30 minutos fora dele.
- Critério de encerramento do incidente: quais métricas, por quanto tempo estáveis, e o que precisa ficar registrado como follow-up.

Restrições: use apenas kubectl, aws cli e argocd cli. Não sugira ferramenta que o plantonista não tem. Todo comando destrutivo ou que afete tráfego deve vir com um aviso explícito do impacto e o que verificar antes de executar.

[EXPECTATION]
O resultado esperado é um runbook autossuficiente em Markdown, que qualquer pessoa de plantão consiga seguir do início ao fim sem depender de quem já conhece o sistema, e que reduza o tempo de atendimento dos atuais 30 a 40 minutos para algo previsível e repetível.

Ele deve começar com um bloco de resumo (severidade, tempo estimado de atendimento, impacto potencial, primeira ação) e uma tabela de decisão rápida para os 3 cenários mais prováveis, antes dos passos detalhados. Ao final, uma seção de ações de prevenção a levar para o time como follow-up, para que o alerta pare de recorrer 4 vezes por semana.

Nenhum passo pode terminar sem critério de verificação. Nenhuma decisão de escalação pode ficar em aberto.
````

---

## Modelo

**Claude Opus 5 Max (Anthropic)**

Escolhido porque o entregável é um documento procedural longo em que a consistência interna é o requisito principal: cada passo precisa fechar com critério de verificação, cada bifurcação precisa apontar para um passo que existe, e nenhum comando pode citar recurso que não tenha sido descoberto antes. É um trabalho de coerência ao longo de muitas páginas, não de criatividade pontual.

---

## Output

### Runbook — `[CRITICAL] High memory usage on Chronos API pods (>85% for 10min)`

#### Resumo

| Campo | Valor |
|---|---|
| **Severidade** | CRITICAL — Chronos é tier-0, ponto de entrada de todo o tráfego da empresa |
| **Tempo estimado** | 12 a 18 minutos até mitigação ou escalação. Nunca passe de 10 min (horário comercial) ou 15 min (fora dele) sem acionar @chronos-core |
| **Impacto potencial** | OOMKill em cascata: pods morrem, HPA repõe, os que sobram recebem mais tráfego e estouram também. O resultado final é indisponibilidade total do gateway |
| **Primeira ação** | Passo 1: postar o ACK em #oncall-chronos e anotar o horário. Não execute nenhuma mitigação antes do Passo 4 |
| **Escopo** | Namespace `production`, Deployment `chronos-api`, cluster EKS |
| **Ferramentas** | Apenas `kubectl`, `aws`, `argocd`. Se você não tem acesso a alguma delas, escale imediatamente (ver Passo 11) |

> **Regra de ouro deste runbook:** o alerta é de memória, mas o HPA do Chronos escala por **CPU a 70%**. Isso significa que o Kubernetes **não vai escalar sozinho** por causa de memória. Não espere autocorreção.

> **Segunda regra:** o Chronos é gerido por **Argo CD**. Se o app estiver com sync automático e self-heal, qualquer alteração feita com `kubectl edit`, `kubectl scale` ou `kubectl patch` **será revertida sozinha em poucos minutos**. O Passo 4 verifica isso antes de qualquer mitigação. Não pule.

#### Tabela de decisão rápida — 3 cenários mais prováveis

| Sinal observado na triagem | Cenário provável | Ação imediata | Vá para |
|---|---|---|---|
| Memória sobe de forma linear e contínua nos pods **mais antigos**; pods novos começam baixos; **sem** aumento de tráfego; deploy tem mais de 24h | **Memory leak progressivo** | Restart controlado, em ondas, para zerar a memória e comprar tempo | Passo 8 |
| Memória alta em **todos** os pods ao mesmo tempo; requisições por segundo acima do normal; CPU também alta; HPA já subiu réplicas | **Pico legítimo de tráfego** | Aumentar `minReplicas` do HPA para adicionar capacidade | Passo 7 |
| Memória alta **junto com** latência do Ledger alta, fila do Reactor crescendo ou erros de timeout nos logs | **Degradação de dependência** (requisições acumulam em memória esperando I/O) | Não reinicie o Chronos: o gargalo está fora dele. Escale para @chronos-core com a evidência da dependência | Passo 6 → Passo 11 |
| Quarto caso: alerta começou menos de 2h depois de um deploy | **Regressão de deploy** | Rollback via Argo CD | Passo 9 |

---

#### Passo 0 — Preparar o terminal (30 segundos)

**Objetivo:** fixar as variáveis usadas por todos os comandos, para você não digitar nome de recurso errado às 3h da manhã.

```bash
export NS=production
export APP=chronos-api
export DEPLOY=chronos-api
export EVID="/tmp/incident-chronos-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$EVID" && echo "Evidências em: $EVID"
date -u +"T0 = %Y-%m-%d %H:%M:%SZ" | tee "$EVID/00-inicio.txt"
```

**O que observar:** o caminho de `$EVID` e o horário T0. Anote T0 em algum lugar visível; todos os prazos de escalação contam a partir dele.

**Verificação:** o diretório foi criado e `kubectl get ns $NS` responde sem erro.

```bash
kubectl get ns "$NS"
```

**Bifurcação:**
- Diretório criado e namespace existe → **Passo 1**.
- `kubectl` retorna erro de autenticação, contexto ou permissão → você não tem como atender. **Passo 11, gatilho E5**, escalação imediata.

---

#### Passo 1 — Abrir o incidente no canal e ligar o cronômetro (30 segundos)

**Objetivo:** garantir que existe registro do atendimento desde o primeiro minuto, mesmo que você precise escalar depois.

Poste em **#oncall-chronos**, exatamente neste formato:

```text
:rotating_light: ACK [CRITICAL] High memory usage on Chronos API pods (>85% for 10min)
T0: <horário UTC do Passo 0>
Plantonista: <seu nome>
Status: triagem iniciada, seguindo runbook de memória do Chronos
Próxima atualização: T0+5min
```

**O que observar:** nada na saída de comando. O que importa é o horário do post, que passa a ser a referência para todos.

**Verificação:** a mensagem está publicada no canal e você sabe qual é o seu T0.

**Bifurcação:**
- Publicado → **Passo 2**.
- Sem acesso ao canal → siga o atendimento e registre o timeline em `$EVID/timeline.txt`; mencione a falta de acesso ao escalar. → **Passo 2**.

> **Gatilho de relógio, válido de agora até o encerramento:** se o alerta não estiver mitigado em **T0+10min** (horário comercial) ou **T0+15min** (fora dele), vá para o **Passo 11, gatilho E6**, independentemente do passo em que você estiver. Este prazo não é negociável e não depende de você achar que está perto de resolver.

---

#### Passo 2 — Confirmar que o alerta é real: memória por pod contra o limit (2 minutos)

**Objetivo:** medir o consumo real de cada pod e comparar com o limit configurado, para saber se o alerta é verdadeiro e quantas réplicas estão afetadas.

```bash
# 2.1 — consumo atual, do maior para o menor
kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r | tee "$EVID/01-top.txt"

# 2.2 — limits, requests, idade e reinícios de cada pod
kubectl get pods -n "$NS" -l app="$APP" \
  -o custom-columns='POD:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,MEM_REQ:.spec.containers[0].resources.requests.memory,MEM_LIM:.spec.containers[0].resources.limits.memory,IDADE:.metadata.creationTimestamp,NODE:.spec.nodeName' \
  | tee "$EVID/02-pods.txt"

# 2.3 — houve OOMKill? (esta é a pergunta mais importante do passo)
kubectl get pods -n "$NS" -l app="$APP" \
  -o custom-columns='POD:.metadata.name,ULTIMO_MOTIVO:.status.containerStatuses[0].lastState.terminated.reason,EXIT:.status.containerStatuses[0].lastState.terminated.exitCode,QUANDO:.status.containerStatuses[0].lastState.terminated.finishedAt' \
  | tee "$EVID/03-oomkill.txt"
```

**O que observar:**
- Em 2.1, a terceira coluna é a memória em bytes/Mi. **Não presuma o valor do limit**: leia `MEM_LIM` na saída de 2.2 e calcule o percentual (`memória_atual ÷ MEM_LIM`). O alerta dispara em 85%.
- Em 2.2: quantos pods existem (o normal é 6), quantos estão `READY=true`, e a coluna `RESTARTS`. Reinício maior que zero nas últimas horas é sinal forte.
- Em 2.3: `ULTIMO_MOTIVO=OOMKilled` ou `EXIT=137` significa que o kernel já matou o container por memória. Isso não é aviso, é dano em andamento.

**Verificação:** você sabe responder três números: (a) quantos pods estão acima de 85% do limit, (b) quantos pods existem no total, (c) houve OOMKill nas últimas horas, sim ou não.

**Bifurcação:**
- **Nenhum pod acima de 85%** e nenhum OOMKill → alerta possivelmente já resolvido sozinho ou falso positivo. → **Passo 12** (encerramento), registrando como "autorresolvido, investigar flapping do alerta".
- **1 ou 2 pods acima de 85%**, sem OOMKill → **Passo 3**.
- **3 ou mais pods acima de 85%**, ou **qualquer OOMKill** → risco de cascata. Escale **agora, em paralelo** com a investigação: **Passo 11, gatilho E1**, e continue no **Passo 3** enquanto espera.

---

#### Passo 3 — Medir o impacto no usuário antes de tocar em qualquer coisa (2 minutos)

**Objetivo:** decidir se você está diante de um problema de capacidade que ainda não afeta ninguém ou de uma indisponibilidade em curso; a resposta muda o nível de agressividade permitido.

```bash
# 3.1 — quantos pods estão realmente recebendo tráfego
kubectl get endpoints -n "$NS" "$APP" -o wide | tee "$EVID/04-endpoints.txt"
kubectl get endpointslices -n "$NS" -l kubernetes.io/service-name="$APP" \
  -o custom-columns='SLICE:.metadata.name,ENDERECOS:.endpoints[*].addresses,PRONTOS:.endpoints[*].conditions.ready' 2>/dev/null

# 3.2 — descobrir se existe ALB na frente do serviço (não presuma que existe)
aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?contains(LoadBalancerName,'chronos')].[LoadBalancerName,LoadBalancerArn]" \
  --output table
```

Se o comando 3.2 retornou um ALB, meça erro e latência reais:

```bash
export ALB_DIM=$(aws elbv2 describe-load-balancers \
  --query "LoadBalancers[?contains(LoadBalancerName,'chronos')].LoadBalancerArn" \
  --output text | head -1 | sed 's|.*:loadbalancer/||')
echo "Dimensão do ALB: $ALB_DIM"

export T_INI=$(date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)
export T_FIM=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# 3.3 — erros 5xx nos últimos 30 min, em janelas de 5 min
aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count --dimensions Name=LoadBalancer,Value="$ALB_DIM" \
  --start-time "$T_INI" --end-time "$T_FIM" --period 300 --statistics Sum \
  --output table | tee "$EVID/05-5xx.txt"

# 3.4 — volume de requisições, para separar pico de tráfego de leak
aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name RequestCount --dimensions Name=LoadBalancer,Value="$ALB_DIM" \
  --start-time "$T_INI" --end-time "$T_FIM" --period 300 --statistics Sum \
  --output table | tee "$EVID/06-requests.txt"

# 3.5 — latência p99
aws cloudwatch get-metric-statistics --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime --dimensions Name=LoadBalancer,Value="$ALB_DIM" \
  --start-time "$T_INI" --end-time "$T_FIM" --period 300 --extended-statistics p99 \
  --output table | tee "$EVID/07-latencia.txt"
```

Se **não** houver ALB, use o fallback pelas métricas do próprio pod (somente leitura, não afeta tráfego):

```bash
export POD_PIOR=$(kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r | head -1 | awk '{print $1}')
echo "Pod com maior consumo: $POD_PIOR"
kubectl port-forward -n "$NS" "pod/$POD_PIOR" 19090:8080 >/dev/null 2>&1 &
export PF_PID=$!
sleep 3
curl -s localhost:19090/metrics | grep -Ei 'http_(requests|request_duration)|error|5xx' | head -40 | tee "$EVID/08-metrics-fallback.txt"
kill "$PF_PID"
```

**O que observar:**
- Em 3.1: quantos endereços estão `ready`. Se o normal é 6 e você vê 4, dois pods já saíram de rotação e os outros estão absorvendo o tráfego deles.
- Em 3.3: qualquer valor de 5xx diferente de zero e, principalmente, **crescendo** janela a janela.
- Em 3.4: `RequestCount` subindo 30% ou mais em relação às primeiras janelas indica pico legítimo de tráfego, não leak.
- Em 3.5: p99 crescendo janela a janela é degradação percebida pelo cliente.

**Verificação:** você consegue classificar o impacto em uma das três faixas:
- **Sem impacto:** 5xx em zero, p99 estável, todos os pods `ready`.
- **Impacto parcial:** 5xx acima de zero mas abaixo de 1% do `RequestCount`, ou p99 até 2x a primeira janela.
- **Impacto severo:** 5xx acima de 5% do `RequestCount`, ou p99 acima de 3x, ou menos de 4 pods `ready`.

**Bifurcação:**
- **Sem impacto** → você tem tempo. → **Passo 4**.
- **Impacto parcial** → siga, mas sem desvios. → **Passo 4**.
- **Impacto severo** → **Passo 11, gatilho E2**, escalação imediata, e continue no **Passo 4** em paralelo. Não pare de investigar esperando resposta.

---

#### Passo 4 — Verificar deploy recente e o modo de sync do Argo CD (2 minutos)

**Objetivo:** descobrir se um deploy causou isso e, principalmente, se o Argo CD vai reverter qualquer mitigação manual que você fizer.

```bash
# 4.1 — estado do app, incluindo a política de sync
argocd app get "$APP" | tee "$EVID/09-argocd-get.txt"

# 4.2 — histórico de deploys, com data e revisão
argocd app history "$APP" | tail -10 | tee "$EVID/10-argocd-history.txt"

# 4.3 — o que está rodando difere do que está no Git?
argocd app diff "$APP" | tee "$EVID/11-argocd-diff.txt"

# 4.4 — confirmação pelo lado do cluster: quando o rollout mudou pela última vez
kubectl rollout history -n "$NS" "deployment/$DEPLOY" | tee "$EVID/12-rollout-history.txt"
kubectl get deployment -n "$NS" "$DEPLOY" \
  -o custom-columns='DEPLOY:.metadata.name,IMAGEM:.spec.template.spec.containers[0].image,GERACAO:.metadata.generation,ATUALIZADO:.status.conditions[?(@.type=="Progressing")].lastUpdateTime' \
  | tee "$EVID/13-deploy.txt"
```

**O que observar:**
- Em 4.1, duas linhas decidem sua próxima hora:
  - `Sync Policy: Automated` com `SelfHeal` ligado → **toda alteração via kubectl será revertida**. Use o caminho Argo CD (Passos 7-B e 9), não o kubectl direto.
  - `Sync Policy: <none>` ou `Manual` → alterações via kubectl permanecem.
- Em 4.2 e 4.4: a data do último deploy. Compare com T0.
- Em 4.3: se o diff não estiver vazio, alguém já mexeu à mão no cluster. Registre, isso vira follow-up.

**Verificação:** você sabe responder: (a) o último deploy foi há menos de 2h, sim ou não; (b) o sync é automático com self-heal, sim ou não.

**Bifurcação:**
- **Deploy há menos de 2h** → suspeita principal é regressão. → **Passo 5** (coletar evidência) e depois **Passo 9** (rollback).
- **Deploy há mais de 2h** → **Passo 5**.
- **`argocd` retorna erro de login ou permissão** → você perdeu o caminho de rollback. **Passo 11, gatilho E5**, e continue no **Passo 5**.

---

#### Passo 5 — Coletar a evidência que desaparece no restart (3 minutos)

**Objetivo:** salvar em disco tudo que morre junto com o pod, antes de qualquer mitigação. Este passo é obrigatório e não pode ser pulado: sem ele o alerta volta na semana que vem e ninguém sabe por quê.

> Todos os comandos deste passo são **somente leitura**. Nenhum afeta tráfego.

```bash
export POD_PIOR=$(kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r | head -1 | awk '{print $1}')
echo "Pod alvo da coleta: $POD_PIOR" | tee -a "$EVID/timeline.txt"

# 5.1 — describe completo: limites, eventos, último estado de terminação
kubectl describe pod -n "$NS" "$POD_PIOR" > "$EVID/14-describe-$POD_PIOR.txt"

# 5.2 — logs atuais e do container anterior (o anterior só existe se já houve restart)
kubectl logs -n "$NS" "$POD_PIOR" --tail=2000 > "$EVID/15-logs-atual.txt" 2>&1
kubectl logs -n "$NS" "$POD_PIOR" --previous --tail=2000 > "$EVID/16-logs-anterior.txt" 2>&1 || \
  echo "sem container anterior (nenhum restart)" > "$EVID/16-logs-anterior.txt"

# 5.3 — eventos do namespace, ordenados por horário
kubectl get events -n "$NS" --sort-by=.lastTimestamp | tail -50 > "$EVID/17-events.txt"

# 5.4 — snapshot das métricas do pod, incluindo memória por área, se exposta
kubectl port-forward -n "$NS" "pod/$POD_PIOR" 19090:8080 >/dev/null 2>&1 &
export PF_PID=$!
sleep 3
curl -s localhost:19090/metrics > "$EVID/18-metrics-completo.txt"

# 5.5 — perfil de heap, SOMENTE se o endpoint pprof existir; verifique antes
curl -s -o /dev/null -w "pprof status: %{http_code}\n" localhost:19090/debug/pprof/heap
# Se o status for 200, capture. Se for 404, siga sem o heap e registre isso no follow-up.
curl -s localhost:19090/debug/pprof/heap > "$EVID/19-heap.pprof" 2>/dev/null
kill "$PF_PID"

# 5.6 — duas medições de memória com 60s de intervalo: revela a inclinação da curva
kubectl top pods -n "$NS" -l app="$APP" --no-headers > "$EVID/20-mem-t1.txt"
sleep 60
kubectl top pods -n "$NS" -l app="$APP" --no-headers > "$EVID/21-mem-t2.txt"
paste "$EVID/20-mem-t1.txt" "$EVID/21-mem-t2.txt" | tee "$EVID/22-mem-delta.txt"
```

**O que observar:**
- Em 5.1: a seção `Last State` com `OOMKilled`, e os `Events` com `Killing`, `BackOff` ou `Unhealthy`.
- Em 5.2: exceções repetidas, mensagens de timeout, "connection pool", "queue full", "circuit breaker". Guarde a mensagem exata; ela é o que o @chronos-core vai querer ler primeiro.
- Em 5.5: se o status for 404, não insista, o binário não expõe pprof. Isso vira item de follow-up.
- Em 5.6: compare as duas colunas de memória. Crescimento de mais de 2% do limit em 60 segundos, com tráfego estável, é curva de leak.

**Verificação:** os arquivos de 14 a 22 existem em `$EVID` e você já leu a mensagem de erro dominante em `15-logs-atual.txt`.

```bash
ls -la "$EVID"
```

**Bifurcação:** este passo apenas coleta, não resolve. Sempre siga para o **Passo 6**.

---

#### Passo 6 — Classificar a causa: o Chronos é a vítima ou o culpado? (2 minutos)

**Objetivo:** verificar as duas dependências diretas antes de reiniciar o Chronos, porque reiniciar o gateway quando o problema está no Ledger ou no Reactor piora o incidente.

```bash
# 6.1 — Ledger (PostgreSQL no RDS): descobrir a instância
aws rds describe-db-instances \
  --query "DBInstances[?contains(DBInstanceIdentifier,'ledger')].[DBInstanceIdentifier,DBInstanceStatus,DBInstanceClass]" \
  --output table | tee "$EVID/23-rds.txt"

export DB_ID=$(aws rds describe-db-instances \
  --query "DBInstances[?contains(DBInstanceIdentifier,'ledger')].DBInstanceIdentifier" \
  --output text | head -1)
echo "Instância do Ledger: $DB_ID"

# 6.2 — conexões e latência do Ledger nos últimos 30 min
for M in DatabaseConnections ReadLatency WriteLatency CPUUtilization; do
  echo "=== $M ==="
  aws cloudwatch get-metric-statistics --namespace AWS/RDS --metric-name "$M" \
    --dimensions Name=DBInstanceIdentifier,Value="$DB_ID" \
    --start-time "$T_INI" --end-time "$T_FIM" --period 300 --statistics Average Maximum \
    --output table
done | tee "$EVID/24-ledger-metrics.txt"

# 6.3 — Reactor (SQS): descobrir as filas
aws sqs list-queues --queue-name-prefix reactor --output table | tee "$EVID/25-sqs-list.txt"

export FILA=$(aws sqs list-queues --queue-name-prefix reactor --query 'QueueUrls[0]' --output text)
echo "Fila do Reactor: $FILA"

# 6.4 — profundidade da fila e mensagens em voo
aws sqs get-queue-attributes --queue-url "$FILA" \
  --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible ApproximateNumberOfMessagesDelayed \
  --output table | tee "$EVID/26-sqs-depth.txt"

# 6.5 — idade da mensagem mais antiga: o melhor indicador de consumer travado
aws cloudwatch get-metric-statistics --namespace AWS/SQS \
  --metric-name ApproximateAgeOfOldestMessage \
  --dimensions Name=QueueName,Value="$(basename "$FILA")" \
  --start-time "$T_INI" --end-time "$T_FIM" --period 300 --statistics Maximum \
  --output table | tee "$EVID/27-sqs-idade.txt"
```

**O que observar:**
- Em 6.2: `DatabaseConnections` perto do máximo da classe da instância, ou `ReadLatency`/`WriteLatency` acima de 100ms sustentados. Ambos fazem requisições ficarem presas no Chronos consumindo memória.
- Em 6.4: `ApproximateNumberOfMessages` na ordem de dezenas de milhares, ou crescendo entre execuções do comando.
- Em 6.5: `ApproximateAgeOfOldestMessage` acima de 300 segundos e subindo indica consumer não acompanhando.

**Verificação:** classifique em um dos quatro cenários, com o número que sustenta a escolha:

| Cenário | Evidência objetiva |
|---|---|
| **A. Leak progressivo** | Memória cresce em 5.6 com `RequestCount` estável em 3.4; pods antigos consomem mais que os novos; dependências saudáveis em 6.2 e 6.4 |
| **B. Pico de tráfego** | `RequestCount` em 3.4 subiu 30% ou mais; memória alta em todos os pods de forma parecida; dependências saudáveis |
| **C. Degradação de dependência** | Latência do Ledger alta em 6.2 **ou** fila/idade do Reactor crescendo em 6.4 e 6.5, com timeouts nos logs de 5.2 |
| **D. Regressão de deploy** | Deploy há menos de 2h no Passo 4 e memória só cresce nos pods da revisão nova |

**Bifurcação:**
- **A. Leak** → **Passo 8** (restart controlado).
- **B. Pico** → **Passo 7** (adicionar capacidade).
- **C. Dependência** → **não reinicie o Chronos**. **Passo 11, gatilho E3**: o dono da dependência precisa entrar. Registre no canal com os números de 6.2/6.4/6.5.
- **D. Regressão** → **Passo 9** (rollback).
- **Nenhum cenário se encaixa com evidência clara** → **Passo 11, gatilho E4**. Não escolha uma mitigação por eliminação em serviço tier-0.

---

#### Passo 7 — Mitigação 1, menos invasiva: adicionar capacidade (3 minutos)

**Objetivo:** diluir o consumo entre mais réplicas quando a causa é volume de tráfego.

> **Impacto e risco:** este é o caminho mais seguro para o tráfego, mas **não é gratuito**. Cada réplica nova abre conexões novas no Ledger. Se o Passo 6.2 mostrou `DatabaseConnections` perto do limite, subir réplicas **pode derrubar o banco** e transformar um incidente de memória em indisponibilidade total. Verifique 6.2 antes de executar. Se as conexões estiverem acima de 80% do máximo, **não execute este passo**: vá para o Passo 11, gatilho E3.

Antes de mudar, veja o estado do HPA:

```bash
kubectl get hpa -n "$NS" | tee "$EVID/28-hpa.txt"
export HPA=$(kubectl get hpa -n "$NS" -o jsonpath='{.items[?(@.spec.scaleTargetRef.name=="chronos-api")].metadata.name}')
echo "HPA do Chronos: $HPA"
kubectl describe hpa -n "$NS" "$HPA" | tee "$EVID/29-hpa-describe.txt"
```

**O que observar:** `MINPODS`, `MAXPODS`, `REPLICAS` e a coluna de targets. O esperado é min 4, max 12, CPU 70%. Se `REPLICAS` já está em **12**, o HPA está no teto e este passo não tem efeito: vá direto para o **Passo 11, gatilho E1**.

**Caminho A — Argo CD com sync automático e self-heal (o que você viu no Passo 4.1):**

Alterar o HPA por kubectl será revertido. Suspenda o self-heal, aplique, e **registre para religar depois**:

```bash
# desliga a auto-sincronização temporariamente
argocd app set "$APP" --sync-policy none
echo "$(date -u +%H:%M:%SZ) auto-sync DESLIGADO - RELIGAR NO PASSO 12" | tee -a "$EVID/timeline.txt"

kubectl patch hpa -n "$NS" "$HPA" --type=merge -p '{"spec":{"minReplicas":9}}'
```

**Caminho B — sync manual ou sem política:**

```bash
kubectl patch hpa -n "$NS" "$HPA" --type=merge -p '{"spec":{"minReplicas":9}}'
```

Acompanhe por até 3 minutos:

```bash
kubectl get pods -n "$NS" -l app="$APP" -w
# Ctrl+C quando houver 9 pods Running e Ready
kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r
```

**O que observar:** os pods novos devem ficar `Ready` e a memória dos pods antigos deve **parar de subir** conforme o tráfego se distribui.

**Verificação:** 3 minutos após os pods novos ficarem `Ready`, nenhum pod acima de 85% do limit e nenhum OOMKill novo.

**Bifurcação:**
- **Memória caiu abaixo de 85% em todos os pods** → **Passo 10** (registrar) e **Passo 12** (encerrar).
- **Memória continua subindo mesmo com 9 réplicas** → não é capacidade, é leak. → **Passo 8**.
- **Pods novos não ficam `Ready` em 3 minutos**, ou o Ledger degradou depois do scale-out → **Passo 11, gatilho E1**.

---

#### Passo 8 — Mitigação 2: restart controlado em ondas (4 minutos)

**Objetivo:** zerar a memória dos pods afetados sem derrubar o serviço, comprando tempo até a correção real do leak.

> **Impacto e risco:** aqui você **mexe em tráfego de produção**. Um `rollout restart` recria todos os pods; se as probes de readiness estiverem mal configuradas ou o processo demorar a subir, você perde capacidade no meio de um incidente. O risco menor é matar **um** pod primeiro e observar. Nunca comece pelo restart de todos.
>
> **Antes de executar, confirme as duas condições:**
> 1. `kubectl get endpoints -n production chronos-api` mostra **pelo menos 4 endereços prontos** (perder 1 ainda deixa 3 servindo enquanto o novo sobe).
> 2. Você já executou o Passo 5. Depois do restart a evidência do processo atual desaparece para sempre.

**8.1 — Matar apenas o pior pod e observar (menos invasivo):**

```bash
kubectl get endpoints -n "$NS" "$APP" -o wide   # confirme >= 4 endereços prontos
export POD_PIOR=$(kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r | head -1 | awk '{print $1}')
echo "Vai deletar: $POD_PIOR" && sleep 2
kubectl delete pod -n "$NS" "$POD_PIOR"
echo "$(date -u +%H:%M:%SZ) deletado pod $POD_PIOR" | tee -a "$EVID/timeline.txt"

kubectl get pods -n "$NS" -l app="$APP" -w
# Ctrl+C quando o pod substituto estiver Running e Ready
kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r
```

**O que observar:** o pod substituto deve nascer com memória baixa, na ordem do `MEM_REQ`, e ficar `Ready` em menos de 2 minutos. Os demais pods não devem piorar.

**Verificação:** pod novo `Ready`, consumo dele abaixo de 50% do limit, e o total de endereços prontos voltou ao valor anterior.

**Bifurcação:**
- **Pod novo subiu saudável e a memória agregada caiu** → repita 8.1 para o próximo pod acima de 85%, **um por vez**, esperando `Ready` entre cada um. Quando nenhum pod estiver acima de 85% → **Passo 10** e **Passo 12**.
- **Pod novo também chega a 85% em menos de 10 minutos** → o leak é rápido ou o problema não é o pod. → **Passo 11, gatilho E4**.
- **Pod substituto não fica `Ready` em 2 minutos** → pare imediatamente, não delete mais nenhum pod. → **Passo 11, gatilho E1**.

**8.2 — Restart completo em rolling (mais invasivo, só se 8.1 resolveu parcialmente e há mais de 3 pods afetados):**

```bash
# Rolling restart respeita maxUnavailable do Deployment; ainda assim recria TODOS os pods.
kubectl rollout restart -n "$NS" "deployment/$DEPLOY"
kubectl rollout status -n "$NS" "deployment/$DEPLOY" --timeout=5m
```

**Verificação:** `rollout status` termina com sucesso dentro de 5 minutos e nenhum pod acima de 85%.

**Bifurcação:**
- **Sucesso** → **Passo 10** e **Passo 12**.
- **`rollout status` estoura o timeout de 5 minutos** → **Passo 11, gatilho E1**, e considere `kubectl rollout undo` apenas sob orientação do @chronos-core.

---

#### Passo 9 — Mitigação 3: rollback via Argo CD (4 minutos)

**Objetivo:** voltar para a última revisão saudável quando a evidência aponta regressão de deploy.

> **Impacto e risco:** rollback troca a versão em execução do serviço que recebe **todo** o tráfego da empresa. Se a versão nova já gravou dados em formato novo, ou se houve migração de schema no Ledger, voltar a versão pode causar erro pior que o consumo de memória. **Antes de executar, verifique se o changelog do deploy contém migração de banco.** Se contiver, ou se você não conseguir determinar isso, **não faça rollback sozinho**: Passo 11, gatilho E3.

```bash
# 9.1 — identificar as revisões e a data de cada uma
argocd app history "$APP" | tail -10

# 9.2 — ver exatamente o que mudou entre o que roda e o Git
argocd app diff "$APP"

# 9.3 — confirmar a imagem atual, para poder comparar depois
kubectl get deployment -n "$NS" "$DEPLOY" -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

**O que observar:** em 9.1, o `ID` da última revisão **anterior** ao início do problema, com sua data. Anote esse ID; é o único parâmetro do rollback. Em 9.2, procure mudanças em `resources.limits.memory`, variáveis de ambiente e tag de imagem.

Execute o rollback (substitua `<ID>` pelo ID anotado em 9.1):

```bash
echo "$(date -u +%H:%M:%SZ) iniciando rollback para revisao <ID>" | tee -a "$EVID/timeline.txt"
argocd app rollback "$APP" <ID>
argocd app wait "$APP" --health --timeout 300
kubectl rollout status -n "$NS" "deployment/$DEPLOY" --timeout=5m
```

**Verificação:** `argocd app wait` retorna `Healthy`, a imagem em 9.3 mudou para a da revisão anterior, e 5 minutos depois nenhum pod está acima de 85% do limit.

```bash
kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r
kubectl get pods -n "$NS" -l app="$APP" \
  -o custom-columns='POD:.metadata.name,RESTARTS:.status.containerStatuses[0].restartCount,MOTIVO:.status.containerStatuses[0].lastState.terminated.reason'
```

**Bifurcação:**
- **Memória normalizou depois do rollback** → confirmada a regressão. → **Passo 10**, **Passo 12**, e abra o follow-up bloqueando o redeploy da revisão ruim.
- **Memória continua alta com a versão antiga** → não era o deploy. → **Passo 11, gatilho E4**.
- **`argocd app wait` falha ou estoura 300s** → **Passo 11, gatilho E1**, imediato.

---

#### Passo 10 — Registrar no canal o que foi feito (1 minuto)

**Objetivo:** deixar o rastro que o próximo plantonista e o postmortem vão usar.

Poste em **#oncall-chronos**:

```text
:white_check_mark: Mitigado — High memory usage on Chronos API pods
T0: <horário> | Mitigado em: <horário> | Duração: <minutos>
Cenário identificado: <A leak / B pico / C dependência / D regressão>
Evidência que sustenta: <número concreto: ex. memória +4%/min com RequestCount estável>
Ação executada: <passo 7 / 8.1 / 8.2 / 9, com o comando>
Impacto ao usuário: <5xx observados, p99, pods fora de rotação>
Evidências salvas em: <caminho de $EVID> (anexar ao ticket)
Pendências: <ex. auto-sync do Argo CD ainda desligado / minReplicas em 9>
Próxima verificação: T+30min para encerramento
```

**Cadência de atualização durante todo o atendimento, sem exceção:**

| Momento | O que postar |
|---|---|
| T0 | ACK do Passo 1 |
| T0+5min | Resultado da triagem: quantos pods afetados, impacto medido |
| T0+10min | Ação escolhida e por quê, ou escalação |
| A cada 10min depois | Status, mesmo que seja "sem mudança" |
| Ao mitigar | Este bloco do Passo 10 |
| Ao encerrar | Bloco do Passo 12 |

**Verificação:** a mensagem está no canal e cita o caminho de `$EVID`.

**Bifurcação:** sempre siga para o **Passo 12**.

---

#### Passo 11 — Escalação para @chronos-core: gatilhos objetivos

**Objetivo:** eliminar o julgamento subjetivo sobre "quando chamar alguém". Se qualquer gatilho abaixo for verdadeiro, escale. Não pondere, não espere melhorar.

| Gatilho | Condição objetiva | Quando |
|---|---|---|
| **E1** | 3 ou mais pods acima de 85% do limit, **ou** qualquer OOMKill, **ou** HPA já em 12 réplicas, **ou** pod substituto não fica `Ready` em 2 min, **ou** `rollout`/`argocd wait` estoura o timeout | Imediato, em paralelo com a investigação |
| **E2** | 5xx acima de 5% do `RequestCount`, **ou** p99 acima de 3x a primeira janela, **ou** menos de 4 pods `ready` | Imediato |
| **E3** | Causa está fora do Chronos (Ledger ou Reactor degradados), **ou** o rollback envolve migração de banco, **ou** `DatabaseConnections` acima de 80% do máximo | Imediato: você não deve agir sozinho fora do seu escopo |
| **E4** | Nenhum cenário do Passo 6 se encaixa com evidência, **ou** a mitigação executada não resolveu | Imediato |
| **E5** | Você não tem acesso a `kubectl`, `aws` ou `argocd`, ou falta permissão para o comando necessário | Imediato |
| **E6 (relógio)** | Nada acima é verdadeiro, mas o alerta **não foi mitigado** dentro do prazo: **10 minutos** desde T0 em horário comercial, **15 minutos** fora dele | Ao vencer o prazo, sem discussão |

> O prazo do E6 é menor que o SLA de resposta do @chronos-core (15 min em horário comercial, 30 min fora dele) de propósito: você aciona antes para que a resposta chegue dentro do SLA, não depois.

**Como escalar.** Poste em **#oncall-chronos** marcando **@chronos-core**:

```text
:rotating_light: ESCALANDO @chronos-core — High memory usage on Chronos API pods
Gatilho: <E1..E6> — <condição exata que disparou, com o número>
T0: <horário> | Agora: <horário> | Decorrido: <minutos>
Estado atual: <X de 6 pods acima de 85%>, <OOMKills: N>, <réplicas: N>, <HPA: min/max/atual>
Impacto ao usuário: <5xx %>, <p99>, <pods ready / total>
Cenário suspeito: <A/B/C/D ou "indeterminado">
Já executei: <lista de passos>
Evidências: <caminho de $EVID>
Não executei ainda: <ex. rollback, porque pode envolver migração de banco>
SLA de resposta esperado: <15min horário comercial / 30min fora>
```

**Verificação:** a mensagem foi postada **com a menção @chronos-core** e cita o gatilho pelo código.

**Bifurcação:**
- **Alguém do @chronos-core respondeu** → continue executando sob orientação, mantendo a cadência de atualização do Passo 10.
- **Sem resposta ao fim do SLA** (15 min comercial, 30 min fora) → acione o canal de escalação secundária da empresa e registre no mesmo thread que o SLA venceu. Não fique esperando em silêncio.

---

#### Passo 12 — Encerrar o incidente: critério objetivo (30 minutos de observação)

**Objetivo:** garantir que "resolvido" significa estável e medido, não "parou de alertar".

```bash
# Rode este bloco 3 vezes, com 10 minutos de intervalo (T+10, T+20, T+30)
date -u +"=== Verificação %H:%M:%SZ ==="
kubectl top pods -n "$NS" -l app="$APP" --no-headers | sort -k3 -h -r
kubectl get pods -n "$NS" -l app="$APP" \
  -o custom-columns='POD:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,MOTIVO:.status.containerStatuses[0].lastState.terminated.reason'
kubectl get hpa -n "$NS" "$HPA"
kubectl get endpoints -n "$NS" "$APP" -o wide
```

**Critérios de encerramento — todos precisam ser verdadeiros nas 3 verificações:**

| Critério | Valor exigido |
|---|---|
| Memória de todos os pods | Abaixo de **70%** do limit (não 85%: você precisa de margem) |
| OOMKill / novos restarts | **Zero** durante os 30 minutos |
| Pods `ready` | **Todos** os do `spec.replicas` atual |
| HPA | Fora do teto de 12 réplicas |
| Erros 5xx (repita 3.3) | De volta ao valor da primeira janela do Passo 3 |
| p99 (repita 3.5) | Até 20% acima do valor da primeira janela do Passo 3 |

**Reverter o que foi mexido temporariamente — obrigatório antes de encerrar:**

```bash
# Se você desligou o auto-sync no Passo 7, RELIGUE
argocd app get "$APP" | grep -i "sync policy"
argocd app set "$APP" --sync-policy automated --self-heal
argocd app get "$APP" | grep -i "sync policy"   # confirme que voltou

# Se você subiu minReplicas, decida: manter (e levar ao Git) ou voltar ao valor original
kubectl get hpa -n "$NS" "$HPA"
```

> **Atenção:** se você subiu `minReplicas` por kubectl e religou o self-heal, o Argo CD vai voltar ao valor do Git e a capacidade extra desaparece. Escolha uma das duas: abrir PR no `hvt/chronos-api` com o novo valor, ou baixar `minReplicas` de volta de forma consciente. **Deixar as duas coisas no ar é como o próximo incidente começa.**

**Poste o encerramento em #oncall-chronos:**

```text
:checkered_flag: Encerrado — High memory usage on Chronos API pods
Duração total: <T0 até agora>
Causa raiz (ou hipótese): <cenário + evidência>
Mitigação aplicada: <ação>
Estado final: memória máx <X>% do limit, 0 restarts em 30min, <N> pods ready, 5xx em <valor>
Alterações temporárias revertidas: auto-sync <sim>, minReplicas <valor final>
Follow-ups abertos: <IDs dos tickets>
Evidências: <caminho de $EVID>
```

**Verificação:** os 6 critérios da tabela foram verdadeiros nas 3 verificações, o auto-sync está no estado original e existe pelo menos **um** ticket de follow-up aberto.

**Bifurcação:**
- **Todos os critérios verdadeiros** → incidente encerrado. Anexe `$EVID` ao ticket.
- **Qualquer critério falhou em qualquer uma das 3 verificações** → o incidente **não** está encerrado. Volte ao **Passo 6** para reclassificar e, se já passou do prazo do E6, **Passo 11**.

---

#### Ações de prevenção — para o alerta parar de acontecer 4x por semana

O runbook acima reduz o tempo de atendimento, mas trata sintoma. Os itens abaixo são o follow-up a levar ao time, em ordem de impacto sobre a recorrência:

1. **Encontrar o leak, não conviver com ele.** Se o Passo 5.5 retornou 404, a primeira tarefa é expor `pprof` (ou o equivalente do runtime) em produção com acesso restrito. Sem perfil de heap, todo atendimento vira restart às cegas.
2. **HPA não escala por memória.** O alerta é de memória e o HPA olha só CPU a 70%. Adicionar métrica de memória ao HPA elimina a classe inteira de incidentes de "pico legítimo" (cenário B), que hoje exige intervenção manual.
3. **`requests` igual a `limits` para memória.** Isso move o pod para QoS `Guaranteed` e evita que o gateway seja a primeira vítima quando o nó fica sob pressão.
4. **Alerta de aviso em 70%, com janela de tendência.** Um único alerta em 85% avisa tarde e sem contexto. Um aviso em 70% mais um alerta de *taxa de crescimento* permitem agir antes do OOMKill e separam leak de pico automaticamente.
5. **Dump de heap automático no OOM.** Configurar o processo para escrever o dump em volume e um `preStop` que envie para o S3. Hoje a evidência mais valiosa morre junto com o container.
6. **Limitar o pool de conexões ao Ledger por réplica.** Enquanto o scale-out puder esgotar as conexões do RDS, a mitigação mais segura do runbook (Passo 7) continuará carregando risco de derrubar o banco.
7. **Timeout e circuit breaker na publicação para o Reactor.** O cenário C existe porque requisições ficam presas em memória esperando dependência. Com timeout curto e circuit breaker, o Chronos degrada em vez de acumular.
8. **Revisar o limit com dado real.** Medir o working set em p99 nos últimos 30 dias e dimensionar a partir disso. É possível que 85% do limit atual seja simplesmente o consumo normal do serviço, e nesse caso o alerta está errado, não a aplicação.
9. **Registrar `minReplicas` no Git.** Se o plantão precisa subir réplicas 4 vezes por semana, o valor no `hvt/chronos-api` está defasado.
10. **Testar este runbook em game day.** Um runbook que nunca foi executado fora de incidente ainda não é confiável. Rodar em simulação valida os comandos e mede o tempo real de atendimento.

---

## Justificativa

**Role:** o Role foi escrito com dois lados, e ambos mudaram o resultado: o modelo assume o papel de SRE líder que escreve o procedimento, e o **leitor** é definido como o plantonista às 3h da manhã, sem conhecimento do Chronos e sem ninguém para consultar. É esse leitor que explica por que o runbook começa fixando variáveis de shell no Passo 0, por que nenhum comando aparece com `<pod-name>` sem antes ter o comando que descobre o valor, e por que as duas armadilhas do ambiente (HPA que escala por CPU e não por memória; Argo CD que reverte alteração manual) estão no topo como "regra de ouro" em vez de enterradas no meio do texto.

**Input:** o Input entregou o ambiente fechado (EKS, namespace `production`, 6 réplicas, HPA min 4/max 12/CPU 70%, Argo CD no repo `hvt/chronos-api`, Ledger em PostgreSQL, Reactor em SQS, `/metrics`, e apenas `kubectl`/`aws`/`argocd`), e é isso que permite comando pronto para colar em vez de instrução genérica. A restrição de ferramentas foi a mais produtiva: sem Prometheus na mão, a medição de impacto do usuário precisou sair de `aws cloudwatch` sobre o ALB, com fallback via `port-forward` no `/metrics` para o caso de não existir ALB, e a checagem de dependências virou `aws rds` e `aws sqs` em vez de "verifique o dashboard".

**Steps:** a estrutura de 5 partes por passo (título com objetivo, comandos, o que observar, verificação, bifurcação) é o que transforma o documento em algo executável sob estresse. O Steps também definiu a ordem que evita o erro mais comum nesse alerta: medir impacto no usuário (Passo 3) e classificar se o Chronos é vítima ou culpado (Passo 6) **antes** de qualquer mitigação, com as ações ordenadas da menos para a mais invasiva (capacidade → matar um pod → rolling restart → rollback) e cada uma com o risco declarado para um serviço que recebe todo o tráfego da empresa.

**Expectation:** a Expectation fixou o formato de entrada (bloco de resumo e tabela de decisão rápida para 3 cenários, antes dos passos), o objetivo operacional (sair de 30-40 minutos para algo previsível, com prazos de escalação em 10/15 minutos que chegam antes do SLA de 15/30 do @chronos-core), a proibição de passo sem verificação e de escalação em aberto (resolvida com os 6 gatilhos objetivos E1 a E6, incluindo um gatilho de relógio), e a seção final de prevenção, que é o que ataca a recorrência de 4 vezes por semana em vez de só acelerar o atendimento.

**Ressalvas de honestidade do output:** três pontos que o runbook assume e que precisam ser conferidos no ambiente real antes de publicar: `kubectl top` depende de metrics-server instalado no cluster; o nome do Service e a existência do ALB foram tratados por descoberta, com fallback, justamente porque o enunciado não os fornece; e o endpoint `/debug/pprof/heap` do Passo 5.5 tem verificação de status HTTP antes do uso porque pode simplesmente não existir. Nenhum valor de `limit` foi inventado: o runbook obriga o plantonista a ler `MEM_LIM` da saída e calcular o percentual, porque o enunciado não informa esse número.
