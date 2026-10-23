# Curadoria da skill `padrao-de-manifests-metacortex`

O que entrou na skill, o que ficou fora, e por quê. Cada decisão está amarrada a uma
medição ou a um erro que eu cometi, não a preferência.

Skill em `.kiro/skills/padrao-de-manifests-metacortex/`.

---

## 0. Como a skill foi produzida, e com qual ferramenta

| | |
|---|---|
| **Agente** | Kiro (IDE), sessão em modo Autopilot |
| **Modelo** | Claude Opus 5 |
| **Sub-agentes** | `introspect` para o formato de skill do Kiro; `general-task-execution` para os três testes cegos de validação |
| **Ferramentas determinísticas** | `trivy` 0.52.2, `kubectl` v1.33.13 contra k3d/k3s v1.31.5, `python3` 3.10 com PyYAML |

**O fluxo veio antes da skill, nesta ordem:**

1. Rodei o Trivy no manifesto barrado e numa sonda que viola as 19 regras de propósito,
   para medir a cobertura **antes** de escrever qualquer linha de script.
2. Conferi o manifesto barrado à mão, regra por regra, abrindo o repositório do kube-news
   para decidir as probes: está em `fluxos/fluxo-01-conferencia-manual.md`.
3. Gerei os manifests de dois projetos à mão, lendo o código de cada um: está em
   `fluxos/fluxo-02-geracao-de-manifests.md`.
4. **Só então** empacotei: o que nos dois fluxos foi comparação de string virou script, o
   que exigiu abrir o projeto virou instrução.
5. Validei com três sub-agentes que só podiam usar a skill, contra manifestos novos.

Os dois fluxos registram onde eu travei e onde eu errei, e é de lá que vêm as decisões de
corte. A skill não foi escrita de cabeça e depois ilustrada: ela é a destilação de dois
fluxos que produziram artefato real.

---

## 1. A pergunta que organiza tudo: quem é o juiz de cada regra

O ticket manda descobrir o que o Trivy já faz **antes** de escrever código. Fiz isso, e a
resposta mudou o desenho da skill duas vezes.

### Como o mapa foi levantado

Rodar `trivy config` no manifesto a revisar **não produz mapa de cobertura**: regra que o
Trivy tem e que aquele manifesto não viola não aparece na saída, e fica impossível
distinguir "não tem a regra" de "tem, mas não disparou".

Foram dois experimentos:

| Experimento | Regras FAIL |
|---|---|
| `trivy config` no manifesto barrado | **14** |
| `trivy config` num manifesto-sonda que viola as 19 de propósito | **20** |

A diferença fecha o mapa. Evidência em `evidencias/relatorios/06-trivy-saida-crua.txt`.

### Divisão final, regra por regra

| Regra | Nível na casa | Juiz | Linha do script ou instrução |
|---|---|---|---|
| 1.1 nome kebab-case | obrigatório | **script** | `regra_1_1_kebab` |
| 1.2 namespace `<cliente>-<ambiente>` | obrigatório | **script** | `regra_1_2_namespace` |
| 1.3 os quatro rótulos | obrigatório | **script** | `regra_1_3_rotulos` |
| 1.4 seletor casa com pod | obrigatório | **script** | `regra_1_4_seletor` |
| 1.5 anotação de dono | recomendado | **script** | `regra_1_5_dono` |
| 1.6 nome do container | recomendado | **script** | `regra_1_6_nome_container` |
| 2.1 requests e limits | obrigatório | **Trivy**, traduzido | `TRIVY_PARA_REGRA` → KSV011/015/016/018 |
| 2.2 probes | obrigatório | **script** (presença) + **instrução** (o que tocam) | `regra_2_2_probes` + passo 3 |
| 2.3 replicas >= 2 em prod | obrigatório em prod | **script** | `regra_2_3_replicas` |
| 2.4 estratégia | obrigatório em prod | **script** | `regra_2_4_estrategia` |
| 2.5 PodDisruptionBudget | recomendado | **script** | `regra_2_5_pdb` |
| 2.6 período de graça | recomendado | **só instrução** | passo 3 |
| 3.1 tag `:latest` | proibido | **Trivy**, traduzido | KSV013 |
| 3.2 securityContext | obrigatório | **script** (os 5 campos) + **instrução** (caminho do volume) | `regra_3_2_security_context` + passo 3 |
| 3.3 segredo em texto puro | proibido | **script** (URI e nome sensível) + **instrução** (nome inocente) | `regra_3_3_segredo` + passo 3 |
| 3.4 `automountServiceAccountToken` | obrigatório | **script** | `regra_3_4_automount` |
| 3.5 ServiceAccount dedicada | recomendado | **script** | `regra_3_5_serviceaccount` |
| 3.6 host*/privileged | proibido | **Trivy**, traduzido | KSV008/009/010/017 |
| 3.7 registry interno | obrigatório | **script** | `regra_3_7_registry` |

