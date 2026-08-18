# Desafio 1 — Frameworks de Prompt Engineering aplicados a Cloud, DevOps e SRE

Desafio prático da pós-graduação **AIOps e IA na Engenharia de Cloud**, no capítulo de Engenharia de Prompt e Contexto.

A proposta: usar um cenário fictício de empresa de tecnologia para aplicar **5 frameworks de prompt engineering** em 8 situações realistas de Cloud, DevOps e SRE. O objeto de estudo não é a resposta da IA, é **o prompt**: em 7 questões o framework vem definido pelo enunciado, e na 8ª a escolha do framework é livre e precisa ser justificada contra alternativas.

Cada questão é uma tarefa que um engenheiro de plataforma faria num dia normal de trabalho: containerizar um serviço, automatizar backup de banco, analisar fatura de cloud, escrever SQL para uma PM, modernizar manifest de Kubernetes, padronizar módulo Terraform, escrever runbook de plantão e conduzir postmortem de incidente em andamento.

> Todos os dados, sistemas e pessoas do cenário são fictícios. Nada aqui vem de ambiente real.

---

## O cenário: Hill Valley Tech

Empresa fictícia usada como contexto comum às 8 questões.

**Sistemas em produção**

| Sistema | O que é |
|---|---|
| **Chronos** | API gateway e plataforma core, ponto de entrada de todo o tráfego da empresa |
| **Ledger** | Data warehouse em PostgreSQL com histórico de transações e eventos |
| **Reactor** | Processamento assíncrono por filas de mensagens |
| **Beacon** | Observabilidade: métricas, logs e alertas de todo o ambiente |
| **Lift** | Produto em beta, fora do core principal |

**Pessoas e papéis** Cada questão chega por uma pessoa diferente, e isso muda o que o prompt precisa produzir.

Doc Brown (CTO), Jennifer Parker (PM), Lorraine Baines (lidera SRE e o plantão), George McFly (engenheiro sênior, autor do legado), Goldie Wilson (CEO, olha custo), Strickland (head de segurança e compliance).

---

## Os 5 frameworks

| Sigla | Componentes | Usado em |
|---|---|---|
| **R-T-F** | Role, Task, Format | Q01, Q02 |
| **T-A-G** | Task, Action, Goal | Q03, Q04 |
| **B-A-B** | Before, After, Bridge | Q05 |
| **C-A-R-E** | Context, Action, Result, Example | Q06 |
| **R-I-S-E** | Role, Input, Steps, Expectation | Q07 |
| escolha livre | um dos 5 acima, com justificativa comparativa | Q08 |

---

## O que cada arquivo contém

Os 4 campos são obrigatórios pelo enunciado do desafio:

1. **Prompt:** o texto exato usado, na íntegra.
2. **Modelo:** qual modelo rodou o prompt, com uma linha explicando por que ele foi escolhido para aquela tarefa.
3. **Output:** a resposta real do modelo.
4. **Justificativa:** como os componentes do framework aparecem no prompt. Onde o output saiu com defeito, o defeito está documentado com a evidência, em vez de escondido.

---

## As 8 questões

| # | Questão | Framework | Tarefa | Arquivo |
|---|---|---|---|---|
| 01 | Dockerfile para o Lift | R-T-F | Containerizar uma API Python/Flask para Kubernetes | [Questão 01.md](<Questão 01.md>) |
| 02 | Script de backup do Ledger | R-T-F | Rotina bash de backup PostgreSQL para S3, via cron | [Questão 02.md](<Questão 02.md>) |
| 03 | Redução de custo cloud | T-A-G | Relatório de economia sobre fatura AWS, meta de 15% | [Questão 03.md](<Questão 03.md>) |
| 04 | Relatório de transações | T-A-G | Query SQL de crescimento por categoria, 6 meses | [Questão 04.md](<Questão 04.md>) |
| 05 | Modernizar deployment legado | B-A-B | Manifest Kubernetes de 3 anos fora do padrão atual | [Questão 05.md](<Questão 05.md>) |
| 06 | Módulo Terraform S3 | C-A-R-E | Módulo reutilizável aderente ao padrão de compliance | [Questão 06.md](<Questão 06.md>) · [código](<Questão 06>) |
| 07 | Runbook de plantão | R-I-S-E | Procedimento para alerta que recorre 4x por semana | [Questão 07.md](<Questão 07.md>) |
| 08 | Postmortem de incidente | R-I-S-E (escolhido) | Decidir rollback ou scaling em 20 min, com incidente ativo | [Questão 08.md](<Questão 08.md>) |

---

### Questão 01 — Dockerfile para o Lift · R-T-F

