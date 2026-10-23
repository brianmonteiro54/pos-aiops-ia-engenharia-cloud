# Decisões do manifesto do kube-news em `nyx-dev`

Mesmo exercício do fake-shop, aplicação diferente e ambiente diferente. O que muda é
exatamente o que interessa para a skill: **o padrão é o mesmo, as respostas não são.**

Repositório lido: `https://github.com/KubeDev/kube-news`.

## 1. O namespace decide quais regras valem

Duas das seis regras da seção 2 são condicionadas a `prod`:

| Regra | Em `orion-prod` | Em `nyx-dev` |
|---|---|---|
| 2.3 réplicas | obrigatório `>= 2` → `replicas: 2` | não se aplica → `replicas: 1` |
| 2.4 estratégia | obrigatório `maxUnavailable: 0` | não se aplica → `maxUnavailable: 1` |
| 2.5 PDB | esperado (prod, 2 réplicas) → PDB declarado | não se aplica |

Isto não é economia de esforço: em dev, `maxUnavailable: 1` com `maxSurge: 0` é a escolha
**mais correta** que a de prod, pelo motivo do item 2.

É também a razão pela qual a skill precisa derivar o ambiente do nome do namespace em vez
de aplicar as 19 regras cegamente. Um relatório que exige `replicas >= 2` em `nyx-dev`
está errado, e errado de um jeito que faz o revisor desconfiar do resto do relatório.

## 2. A migração NÃO pode virar Job, ao contrário do fake-shop

No fake-shop a migração estava no `entrypoint.sh` e eu a movi para um Job. Aqui a decisão
se inverte, e o motivo é só visível no código.

`src/server.js:80`:

```js
models.initDatabase();
app.listen(8080);
```

E `src/models/post.js`:

```js
exports.initDatabase = () => {
    seque.sync({ alter: true })
}
```

A criação e alteração do schema está **dentro do processo da aplicação**, chamada
incondicionalmente no start. Não existe comando separado para invocar. Extrair isso para
um Job exigiria mudar o código da aplicação, o que está fora do escopo de um ticket de
manifesto.

Consequências que o manifesto assume:

- **`replicas: 1` deixa de ser só "o default de dev" e passa a ser requisito.** Duas
  réplicas são dois `ALTER TABLE` concorrentes na mesma tabela.
- **`maxSurge: 0` com `maxUnavailable: 1`** garante que o pod novo só suba depois de o
  antigo morrer. Com `maxSurge: 1` haveria, por alguns segundos, duas versões rodando
  `sync({alter: true})` com schemas diferentes em mente.

Para levar esta aplicação a prod seria preciso mudar o código primeiro. Isso é um achado
do ticket, não uma pendência do manifesto: **o padrão da Metacortex é cumprível aqui só
porque o ambiente é dev.**

## 3. As probes: esta aplicação tem endpoints de saúde, e os dois são cegos ao banco

`src/system-life.js`:

| Probe | Rota | Linha | O que faz |
|---|---|---|---|
| readiness | `GET /ready` | `:11` | compara `readTime` com o relógio. **Não toca o banco** |
| liveness | `GET /health` | `:22` | devolve `{state, machine}`. **Não toca o banco** |

Comparado ao fake-shop, isto é mais fácil e **pior**. Mais fácil porque a regra 2.2 é
satisfeita sem improvisar com rota de negócio. Pior porque nenhum dos dois endpoints sabe
se o banco responde: o pod entra no Service antes de a conexão existir, e a primeira
requisição de verdade é que descobre. Em dev é aceitável; em prod exigiria um `/ready`
que faz `SELECT 1`, e isso é mudança de código.

Um detalhe que achei de passagem e que muda a leitura da liveness: `src/server.js:22`
registra o middleware `healthMid` **antes** das rotas.

```js
app.use(config.middlewares.healthMid);
app.use('/', config.routers);
```

Então quando alguém chama `PUT /unhealth`, o 500 passa a valer para **toda** requisição,
inclusive `/ready` e `/health`. É o que faz a liveness em `/health` de fato conseguir
reiniciar o container, sem esse middleware, `/health` responderia 200 para sempre e a
liveness seria decorativa. Não muda a escolha das probes, explica por que ela funciona.

## 4. `readOnlyRootFilesystem: true` precisou de UM volume, não dois

Contraste direto com o fake-shop, e é o melhor exemplo de por que a regra 3.2 não é
automatizável:

| | fake-shop | kube-news |
|---|---|---|
| biblioteca de métricas | `GunicornPrometheusMetrics` | `express-prom-bundle` |
| modelo de processo | gunicorn, múltiplos workers | node, processo único |
| precisa de diretório gravável | **sim**, `PROMETHEUS_MULTIPROC_DIR` | **não**, agrega em memória |
| volumes para a flag ligada | `/tmp` + `/tmp/metrics` | só `/tmp` |

Mesma regra do padrão, mesma flag, dois manifestos diferentes. A resposta está na
biblioteca, não no YAML.

## 5. A senha tem um default embutido no código, e isso muda o risco da regra 3.3

`src/models/post.js:6-11`:

```js
const DB_PASSWORD = process.env.DB_PASSWORD || "Pg#123";
```

Todas as seis variáveis `DB_*` têm fallback. O efeito prático: se o `secretKeyRef` falhar
ou o Secret não existir, **a aplicação não quebra**: ela sobe silenciosamente tentando
conectar com `kubedevnews` / `Pg#123` em `localhost`. Não há erro de configuração, só um
pod pronto que não serve nada.

Duas consequências para o manifesto:

- `DB_PASSWORD` vem de `secretKeyRef` sem `optional: true` (o default já é obrigatório),
  para o pod falhar no start se o Secret não existir em vez de cair no fallback.
- A senha `Pg#123` está no código-fonte público do projeto. Isso é problema do projeto,
  não do manifesto, mas é exatamente a classe de segredo em texto puro que a regra 3.3
  existe para pegar, e que está fora do alcance de qualquer verificação de manifesto.

## 6. Configuração não-secreta foi para ConfigMap, não para `env` literal

As cinco variáveis que não são segredo (`DB_HOST`, `DB_PORT`, `DB_DATABASE`,
`DB_USERNAME`, `DB_SSL_REQUIRE`) estão em ConfigMap consumido por `envFrom`.

No fake-shop elas ficaram como `value` literal no Deployment. A diferença é deliberada e
vale como anotação sobre o padrão: **ele não opina sobre isso.** As duas formas passam as
19 regras. Escolhi ConfigMap aqui porque mudar o endereço do banco em dev é frequente e
com `envFrom` não é preciso tocar no Deployment.

`DB_SSL_REQUIRE` é `"false"` entre aspas porque o código faz `value === 'true'`
(`src/models/post.js:4`). YAML sem aspas entregaria um boolean, o `kubectl` recusaria o
ConfigMap, e a mensagem de erro não explicaria o motivo.