**Script 15, Trivy 3, só leitura 1.**

### O critério de corte

Entrou no script o que se decide **olhando só o YAML**: parsing, comparação de string,
presença de campo, igualdade entre dois campos. É onde leitura humana erra e script não
erra, e eu quase errei a 1.4 no fluxo 1, confundindo o seletor do Deployment com o do
Service.

Ficou como instrução o que exige **ler o código da aplicação**: o que cada endpoint toca,
se a aplicação trata SIGTERM, em que caminhos ela escreve. Nenhuma dessas respostas está
no manifesto, e script que finge decidir isso produz relatório confiante e errado.

---

## 2. O que o Trivy cobre, e por que eu não reimplementei

O enunciado proíbe reimplementar o que a ferramenta já faz. Respeitei em 2.1, 3.1 e 3.6:
o script **invoca** o Trivy, lê o JSON e traduz cada `KSV`. Não há uma linha de lógica
minha sobre `requests`, `:latest` ou `hostNetwork`.

Mas repassar a saída crua seria pior que não usar. Dois motivos medidos:

### A severidade do Trivy não é a obrigatoriedade da casa

| KSV | Severidade no Trivy | Regra da casa | Nível na casa |
|---|---|---|---|
| KSV015 requests de CPU | **LOW** | 2.1 | **obrigatório** |
| KSV016 requests de memória | **LOW** | 2.1 | **obrigatório** |
| KSV011 limite de CPU | **LOW** | 2.1 | **obrigatório** |
| KSV018 limite de memória | **LOW** | 2.1 | **obrigatório** |
| KSV013 tag `:latest` | MEDIUM | 3.1 | **proibido** |

Quem filtra por `--severity HIGH,CRITICAL` (prática comum) **perde a regra 2.1 inteira**.
Daí a tradução: o script reporta KSV015 como "2.1, obrigatório, barra o deploy".

### O Trivy tem regras que a casa não adota

`KSV021`, `KSV030`, `KSV104` e `KSV117` vão para um bloco informativo em vez de se
misturarem às violações. Relatório que mistura o padrão da casa com o padrão do Trivy faz
o revisor perder tempo consertando o que a casa não pede.

---

## 3. As três regras onde eu decidi contra a ferramenta, e a medição que sustenta

### 3.3: o Trivy produz aparência de cobertura

Esta é a regra que mais pesa: é `proibido`, e é a que vaza credencial de banco de produção.

Três mecanismos testados, nenhum resolve:

**`trivy fs --scanners secret`**: sonda com seis valores de formatos diferentes:

| Variável | Forma do valor | Detectado? |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `AKIA` + 16 caracteres | **sim**, CRITICAL |
| `AWS_SECRET_ACCESS_KEY` | 40 caracteres | **sim**, CRITICAL |
| `GITHUB_TOKEN` | `ghp_` + 36 caracteres | **sim**, CRITICAL |
| `SLACK_TOKEN` | `xoxb-` com três segmentos | **sim**, HIGH |
| `PRIVATE_KEY` | bloco `BEGIN RSA PRIVATE KEY` | **sim**, HIGH |
| `DATABASE_URL` | `postgres://nyx:s3nh4-do-banco@pg…:5432/nyx` | **NÃO** |

