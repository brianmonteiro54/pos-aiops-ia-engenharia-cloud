# O que o Trivy cobre do padrão, e o que não cobre

Medido com **Trivy 0.52.2**. Cobertura depende de versão: ao atualizar, refaça o
experimento do passo 1 em vez de confiar nesta tabela.

> Os manifestos-sonda citados aqui estão em `Engenharia-de-Prompt-e-Contexto/Desafio 3 -
> Skills de DevOps e Projetos com SDD/ticket-01-padrao-de-manifests/evidencias/sondas/`, e
> as saídas das execuções na pasta `evidencias/relatorios/` ao lado. Use-os para refazer a
> medição depois de atualizar o Trivy.
>
> A sonda de segredos é a exceção: ela é **gerada** por `gerar-sonda-de-segredos.py`, e
> não versionada. Os valores precisam ter a forma exata de credencial real para o scanner
> disparar, e essa forma faz o push protection do GitHub recusar o push — aconteceu de
> fato, com três violações. O gerador sorteia os valores a cada execução, porque o
> experimento mede a forma e não um valor específico. Rode o gerador para refazer a
> medição e apague o arquivo depois.

Este arquivo existe para responder uma frase específica: **"o Trivy passou, então está
certo."** Não está.

## Como o mapa foi levantado

Rodar `trivy config` no manifesto a revisar **não produz mapa de cobertura**. Regra que o
Trivy tem e que aquele manifesto não viola simplesmente não aparece na saída, e fica
impossível distinguir "o Trivy não tem a regra" de "tem, mas não disparou".

Foram dois experimentos:

| Experimento | Comando | Regras que dispararam |
|---|---|---|
| manifesto real barrado | `trivy config nyx-api-barrado.yaml` | **14** |
| manifesto-sonda que viola tudo de propósito | `trivy config trivy-viola-tudo.yaml` | **20** |

A diferença entre os dois é o que fecha o mapa. A sonda viola as 19 regras do padrão de
propósito; o que ela **não** fez disparar, o Trivy não tem.

## Placar

**De 19 regras acionáveis, o Trivy cobre 3 por inteiro, 1 em parte e não cobre 15.**

| Regra | Nível na casa | Trivy | Evidência |
|---|---|---|---|
| 1.1 nome kebab-case | obrigatório | **não** | sonda com `SondaViolaTudo` não disparou |
| 1.2 namespace `<cliente>-<ambiente>` | obrigatório | **não** | sonda com `ambiente-errado` não disparou |
| 1.3 os quatro rótulos | obrigatório | **não** | sonda só com `app:` não disparou |
| 1.4 seletor casa com pod | obrigatório | **não** | sonda com `app: sonda` x `app: sonda-diferente` não disparou |
| 1.5 anotação de dono | recomendado | **não** | — |
| 1.6 nome do container | recomendado | **não** | — |
| **2.1 requests e limits** | obrigatório | **sim** | KSV011, KSV015, KSV016, KSV018 |
| 2.2 readiness e liveness | obrigatório | **não** | sonda sem probe nenhuma, nada disparou — nem a presença dos campos |
| 2.3 replicas >= 2 em prod | obrigatório | **não** | sonda com `replicas: 1` não disparou |
| 2.4 estratégia de atualização | obrigatório em prod | **não** | sem `strategy`, nada disparou |
| 2.5 PodDisruptionBudget | recomendado | **não** | — |
| 2.6 período de graça | recomendado | **não** | — |
| **3.1 tag `:latest`** | proibido | **sim** | KSV013 |
| 3.2 securityContext | obrigatório | **parcial, e não serve de veredito** | KSV012, KSV001, KSV014, KSV003, KSV106, KSV105, KSV020, KSV021 — ver seção dedicada |
| 3.3 segredo em texto puro | proibido | **não** | ver seção dedicada abaixo |
| 3.4 `automountServiceAccountToken` | obrigatório | **não** | sonda com `true` explícito não disparou |
| 3.5 ServiceAccount dedicada | recomendado | **não** | sonda com `serviceAccountName: default` não disparou |
| **3.6 hostNetwork/hostPID/privileged** | proibido | **sim** | KSV008, KSV009, KSV010, KSV017 |
| 3.7 registry interno | obrigatório | **não** | sonda com `docker.io/library/nginx` não disparou |