O Lift vai sair de VMs e entrar no cluster Kubernetes. O código existe: API Python/Flask na porta 8080, dependências com versões fixadas, duas variáveis obrigatórias em runtime (`DATABASE_URL`, `API_KEY`), start com gunicorn e 4 workers. Falta o Dockerfile.

**O que era pedido:** um prompt R-T-F que produzisse o Dockerfile de produção seguindo boas práticas de imagem, multi-stage build, usuário não-root, base enxuta com tag fixa, cache eficiente de camadas, e que restringisse o **formato** da resposta a só o Dockerfile comentado, sem prosa em volta.

O `Format` é o componente interessante desta questão: é ele que transforma a resposta em artefato pronto para commit em vez de tutorial.

### Questão 02 — Script de backup do Ledger · R-T-F

O Ledger nunca teve backup automatizado. É uma dependência em aberto no radar da SRE, que quer resolver com uma rotina diária via cron.

**O que era pedido:** um prompt R-T-F que produzisse um script bash de produção com pipeline `pg_dump` → `gzip` → `aws s3 cp`, retenção de 30 dias no S3, log com timestamp, verificação de espaço em disco, proteção contra execução concorrente, exit code distinto por tipo de falha e senha lida de variável de ambiente, nunca do script.

O requisito que separa script amador de script de produção está aqui: **falha no meio do pipe não pode gerar backup incompleto tratado como sucesso.**

### Questão 03 — Relatório de redução de custo cloud · T-A-G

A CEO definiu meta de reduzir 15% do custo cloud no trimestre sem degradar SLA. O breakdown da fatura AWS do último mês veio em CSV com 12 linhas de serviço, cada uma com categoria, custo, uso médio e uma observação.

**O que era pedido:** um prompt T-A-G que produzisse um relatório de oportunidades priorizadas por impacto, cada uma com economia estimada em USD e em % da conta, esforço de implementação e riscos ou pré-requisitos, respondendo se a meta é atingível apenas com ações de baixo risco para SLA.

O `Goal` é o que faz o relatório responder à pergunta do CTO em vez de listar boas práticas de FinOps.

### Questão 04 — Relatório mensal de transações do Ledger · T-A-G

A PM está fechando uma apresentação para a CEO sobre crescimento de transações por categoria. Ela não escreve SQL, então a demanda caiu na fila da engenharia.

**O que era pedido:** um prompt T-A-G que produzisse a query PostgreSQL, com o DDL das tabelas fornecido no próprio prompt: filtrar só transações `completed`, recortar 6 meses, agrupar por mês e categoria, converter centavos em reais com tipo numérico exato e escrever o filtro de data de modo a permitir uso do índice.

O output desta questão saiu com três defeitos reais, todos documentados com a evidência da execução. É o caso que mostra que output plausível não é output correto.

### Questão 05 — Modernizar deployment legado · B-A-B

Numa revisão de produção, o CTO encontrou o manifest do Chronos escrito três anos antes: 1 réplica, imagem `:latest`, segredos em texto puro versionados no Git, sem probes, sem resources, sem securityContext. Ninguém mexeu desde então, e o Chronos recebe todo o tráfego da empresa.

**O que era pedido:** um prompt B-A-B que recebesse o manifest legado como entrada e produzisse a versão modernizada, mais os objetos auxiliares necessários, com cada mudança justificada contra o problema que resolve e uma ordem de migração que não derrubasse o serviço durante a transição.

É a questão em que o framework casa melhor com o problema: existe um estado atual conhecido, um estado desejado conhecido, e a dificuldade real é a **travessia** entre os dois.

### Questão 06 — Módulo Terraform no padrão interno · C-A-R-E

Segurança e compliance publicaram o padrão interno de IaC: tags obrigatórias, prefixo nos nomes, `description` e `type` em toda variável, e para S3 encryption, versioning, block public access e logging sempre ativos. O CTO pediu um módulo reutilizável de buckets S3 que todos os times vão consumir.

**O que era pedido:** um prompt C-A-R-E que produzisse o módulo completo arquivo por arquivo, seguro por padrão (compliance nunca como opt-in), no **mesmo estilo** de um módulo de VPC existente fornecido como snippet de referência.

O `Example` é o componente decisivo: sem ele o módulo sairia correto e fora do padrão visual da casa. O módulo gerado está versionado como código em [`Questão 06/`](<Questão 06>), não apenas transcrito no markdown.

### Questão 07 — Runbook para alerta recorrente · R-I-S-E

O Beacon dispara em média 4 vezes por semana o mesmo alerta crítico de memória alta nos pods do Chronos. Cada plantonista gasta de 30 a 40 minutos resolvendo, de forma diferente a cada vez, porque não existe procedimento documentado.

