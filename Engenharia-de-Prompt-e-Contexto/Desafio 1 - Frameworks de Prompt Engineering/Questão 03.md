# Questão 03 — Relatório de redução de custos cloud

**Framework:** T-A-G (Task, Action, Goal)

---

## Prompt

````text
[TASK]
Gere um relatório técnico de oportunidades de redução de custo cloud da Hill Valley Tech, a partir do breakdown de custos AWS do último mês fornecido abaixo em CSV.

```csv
servico,categoria,custo_mensal_usd,uso_medio_pct,observacao
EC2 Reserved Instances,compute,42500,88,"RIs de 1 ano expirando em 3 meses"
EC2 On-Demand,compute,28300,34,"instancias de dev e homologacao ligadas 24/7"
EKS (nodes m5.2xlarge),compute,36900,47,"cluster de producao do Chronos, HPA raramente acima de 8 pods"
RDS PostgreSQL (Ledger),databases,31200,52,"db.r5.4xlarge Multi-AZ, on-demand, sem reserva"
ElastiCache Redis,databases,9800,21,"cluster dimensionado em 2024 e nunca revisado"
S3,storage,14600,100,"97% dos objetos em Standard, sem lifecycle policy"
EBS,storage,11200,39,"volumes gp2, cerca de 40% sem anexo a nenhuma instancia"
CloudWatch Logs,observability,13400,100,"retencao infinita, inclui logs de debug do Chronos"
CloudWatch Metrics,observability,5100,100,"metricas customizadas duplicadas com o Beacon"
Data Transfer Out,network,8700,100,"trafego cross-AZ entre Chronos e Ledger"
NAT Gateway,network,6300,12,"3 NAT Gateways, um por AZ, dois com trafego residual"
Lambda,compute,2100,100,"funcoes do Reactor, custo estavel e previsivel"
```

[ACTION]
Para produzir o relatório, execute a análise nesta ordem:

1. Calcule o custo total mensal a partir do CSV e mostre o valor usado como base de todos os percentuais.
2. Consolide o custo por categoria (compute, databases, storage, observability, network) e identifique onde o dinheiro está concentrado.
3. Cruze custo mensal com uso médio percentual e com a observação de cada linha para achar desperdício: recurso superprovisionado, recurso ocioso, recurso órfão, ausência de reserva/savings plan, ausência de política de retenção ou de lifecycle e arquitetura que gera tráfego pago desnecessário.
4. Transforme cada achado em uma oportunidade de economia com estimativa de economia mensal em USD, deixando explícita a premissa de cálculo de cada estimativa.
5. Ordene as oportunidades por impacto financeiro decrescente e calcule o total acumulado, indicando em que ponto da lista a meta é alcançada.
6. Para cada oportunidade, classifique o esforço de implementação como baixo, médio ou alto e liste os riscos e pré-requisitos, avaliando explicitamente se há risco de degradar SLA.
7. Separe as oportunidades que podem ser executadas sem risco de SLA das que exigem janela de manutenção, teste de carga ou aprovação prévia.
8. Não invente serviços, valores ou linhas que não estejam no CSV. Se algum dado necessário estiver faltando, declare a premissa adotada.

[GOAL]
O objetivo de negócio é reduzir 15% do custo cloud até o fim do próximo trimestre sem degradar SLA. A meta foi definida pela Goldie (CEO) e o relatório será usado pelo Doc Brown (CTO) para decidir o que o time executa primeiro.

O relatório precisa deixar claro, de forma verificável:

- O custo total atual e quanto representa a meta de 15% em USD.
- As oportunidades priorizadas por impacto, cada uma com economia estimada em USD e em % da conta total.
- O esforço de implementação de cada oportunidade (baixo, médio ou alto).
- Os riscos e pré-requisitos de cada oportunidade, com destaque para qualquer risco de impacto em SLA.
- Se a meta de 15% é atingível apenas com as oportunidades de risco baixo para SLA e, caso não seja, o que a mais precisaria entrar e sob quais condições.
- Um plano de execução sugerido em ondas, começando pelo que dá mais economia com menor risco.

