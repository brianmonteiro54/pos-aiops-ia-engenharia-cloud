# Padrão de Manifests da Metacortex

Transcrição do wiki interno de Plataforma, mantido por Segurança & Compliance.
**Última revisão: 2026-07-29.** Aplica-se a todo manifesto que sobe para qualquer cluster
do parque, em qualquer ambiente.

> **Como ler este arquivo.** As regras abaixo são o texto da casa. Onde esta skill precisou
> **interpretar** algo que o padrão não diz explicitamente, há um bloco marcado
> `INTERPRETAÇÃO DA SKILL` com o motivo. Isso existe para que ninguém confunda o que a casa
> exige com o que eu decidi. Em divergência, o wiki prevalece.

## Vocabulário de obrigatoriedade

| Nível | Efeito |
|---|---|
| `obrigatório` | **a revisão barra sem discussão** |
| `recomendado` | a exceção precisa estar **escrita no PR** |
| `proibido` | **existe um caso registrado de estrago** |

Cada regra nasceu de um incidente, de uma auditoria ou de uma discussão que ninguém quer
ter de novo.

---

# Bloco 1 — Identidade e nomenclatura

## 1.1 Nome de recurso em kebab-case · `obrigatório`

Nome de objeto é minúsculo, palavras separadas por hífen, sem camelCase, sem underscore,
sem ponto. A API aceita menos do que as pessoas imaginam, e nome fora do padrão quebra
ferramenta de listagem e seletor escrito à mão.

```yaml
# errado
metadata:
  name: NyxAPI
# certo
metadata:
  name: nyx-api
```

## 1.2 Namespace no formato `<cliente>-<ambiente>` · `obrigatório`

Um cliente nunca compartilha namespace com outro, e ambiente nunca compartilha namespace
com ambiente. Ambientes válidos: `dev`, `stg`, `prod`. Exemplos: `nyx-prod`, `orion-stg`,
`helio-dev`.

Namespace fora desse formato **não é criado pelo Construct** e o manifesto não tem onde
aterrissar.

> **Esta regra é o que define o ambiente** para as regras 2.3, 2.4 e 2.5.

## 1.3 Rótulos obrigatórios em todo objeto · `obrigatório`

Todo objeto — Deployment, Service, ConfigMap, Secret, Job, CronJob — carrega os quatro
rótulos. São eles que sustentam o inventário, o rateio de custo por cliente e a resposta à
pergunta "quem é o dono disso?" às três da manhã.

```yaml
metadata:
  labels:
    app.kubernetes.io/name: nyx-api        # o componente
    app.kubernetes.io/instance: nyx-prod   # a instalação
    app.kubernetes.io/part-of: nyx         # o produto do cliente
    app.kubernetes.io/managed-by: platform # quem aplica: platform | argocd | helm
```

O rótulo curto `app:` sozinho **não atende**. Pode continuar existindo por compatibilidade
com seletores antigos, mas não substitui os quatro.

## 1.4 O seletor tem que casar com os rótulos do pod · `obrigatório`

É o erro mais comum do parque, e o mais silencioso: o objeto sobe, a revisão passa, e o
serviço simplesmente não tem para onde mandar tráfego. O `selector` do Service e o
`matchLabels` do Deployment precisam ser **idênticos aos rótulos do template do pod,
caractere por caractere**.

```yaml
# errado — um hífen de diferença e o Service fica sem endpoint
spec:
  selector:
    app: nyx-api
template:
  metadata:
    labels:
      app: nyxapi
```

> **INTERPRETAÇÃO DA SKILL.** O script compara por **subconjunto**: toda chave presente no
> seletor precisa existir no pod com o mesmo valor, mas o seletor pode usar menos chaves
> que o pod. É o que o Kubernetes de fato faz, e é o uso recomendado — selecionar por
> `name` e `instance` enquanto o pod tem os quatro rótulos da regra 1.3, porque `part-of` e
> `managed-by` não distinguem workloads.
>
> Leitura literal de "idênticos" exigiria o conjunto inteiro, o que tornaria a 1.3 e a 1.4
> incompatíveis na prática. Se a casa quiser a leitura estrita, o script muda numa linha —
> mas aí todo manifesto que seleciona por subconjunto passa a barrar.