## Armadilha 1 — a severidade do Trivy não é a obrigatoriedade da casa

Severidades medidas no manifesto barrado:

| KSV | Severidade no Trivy | Regra da casa | Nível na casa |
|---|---|---|---|
| KSV015 | **LOW** | 2.1 | **obrigatório** |
| KSV016 | **LOW** | 2.1 | **obrigatório** |
| KSV011 | **LOW** | 2.1 | **obrigatório** |
| KSV018 | **LOW** | 2.1 | **obrigatório** |
| KSV003 | **LOW** | 3.2 | **obrigatório** |
| KSV013 | MEDIUM | 3.1 | **proibido** |
| KSV012 | MEDIUM | 3.2 | **obrigatório** |
| KSV001 | MEDIUM | 3.2 | **obrigatório** |
| KSV014 | HIGH | 3.2 | obrigatório |

As quatro regras de `requests`/`limits` são **LOW** no Trivy e **barram o deploy** na
Metacortex. A tag `:latest` é MEDIUM no Trivy e `proibido` na casa. Quem filtra a saída por
`--severity HIGH,CRITICAL` — o que é prática comum — **não vê nenhuma das cinco violações
LOW e perde a regra 2.1 inteira.**

As linhas da regra 3.2 nesta tabela estão aqui como prova do desencontro de severidade.
O script **não** usa esses KSVs como veredito da 3.2 — ver a armadilha 2.

É por isso que `scripts/conferir_manifesto.py` não repassa a saída do Trivy: ele traduz
cada KSV para a regra da casa com o nível da casa.

## Armadilha 2 — a regra 3.2 erra nas duas direções, e por isso o Trivy não a julga

Esta é a única regra em que o script **não** delega ao Trivy. O motivo é que a cobertura
dele falha nos dois sentidos ao mesmo tempo.

### Falso negativo: não existe o conceito de "bloco"

O Trivy confere os cinco requisitos por **regras separadas**, com severidades que vão de
LOW a HIGH. Ele não tem o conceito de "o bloco inteiro que a Metacortex exige". Duas
consequências:

- Lendo a saída, ninguém descobre que são cinco requisitos de **uma regra só** da casa,
  nem que faltar qualquer um deles barra o deploy.
- Quem filtra por `--severity HIGH,CRITICAL` vê só `KSV014` e **perde quatro dos cinco**.

### Falso positivo: `KSV020` e `KSV021` são cegos para a herança

As duas (UID <= 10000, GID <= 10000) olham **apenas** `containers[].securityContext`.
`runAsUser` declarado no nível do **pod** não é considerado, embora o Kubernetes o herde.

Verificado com duas variantes do mesmo Deployment, as duas rodando com UID 10001:

| Sonda | Onde está `runAsUser: 10001` | Resultado |
|---|---|---|
| `trivy-uid-a-nivel-pod.yaml` | `spec.template.spec.securityContext` | **FAIL: KSV020, KSV021** |
| `trivy-uid-b-nivel-container.yaml` | `containers[].securityContext` | nenhuma falha |

Um deles o Trivy acusa. E a cegueira é **inconsistente dentro do próprio Trivy**: na mesma
execução, `KSV012` (`runAsNonRoot`) lê corretamente o nível do pod e não dispara. Ou seja,
ele entende herança em uma regra e não entende em outras duas.

### Correção de duas classificações erradas minhas

