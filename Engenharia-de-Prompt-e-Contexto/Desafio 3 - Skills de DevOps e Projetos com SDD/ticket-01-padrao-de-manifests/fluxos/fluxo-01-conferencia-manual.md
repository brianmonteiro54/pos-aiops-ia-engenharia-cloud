# Fluxo executado 1 — conferência manual do manifesto barrado

Registro do que eu fiz **antes** de existir skill. É daqui que a skill nasce: a ordem dos
passos, o que precisou de ferramenta, o que precisou de leitura do projeto e onde eu
travei. A skill é o empacotamento deste fluxo, não um texto escrito de cabeça.

## Passo 1 — Trivy primeiro, antes de qualquer script

O ticket manda descobrir o que o Trivy já pega antes de escrever código. Rodei:

```bash
trivy config manifests/
```

14 regras dispararam no manifesto barrado. Mas essa lista **não é o mapa de cobertura**:
regra que o Trivy tem e que o manifesto não viola não aparece. Para separar "o Trivy não
tem a regra" de "tem, mas não disparou", escrevi um manifesto-sonda que viola tudo de
propósito (`trivy-viola-tudo.yaml`) e rodei de novo: **20 regras**.

A diferença entre as duas execuções é o que fecha o mapa.

### Mapa de cobertura, verificado por execução

| Regra do padrão | Obrigatoriedade | Trivy cobre? | Evidência |
|---|---|---|---|
| 1.1 nome em kebab-case | obrigatório | **não** | sonda com `SondaViolaTudo` não disparou nada |
| 1.2 namespace `<cliente>-<ambiente>` | obrigatório | **não** | sonda com `ambiente-errado` não disparou |
| 1.3 quatro rótulos obrigatórios | obrigatório | **não** | sonda só com `app:` não disparou |
| 1.4 seletor casa com rótulo do pod | obrigatório | **não** | sonda com `app: sonda` x `app: sonda-diferente` não disparou |
| 1.5 anotação de dono | recomendado | **não** | — |
| 1.6 nome do container = componente | recomendado | **não** | — |
| 2.1 requests e limits | obrigatório | **sim** | KSV011, KSV015, KSV016, KSV018 |
| 2.2 readiness e liveness | obrigatório | **não** | manifesto sem probe nenhuma, nada disparou |
| 2.3 replicas >= 2 em prod | obrigatório | **não** | sonda com `replicas: 1` não disparou |
| 2.4 estratégia de atualização | obrigatório em prod | **não** | sem `strategy`, nada disparou |
| 2.5 PodDisruptionBudget | recomendado | **não** | — |
| 2.6 terminationGracePeriodSeconds | recomendado | **não** | — |
| 3.1 tag `:latest` | proibido | **sim** | KSV013 |
| 3.2 securityContext | obrigatório | **parcial** | KSV012, KSV001, KSV014, KSV003, KSV106, KSV020, KSV105 |
| 3.3 segredo em texto puro | proibido | **não** | ver passo 2 |
| 3.4 `automountServiceAccountToken: false` | obrigatório | **não** | sonda com `true` explícito não disparou |
| 3.5 ServiceAccount dedicada | recomendado | **não** | sonda com `serviceAccountName: default` não disparou |
| 3.6 hostNetwork, hostPID, privileged | proibido | **sim** | KSV008, KSV009, KSV010, KSV017 |
| 3.7 imagem só de registry interno | obrigatório | **não** | sonda com `docker.io/library/nginx` não disparou |

**Placar: de 19 regras acionáveis, o Trivy cobre 3 por inteiro (2.1, 3.1, 3.6), 1 em
parte (3.2) e não cobre 15.**

Nota sobre 3.2 ser "parcial": o Trivy confere os cinco campos do `securityContext` do
padrão por regras separadas e com severidades diferentes — `readOnlyRootFilesystem` é
HIGH, `runAsNonRoot` é MEDIUM, `capabilities.drop` é LOW. Ele não tem o conceito de "o
bloco inteiro que a Metacortex exige". Quem lê a saída do Trivy não sabe que são cinco
campos de uma regra só da casa.