## 1.5 Anotação de dono · `recomendado`

`metacortex.io/owner` com o time responsável, e `metacortex.io/runbook` com a URL do
procedimento de plantão **quando existir**. O plantão agradece.

## 1.6 Nome de container igual ao componente · `recomendado`

Container chamado `app`, `main` ou `container` obriga quem está lendo log a abrir o
manifesto para descobrir o que é. Use o nome do componente: `api`, `worker`, `scheduler`.

---

# Bloco 2 — Resiliência

## 2.1 `requests` e `limits` obrigatórios · `obrigatório`

Todo container declara `requests` e `limits` de CPU e memória. Container sem `requests` é
escalonado às cegas; container sem `limits` de memória derruba o nó do vizinho.

```yaml
resources:
  requests: {cpu: 100m, memory: 128Mi}
  limits:   {cpu: 500m, memory: 512Mi}
```

**Regra de bolso da casa:** `limits` de memória entre **1,5x e 2x** o consumo observado em
regime. Apertar demais gera reinício por OOM; folgar demais desperdiça reserva do cliente.

## 2.2 `readinessProbe` e `livenessProbe` obrigatórias · `obrigatório`

Sem probe, o Kubernetes considera o container pronto assim que o processo sobe — e manda
tráfego para aplicação que ainda está carregando. As duas probes são obrigatórias **em
qualquer ambiente**, e precisam apontar para endpoints que a aplicação **de fato expõe**.

A distinção importa: readiness responde "posso receber tráfego agora?" e liveness responde
"ainda estou vivo?". Apontar as duas para o mesmo endpoint que checa banco é um jeito
conhecido de derrubar a aplicação inteira quando o banco fica lento — a liveness falha, o
container reinicia, e **o reinício não conserta banco**.

> **INTERPRETAÇÃO DA SKILL.** O padrão não isenta `Job`, `CronJob` nem `initContainer`. O
> script isenta, porque container que roda e termina não tem o que sondar e o Kubernetes
> não aceita probe em `initContainer` comum. Se a casa discordar, é uma linha no script.

## 2.3 `replicas >= 2` em prod · `obrigatório`

Réplica única em produção significa indisponibilidade a cada deploy, a cada drain de nó e a
cada evicção. **Em dev e stg, uma réplica é aceitável.**

## 2.4 Estratégia de atualização · `obrigatório em prod`

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxUnavailable: 0
    maxSurge: 1
```

`maxUnavailable: 0` garante que a capacidade não cai durante o rollout. O custo é precisar
de espaço para uma réplica a mais durante a troca.

> **O padrão não prevê `Recreate` em prod.** Qualquer estratégia diferente da acima é
> violação de regra obrigatória e exige exceção aprovada por Segurança & Compliance. Isso
> inclui banco com volume único: o caso é real e legítimo, mas o caminho é a exceção
> formal, não a leitura flexível da regra.

## 2.5 `PodDisruptionBudget` em prod · `recomendado`

Todo workload de prod **com mais de uma réplica** declara um PDB com `minAvailable: 1` no
mínimo. Sem PDB, uma manutenção de nó pode derrubar todas as réplicas ao mesmo tempo.

## 2.6 `terminationGracePeriodSeconds` compatível com a aplicação · `recomendado`

O padrão de 30s não serve para worker que processa mensagem longa. Se a aplicação precisa
de mais tempo para drenar, declare — e garanta que ela **trata SIGTERM**.

---

# Bloco 3 — Segurança

> Segurança & Compliance mantém uma varredura de configuração no pipeline, com **Trivy**,
> rodando sobre o diretório de manifests. **Ela não substitui esta página**: o que a
> varredura não conhece continua sendo conferido na revisão, e **é onde a maior parte dos
> barramentos acontece.**

Esse parágrafo é a justificativa da skill inteira. O mapa medido está em
`cobertura-do-trivy.md`: de 19 regras, o Trivy é juiz de 3.

## 3.1 Tag `:latest` proibida · `proibido`

Imagem sempre em **tag imutável ou digest**. `:latest` torna impossível saber o que está
rodando, quebra rollback e faz dois pods do mesmo Deployment rodarem versões diferentes.

```yaml
# errado
image: registry.metacortex.io/nyx/api:latest
# certo
image: registry.metacortex.io/nyx/api:2.9.1
# melhor ainda
image: registry.metacortex.io/nyx/api@sha256:9f2c...
```

## 3.2 `securityContext` obrigatório · `obrigatório`

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 10001
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
```

