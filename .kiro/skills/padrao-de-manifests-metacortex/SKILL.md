---
name: padrao-de-manifests-metacortex
description: >-
  Confere e gera manifests de Kubernetes contra o Padrão de Manifests da Metacortex
  (19 regras de nomenclatura, resiliência e segurança). Use ao revisar um YAML ANTES do
  apply, ao escrever manifests novos a partir de um projeto, ao responder "isto passa na
  revisão?", ao preparar PR de manifesto, ou quando o YAML é recusado por erro de schema ou
  campo inválido, ou quando alguém diz "esse manifesto não sobe" e o erro é do YAML. Serve
  para gerar manifesto de um projeto que ainda não tem nenhum: peça o repositório antes,
  porque porta, probe e variável se descobrem lendo o código. NÃO use quando o objeto já
  está no cluster e o problema é de execução (pod que não sobe, CrashLoopBackOff,
  OOMKilled, ImagePullBackOff, Service sem endpoint, 503) isso é triagem de cluster, outra
  skill. Nem para explicar conceito de Kubernetes. O limite é a fonte da verdade: esta
  skill lê arquivo YAML e código-fonte, nunca o estado do cluster.
compatibility: >-
  Requer python3 com PyYAML. O trivy é opcional: com ele o script julga 15 regras e traduz
  outras 3 (2.1, 3.1, 3.6); sem ele as mesmas 15 continuam conferidas e as 3 ficam sem
  conferência, com aviso na saída. A 19a regra, 2.6, é manual em qualquer caso. A 3.2 é
  julgada pelo script e não depende do trivy. Não requer acesso ao cluster.
metadata:
  autor: brian-monteiro
  versao: "1.0"
  revisao-do-padrao: "2026-07-29"
---

# Padrão de Manifests da Metacortex

O padrão tem **19 regras acionáveis** em três seções: nomenclatura e rótulos (1.x),
disponibilidade e recursos (2.x), segurança (3.x). O texto completo, com a obrigatoriedade
de cada uma, está em `references/padrao-completo.md`. Leia esse arquivo quando precisar
citar uma regra no relatório ou decidir se algo é `obrigatório`, `recomendado` ou
`proibido`: a diferença decide se o deploy barra ou só exige justificativa no PR.

## Os dois modos

| Modo | Entrada | Saída |
|---|---|---|
| **conferência** | YAML existente | relatório de violações por objeto e campo |
| **escrita** | repositório de um projeto | manifests que passam nas 19 regras |

Os dois começam igual: descobrir o que a ferramenta já responde, para não gastar leitura
com o que o Trivy diz de graça.

## Modo conferência

### Passo 1: Trivy primeiro, sempre

```bash
trivy config <arquivo-ou-diretorio>
```

Rode isto **antes** de ler o YAML regra por regra. O Trivy cobre por inteiro as regras
**2.1** (requests e limits), **3.1** (tag `:latest`) e **3.6** (hostNetwork, hostPID,
privileged), e cobre em parte a **3.2** (securityContext).

**Rode este comando uma vez, na primeira conferência de um conjunto de manifests, para ver
a saída crua.** Nas conferências seguintes o passo 2 já faz esta chamada por você: não é
preciso repetir. Vale voltar aqui quando alguém contestar o relatório dizendo "mas o Trivy
passou", porque a saída crua é a evidência.

Três armadilhas na saída crua, e as três já estão tratadas pelo script do passo 2:

- **A severidade do Trivy não é a obrigatoriedade da casa.** Ele reporta "requests de CPU
  não especificado" como LOW; na Metacortex requests e limits são `obrigatório` e barram o
  deploy. Quem lê o Trivy direto conclui que é opcional.
- **O Trivy não julga a regra 3.2 de forma confiável.** Ele confere os cinco requisitos por
  regras separadas, com severidades de LOW a HIGH, e não tem o conceito do bloco inteiro
  que a casa exige. Por isso a 3.2 é julgada pelo script.
- **O Trivy tem regras que o padrão não adota**, e elas saem no bloco informativo:
  `KSV020`/`KSV021` (UID/GID <= 10000 (**o padrão não estabelece piso de UID**),
  `KSV008` (hostIPC) a regra 3.6 proíbe três campos e não inclui este), `KSV030`,
  `KSV104`, `KSV117`. E tem o `AVD-KSV-01010`, cujo nome sugere que cobre a regra 3.3 e
  que **não cobre**.