## Passo 2 — o achado que mais pesa: o Trivy não vê o segredo

`trivy config` não faz detecção de segredo. Testei o scanner dedicado:

```bash
trivy fs --scanners secret manifests/
```

Nada. Testei com um arquivo de sonda contendo seis segredos de formatos diferentes
(gerada por `../evidencias/sondas/gerar-sonda-de-segredos.py`), e o resultado separa o
problema com precisão:

| Variável na sonda | Forma do valor (sintético) | Detectado? |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `AKIA` + 16 caracteres | **sim**, CRITICAL |
| `AWS_SECRET_ACCESS_KEY` | 40 caracteres | **sim**, CRITICAL |
| `GITHUB_TOKEN` | `ghp_` + 36 caracteres | **sim**, CRITICAL |
| `SLACK_TOKEN` | `xoxb-` com três segmentos | **sim**, HIGH |
| `PRIVATE_KEY` | bloco `BEGIN RSA PRIVATE KEY` | **sim**, HIGH |
| `DATABASE_URL` | `postgres://nyx:s3nh4-do-banco@pg...:5432/nyx` | **não** |

O Trivy reconhece **formato conhecido de credencial**, não senha arbitrária dentro de
string de conexão. O manifesto barrado tem exatamente o segundo caso. Ou seja: a regra
mais perigosa do padrão — a única classificada como `proibido` junto com `:latest` e
`hostNetwork` — é invisível para a ferramenta.

Isso decide a prioridade do script: 3.3 entra, e entra com detecção de padrão de
conexão, não de formato de credencial.

## Passo 3 — conferência regra por regra

Com o mapa na mão, conferi o manifesto barrado contra as 19 regras acionáveis.

### Violações obrigatórias e proibidas

| # | Regra | O que está no manifesto | Por que viola |
|---|---|---|---|
| 1.1 | nome em kebab-case | `metadata.name: NyxAPI` | tem maiúsculas; o correto é `nyx-api` |
| 1.3 | quatro rótulos | Deployment só tem `app: nyxapi`; **o Service não tem rótulo nenhum**; o template do pod só tem `app: nyxapi` | faltam os quatro `app.kubernetes.io/*` em três objetos |
| 1.4 | seletor casa com pod | Service `selector: app: nyx-api` x rótulo do pod `app: nyxapi` | **um hífen de diferença: o Service nunca terá endpoint** |
| 2.1 | requests e limits | ausentes | container sem requests é escalonado às cegas |
| 2.2 | readiness e liveness | ausentes | ver passo 4, exige ler o projeto |
| 2.3 | replicas >= 2 em prod | `replicas: 1`, namespace `nyx-prod` | indisponibilidade a cada deploy |
| 2.4 | estratégia de atualização | ausente | em prod é obrigatório `maxUnavailable: 0` |
| 3.1 | tag `:latest` | `registry.metacortex.io/nyx/api:latest` | **proibido** |
| 3.2 | securityContext | ausente por inteiro | faltam os cinco campos |
| 3.3 | segredo em texto puro | `DATABASE_URL` com `s3nh4-do-banco` | **proibido**, e o Trivy não pega |
| 3.4 | automountServiceAccountToken | ausente | obrigatório desde 2026-07-29 |

### Violações de regra recomendada

| # | Regra | Situação |
|---|---|---|
| 1.5 | anotação de dono | sem `metacortex.io/owner` nem `runbook` |
| 2.5 | PodDisruptionBudget | ausente; com replicas >= 2 em prod passa a ser esperado |
| 3.5 | ServiceAccount dedicada | não declarada, usa a `default` do namespace |

### Conforme

| # | Regra | Por quê |
|---|---|---|
| 1.2 | namespace | `nyx-prod` está no formato `<cliente>-<ambiente>` |
| 1.6 | nome do container | `api` é o nome do componente, não `app` nem `main` |
| 3.6 | hostNetwork/hostPID/privileged | nenhum dos três é usado |
| 3.7 | registry interno | `registry.metacortex.io` está correto |

**Resultado: 11 violações obrigatórias ou proibidas, 3 recomendadas, 4 conformes,
1 não aplicável (2.6).**