Formato: relatório em Markdown, com resumo executivo de no máximo 5 linhas no topo, tabela de oportunidades priorizadas e uma seção por oportunidade com detalhamento técnico. Números sempre acompanhados da premissa de cálculo.
````

---

## Modelo

**DeepSeek — modelo especialista com pensamento profundo (DeepThink)**

Escolhido porque a questão é de raciocínio quantitativo em cadeia (somar, ratear por categoria, derivar economia com premissa explícita, acumular e comparar com a meta), onde um modelo de raciocínio profundo erra menos na aritmética e mantém a rastreabilidade de cada número. Também atende à exigência de usar mais de um provider ao longo do desafio.

---

## Output

### Relatório Técnico de Redução de Custo Cloud — Hill Valley Tech

#### Resumo executivo

- Custo mensal atual: USD 210.100; meta de 15%: USD 31.515.
- Maior concentração de custo: compute 52,3% e databases 19,5%.
- Foram priorizadas 10 oportunidades com economia potencial total de USD 72.614/mês.
- A meta é alcançada após a 2ª oportunidade por impacto e também é atingível só com oportunidades de baixo risco de SLA.
- Plano sugerido: começar por reservas, retenção, expurgo e schedule dev/homolog; depois ajustar produção com janela e teste de carga.

#### 1. Base de cálculo e meta

Custo total mensal calculado a partir do CSV: **USD 210.100**.
Meta de redução de 15%: **USD 31.515/mês**.
Custo alvo desejado: **USD 178.585/mês**.

##### 1.1 Consolidação por categoria

| Categoria | Custo mensal USD | % da conta |
|---|---:|---:|
| Compute | 109.800 | 52,3% |
| Databases | 41.000 | 19,5% |
| Storage | 25.800 | 12,3% |
| Observability | 18.500 | 8,8% |
| Network | 15.000 | 7,1% |
| **Total** | **210.100** | **100%** |

O dinheiro está concentrado principalmente em compute, puxado por EC2 Reserved, EC2 On-Demand e EKS.

#### 2. Oportunidades priorizadas por impacto financeiro

| # | Oportunidade | Economia estimada USD/mês | % da conta | Acumulado USD | Esforço | Risco de SLA |
|---|---|---:|---:|---:|---|---|
| 1 | EC2 On-Demand dev/homolog: desligar fora do horário | 18.200 | 8,7% | 18.200 | Médio | Baixo |
| 2 | EKS Chronos: right-size de nodes m5.2xlarge | 13.764 | 6,6% | 31.964 | Alto | Alto |
| 3 | RDS PostgreSQL: comprar RI/Savings Plans | 9.360 | 4,5% | 41.324 | Baixo | Baixo |
| 4 | CloudWatch Logs: retenção 30 dias e cortar debug | 6.700 | 3,2% | 48.024 | Baixo | Baixo* |
| 5 | ElastiCache Redis: right-size do cluster | 6.370 | 3,0% | 54.394 | Médio | Médio |
| 6 | EBS: excluir volumes órfãos | 4.480 | 2,1% | 58.874 | Baixo | Baixo |
| 7 | S3: lifecycle policy Standard → IA/Glacier | 4.380 | 2,1% | 63.254 | Baixo | Baixo |
| 8 | NAT Gateway: consolidar 3 NATs em 1 | 4.200 | 2,0% | 67.454 | Médio | Médio |
| 9 | Data Transfer Out: reduzir cross-AZ Chronos↔Ledger | 2.610 | 1,2% | 70.064 | Alto | Médio/Alto |
| 10 | CloudWatch Metrics: deduplicar métricas Beacon | 2.550 | 1,2% | 72.614 | Baixo | Baixo |

\* CloudWatch Logs é classificado como risco baixo para SLA de produção, desde que logs de auditoria/compliance sejam preservados.

**Meta de 15%:** a meta é alcançada após a 2ª oportunidade, com acumulado de USD 31.964, ou seja, 15,2% da conta total.

#### 3. Detalhamento técnico por oportunidade