`readOnlyRootFilesystem` exige que o que precisa escrever use `emptyDir` montado no caminho
certo. Dá trabalho uma vez e fecha uma classe inteira de escalonamento de privilégio.

> **INTERPRETAÇÃO DA SKILL — o nível de cada campo.** O padrão mostra um bloco único e não
> diz se ele é de pod ou de container. Fato da API do Kubernetes, verificado contra
> apiserver v1.31.5:
>
> | Campo | Nível aceito |
> |---|---|
> | `runAsNonRoot` | pod ou container — o container **herda** do pod |
> | `runAsUser` | pod ou container — o container **herda** do pod |
> | `allowPrivilegeEscalation` | **só container** |
> | `readOnlyRootFilesystem` | **só container** |
> | `capabilities` | **só container** |
>
> Os três últimos **não existem** em `PodSecurityContext`. O que acontece ao declará-los no
> pod depende do caminho do apply:
>
> | Caminho | Resultado |
> |---|---|
> | `kubectl apply` (strict, é o default) | **recusa**: `strict decoding error: unknown field` |
> | `kubectl apply --server-side` | **recusa**: `field not declared in schema` |
> | `kubectl apply --validate=false` | **aceita e descarta em silêncio** |
>
> O terceiro é o perigoso: o container fica sem `securityContext` nenhum e o YAML no Git
> continua dizendo que o workload está endurecido.

> **O QUE A SKILL NÃO EXIGE, E JÁ EXIGIU POR ERRO MEU.** O `runAsUser: 10001` acima é
> **exemplo**, não limiar. O padrão não estabelece piso de UID. Uma versão anterior desta
> skill cobrava "acima de 10000" como se fosse regra da casa — era invenção minha, e fazia
> o `runAsUser: 70` da imagem alpine do Postgres barrar indevidamente. Hoje a regra exige
> `runAsUser` **declarado e não-root**, o que `runAsNonRoot: true` já garante.
>
> Consequência: `KSV020`/`KSV021` do Trivy (UID/GID <= 10000) **não** correspondem a regra
> da casa e ficam no bloco informativo.

## 3.3 Segredo em texto puro proibido · `proibido`

Nenhum valor sensível entra no manifesto — **nem em `env.value`, nem em ConfigMap, nem em
comentário**. Sempre por referência a um Secret.

```yaml
# errado
env:
  - name: DATABASE_URL
    value: "postgres://nyx:s3nh4-do-banco@pg.nyx-prod.svc:5432/nyx"
# certo
env:
  - name: DATABASE_URL
    valueFrom:
      secretKeyRef: {name: nyx-db, key: url}
```

Lembre que Secret do Kubernetes é **base64, não criptografia**. O padrão vale para não
versionar o segredo no Git; a proteção em repouso é assunto do cluster.

> **COBERTURA DA SKILL.** O script varre `env.value`, `ConfigMap.data` e
> `Secret.stringData`. **Não varre comentário**, que o padrão também proíbe — comentário é
> descartado pelo parser de YAML antes de o script ver. Fica como instrução de leitura
> manual no passo 3.
>
> O Trivy não cobre esta regra. Demonstração em `cobertura-do-trivy.md`.

## 3.4 `automountServiceAccountToken: false` quando não fala com a API · `obrigatório`

A maioria das aplicações não precisa conversar com o apiserver, e montar o token por padrão
entrega uma credencial de graça para quem comprometer o container.

Passou de `recomendado` a `obrigatório` em **2026-07-29**.