Os valores são sintéticos e a tabela descreve a forma em vez de reproduzi-la, porque o
push protection do GitHub casa com a forma: ver a seção 8.

Ele reconhece formato conhecido de credencial de terceiro. Senha arbitrária dentro de URI
não tem formato reconhecível.

**`AVD-KSV-01010`**: descoberto tarde, num manifesto de teste que não estava no
experimento original. O título é "ConfigMap with sensitive content", o que faz qualquer um
concluir que a 3.3 está coberta. Mesma senha em três lugares:

| Onde está a senha | `AVD-KSV-01010` | `--scanners secret` | script |
|---|---|---|---|
| `ConfigMap.data` | dispara | não | **sim** |
| `Secret.stringData` | **não** | não | **sim** |
| `Deployment` → `env.value` | **não** | não | **sim** |

E quando dispara, não é a senha que ele achou. A mensagem diz o que casou:
`'{"postgres"}'`: o esquema da URI. Noutro teste casou com `'{"CACHE_TTL", "mysql"}'`:
um tempo de expiração em segundos e o nome de um motor de banco. Dois falsos positivos e
um falso negativo num único achado. A localização aponta para a linha do separador `---`.

**O script** faz detecção de padrão de URI com credencial
(`esquema://usuario:senha@host`) mais nome de variável sensível com valor literal, nos três
lugares, com o campo exato no relatório.

### 3.2: o Trivy erra nas duas direções, então não pode ser o juiz

Esta foi a decisão mais difícil e a que mudei no meio do caminho. A primeira versão do
script delegava a 3.2 ao Trivy. Está errado, por dois motivos opostos:

- **Falso negativo:** ele confere os cinco requisitos por regras separadas, com
  severidades de LOW a HIGH, e não tem o conceito do "bloco inteiro" que a casa exige.
  Quem filtra por severidade alta vê só `KSV014` e perde quatro dos cinco.
- **Falso positivo:** `KSV020` olha só `containers[].securityContext` e ignora `runAsUser`
  declarado no **pod**, que o Kubernetes herda. Verificado com duas variantes do mesmo
  Deployment, as duas rodando com UID 10001:

  | Sonda | Onde está `runAsUser: 10001` | Resultado |
  |---|---|---|
  | `trivy-uid-a-nivel-pod.yaml` | `securityContext` do pod | **FAIL: KSV020, KSV021** |
  | `trivy-uid-b-nivel-container.yaml` | `securityContext` do container | nenhuma falha |

  E a cegueira é inconsistente dentro do próprio Trivy: na mesma execução, `KSV012`
  (`runAsNonRoot`) lê o nível do pod corretamente e não dispara.

Como a 3.2 é `obrigatório`, ela não pode ficar sem juiz. `regra_3_2_security_context`
julga o bloco com a herança, e os KSVs correspondentes passaram a ser **corroboração**.

Não é reimplementação por capricho: é cobrir uma lacuna medida, e o único lugar em que o
script julga por cima da ferramenta.

### 2.2: a presença das probes é parsing, e eu tinha deixado de fora

A primeira versão da skill mandava conferir as probes à mão por inteiro. Errado: a
**presença** dos dois campos é parsing puro, pelo mesmo critério que colocou 1.1 e 1.4 no
script. Só o julgamento de *o que cada endpoint toca* precisa de leitura.

Hoje o script confere:
- as duas probes existem: faltar uma **barra**
- as duas testam exatamente a mesma coisa: vira `recomendado`, porque o veredito depende
  do que o teste toca
- e não exige probe de `Job`, `CronJob` nem `initContainer`

Efeito mensurável: o manifesto barrado passou de **19 para 20 violações**. A 2.2 era uma
violação real que o script não pegava.

---

## 4. Corpo da skill x `references/` x script

Regra que usei: **o corpo é o procedimento, a reference é a consulta.**