##### 3.1 EC2 On-Demand — Desligar dev/homolog fora do horário

**Economia estimada:** USD 18.200/mês

**Premissa de cálculo:**
USD 28.300 × 64,3% = USD 18.200.
Ambientes dev/homolog estão ligados 24/7. Adotar schedule de 12h×5 dias = 60h/semana; 60h/168h = 35,7% do tempo atual; economia de 64,3%.

**Esforço:** Médio

**Riscos e pré-requisitos:**

- Pode impactar times de desenvolvimento e homologação fora do horário comercial.
- Requer inventário, tags, automação de stop/start e start-on-demand.
- Não degrada SLA de produção.
- Instâncias que não puderem ser desligadas podem receber Savings Plans como alternativa.

**Risco de SLA:** Baixo.

##### 3.2 EKS — Right-size de nodes m5.2xlarge

**Economia estimada:** USD 13.764/mês

**Premissa de cálculo:**
USD 36.900 × 37,3% = USD 13.764.
Uso médio atual: 47%. Meta de utilização: 75%.
Capacidade necessária = 47% / 75% = 62,7% da atual.
Redução de capacidade = 37,3%.

**Esforço:** Alto

**Riscos e pré-requisitos:**

- Cluster de produção do Chronos; risco alto de degradação se picos de carga não forem absorvidos.
- Exige teste de carga, análise de pico, ajuste de HPA, rollout gradual.
- Pré-requisito: métricas de pico, node groups menores, cenário de rollback.

**Risco de SLA:** Alto. Exige janela de manutenção e teste de carga.

##### 3.3 RDS PostgreSQL — Reserva / Savings Plans

**Economia estimada:** USD 9.360/mês

**Premissa de cálculo:**
USD 31.200 × 30% = USD 9.360.
Instância on-demand sem reserva; desconto estimado de ~30% para RDS Reserved Instance de 1 ano, no-upfront ou partial.

**Esforço:** Baixo

**Riscos e pré-requisitos:**

- Compromisso financeiro de 1 ano.
- Sem alteração de infraestrutura; não degrada SLA.
- Observação: uso médio de 52% sugere possível right-size futuro, mas isso é de alto risco e não entra na meta conservadora.

**Risco de SLA:** Baixo.

##### 3.4 CloudWatch Logs — Retenção e corte de logs de debug

**Economia estimada:** USD 6.700/mês

**Premissa de cálculo:**
USD 13.400 × 50% = USD 6.700.
Retenção infinita e logs de debug do Chronos. Aplicar retenção de 30 dias para logs não-auditados e desativar debug.

**Esforço:** Baixo

**Riscos e pré-requisitos:**

- Reduz capacidade de diagnóstico se forem removidos logs de erro/auditoria.
- Preservar logs de compliance e de erro.
- Não afeta diretamente SLA de produção.

**Risco de SLA:** Baixo, com atenção a compliance.

##### 3.5 ElastiCache Redis — Right-size do cluster

**Economia estimada:** USD 6.370/mês

**Premissa de cálculo:**
USD 9.800 × 65% = USD 6.370.
Uso médio atual: 21%. Meta de utilização: ~60%.
Capacidade necessária = 21% / 60% = 35% da atual; economia de 65%.

**Esforço:** Médio

**Riscos e pré-requisitos:**

- Cache de produção; redução excessiva pode causar evictions e aumento de latência.
- Exige teste com workload real, monitoramento de memória e rollback.

**Risco de SLA:** Médio. Exige janela e teste.

##### 3.6 EBS — Excluir volumes órfãos

**Economia estimada:** USD 4.480/mês

**Premissa de cálculo:**
USD 11.200 × 40% = USD 4.480.
Cerca de 40% dos volumes gp2 estão sem anexo a nenhuma instância.

**Esforço:** Baixo

**Riscos e pré-requisitos:**

- Risco de excluir volume errado; mitigar com snapshot prévio e verificação de IDs.
- Volumes sem anexo não afetam SLA.

**Risco de SLA:** Baixo.

##### 3.7 S3 — Lifecycle policy