### Passo 2: o script, que julga 15 das 19 regras

```bash
python3 scripts/conferir_manifesto.py <arquivo-ou-diretorio>
python3 scripts/conferir_manifesto.py <caminho> --json        # para encadear
python3 scripts/conferir_manifesto.py <caminho> --sem-trivy   # sem o trivy instalado
```

Código de saída: `0` nada barra, `1` ao menos uma violação obrigatória ou proibida,
`2` erro de uso ou YAML inválido.

O script invoca o Trivy por dentro e **traduz** cada `KSV` para a regra da casa com a
obrigatoriedade da casa, separando em blocos distintos o que corrobora a 3.2, o que o
padrão não adota, e o que o mapa de cobertura ainda não classificou.

Divisão de trabalho, somando 19:

| Juiz | Regras | Quantas |
|---|---|---|
| **script** | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, **2.2** (só a parte mecânica), 2.3, 2.4, 2.5, **3.2**, 3.3, 3.4, 3.5, 3.7 | 15 |
| **Trivy**, traduzido pelo script | 2.1, 3.1, 3.6 | 3 |
| **só leitura** | 2.6 | 1 |

O script cobre o que se verifica olhando só o YAML: parsing, comparação de string,
presença de campo, igualdade entre dois campos. É onde leitura humana erra e script não
erra. Três regras ficam **parcialmente** com ele e exigem o passo 3 para fechar: 2.2 (ele
confere que as duas probes existem e se testam a mesma coisa, não o que elas tocam), 3.2
(os cinco requisitos, não os caminhos de escrita) e 3.3 (senha em URI e nome de variável
sensível, não variável de nome inocente).

Cinco comportamentos do script que vale conhecer antes de confiar no relatório:

- **Deriva o ambiente do nome do namespace.** As regras 2.3, 2.4 e 2.5 só valem em `prod`.
  Exigir `replicas >= 2` em `nyx-dev` é um erro que faz o revisor desconfiar do resto.
- **Distingue o seletor do Deployment do seletor do Service.** São dois erros diferentes
  com sintomas diferentes, e o relatório cita qual objeto está quebrado, porque o conserto
  é em lugares diferentes.
- **Na regra 1.4, compara por subconjunto**, como o Kubernetes faz: toda chave do seletor
  precisa existir no pod com o mesmo valor, mas o seletor pode usar menos chaves que o
  pod. Selecionar por `name` e `instance` com o pod tendo os quatro rótulos é correto.
- **Na regra 3.2, entende a herança pod → container.** `runAsNonRoot` e `runAsUser`
  declarados no pod satisfazem a regra. Os outros três requisitos não existem no nível do
  pod, e o relatório avisa quando alguém os declarou ali por engano. **Não há piso de
  UID**: o padrão exige `runAsUser` declarado e não-root, nada além disso.
- **Na regra 2.4, qualquer `strategy.type` diferente de `RollingUpdate` barra em prod.**
  O padrão não prevê `Recreate`. Banco com volume único é caso legítimo, e o caminho é a
  exceção formal.
- **Na regra 2.2, não exige probe de `Job`, `CronJob` nem `initContainer`.** Container que
  roda e termina não tem o que sondar. Probe ausente ali não é achado.

### Passo 3: abra o projeto para as quatro regras que o YAML não responde

Nenhuma ferramenta e nenhum script decide estas. A resposta está no código da aplicação:

| Regra | Nível | O que descobrir no código |
|---|---|---|
| **2.2** probes | `obrigatório` | quais endpoints existem e **o que cada um toca**. Procure rota de saúde; se não houver, escolha rotas de negócio pelo que acessam. Faltar uma das duas **barra** |
| **2.6** período de graça | `recomendado` | a aplicação trata SIGTERM? Fecha conexão ou morre junto com as requisições em curso? Sem justificativa no PR fica **pendente**, não conforme |
| **3.2** `readOnlyRootFilesystem` | `obrigatório` | **em que caminhos** a aplicação escreve, para montar `emptyDir` ali. O script já conferiu os cinco requisitos; aqui falta só o caminho |
| **3.3** variáveis | `proibido` | quais nomes o código de fato lê, e qual delas é segredo. O script pega senha em URI e nome sensível; falta a variável de nome inocente |

**O que fazer quando você não tem o projeto para abrir.** Revisão feita só com o YAML na
mão é comum, e aí nada do passo 3 se confirma. Não barre por isso, e não declare conforme:

