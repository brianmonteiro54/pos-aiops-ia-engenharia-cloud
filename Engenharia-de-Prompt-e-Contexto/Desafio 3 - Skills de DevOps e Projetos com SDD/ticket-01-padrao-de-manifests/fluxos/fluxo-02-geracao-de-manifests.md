# Fluxo executado 2 — geração de manifests para dois projetos

Registro do segundo fluxo feito **antes** de existir skill. O primeiro foi conferir um
manifesto pronto; este é o inverso — partir de um repositório e escrever o YAML.

Os dois fluxos juntos é que definem o escopo da skill. Se eu tivesse feito só a
conferência, a skill teria um modo só e perderia metade do trabalho real: na Metacortex
alguém também **escreve** manifesto, e as decisões difíceis são diferentes nos dois casos.

Projetos: `KubeDev/fake-shop` em `orion-prod`, `KubeDev/kube-news` em `nyx-dev`.

## Por que dois projetos, e por que ambientes diferentes

Um projeto só não revela o que importa. Com dois, apareceram **cinco pares de decisões
opostas sob a mesma regra** — e é isso que mostra onde o padrão termina e o julgamento
começa:

| | fake-shop (`orion-prod`) | kube-news (`nyx-dev`) |
|---|---|---|
| regra 2.3 réplicas | `replicas: 2` (obrigatório em prod) | `replicas: 1` (regra não se aplica) |
| regra 2.4 estratégia | `maxUnavailable: 0` | `maxUnavailable: 1`, e é o **mais correto** aqui |
| migração de schema | extraída para `Job` | **impossível extrair** sem mudar o código |
| probes | inventadas a partir de rotas de negócio | endpoints de saúde já existem |
| volumes para a 3.2 | dois (`/tmp` + `/tmp/metrics`) | um (`/tmp`) |

Mesmo padrão, mesmas 19 regras, dez respostas diferentes. Nenhuma delas sai do YAML.

## Passo 1 — ler o projeto antes de escrever uma linha de YAML

Cinco perguntas, nesta ordem. A última é a que muda a arquitetura do manifesto.

### fake-shop

| Pergunta | Resposta | Onde |
|---|---|---|
| porta | 5000 | `src/entrypoint.sh` (`gunicorn --bind 0.0.0.0:5000`) |
| endpoints de saúde | **não existem** | `src/index.py` — nenhuma rota `/health` ou `/ready` |
| variáveis | `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT` | `src/index.py:22-26` |
| caminhos de escrita | `PROMETHEUS_MULTIPROC_DIR`, obrigatório e gravável | `src/index.py:19-20` |
| migração | **comando separado**, `flask db upgrade`, antes do gunicorn | `src/entrypoint.sh` |

### kube-news