**Primeiro erro: `KSV020` estava no balde errado.** A primeira versão deste arquivo o
colocava como "regra que o padrão da casa não adota", ao lado de `KSV030`, `KSV104` e
`KSV117`. A regra 3.2 exige `runAsUser` acima de 10000 — é exatamente o que `KSV020`
cobra. Ele não é irrelevante; é a intenção certa com implementação que não serve de
veredito.

O efeito do erro era concreto: o `runAsUser: 70` do Postgres aparecia como informativo e
**não barrava a revisão**, quando o padrão manda barrar até existir exceção aprovada. Hoje
o script julga a 3.2 por conta própria, com herança, e `KSV020` aparece como corroboração.

**Segundo erro: `KSV021` foi arrastado junto, e não deveria.** `KSV021` cobra **GID**, e a
tabela dos cinco requisitos da 3.2 não menciona `runAsGroup` em lugar nenhum. Ele não
corrobora requisito algum da casa, então voltou para `TRIVY_FORA_DO_PADRAO`. A correção do
`KSV020` estava certa; estendê-la ao par inteiro foi inferência preguiçosa, e dois KSVs com
números vizinhos não são a mesma regra.

`KSV021`, `KSV030`, `KSV104` e `KSV117` estão fora do padrão de verdade.

## O achado que mais pesa — a regra 3.3

Esta é a seção mais importante do arquivo, porque aqui o Trivy produz **a aparência de
cobertura sem a cobertura**. São três mecanismos diferentes, e nenhum dos três resolve.

### Mecanismo 1 — `trivy fs --scanners secret`

É o scanner dedicado a segredo. Testado contra uma sonda com seis valores de formatos
diferentes, gerada por `gerar-sonda-de-segredos.py`:

| Variável | Valor | Detectado? |
|---|---|---|
| `AWS_ACCESS_KEY_ID` | `AKIA` + 16 caracteres | **sim** — CRITICAL `aws-access-key-id` |
| `AWS_SECRET_ACCESS_KEY` | 40 caracteres | **sim** — CRITICAL `aws-secret-access-key` |
| `GITHUB_TOKEN` | `ghp_` + 36 caracteres | **sim** — CRITICAL `github-pat` |
| `SLACK_TOKEN` | `xoxb-` com três segmentos | **sim** — HIGH `slack-access-token` |
| `PRIVATE_KEY` | bloco `BEGIN RSA PRIVATE KEY` | **sim** — HIGH `private-key` |
| `DATABASE_URL` | `postgres://nyx:s3nh4-do-banco@pg.nyx-prod.svc:5432/nyx` | **NÃO** |

Todos os valores da sonda são sintéticos. Cinco de seis detectados.

Ele reconhece **formato conhecido de credencial de terceiro**. Senha arbitrária dentro de
string de conexão não tem formato reconhecível, e é exatamente o que o manifesto barrado
da Metacortex contém.

### Mecanismo 2 — `AVD-KSV-01010`, a regra que parece cobrir e não cobre

`trivy config` tem uma regra chamada **"ConfigMap with sensitive content"**. Pelo título,
qualquer um conclui que a regra 3.3 está coberta. Ela não está, por três motivos medidos.

**Motivo 1: alcança um lugar de três.** A mesma senha, em três lugares
(`trivy-senha-em-tres-lugares.yaml`):

| Onde está a senha | `AVD-KSV-01010` | `--scanners secret` | script da skill |
|---|---|---|---|
| `ConfigMap.data` | dispara | não | **sim** |
| `Secret.stringData` | **não dispara** | não | **sim** |
| `Deployment` → `env.value` | **não dispara** | não | **sim** |

`env.value` é a forma mais comum de vazamento e o caso do manifesto barrado.

**Motivo 2: quando dispara, não é a senha que ele achou.** A mensagem diz o que casou:

```text
ConfigMap 'lugar-um' ... stores sensitive contents in key(s) or value(s) '{"postgres"}'
```