| Conteúdo | Onde | Por quê |
|---|---|---|
| a ordem dos passos nos dois modos | **corpo** | é o que define o comportamento; precisa estar carregado sempre |
| comportamentos do script que afetam confiança no relatório | **corpo** | quem lê o relatório precisa saber que 2.3 só vale em prod |
| as 4 regras do passo 3 e o que descobrir | **corpo** | é instrução de execução |
| o que fazer com imagem de terceiro | **corpo** | a 3.7 torna esse caso comum, não exceção |
| formato do relatório e os três blocos | **corpo** | sem isso o relatório sai diferente a cada vez |
| texto das 19 regras com obrigatoriedade | `references/padrao-completo.md` | consulta pontual, para citar regra |
| tabela campo por campo da 3.2 | `references/padrao-completo.md` | detalhe denso, consultado quando a dúvida aparece |
| mapa de cobertura, severidades, falsos positivos | `references/cobertura-do-trivy.md` | argumento para quando alguém contesta o relatório |
| as 15 verificações mecânicas | `scripts/conferir_manifesto.py` | determinístico; instrução aqui seria desperdício e erraria |

Corpo do `SKILL.md` (sem o frontmatter): **249 linhas, ~3420 tokens**: dentro do limite
recomendado de 500 linhas / 5000 tokens, com as duas references somando mais 500 linhas
que só carregam quando o passo manda.

### O que eu tirei do corpo de propósito

- **Severidades do Trivy KSV por KSV**: foi para a reference. No corpo ficou só o
  princípio ("LOW no Trivy pode ser obrigatório na casa"), que é o que muda a ação.
- **As tabelas de experimento**: evidência, não procedimento. Quem executa a skill não
  precisa delas; quem contesta o relatório precisa.
- **O texto integral das 19 regras**: no corpo ficou o número, o nível e o critério de
  cada uma só nas quatro do passo 3.

---

## 5. A `description`: separar "antes do apply" de "cluster rodando"

O frontmatter é o único lugar contra o qual o Kiro faz matching, e esta skill vai conviver
com a de triagem de cluster do Ticket 02. Se as duas descriptions se sobrepõem, o
roteamento erra e o custo é alto nas duas direções: usar esta skill num pod em
`CrashLoopBackOff` produz análise de YAML para um problema de runtime.

A description declara as duas coisas:

- **quando usar**: revisar YAML antes do apply, escrever manifests, "isto passa na
  revisão?", investigar deploy barrado pelo Construct, preparar PR
- **quando NÃO usar**, por nome: `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`,
  Service sem endpoint em produção, qualquer coisa que exija `kubectl` contra cluster vivo

E fecha com o critério que generaliza além da lista: **o limite é a fonte da verdade**,
esta skill lê arquivo YAML e código-fonte, nunca o estado do cluster.

697 de 1024 caracteres. O `compatibility` declara a dependência real e o que se perde sem
o Trivy (2.1, 3.1 e 3.6 deixam de ser conferidas; a 3.2 não depende dele).

---

## 6. Validação: três testes cegos, e o que eles acharam

Escrever a skill e declarar que funciona não é evidência. Despachei **três sub-agentes**
que só podiam usar a skill, sem acesso aos fluxos manuais nem às sondas, com manifestos
que eles não tinham visto. Detalhe em `validacao/testes-cegos.md`.

| Teste | Manifesto | Atritos reportados | Defeitos reais |
|---|---|---|---|
| 1 | `vega-stg` (stg, Redis de terceiro) | 5 | 5 |
| 2 | `vega-stg`, depois das correções | 6 | 5 |
| 3 | `atlas-prod` (prod, 3.2 no nível errado) | 5 | 5 |

Os três reproduziram os vereditos corretos. O valor não estava nisso: estava nos
**quinze defeitos** que eles acharam na skill. Os cinco que mais custaram:

1. **A 3.2 não tinha juiz** e meus dois references se contradiziam sobre o nível dos
   campos. Virou `regra_3_2_security_context` + a tabela campo por campo.
2. **"Declarados no pod são silenciosamente ignorados" estava errado.** Testei contra o
   apiserver: `kubectl apply` strict **recusa** com `strict decoding error`;
   `--server-side` recusa; só `--validate=false` aceita e descarta. Afirmação factual
   minha, não verificada, corrigida com medição.
