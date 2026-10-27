# Conferência completa de `nyx-api-barrado.yaml`

A saída do script está em `evidencias/relatorios/01-manifesto-barrado.txt`: 20 violações
distribuídas em 11 regras, 3 pendências de justificativa, 4 apontamentos do Trivy fora do
padrão da casa.

**A saída do script não é a conferência.** A skill divide o julgamento em três juízes, e o
terceiro é leitura de código:

| Juiz | Regras | O que ele responde |
|---|---|---|
| `scripts/conferir_manifesto.py` | 15 | presença, formato e comparação de campo |
| Trivy | 3 | corroboração em 2.1, 3.1 e 3.6 |
| **leitura do repositório** | **1** (2.2) | **qual valor** colocar, e se o campo faz sentido para esta aplicação |

Este documento é o terceiro juiz aplicado ao manifesto barrado. Sem ele o relatório diz
"faltam as duas probes" e não diz onde apontá-las, o que é metade de uma revisão.

Repositório lido: [`KubeDev/kube-news`](https://github.com/KubeDev/kube-news), clone raso de
`main`. Toda afirmação abaixo tem arquivo e linha.

## O que o manifesto barrado tem

```yaml
containers:
  - name: api
    image: registry.metacortex.io/nyx/api:latest
    ports: [{containerPort: 8080}]
    env:
      - name: DATABASE_URL
        value: "postgres://nyx:s3nh4-do-banco@pg.nyx-prod.svc:5432/nyx"
```

Nenhuma probe, nenhum `resources`, nenhum `securityContext`. Namespace `nyx-prod`, o que
liga as regras condicionais a produção.

## Regra 2.2: as duas probes, e para onde apontá-las

O script sabe dizer que `readinessProbe` e `livenessProbe` estão ausentes. Ele não sabe que
endpoints existem nem o que cada um toca. O repositório sabe.

### Os endpoints de saúde

`src/system-life.js` declara três rotas de ciclo de vida:

| Rota | Linha | O que faz | Toca o banco? |
|---|---|---|---|
| `GET /ready` | `11-20` | compara `readTime` com o relógio; 200 ou 500 | **não** |
| `GET /health` | `22-28` | devolve `{state: 'up', machine: os.hostname()}` | **não** |
| `PUT /unhealth` | `30-34` | vira `isHealth` para `false` | n/d |

```js
// src/system-life.js:11
router.get('/ready', (req, res) => {
    if (isRead()) { res.statusCode = 200; return res.send('Ok'); }
    else          { res.statusCode = 500; return res.send(''); }
});
```

### A porta é fixa no código

`src/server.js:81`:

```js
app.listen(8080);
```

Sem `process.env.PORT`. Então `containerPort: 8080` e `targetPort: 8080` do manifesto estão
certos, e isso passa de "provavelmente certo" para **confirmado**. É a distinção da regra
4.5 do vocabulário: `port` é onde o Service escuta, `targetPort` é onde o container escuta.

### O valor que entra no manifesto

```yaml
readinessProbe:
  httpGet: {path: /ready, port: 8080}
  initialDelaySeconds: 10
livenessProbe:
  httpGet: {path: /health, port: 8080}
  initialDelaySeconds: 20
  periodSeconds: 20
```

A regra 2.2 proíbe apontar as duas para o mesmo endpoint que checa dependência externa,
porque banco lento passa a reiniciar container em vez de só tirá-lo do Service. **Aqui a
regra é satisfeita de graça**: nenhuma das duas rotas toca o Postgres.

### O detalhe que faz a liveness funcionar, e que só o código mostra

`src/server.js:22-23`, nesta ordem:

```js
app.use(config.middlewares.healthMid);   // linha 22
app.use('/', config.routers);            // linha 23
```

`healthMid` (`system-life.js:43-51`) devolve 500 em **qualquer** requisição quando
`isHealth` é `false`. Por estar registrado **antes** do roteador, ele cobre também `/ready`
e `/health`.

Consequência: `PUT /unhealth` derruba os dois endpoints, e é isso que permite à liveness em
`/health` de fato reiniciar o container. Se o middleware estivesse registrado depois,
`/health` responderia 200 para sempre e a liveness seria decorativa.

Isso não muda a escolha das probes. **Explica por que ela funciona**, e é o tipo de
afirmação que uma revisão de manifesto não consegue fazer sem abrir o projeto.

### A ressalva que a leitura obriga a registrar

As duas probes são cegas ao banco. Satisfazem a 2.2 e **não** garantem que a aplicação
serve: o pod entra no Service antes de a conexão com o Postgres existir, e a primeira
requisição de verdade é que descobre.

Em `nyx-dev` isso é aceitável e está registrado em `manifests/kube-news/DECISOES.md`.
**Este manifesto é `nyx-prod`**, e em produção um `/ready` que não faz `SELECT 1` é lacuna
real. Corrigir exige mudar o código da aplicação, o que está fora de um ticket de manifesto.

**Vai para o PR como achado, não como pendência do YAML.**

## Regra 3.3: o achado que inverte a correção

O script marca a 3.3 por senha em texto puro dentro de `env[DATABASE_URL].value`. A correção
óbvia seria mover para `secretKeyRef`. **A leitura do repositório mostra que isso está
errado.**

`src/models/post.js:8-13` é onde toda configuração de banco é lida:

```js
const DB_DATABASE    = process.env.DB_DATABASE    || "kubedevnews";
const DB_USERNAME    = process.env.DB_USERNAME    || "kubedevnews";
const DB_PASSWORD    = process.env.DB_PASSWORD    || "Pg#123";
const DB_HOST        = process.env.DB_HOST        || "localhost";
const DB_PORT        = parseInt(process.env.DB_PORT, 10) || 5432;
const DB_SSL_REQUIRE = strToBool(process.env.DB_SSL_REQUIRE) || false;
```

Busca por `DATABASE_URL` no projeto inteiro:

```
$ grep -rn 'DATABASE_URL' kube-news/
(nenhum resultado)
```

**A variável não existe na aplicação.** Ela vaza uma senha e não configura nada. As seis que
o código lê são as acima, e só `DB_PASSWORD` é segredo.

Então a correção não é mover `DATABASE_URL` para um Secret, é **substituí-la**:

```yaml
envFrom:
  - configMapRef: {name: nyx-api}        # DB_HOST, DB_PORT, DB_DATABASE, DB_USERNAME, DB_SSL_REQUIRE
env:
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef: {name: nyx-db, key: password}
```

### E há um agravante, também só visível no código

As seis variáveis têm **fallback**. Se o Secret não existir ou a chave estiver errada, a
aplicação **não quebra**: ela sobe conectando em `localhost` com `kubedevnews` / `Pg#123`.

O resultado é um pod `Ready` que não serve nada, sem erro em log nenhum. É o pior modo de
falha possível, porque não dispara alarme.

Daí duas exigências para o manifesto corrigido:

- `secretKeyRef` **sem** `optional: true`, para o pod falhar no start se o Secret faltar
- `DB_SSL_REQUIRE` entre aspas. `strToBool` (`models/post.js:4-6`) faz `value === 'true'`,
  então o valor precisa chegar como string. Sem aspas o YAML entrega boolean e o `kubectl`
  recusa o ConfigMap com uma mensagem que não explica o motivo

E uma observação que não é do manifesto: `Pg#123` está no código-fonte público do projeto.
É exatamente a classe de segredo que a regra 3.3 existe para pegar, e está fora do alcance
de qualquer verificação de manifesto.

## Regra 3.2: `readOnlyRootFilesystem` precisa de qual volume?

O script e o Trivy sabem dizer que a flag está ausente. Nenhum dos dois sabe se ligá-la
derruba a aplicação, e isso depende de onde ela escreve.

`src/server.js:5` e `src/middleware.js:1-7` usam `express-prom-bundle` e `prom-client`
agregando **em memória**, num processo Node único. Busca por escrita em disco:

```
$ grep -rnE 'writeFile|createWriteStream|mkdir|multiproc|PROMETHEUS' src/ --include='*.js'
(nenhum resultado)
```

**Nenhum caminho de escrita.** Então `readOnlyRootFilesystem: true` sobe com um único
`emptyDir` em `/tmp`, por precaução para temporários do runtime.

Contraste que vale guardar: o fake-shop usa `GunicornPrometheusMetrics` com múltiplos
workers, que **exige** `PROMETHEUS_MULTIPROC_DIR` gravável, e precisou de dois volumes.
Mesma regra do padrão, mesma flag, respostas diferentes. A resposta está na biblioteca, não
no YAML.

## Regra 2.3: o conserto mecânico é inseguro nesta aplicação

Este é o achado mais consequente da leitura, e ele **não** é sobre probes.

O script barra a 2.3 porque `replicas: 1` em `nyx-prod`. A correção mecânica é subir para 2.
O código diz que isso cria um problema novo.

`src/server.js:80`, antes do `listen`:

```js
models.initDatabase();
app.listen(8080);
```

E `src/models/post.js:58-60`:

```js
exports.initDatabase = () => {
    seque.sync({ alter: true })
}
```

A criação e alteração de schema roda **dentro do processo da aplicação**, incondicionalmente,
no start. Não existe comando separado para invocar.

Com `replicas: 2` em produção, cada rollout dispara **dois `sync({alter: true})`
concorrentes na mesma tabela**. Extrair isso para um `Job` exigiria mudar o código, o que um
ticket de manifesto não faz.

Então a 2.3 neste manifesto é um impasse honesto:

| Caminho | Problema |
|---|---|
| manter `replicas: 1` | viola regra obrigatória em prod, e exige aprovação escrita de Segurança & Compliance com prazo |
| subir para `replicas: 2` | satisfaz a regra e introduz migração concorrente, que é pior |
| mudar o código para extrair a migração | é o certo, e está fora do escopo do ticket |

**O relatório tem que dizer isso.** Um revisor que só lê a saída do script aplica o conserto
mecânico e cria um defeito que ninguém vai associar à revisão. Comparar com
`manifests/kube-news/nyx-dev.yaml`, onde `replicas: 1` é **correto** porque `nyx-dev` não
aciona a 2.3: a mesma aplicação é cumprível em dev e não é em prod, e o padrão só é
satisfeito ali por causa do ambiente.

## O que mudou no veredito por causa do passo 3

| Regra | Só com o script | Com a leitura do repositório |
|---|---|---|
| **2.2** | "faltam as duas probes" | `/ready:8080` e `/health:8080`, nenhuma toca o banco, com a ressalva de que nenhuma sabe se o banco responde em prod |
| **3.3** | "senha em texto puro em `DATABASE_URL`" | a variável **não é lida pela aplicação**: substituir pelas seis `DB_*`, e o fallback silencioso exige `secretKeyRef` não opcional |
| **3.2** | "faltam os cinco campos" | `readOnlyRootFilesystem: true` sobe com um `emptyDir` em `/tmp`; a aplicação não escreve em disco |
| **2.3** | "`replicas: 1` em prod, barra" | o conserto mecânico para 2 cria migração concorrente; é impasse de arquitetura, não de YAML |
| porta | `containerPort: 8080` presente | confirmado em `server.js:81`, sem `process.env.PORT` |

Quatro das onze regras violadas mudaram de conteúdo, e uma delas mudou de **direção**. É a
diferença entre um relatório que lista campos ausentes e um que diz o que fazer.

## Limite deste passo

- a leitura foi de `main` no dia da conferência. A imagem do manifesto é
  `registry.metacortex.io/nyx/api:latest`, e `:latest` é proibida pela regra 3.1 justamente
  porque **não dá para saber qual commit está rodando**. Então a correspondência entre o
  código lido e a imagem em execução é presumida, não verificada: é a própria violação da
  3.1 degradando a conferência
- `seque.sync({alter: true})` é o que o código faz hoje. Se a aplicação passar a usar
  migração versionada, a conclusão sobre a 2.3 muda
- nada aqui foi executado. É leitura de código, não teste