**Economia estimada:** USD 4.380/mês

**Premissa de cálculo:**
USD 14.600 × 30% = USD 4.380.
97% dos objetos em Standard. Estima-se que 60% dos objetos possam ir para S3 IA/Glacier; custo médio de 50% sobre essa parcela.
Economia = 60% × 50% = 30%.

**Esforço:** Baixo

**Riscos e pré-requisitos:**

- Custos de recuperação e latência se dados forem acessados com frequência.
- Usar S3 Inventory e regras por prefixo/idade.

**Risco de SLA:** Baixo.

##### 3.8 NAT Gateway — Consolidar NATs

**Economia estimada:** USD 4.200/mês

**Premissa de cálculo:**
USD 6.300 × 2/3 = USD 4.200.
Existem 3 NAT Gateways; dois com tráfego residual. Remover 2, mantendo 1.

**Esforço:** Médio

**Riscos e pré-requisitos:**

- Pode afetar alta disponibilidade de egress da rede.
- Validar rotas, AZs e failover antes de remover.
- Exige janela de manutenção.

**Risco de SLA:** Médio.

##### 3.9 Data Transfer Out — Reduzir tráfego cross-AZ

**Economia estimada:** USD 2.610/mês

**Premissa de cálculo:**
USD 8.700 × 30% = USD 2.610.
Tráfego cross-AZ entre Chronos e Ledger pode ser reduzido com colocalização, afinidade de zona ou endpoints privados.

**Esforço:** Alto

**Riscos e pré-requisitos:**

- Mudança arquitetural em produção.
- Pode afetar latência e disponibilidade.
- Exige mapeamento de dependências, aprovação prévia e janela.

**Risco de SLA:** Médio/Alto.

##### 3.10 CloudWatch Metrics — Deduplicar métricas do Beacon

**Economia estimada:** USD 2.550/mês

**Premissa de cálculo:**
USD 5.100 × 50% = USD 2.550.
Métricas customizadas duplicadas com o Beacon; eliminar 50% das métricas redundantes.

**Esforço:** Baixo

**Riscos e pré-requisitos:**

- Validar dashboards e alarmes antes de remover.
- Garantir que o Beacon seja fonte confiável.

**Risco de SLA:** Baixo.

#### 4. Meta de 15% e risco de SLA

A meta de redução é USD 31.515/mês.

**Oportunidades de baixo risco de SLA**

| # | Oportunidade | Economia USD/mês |
|---|---|---:|
| 1 | EC2 On-Demand dev/homolog: desligar fora do horário | 18.200 |
| 3 | RDS PostgreSQL: comprar RI/Savings Plans | 9.360 |
| 4 | CloudWatch Logs: retenção 30 dias e cortar debug | 6.700 |
| 6 | EBS: excluir volumes órfãos | 4.480 |
| 7 | S3: lifecycle policy | 4.380 |
| 10 | CloudWatch Metrics: deduplicar métricas Beacon | 2.550 |
| **Total** | **Baixo risco de SLA** | **45.670** |

Sim, a meta de 15% é atingível apenas com oportunidades de risco baixo para SLA.
Se excluirmos CloudWatch Logs por questão de compliance, as demais oportunidades de baixo risco somam USD 38.970, ainda acima da meta de USD 31.515.

**Oportunidades que exigem janela, teste de carga ou aprovação prévia**

| # | Oportunidade | Risco de SLA | Condição |
|---|---|---|---|
| 2 | EKS right-size | Alto | Teste de carga, janela, aprovação |
| 5 | ElastiCache right-size | Médio | Teste de performance, janela |
| 8 | NAT Gateway consolidation | Médio | Validação de HA, janela |
| 9 | Data Transfer cross-AZ reduction | Médio/Alto | Aprovação de arquitetura, janela |

#### 5. Plano de execução sugerido em ondas

**Onda 1 — Semanas 0 a 2: ações de baixo risco e ganho imediato**