3. **A presença das probes é parsing** e estava fora do script (item 3 acima).
4. **`KSV021` cobra GID, e a 3.2 não tem requisito de `runAsGroup`.** Eu havia movido
   `KSV020` e `KSV021` juntos para o balde de corroboração; a correção valia para o
   `KSV020` e não para o par. Dois KSVs com números vizinhos não são a mesma regra.
5. **`maxUnavailable: "0%"` era marcado como violação.** A comparação era com `(0, "0")`
   e o campo aceita percentual. Bug real, e `maxSurge` não era conferido de forma alguma.

Um sexto atrito eu diagnostiquei errado, e vale registrar: o teste 3 apontou que a regra
2.4 premiava a opção pior, porque `maxUnavailable: 1` barrava e `Recreate` (que derruba a
capacidade inteira) só pedia justificativa. Classifiquei como tensão do padrão da casa,
fora do meu alcance. Não era: o padrão **não menciona `Recreate`**, e a flexibilização era
minha. Detalhe na seção 7.

---

## 7. O que NÃO foi empacotado, e por quê

### O Bloco 4 inteiro: vocabulário e conceitos

A decisão de corte mais volumosa: **oito itens, nenhum empacotado.** São 4.1 Pod,
4.2 ReplicaSet, 4.3 Deployment, 4.4 Service, 4.5 `port` x `targetPort`, 4.6 Endpoints,
4.7 ConfigMap e Secret, 4.8 Probes.

Três motivos, em ordem de peso:

1. **Nenhum item produz veredito.** A skill existe para dizer "isto barra" ou "isto passa".
   A definição de ReplicaSet não muda uma linha de relatório. O próprio padrão diz que o
   bloco existe "para quem está chegando na plataforma" e que "quem já opera os clusters
   pode pular direto para os blocos anteriores": é material de onboarding, e a skill não é
   onboarding.
2. **Custo de contexto sem retorno.** O corpo do `SKILL.md` carrega inteiro a cada
   ativação. Oito definições de objeto do Kubernetes gastariam orçamento em toda conferência
   para informar o que o agente já sabe.
3. **Público errado.** O bloco responde "o que é um Service"; a skill responde "este
   Service está conforme". Quem precisa do primeiro não está fazendo revisão de manifesto.

**Duas exceções, e elas entraram como conhecimento aplicado, não como texto:**

- **4.5** (`port` x `targetPort`) virou prática nos manifests gerados: o `targetPort`
  aponta para o **nome** da porta e não para o número, para o Service acompanhar se a porta
  do container mudar. A definição não está no corpo da skill; o comportamento está.
- **4.8** (probes) reforça a regra 2.2, e a parte operacional: liveness reinicia, readiness
  tira do Service: está no corpo porque é o critério de decisão das probes. A `startupProbe`,
  que o bloco menciona e nenhuma regra exige, ficou fora.

O bloco está transcrito no fim de `references/padrao-completo.md` com esta justificativa ao
lado, para que a decisão seja auditável sem precisar voltar ao wiki.

### Três exigências que eu inventei, e que o anexo desmentiu

Não é curadoria, é erro, mas pertence aqui porque mudou veredito e porque o mecanismo é o
mesmo que faz uma skill apodrecer.

| O que a skill exigia | O que o padrão diz | Efeito do erro |
|---|---|---|
| 3.2 com `runAsUser` **acima de 10000** | o wiki mostra `runAsUser: 10001` como **exemplo**; não há piso de UID | o `runAsUser: 70` da imagem alpine do Postgres **barrava** indevidamente |
| 2.4 aceitando `Recreate` em prod como justificável | o padrão exige `RollingUpdate` com `maxUnavailable: 0` e **não prevê alternativa** | `Recreate` passava como `recomendado` quando deveria barrar |
| 3.6 incluindo `hostIPC` | o padrão proíbe **três** campos: `hostNetwork`, `hostPID`, `privileged` | `KSV008` entrava como violação da casa |

As três nasceram do mesmo movimento: a regra parecia incompleta e eu completei de cabeça. O
limiar de 10000 veio do `KSV020` do Trivy; a flexibilização do `Recreate` veio de eu querer
acomodar o Postgres com volume único; o `hostIPC` veio de o `KSV008` estar ao lado dos
outros três no catálogo.