**O que era pedido:** um prompt R-I-S-E que produzisse o runbook procedural completo para quem está de plantão às 3h da manhã, não conhece a arquitetura e não tem ninguém para consultar: comandos exatos por passo, verificação objetiva ao fim de cada passo, mitigações ordenadas da menos para a mais invasiva, critérios numéricos de escalação e critério de encerramento do incidente.

O `Role` aqui tem dois lados que mudam o resultado: o papel do modelo e, principalmente, **quem é o leitor do runbook**.

### Questão 08 — Postmortem técnico de incidente em produção · framework à escolha

Incidente em andamento durante o pico de tráfego. O CTO está numa call e precisa, em 20 minutos, decidir entre duas opções mutuamente exclusivas: rollback do deploy que subiu ontem, ou scaling emergencial do banco e do pool de conexões. Os insumos são cinco fontes heterogêneas: changelog, série temporal, trecho de log, estado da fila e estado do cluster.

**O que era pedido:** escolher, entre os 5 frameworks, o que melhor se aplica; escrever o prompt; e **justificar a escolha comparando explicitamente com pelo menos 2 alternativas**, apontando o que se ganharia e o que se perderia em cada uma. Nesta questão a justificativa é o ponto central da avaliação, não o prompt.

Framework escolhido: R-I-S-E, comparado contra T-A-G, C-A-R-E, B-A-B e R-T-F. O argumento é que a escolha não é sobre qual framework é melhor em geral, é sobre qual tem um componente distinto para cada dificuldade **deste** cenário: cinco insumos heterogêneos pedem `Input`, a ordem "diagnostique antes de escolher" pede `Steps`, o rigor de marcar hipótese pede `Role`, e o formato de leitura sob pressão pede `Expectation`.

---

## Modelos usados

O enunciado exige pelo menos 2 providers diferentes ao longo das 8 questões. A distribuição seguiu critério técnico: modelo de raciocínio onde havia cadeia analítica, modelo de código onde havia artefato com formato rígido.

| Questão | Modelo | Provider |
|---|---|---|
| 01 | Gemini Pro (raciocínio estendido) | Google |
| 02 | Gemini Flash (raciocínio estendido) | Google |
| 03 | DeepSeek, modelo especialista com pensamento profundo | DeepSeek |
| 04 | GLM-5 | Zhipu AI |
| 05 | GPT-5.6 Sol Max | OpenAI |
| 06 | GPT-5.6 Terra Max | OpenAI |
| 07 | Claude Opus 5 Max | Anthropic |
| 08 | Claude Opus 5 Max | Anthropic |

Cinco providers no total.

---

## Verificações executadas sobre os outputs

O enunciado pede o output real e permite registrar output ruim, comentando o que seria feito diferente. Em vez de avaliar os resultados por leitura, cada artefato executável foi verificado de fato, e é isso que sustenta as ressalvas registradas nas justificativas:

| Questão | Verificação | Resultado |
|---|---|---|
| 03 | Aritmética do relatório recalculada | Fecha: total USD 210.100, meta USD 15% = USD 31.515, subtotais por categoria e acumulados corretos |
| 04 | Query executada em PostgreSQL 16 com o DDL do enunciado | **3 defeitos confirmados:** janela cobrindo 7 meses em vez de 6, volume sem as 2 casas decimais exigidas, e mês dependente do timezone da sessão |
| 05 | 4 manifests validados com `kubeconform` em modo estrito | 4 válidos, 0 inválidos. Ressalvas registradas são de projeto, não de sintaxe |
| 06 | `terraform fmt`, `init` e `validate` | Sucesso no módulo e no exemplo, com AWS provider v5 resolvido |
| 07 | Coerência do runbook checada por script | 13 passos, todos com critério de verificação e bifurcação; todas as referências entre passos e os 6 gatilhos de escalação resolvidos |
| 08 | Série temporal recalculada em goodput | Requisições bem-sucedidas por segundo caem 23,6% desde o pico enquanto o p99 sobe 2,6x: assinatura de colapso por saturação, não de queda de demanda |

---

## Estrutura

```
Desafio 1 - Frameworks de Prompt Engineering/
├── README.md              # este arquivo
├── Questão 01.md          # R-T-F   — Dockerfile
├── Questão 02.md          # R-T-F   — script de backup
├── Questão 03.md          # T-A-G   — relatório de custo
├── Questão 04.md          # T-A-G   — query SQL
├── Questão 05.md          # B-A-B   — manifest Kubernetes
├── Questão 06.md          # C-A-R-E — módulo Terraform
├── Questão 06/            # o módulo Terraform gerado, versionado como código
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── versions.tf
│   ├── README.md
│   └── examples/basic/main.tf
├── Questão 07.md          # R-I-S-E — runbook de plantão
└── Questão 08.md          # R-I-S-E escolhido — postmortem
```
