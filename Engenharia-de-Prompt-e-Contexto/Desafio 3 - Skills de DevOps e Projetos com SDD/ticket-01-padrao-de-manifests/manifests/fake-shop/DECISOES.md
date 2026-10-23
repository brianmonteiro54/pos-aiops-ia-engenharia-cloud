# Decisões do manifesto do fake-shop em `orion-prod`

O padrão responde o que precisa estar no YAML. Ele não responde **qual valor** colocar,
porque isso depende da aplicação. Este arquivo registra as cinco decisões que exigiram
abrir o código do fake-shop, com a linha que fundamenta cada uma.

Repositório lido: `https://github.com/KubeDev/fake-shop`.

## 1. A migração sai do start do container e vira Job

`src/entrypoint.sh` faz duas coisas em sequência:

```sh
python -m flask db upgrade
gunicorn --bind 0.0.0.0:5000 index:app
```

Em `orion-prod` a regra 2.3 exige no mínimo duas réplicas. Manter o entrypoint da
imagem significa **duas execuções concorrentes de `flask db upgrade` no mesmo banco a
cada rollout**. Alembic usa a tabela `alembic_version` e não um lock de sessão, então o
resultado de duas migrações simultâneas depende de quem commita primeiro.

Três caminhos considerados:

| Opção | Por que não |
|---|---|
| manter no entrypoint | 2 réplicas = 2 migrações concorrentes |
| `initContainer` | roda uma vez **por pod**, então 2 réplicas continuam 2 execuções |
| **Job separado** | roda uma vez por versão, e é o único que resolve |

Por isso o Deployment sobrescreve `command` para subir **só** o gunicorn, e existe um
`Job/orion-web-migracao` com `command: ["python","-m","flask","db","upgrade"]`.

Consequência que o manifesto não resolve e o PR precisa tratar: o Job e o Deployment são
aplicados juntos, sem ordenação. Em produção isto vira um hook de pré-deploy do Construct
ou um `helm hook pre-upgrade`. Está fora do escopo do ticket, mas é dívida registrada.

## 2. As duas probes apontam para rotas diferentes

A regra 2.2 exige readiness **e** liveness, e avisa que apontar as duas para o mesmo
endpoint que checa banco derruba a aplicação quando o banco fica lento. O fake-shop
**não tem endpoint de saúde**: não existe `/health` nem `/ready` em `src/index.py`.

Então as duas probes precisaram sair de rotas de negócio, escolhidas pelo que cada uma
toca:

| Probe | Rota | Linha | O que faz |
|---|---|---|---|
| readiness | `GET /` | `src/index.py:252-254` | `Product.query.all()`: **toca o banco** |
| liveness | `GET /contact` | `src/index.py:49-51` | só renderiza template: **não toca o banco** |

A divisão é o ponto. Banco fora do ar tira o pod do Service (readiness falha) mas **não
reinicia o container** (liveness continua passando). Reiniciar não traz o banco de volta;
tirar do balanceador evita servir erro. Quando o banco volta, o pod volta sozinho.

Descartado `tcpSocket` nas duas: a porta 5000 aceita conexão antes de o WSGI estar
pronto para responder, então `tcpSocket` passaria com a aplicação ainda inicializando.

Descartado apontar as duas para `/`: é exatamente o cenário que a regra 2.2 proíbe.

## 3. `readOnlyRootFilesystem: true` exigiu descobrir onde a aplicação escreve

`src/index.py:19-20`:

```python
metrics = GunicornPrometheusMetrics(app)
```

`GunicornPrometheusMetrics` exige a variável `PROMETHEUS_MULTIPROC_DIR` apontando para um
diretório **gravável**, porque cada worker do gunicorn escreve seu próprio arquivo de
métricas e a biblioteca agrega na leitura. Com root filesystem somente leitura e sem esse
diretório, o processo não sobe.

Daí os dois volumes do container:

- `emptyDir` em `/tmp`: temporários do Python e do gunicorn
- `emptyDir` em `/tmp/metrics`: apontado por `PROMETHEUS_MULTIPROC_DIR`

Esta é a parte da regra 3.2 que nenhuma ferramenta responde. O Trivy sabe dizer que
`readOnlyRootFilesystem` está ausente; ele não sabe **em que caminho** montar o volume
para que a aplicação continue funcionando com a flag ligada.

## 4. As variáveis de ambiente são as cinco que o código lê

`src/index.py:22-26` lê `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_PORT`.

Só `DB_PASSWORD` vem de `secretKeyRef` (regra 3.3). As outras quatro são `value` literal
porque não são segredo: host, porta, nome do banco e nome do usuário não dão acesso a
nada sozinhos, e colocar tudo em Secret só esconde configuração de quem precisa ler.

`FLASK_APP: index.py` é necessário porque o Job chama `flask db upgrade` sem o entrypoint
original, que era quem definia o contexto da aplicação.

## 5. `terminationGracePeriodSeconds: 30`

Gunicorn trata SIGTERM encerrando os workers depois de terminarem a requisição em curso.
A requisição mais longa desta aplicação é o checkout. 30 segundos (o default do
Kubernetes) cobre, e a regra 2.6 só pede que o valor seja **deliberado**, não que seja
diferente do default. Mantido com justificativa, não por omissão.

## Pendência conhecida: o Postgres viola a regra 2.3 de propósito

`orion-prod-postgres.yaml` tem `replicas: 1` em `prod`. O motivo está comentado no
próprio arquivo: com `emptyDir` e sem replicação, duas réplicas sobem com bancos
independentes e a aplicação alterna entre dois estados: pior que uma réplica, não melhor.

O caminho correto é `StatefulSet` com `PersistentVolumeClaim`, fora do escopo deste
ticket. O padrão exige que exceção a regra obrigatória venha com aprovação escrita de
Segurança & Compliance e prazo de validade; este manifesto é de laboratório e a aprovação
não existe. **Por isso a skill reporta este ponto como violação e não como conforme**,
desvio documentado continua sendo desvio até alguém assinar.