| Situação | Veredito |
|---|---|
| o script achou violação mecânica (probe faltando, campo da 3.2 ausente, senha em URI) | **barra**: isso não depende do projeto |
| o script não achou nada e você não pode abrir o projeto | **pendente**, bloco 3, dizendo qual insumo falta |
| você abriu o projeto e confirmou o problema | **barra** |

"Barra se não conseguir confirmar" vale para quando o insumo **existe e contradiz** o
manifesto, não para quando o insumo não foi fornecido. Bloquear um PR por falta de acesso
ao repositório é transferir para o autor um problema que é seu.

**Quando o workload é imagem de terceiro** (Postgres, Redis, nginx, RabbitMQ) não existe
"código da aplicação" para abrir, e isso é comum, não exceção: a regra 3.7 obriga tudo a
passar pelo registry interno, inclusive componente de prateleira. Nesse caso a fonte muda:

- **probes**: use o teste nativo do componente (`pg_isready`, `redis-cli ping`) na
  **readiness**. Veja se o binário existe na variante da imagem e **se há autenticação
  ligada**: um `redis-cli ping` contra Redis com `requirepass` responde `NOAUTH` e a
  readiness nunca fica pronta.
  Para a **liveness** de componente de prateleira, `tcpSocket` é aceitável e muitas vezes
  é a escolha certa: o teste nativo costuma ser a própria dependência, e liveness que
  falha reinicia o container. A troca é consciente: `tcpSocket` não detecta processo vivo
  mas travado. Quando o componente tem um teste de vida que **não** toca o armazenamento,
  prefira ele; quando não tem, registre a escolha no `DECISOES.md`
- **caminhos de escrita**: o `VOLUME` do Dockerfile upstream e a documentação da imagem
  (`PGDATA`, `/data`, `/var/run/...`)
- **período de graça**: se há persistência ligada e quanto o componente leva para gravar
  e sair no SIGTERM

No `DECISOES.md`, cite a documentação da imagem e a tag exata em lugar de arquivo e linha.

A regra 2.2 tem uma armadilha que o próprio padrão descreve: apontar readiness **e**
liveness para o mesmo endpoint que checa banco derruba a aplicação quando o banco fica
lento. O critério é a divisão:

- **readiness** pode tocar a dependência: falhar tira o pod do Service, o que é correto
- **liveness** não deve tocar a dependência: falhar **reinicia o container**, e reiniciar
  não traz o banco de volta

Evite `tcpSocket` para readiness de aplicação web: a porta aceita conexão antes de o
servidor estar pronto para responder.

### Passo 4: relatório

Agrupe em três blocos, nesta ordem, e **cite objeto e campo** em cada achado:

1. **BARRA A REVISÃO**: violação de regra `obrigatório` ou `proibido`
2. **EXIGE JUSTIFICATIVA NO PR**: regra `recomendado`, e também regra `recomendado` que
   você confirmou estar tecnicamente correta mas **sem registro escrito**. É o bloco do
   "pendente": não barra, não é conforme, e o que falta é o texto no PR
3. **NÃO CONFERIDO**: o que exige abrir o projeto, com o que falta descobrir e o nível da
   regra, para o revisor saber se o veredito pendente barra ou não

Uma regra pode aparecer no bloco 2 **e** no 3, e isso não é inconsistência: no 3 você diz
o que falta descobrir, no 2 você dá o veredito. A 2.6 é o caso típico.

**Quando o insumo não veio, diga isso em vez de assumir.** Se você recebeu só o YAML, o
corpo do PR e o `DECISOES.md` não estão na sua mão, e "não existe justificativa" é
diferente de "não me deram a justificativa". Escreva `pendente: não foi fornecido o
DECISOES.md nem o corpo do PR`, e siga. Inventar um veredito sobre insumo que você não
viu é o jeito mais rápido de o relatório perder credibilidade.

"Seletor errado" não diz onde consertar. `Service/nyx-api em nyx-prod, campo
spec.selector: diz 'app: nyx-api' e o rótulo do pod é 'app: nyxapi'` diz.

Para cada violação, inclua **a consequência operacional**, não só o nome da regra. O
revisor precisa saber que um seletor com um hífen de diferença faz o Service subir
saudável e ficar sem endpoint para sempre: é isso que explica o "subiu mas não responde"
que o cliente relatou.

## Modo escrita