Casou com `postgres`, o **esquema da URI**. A senha `S3nh4Secreta` não é mencionada. Num
outro teste a mesma regra casou com `{"CACHE_TTL", "mysql"}` — um tempo de expiração em
segundos e o nome de um banco. É lista de palavras-chave, não detecção de credencial:
dois falsos positivos e um falso negativo num único achado.

**Motivo 3: a localização é inútil.** `CauseMetadata.StartLine` aponta para a linha 3, que
é um separador `---`. Não dá para abrir o arquivo na linha do problema.

### Mecanismo 3 — o que o script faz

Detecção de **padrão de URI com credencial** (`esquema://usuario:senha@host`) mais nome de
variável sensível com valor literal, nos três lugares, com o campo exato no relatório.

### Conclusão da 3.3

Das três regras `proibido` do padrão, a que vaza credencial de banco de produção é a que o
Trivy menos cobre — e cobre de um jeito que **engana**, porque existe uma regra com nome
convincente que dispara às vezes, pelo motivo errado, no lugar errado.

Se alguém disser "o Trivy apontou o ConfigMap, está coberto": o que ele apontou foi a
palavra `postgres`.

## Nota de manutenção

Este mapa foi levantado contra o Trivy **0.52.2**. O `AVD-KSV-01010` foi descoberto
tardiamente, num manifesto de teste que não estava no experimento original — e a primeira
versão do script o **engoliu em silêncio**, porque só reportava IDs que já estavam num dos
dois mapas.

Por isso o script tem o balde `TRIVY APONTOU E O MAPA NÃO CONHECE`. Ao atualizar o Trivy,
rode a sonda e classifique o que cair lá em um dos três mapas:

| Mapa | Quando usar | Efeito no relatório |
|---|---|---|
| `TRIVY_PARA_REGRA` | o Trivy cobre a regra da casa **e acerta** | entra como violação, com o nível da casa |
| `TRIVY_CORROBORA` | a casa adota a regra, mas a implementação do Trivy não serve de veredito | lista separada; quem julga é o script |
| `TRIVY_FORA_DO_PADRAO` | a casa **não adota** a regra | informativo |

A distinção entre os dois últimos não é cosmética. `AVD-KSV-01010` passou pelo balde de
"fora do padrão" por um tempo, e o cabeçalho daquele bloco diz "o padrão da Metacortex não
adota estas regras" — afirmação falsa sobre a 3.3, que é `proibido`. Quem lesse o cabeçalho
e não a linha concluiria o oposto do padrão. Mesmo erro que `KSV020`/`KSV021`, duas vezes.

## Conclusão operacional

O Trivy é insumo, não veredito. A divisão de trabalho que esta skill adota:

| Fonte | Regras | Quantas |
|---|---|---|
| **Trivy**, com severidade traduzida | 2.1, 3.1, 3.6 | 3 |
| **`conferir_manifesto.py`** | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, **2.2**, 2.3, 2.4, 2.5, **3.2**, 3.3, 3.4, 3.5, 3.7 | 15 |
| **só leitura** | 2.6 | 1 |

Três das 15 do script fecham só com o passo 3: **2.2** (ele confere presença das duas
probes e se testam a mesma coisa, não o que tocam), **3.2** (os cinco requisitos, não os
caminhos de escrita) e **3.3** (senha em URI e nome sensível, não variável de nome
inocente).

Das 19 regras, o Trivy é o juiz de **3**. É menos do que a tabela de cobertura sugere, e a
diferença é a 3.2: ele a cobre, mas de um jeito que produz falso negativo e falso positivo
ao mesmo tempo, então a cobertura não vale como veredito.

Nada foi reimplementado por capricho: onde o Trivy cobre e acerta (2.1, 3.1, 3.6), ele é
invocado e a saída é traduzida. A 3.2 é a única em que o script julga por cima dele, e o
motivo está medido acima.