A segunda e a terceira são plausíveis o suficiente para passar numa leitura rápida. A
primeira foi pior: eu a usei para **reverter uma classificação que estava certa**,
`KSV020`/`KSV021` saíram de "fora do padrão" para "corrobora a 3.2", e eu escrevi uma seção
explicando a troca. Está registrada em `cobertura-do-trivy.md`, junto com o desmentido.

O que mudou na skill por causa disso: `references/padrao-completo.md` passou a marcar cada
desvio do texto com `INTERPRETAÇÃO DA SKILL` e o motivo. Hoje restam três interpretações
declaradas: subconjunto na 1.4, isenção de probe para `Job`/`CronJob`/`initContainer` na
2.2, e o nível de cada campo na 3.2, e nenhuma delas se confunde com texto da casa.

Efeito colateral útil: a correção da 2.4 **resolveu** uma tensão que o terceiro teste cego
tinha apontado. O sub-agente observou que a regra premiava a opção pior, porque
`maxUnavailable: 1` barrava e `Recreate` só pedia justificativa. A tensão era minha
invenção, não do padrão.

### O resto do que ficou fora

| Deixado fora | Motivo |
|---|---|
| **Reimplementar 2.1, 3.1, 3.6** | o enunciado proíbe, e o Trivy acerta nessas três. O script invoca e traduz |
| **Varrer segredo em comentário** | a regra 3.3 proíbe segredo "nem em comentário", e o parser de YAML descarta comentário antes de o script ver. Virou instrução de leitura no passo 3 em vez de um segundo parser só para comentários |
| **Aceitar digest como alternativa à tag** | a regra 3.1 aceita `@sha256:...`, e o script só reprova `:latest`, então digest passa sem código extra. Não há verificação de que o digest existe no registry: isso exigiria rede e é trabalho do Loom |
| **Conferir 2.6 por script** | o valor correto depende de a aplicação tratar SIGTERM. Não há como inferir do YAML. É a única regra 100% manual |
| **Decidir o que cada endpoint toca** | exige ler o código. Script que chutasse isso daria veredito confiante e errado na regra mais perigosa de operar |
| **Qualquer acesso ao cluster** | é o limite da skill e o contrato com a de triagem do Ticket 02. `kubectl apply --dry-run=server` aparece como instrução do modo escrita, não como verificação do script |
| **Aplicar correção automática** | a skill reporta e não conserta. Conserto de 1.4 exige decidir qual lado está certo; de 3.3, criar Secret e rotacionar a credencial vazada |
| **Regras do Trivy que a casa não adota** | `KSV021`, `KSV030`, `KSV104`, `KSV117` ficam informativas. Promovê-las seria inventar padrão |
| **Templates de manifesto em `assets/`** | considerei e descartei. Template convida a copiar, e o fluxo 2 mostra que as decisões difíceis mudam de projeto para projeto. O modo escrita dá o procedimento, não o preenchimento |
| **`allowed-tools` no frontmatter** | é experimental na spec e não está na tabela de campos do Kiro. Depender dele deixaria a skill frágil |

---

## 8. Permissões e execução

- **Nada de `chmod +x`.** O script é invocado por interpretador: `python3
  scripts/conferir_manifesto.py`: o que dispensa bit de execução e deixa explícito com
  que runtime ele roda.
- **Rodar o script cai na capability `shell`**, que pede aprovação a menos que exista
  regra `allow` em `~/.kiro/settings/permissions.yaml` ou no escopo do workspace. Em
  workspace não confiável o Kiro pergunta antes de cada comando e nem carrega skills do
  workspace. É o comportamento certo: a skill executa código e invoca ferramenta externa.
- **Duas operações, dois níveis de risco.** `trivy config` e o script são leitura pura:
  não tocam cluster, não escrevem arquivo, não saem para a rede. Já o
  `kubectl apply --dry-run=server` do modo escrita **fala com o apiserver**: é só
  validação de schema, não altera estado, mas exige kubeconfig apontando para o cluster
  certo. A skill avisa que `--dry-run=client` não substitui.