## 3.5 ServiceAccount dedicada · `recomendado`

Não use a `default` do namespace. Uma ServiceAccount por workload, com o RBAC mínimo — e
**nenhum RBAC** quando ela não fala com a API.

## 3.6 `hostNetwork`, `hostPID` e `privileged` proibidos · `proibido`

Sem exceção em workload de cliente. Se for infraestrutura da própria Metacortex e precisar,
o pedido vai para Segurança com justificativa escrita.

> **Três campos, não quatro.** O padrão não menciona `hostIPC`. O Trivy tem `KSV008` para
> ele; a skill reporta como informativo, não como violação da 3.6.

## 3.7 Imagem só de registry interno · `obrigatório`

Todo `image:` aponta para `registry.metacortex.io`. Imagem de registry público entra pelo
**Loom**, que a espelha, escaneia e republica internamente.

---

# Bloco 4 — Vocabulário e conceitos

> **ESTE BLOCO FICOU FORA DA SKILL.** A justificativa está em `curadoria.md`, seção 7. Em
> resumo: é material de onboarding, não critério de revisão — o próprio padrão diz "quem já
> opera os clusters pode pular direto para os blocos anteriores". Nenhum item aqui produz
> veredito, e carregar 8 definições de objeto do Kubernetes no contexto de toda conferência
> gastaria orçamento sem mudar uma linha de relatório.
>
> As duas exceções que **vazaram para dentro da skill como conhecimento aplicado**, sem o
> texto: 4.5 (`port` x `targetPort`), usada ao gerar os Services, e 4.8 (probes), que
> reforça a 2.2.

Os oito itens do bloco, para quem precisar: 4.1 Pod · 4.2 ReplicaSet · 4.3 Deployment ·
4.4 Service · 4.5 A diferença entre `port` e `targetPort` · 4.6 Endpoints ·
4.7 ConfigMap e Secret · 4.8 Probes.

Dois deles têm valor operacional e não só didático, e vale registrar:

- **4.5** — `port` é a porta em que o Service escuta; `targetPort` é a porta em que o
  container realmente escuta. Normalmente são diferentes: o Service publica 80 e o
  container escuta 8080. É por isso que os manifests gerados apontam `targetPort` para o
  **nome** da porta e não para o número.
- **4.6** — o objeto `Endpoints` é onde se descobre que um Service não entrega tráfego: sem
  endereço nenhum, nenhum pod casou com o seletor. E **o campo de endereços não vem vazio
  quando não há nenhum — ele simplesmente não aparece na resposta da API.** Isso é
  diagnóstico de cluster, território da skill de triagem, não desta.

---

# Exceções

| Nível da regra | O que a exceção exige |
|---|---|
| `obrigatório` | aprovação **escrita** de Segurança & Compliance no PR, **com prazo de validade** |
| `recomendado` | só a justificativa no PR |
| `proibido` | **não existe exceção** para workload de cliente |

**Enquanto a aprovação não existe, o achado é violação e não conforme.** Comentário no YAML
explicando o desvio é insumo para a aprovação, não a aprovação. Tratar desvio justificado
como conforme transforma a revisão em carimbo.

---

# Histórico

| Data | Mudança |
|---|---|
| 2026-07-29 | `automountServiceAccountToken: false` passa de recomendado a **obrigatório** |
| 2026-05-14 | Adicionado o bloco de vocabulário a pedido do onboarding |
| 2026-03-02 | `replicas >= 2` em prod passa a ser **obrigatório** após o incidente de março na borda |
| 2025-11-20 | Proibida a tag `:latest` |

---

# Resumo por obrigatoriedade

| Nível | Regras | Total |
|---|---|---|
| `obrigatório` | 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3\*, 2.4\*, 3.2, 3.4, 3.7 | 11 |
| `proibido` | 3.1, 3.3, 3.6 | 3 |
| `recomendado` | 1.5, 1.6, 2.5, 2.6, 3.5 | 5 |

\* condicionadas a `prod`.

**14 regras barram o deploy. 5 exigem justificativa no PR.** O bloco 4 não produz regra.