A ordem é obrigatória: **ler o projeto antes de escrever YAML**, porque três decisões do
manifesto não têm default seguro.

### Passo 1: levantar no repositório

- porta em que a aplicação escuta
- endpoints de saúde, e o que cada um toca (se não houver, quais rotas de negócio servem)
- variáveis de ambiente que o código lê, com os nomes exatos
- caminhos em que a aplicação escreve em disco
- se há migração de schema, e **se ela é um comando separado ou roda dentro do processo**

Esse último item decide a arquitetura do manifesto. Migração num entrypoint com duas
réplicas em prod são duas migrações concorrentes; se existe comando separado, extraia para
um `Job`. `initContainer` **não** resolve, porque roda uma vez por pod. Se a migração está
dentro do código da aplicação, não há como extrair sem mudar o código, e então
`replicas: 1` deixa de ser default de dev e passa a ser requisito.

### Passo 2: escrever

Comece pelo namespace, porque ele decide quais regras valem. Depois Secret, ServiceAccount
e ConfigMap, depois o workload, depois Service e PDB.

Três erros que o padrão pega e que são fáceis de cometer:

- **Copie o bloco de rótulos do template para o seletor, não digite de novo.** A regra 1.4
  é igualdade caractere por caractere.
- **Os cinco requisitos da 3.2 não moram todos no mesmo nível.** `runAsNonRoot` e
  `runAsUser` valem no pod e são herdados pelo container. `allowPrivilegeEscalation`,
  `readOnlyRootFilesystem` e `capabilities` **não existem** no nível do pod. Com apply
  strict o apiserver recusa; com `--validate=false` ele **aceita e descarta em silêncio**,
  e aí o container fica sem `securityContext` nenhum enquanto o YAML diz o contrário. No
  pod ficam também `fsGroup` e `seccompProfile`, que não são requisito da 3.2. A tabela
  campo por campo e os três caminhos de apply estão em `references/padrao-completo.md`.
- **`readOnlyRootFilesystem: true` sem o volume certo não sobe.** Ligue a flag e monte
  `emptyDir` nos caminhos que você descobriu no passo 1.

### Passo 3: validar antes de entregar

```bash
python3 scripts/conferir_manifesto.py <diretorio>        # deve sair com rc=0
kubectl apply --dry-run=server -f <arquivo>              # valida contra o apiserver
```

`--dry-run=client` não serve: ele não valida o schema contra o apiserver.

Registre num `DECISOES.md` ao lado dos manifests tudo que exigiu abrir o código, **com o
arquivo e a linha**. Esse arquivo é o que sustenta o PR; sem ele o revisor não tem como
saber se `terminationGracePeriodSeconds: 30` foi deliberado ou copiado.

## Exceção e desvio não são a mesma coisa

Quando o padrão não pode ser cumprido, o padrão exige exceção com aprovação escrita de
Segurança & Compliance no PR e prazo de validade.

**Enquanto a aprovação não existe, reporte como violação, não como conforme.** Um
`replicas: 1` em prod com um comentário explicando o motivo continua barrando a revisão,
o comentário é insumo para a aprovação, não a aprovação. Marcar como conforme porque está
justificado transforma a skill em carimbo.

O mesmo vale ao gerar: se você escreveu um desvio consciente, o relatório da sua própria
skill deve continuar apontando. Foi assim que o `replicas: 1` e o `Recreate` do Postgres
em `orion-prod` continuaram visíveis: os dois são casos legítimos de banco com volume
único, e os dois seguem barrando até existir aprovação escrita.

**E não invente regra para fechar o raciocínio.** Três exigências desta skill não existiam
no padrão e foram removidas quando confrontadas com o wiki: piso de UID na 3.2, `Recreate`
como alternativa aceitável na 2.4, e `hostIPC` na 3.6. Quando a regra parecer incompleta,
abra `references/padrao-completo.md` em vez de completar de cabeça, o que está marcado
`INTERPRETAÇÃO DA SKILL` é interpretação, o resto é texto da casa.

## Referências

- `references/padrao-completo.md`: as 19 regras com obrigatoriedade e o processo de
  exceção. Consulte para citar regra ou decidir se barra.
- `references/cobertura-do-trivy.md`: o mapa de cobertura verificado por experimento,
  o motivo do falso positivo de `KSV020`/`KSV021`, e a demonstração de que o Trivy **não
  detecta senha dentro de string de conexão**. Consulte quando alguém disser "o Trivy
  passou, então está certo".