| Pergunta | Resposta | Onde |
|---|---|---|
| porta | 8080 | `src/server.js:81` |
| endpoints de saúde | `/ready` e `/health`, **nenhum toca o banco** | `src/system-life.js:11` e `:22` |
| variáveis | `DB_DATABASE`, `DB_USERNAME`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_SSL_REQUIRE` | `src/models/post.js:6-11` |
| caminhos de escrita | nenhum além de `/tmp` — `express-prom-bundle` agrega em memória | `src/package.json` |
| migração | **dentro do processo**, `sequelize.sync({alter: true})` no start | `src/server.js:80` |

## Passo 2 — a decisão que o padrão não prevê: onde roda a migração

O padrão não tem regra sobre migração. Mas a regra 2.3, que exige duas réplicas em prod,
cria o problema: **duas réplicas são duas migrações concorrentes a cada rollout.**

No fake-shop, três opções:

| Opção | Resultado |
|---|---|
| manter no `entrypoint.sh` | 2 réplicas = 2 `flask db upgrade` simultâneos |
| `initContainer` | roda uma vez **por pod**, então 2 réplicas continuam 2 execuções |
| **`Job` separado** | roda uma vez por versão — o único que resolve |

Escolhi `Job`, e o Deployment sobrescreve `command` para subir só o gunicorn.

**No kube-news a mesma análise dá resposta oposta.** `models.initDatabase()` está dentro
do processo da aplicação, chamado incondicionalmente em `src/server.js:80`. Não existe
comando para invocar; extrair exige mudar o código, o que está fora do escopo de um ticket
de manifesto. Consequência: `replicas: 1` deixa de ser "o default de dev" e passa a ser
**requisito**, e `maxSurge: 0` passa a ser necessário para o pod novo não rodar
`sync({alter: true})` concorrendo com o antigo.

Daí a frase que foi para a skill: *se a migração está dentro do código, não há como
extrair, e `replicas: 1` deixa de ser default de dev e passa a ser requisito.*

Dívida registrada e não resolvida: o `Job` e o `Deployment` do fake-shop são aplicados
juntos, sem ordenação. Em produção isso vira hook de pré-deploy. Fora do escopo, mas está
no `DECISOES.md`.

## Passo 3 — a regra 2.2 sem endpoint de saúde

O fake-shop não tem `/health` nem `/ready`. A regra 2.2 exige as duas probes apontando
para endpoints que a aplicação **de fato expõe**, então as duas tiveram que sair de rotas
de negócio — escolhidas pelo que cada uma acessa:

| Probe | Rota | Linha | O que faz |
|---|---|---|---|
| readiness | `GET /` | `src/index.py:252-254` | `Product.query.all()` — **toca o banco** |
| liveness | `GET /contact` | `src/index.py:49-51` | só renderiza template — **não toca** |

A divisão é o ponto, e é o que o padrão adverte: banco fora do ar tira o pod do Service
(readiness falha) mas **não reinicia o container** (liveness passa). Reiniciar não traz o
banco de volta; tirar do balanceador evita servir erro.

Descartei `tcpSocket` nas duas: a porta 5000 aceita conexão antes de o WSGI responder.
Descartei apontar as duas para `/`: é exatamente o cenário que a regra proíbe.

No kube-news a regra foi mais fácil de cumprir e o resultado é **pior**: os dois endpoints
existem e nenhum dos dois toca o banco, então o pod se declara pronto antes de a conexão
existir. Aceitável em dev; em prod exigiria um `/ready` com `SELECT 1`, que é mudança de
código. Está registrado como achado, não como pendência do manifesto.

## Passo 4 — a regra 3.2 e o caminho do `emptyDir`

`readOnlyRootFilesystem: true` é obrigatório, e ligar a flag sem o volume certo faz o
container não subir. **Qual caminho** não está em nenhuma regra:

| | fake-shop | kube-news |
|---|---|---|
| biblioteca de métricas | `GunicornPrometheusMetrics` | `express-prom-bundle` |
| modelo de processo | gunicorn, múltiplos workers | node, processo único |
| precisa de diretório gravável | **sim**, `PROMETHEUS_MULTIPROC_DIR` | **não**, agrega em memória |
| volumes | `/tmp` + `/tmp/metrics` | só `/tmp` |

Este é o melhor exemplo de por que a 3.2 não fecha sem ler o projeto. O Trivy sabe dizer
que a flag está ausente; ele não sabe em que caminho montar o volume para a aplicação
continuar funcionando com a flag ligada.

## Passo 5 — onde eu errei, e o que o erro ensinou

### Erro 1: escrevi `securityContext` como bloco de pod

Minha primeira versão dos dois manifestos colocou os cinco campos da 3.2 no
`spec.template.spec.securityContext`. Três deles — `allowPrivilegeEscalation`,
`readOnlyRootFilesystem` e `capabilities` — **não existem** nesse nível.

Medido depois, contra apiserver v1.31.5:

| Caminho do apply | Resultado |
|---|---|
| `kubectl apply` (strict, default) | **recusa**: `strict decoding error: unknown field` |
| `kubectl apply --server-side` | **recusa**: `field not declared in schema` |
| `kubectl apply --validate=false` | **aceita e descarta em silêncio** |

É o erro mais perigoso que cometi no ticket, porque no terceiro caminho o YAML no Git
continua dizendo que o workload está endurecido e o container fica sem `securityContext`
nenhum. Virou a tabela campo por campo em `references/padrao-completo.md`.

### Erro 2: esqueci `metacortex.io/owner` na ServiceAccount

Gerei dez objetos cumprindo as 19 regras e deixei um sem a anotação de dono. Quem achou
foi o próprio script, rodado contra os manifests que eu mesmo tinha escrito.

Isso decidiu uma coisa sobre a skill: o passo de validação **não é opcional**. Quem gera
está convencido de que acertou, e é justamente quando a conferência mecânica rende.

### Erro 3: deixei uma referência pendurada

Os manifests do fake-shop citavam `DECISOES.md` duas vezes e o arquivo não existia.
Nenhuma ferramenta pega isso. Entrou na skill como instrução explícita do modo escrita.

## Passo 6 — validar

```bash
python3 conferir_manifesto.py manifests/kube-news/     # rc=0
kubectl apply --dry-run=server -f manifests/kube-news/nyx-dev.yaml
```

Os dez objetos do fake-shop e os nove do kube-news passam no `--dry-run=server` contra o
k3d. `--dry-run=client` não serve: não valida schema contra o apiserver, e foi exatamente
o que deixaria passar o erro 1.

Resultado final da conferência dos próprios manifests gerados:

| Conjunto | rc | Barra | Recomendado |
|---|---|---|---|
| fake-shop em `orion-prod` | 1 | 2 (regras 2.3 e 2.4, as duas do Postgres) | 1 |
| kube-news em `nyx-dev` | **0** | 0 | 1 |

**Os dois achados do fake-shop são de propósito e estão documentados**, e os dois saem do
mesmo fato: o Postgres de `orion-prod` tem volume único. `replicas: 1` viola a 2.3 e
`strategy.type: Recreate` viola a 2.4. Subir para duas réplicas daria dois bancos
independentes; usar `RollingUpdate` com `maxSurge: 1` faria duas instâncias disputarem o
mesmo volume. Os dois casos são legítimos e os dois **continuam barrando**, porque desvio
documentado **não é** exceção aprovada — e foi isto que virou a seção "Exceção e desvio não
são a mesma coisa" da skill.

O kube-news em `nyx-dev` sai com `rc=0`: as regras 2.3, 2.4 e 2.5 são condicionadas a
`prod`, e o `runAsUser: 70` da imagem alpine cumpre a 3.2, que não estabelece piso de UID.

## O que este fluxo ensinou sobre a skill

1. **O modo escrita precisa de uma ordem rígida**: ler o projeto, depois escrever. As
   cinco perguntas do passo 1 não são checklist decorativo — a quinta (onde roda a
   migração) muda quais objetos existem no manifesto.
2. **O namespace é a primeira decisão**, porque define quais regras valem. Começar pelo
   Deployment leva a aplicar regra de prod em dev.
3. **Quem gera precisa rodar a conferência contra o próprio trabalho.** Três dos meus
   erros só apareceram assim.
4. **O `DECISOES.md` é parte da entrega, não documentação extra.** Sem ele o revisor não
   distingue valor deliberado de valor copiado, e metade das regras `recomendado` fica
   impossível de julgar.