- **Dependência declarada no `compatibility`**, com o que se degrada sem ela: sem Trivy o
  script confere 15 das 19 e **avisa na saída** que 2.1, 3.1 e 3.6 não foram conferidas.
  Falhar em silêncio seria pior que não rodar.
- **Nenhum segredo é lido ou escrito.** O script reporta a *existência* de senha em texto
  puro e o *tamanho* dela, nunca o valor: `senha de 11 caracteres`, não a senha. Foi
  decisão deliberada: relatório de violação costuma ser colado em PR e em canal de chat.

### A sonda de segredos não pôde ser versionada, e isso é um achado

A sonda do experimento da regra 3.3 precisa de seis valores com a **forma exata** de
credencial real, senão o `trivy fs --scanners secret` não dispara. Essa mesma forma fez o
**push protection do GitHub recusar o push** deste ticket, com três violações:

| Detector | Valor sintético |
|---|---|
| Amazon AWS Access Key ID | `AKIA` + 16 caracteres |
| Amazon AWS Secret Access Key | 40 caracteres |
| Slack API Token | `xoxb-` com três segmentos |

O `ghp_` **não** foi flagrado, provavelmente porque o token sintético não tem checksum
válido: o detector do GitHub é mais estrito que o do Trivy nesse ponto, e os dois
discordam sobre o mesmo valor.

Minha primeira correção foi **guardar os valores em base64** dentro de um gerador. O
GitHub **decodificou o base64 e recusou de novo**, apontando as linhas exatas. Duas coisas
saíram dessa tentativa:

- um fato sobre a ferramenta: o detector do GitHub decodifica base64, o que eu não sabia;
- um erro de julgamento meu. Codificar valor para escapar de um controle de segurança é o
  padrão que o controle existe para impedir, e não melhora por o valor ser falso. Num
  trabalho sobre disciplina operacional, é precedente ruim.

Solução que resolve em vez de contornar: o gerador **sorteia** os cinco valores de formato
conhecido a cada execução. O experimento mede se o scanner reconhece a **forma**: qualquer
`AKIA` com 16 caracteres dispara a regra, o valor é irrelevante para a medição. Assim não
existe credencial no repositório, nem em texto nem codificada. Verificado em três execuções
seguidas: 5 de 6 detectados, sempre os mesmos cinco detectores.

A senha da `DATABASE_URL` segue fixa, porque é o objeto do experimento e precisa ser
identificável no relatório, e é a única que nenhum scanner detecta.

Custo aceito: a sonda não é mais reprodutível byte a byte. O **resultado** é, e está em
`evidencias/relatorios/06-trivy-saida-crua.txt`.

Vale como achado porque é o mesmo conflito que a regra 3.3 descreve, visto do outro lado:
ferramenta que casa por forma e não por conteúdo erra nas duas direções. O Trivy não vê
senha real dentro de URI; o GitHub barra credencial falsa porque parece real. Nenhum dos
dois lê o que o valor significa.

---

## 9. Manutenção: o que apodrece primeiro

A skill tem duas datas embutidas e vale dizer qual quebra antes.

1. **A versão do Trivy.** O mapa de cobertura foi medido com 0.52.2. Versão nova traz
   regra nova, e regra nova que desaparece em silêncio é pior que regra ruidosa: foi
   exatamente o que aconteceu com o `AVD-KSV-01010`. Por isso o script tem o balde
   `TRIVY APONTOU E O MAPA NÃO CONHECE`, e a reference traz a tabela de como classificar o
   que cair nele.
2. **A revisão do padrão (2026-07-29).** Está no `metadata` do frontmatter, no cabeçalho
   da reference e no topo do relatório. Se a casa publicar revisão nova, a divergência
   aparece na primeira conferência.

O `padrao-completo.md` abre dizendo que é transcrição operacional, não o texto normativo:
em divergência de redação o documento da casa prevalece; em divergência de
**obrigatoriedade**, pare e pergunte, porque é a obrigatoriedade que decide se barra.