| # | Ação | Economia USD/mês |
|---|---|---:|
| 3 | RDS RI/Savings Plans | 9.360 |
| 4 | CloudWatch Logs retenção | 6.700 |
| 6 | EBS volumes órfãos | 4.480 |
| 7 | S3 lifecycle | 4.380 |
| 10 | CloudWatch Metrics dedup | 2.550 |
| **Subtotal Onda 1** | | **27.470** |

**Onda 2 — Semanas 2 a 6: schedule de dev/homolog**

| # | Ação | Economia USD/mês |
|---|---|---:|
| 1 | EC2 On-Demand desligar fora do horário | 18.200 |
| **Subtotal Onda 2** | | **18.200** |

Acumulado Onda 1 + Onda 2: USD 45.670 → já supera a meta de USD 31.515.

**Onda 3 — Semanas 6 a 12: mudanças em produção com teste e aprovação**

| # | Ação | Economia USD/mês |
|---|---|---:|
| 2 | EKS right-size | 13.764 |
| 5 | ElastiCache right-size | 6.370 |
| 8 | NAT consolidation | 4.200 |
| 9 | Data Transfer cross-AZ reduction | 2.610 |
| **Subtotal Onda 3** | | **26.944** |

Economia total potencial ao final das três ondas: **USD 72.614/mês**.

#### 6. Premissas e dados ausentes

- Não foram informados: quantidade exata de instâncias EC2, número de nodes EKS, volume e idade de objetos S3, distribuição de tráfego NAT por AZ, picos de carga de produção.
- As estimativas usam premissas declaradas em cada seção; valores reais devem ser validados antes da execução.
- EC2 Reserved Instances expirando em 3 meses é uma ação de proteção, não redução: renovar ou converter em Savings Plans evita aumento futuro.
- Lambda do Reactor está estável e previsível; nenhuma oportunidade de redução identificada.
- Não foram consideradas sobreposições entre EKS right-size e Data Transfer cross-AZ; sinergias adicionais podem existir, mas não foram contabilizadas.

---

## Justificativa

**Task:** o primeiro bloco define um entregável único e verificável (relatório técnico de oportunidades de economia) e entrega o insumo completo no próprio prompt, o CSV de 12 linhas com categoria, custo, uso médio e observação. Sem isso o modelo teria inventado serviços e valores, que é justamente o que o item 8 da Action proibiu.

**Action:** os 8 passos numerados ditaram o método de análise, não só o resultado: somar o total antes de qualquer percentual, consolidar por categoria, cruzar custo × uso × observação para caçar desperdício, converter cada achado em economia com premissa declarada, acumular por impacto e classificar esforço e risco. O output segue essa ordem seção por seção, e cada estimativa aparece com a conta que a gerou (ex.: 60h/168h = 35,7% para o schedule de dev/homolog).

**Goal:** a meta de negócio (15% até o fim do trimestre, sem degradar SLA, decisão do Doc Brown a partir de meta da Goldie) forçou o modelo a fechar as perguntas que importam para a decisão: quanto é 15% em USD (31.515), em que ponto da lista priorizada a meta é atingida, e se ela é alcançável só com itens de baixo risco de SLA. Foi o Goal que produziu a resposta mais útil do relatório: 45.670 em oportunidades de baixo risco, ou 38.970 se CloudWatch Logs for barrado por compliance, ambos acima da meta, o que permite bater os 15% sem tocar no EKS de produção.

**Observações de qualidade e o que eu faria diferente:** conferi a aritmética do output e ela fecha: total de 210.100, os cinco subtotais por categoria, os 10 acumulados, os 45.670 de baixo risco e os 72.614 do total. Duas correções de forma: o modelo emitiu quatro tabelas com linha separadora inválida (3 colunas no cabeçalho e 2 na separadora), que arrumei sem alterar número ou texto, e rebaixei os níveis de heading para o relatório aninhar neste arquivo. Num próximo passe eu pediria também que a tabela priorizada por impacto já trouxesse uma coluna sinalizando quais itens entram na meta "sem risco de SLA", porque hoje a leitura do topo sugere que a meta depende do right-size do EKS, e a seção 4 mostra que não depende.