> **Nota de reconciliação com a saída do script.** O script reporta **20** violações para
> este mesmo manifesto, e não 11. Não é divergência de veredito: aqui eu contei **regras
> violadas**, o script conta **achados**. A regra 1.3 é uma linha nesta tabela e três
> achados no script, porque falta em três objetos distintos; a 3.2 é uma linha aqui e
> cinco achados, um por requisito; a 2.1, quatro.
>
> A contagem do script é a mais útil na prática — cada achado é um lugar para consertar,
> com objeto e campo. A desta tabela serve para discutir cobertura do padrão. O relatório
> em `evidencias/relatorios/01-manifesto-barrado.txt` tem a lista completa.

### Uma distinção que eu quase errei

Minha primeira leitura foi "o seletor está errado". Está — mas em **um** dos dois
objetos. O `matchLabels` do Deployment é `app: nyxapi` e o rótulo do pod é `app: nyxapi`:
**casam**. Quem não casa é o `selector` do Service, que diz `app: nyx-api`. O Deployment
sobe e fica saudável; o Service é que fica sem endpoint.

Isso importa para a skill: o relatório precisa dizer **qual objeto** tem o seletor
quebrado, porque o conserto é em lugares diferentes e o sintoma que o cliente relata
("subiu mas não responde") só se explica com essa precisão.

## Passo 4 — o que o YAML não responde

A regra 2.2 exige as duas probes apontando para endpoints que a aplicação **de fato
expõe**, e avisa que apontar as duas para o mesmo endpoint que checa banco derruba a
aplicação quando o banco fica lento. Nada disso se decide olhando o manifesto.

Abri o repositório do kube-news:

- `src/server.js:81` → `app.listen(8080)`. A porta 8080 do manifesto está correta.
- `src/system-life.js:11` → `GET /ready` responde 200 ou 500 por um relógio interno
  (`readTime`), controlado por `PUT /unreadyfor/:seconds`. **Não toca o banco.**
- `src/system-life.js:22` → `GET /health` responde `{state, machine}`. **Não toca o banco.**
- `src/models/post.js` → o banco é configurado por `DB_HOST`, `DB_DATABASE`,
  `DB_USERNAME`, `DB_PASSWORD`, `DB_PORT`, `DB_SSL_REQUIRE`.

Conclusão que só sai da leitura: **readiness em `/ready`, liveness em `/health`, as duas
na 8080**, e nenhuma das duas depende do banco. O padrão é satisfeito sem o risco que o
próprio padrão descreve.

Detalhe que encontrei de passagem e que vale anotar: `server.js:22` registra o
middleware `healthMid` **antes** das rotas, então quando alguém chama `PUT /unhealth` o
500 passa a valer para toda requisição, inclusive `/ready`. Não muda a escolha das
probes, mas explica por que uma liveness em `/health` consegue de fato reiniciar o
container quando a aplicação se declara doente.

Observação sobre o `DATABASE_URL` do manifesto barrado: o kube-news **não lê**
`DATABASE_URL`. Ele lê as cinco variáveis `DB_*`. Então a variável do manifesto está, ao
mesmo tempo, vazando segredo e não servindo para nada. A correção não é mover
`DATABASE_URL` para um Secret — é trocar pelas variáveis que a aplicação usa, com a
senha vindo de `secretKeyRef`.

## O que este fluxo ensinou sobre a skill

1. **A ordem importa e precisa estar na skill**: Trivy primeiro, depois as regras que ele
   não cobre, depois a leitura do projeto. Rodar a leitura antes do Trivy desperdiça
   contexto com o que a ferramenta já responde.
2. **Três regras precisam de parsing de YAML, não de leitura**: 1.1, 1.2 e 1.4 são
   verificações de string e de igualdade entre dois campos. Errar isso na leitura é
   trivial (eu quase errei a 1.4) e um script não erra.
3. **Duas regras só se resolvem lendo o projeto**: 2.2 (quais endpoints existem e o que
   cada um toca) e, no modo escrita, a lista de variáveis de ambiente.
4. **O relatório precisa citar objeto e campo**, não só a regra. "Seletor errado" não
   diz onde consertar.
