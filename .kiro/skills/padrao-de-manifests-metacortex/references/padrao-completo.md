# Padrão de Manifests da Metacortex — as 19 regras

Revisão **2026-07-29**.

> **Sobre este arquivo.** Ele é a transcrição operacional do padrão: cada regra com o
> número, a obrigatoriedade e o critério objetivo de aprovação. É esta a forma usada pelo
> `scripts/conferir_manifesto.py` e pelo relatório. Para o texto normativo com a redação
> original, consulte o documento da casa — em caso de divergência de redação, o documento
> original prevalece; em caso de divergência de **obrigatoriedade**, pare e pergunte,
> porque é a obrigatoriedade que decide se o deploy barra.

## Vocabulário

| Nível | Efeito na revisão |
|---|---|
| `obrigatório` | **barra o deploy.** Sem discussão |
| `proibido` | **barra o deploy.** Sem discussão |
| `recomendado` | passa, mas **exige justificativa escrita no PR** |

Regra `obrigatório` ou `proibido` só é dispensada por **exceção formal**: aprovação
escrita de Segurança & Compliance no PR, com prazo de validade. Ver o fim deste arquivo.

## Seção 1 — Nomenclatura e rótulos

### 1.1 — Nome em kebab-case · `obrigatório`
`metadata.name` só com minúsculas, dígitos e hífen, começando e terminando em
alfanumérico. Regex: `[a-z0-9]([a-z0-9-]*[a-z0-9])?`.
Reprova `NyxAPI`, `nyx_api`, `nyx.api`. Aprova `nyx-api`.

### 1.2 — Namespace `<cliente>-<ambiente>` · `obrigatório`
Ambiente restrito a `dev`, `stg` ou `prod`. Regex: `[a-z0-9-]+-(dev|stg|prod)`.
Namespace fora do formato o Construct não cria, e o manifesto não tem onde aterrissar.
**Esta regra é a que define o ambiente para as regras 2.3, 2.4 e 2.5.**

### 1.3 — Os quatro rótulos · `obrigatório`
Todo objeto carrega os quatro:

```yaml
app.kubernetes.io/name:        # o componente
app.kubernetes.io/instance:    # a instância (normalmente o namespace)
app.kubernetes.io/part-of:     # o sistema/cliente
app.kubernetes.io/managed-by:  # quem gerencia
```

Valem para `metadata.labels` do objeto **e** para `spec.template.metadata.labels` do pod.
O rótulo curto `app:` não substitui nenhum dos quatro.

### 1.4 — Seletor casa com os rótulos do pod · `obrigatório`
Em dois lugares distintos:

- `spec.selector.matchLabels` do Deployment/StatefulSet/DaemonSet x rótulos do template
- `spec.selector` do Service x rótulos do pod que ele deve atingir

**O critério é subconjunto, não igualdade de conjuntos**, igual ao que o Kubernetes faz:
toda chave presente no seletor precisa existir no pod **com o mesmo valor**,
caractere por caractere. O seletor **pode** usar menos chaves que o pod — selecionar por
`name` e `instance` enquanto o pod tem os quatro rótulos é correto e é o uso recomendado,
porque `part-of` e `managed-by` não distinguem workloads.

O que a regra proíbe é chave do seletor com valor divergente, ou ausente no pod.

São dois erros diferentes com sintomas diferentes. Seletor do controlador quebrado: o
controlador não governa os próprios pods. Seletor do Service quebrado: **o Service sobe
saudável e fica sem endpoint**, e o sintoma relatado é "subiu mas não responde".

### 1.5 — Anotação de dono · `recomendado`
`metadata.annotations` com `metacortex.io/owner`, em **todo objeto da lista da regra 1.3**
— inclusive ConfigMap, Secret e ServiceAccount, não só o Deployment. O escopo é o mesmo da
1.3 de propósito: objeto sem dono é objeto que ninguém remove quando o workload morre, e o
ConfigMap é justamente onde segredo e configuração errada sobrevivem ao resto.

`metacortex.io/runbook` tem escopo diferente e **não é exigido pela regra**. Runbook é
procedimento de plantão, e só existe para o que alguém é chamado a consertar de madrugada
— tipicamente o Deployment. Ausência de runbook em Service, ConfigMap ou ServiceAccount
não é achado. Dono e runbook respondem perguntas diferentes: "de quem é isto" e "o que eu
faço às 3 da manhã".

### 1.6 — Nome do container é o componente · `recomendado`
Reprova `app`, `main`, `container`. Use `api`, `worker`, `scheduler`, `migracao`.

## Seção 2 — Disponibilidade e recursos

### 2.1 — `requests` e `limits` · `obrigatório`
Os quatro valores, em **todo** container: `requests.cpu`, `requests.memory`,
`limits.cpu`, `limits.memory`. Container sem requests é escalonado às cegas.
Coberto pelo Trivy (`KSV011`, `KSV015`, `KSV016`, `KSV018`), **mas como LOW** — ver
`cobertura-do-trivy.md`.

### 2.2 — `readinessProbe` e `livenessProbe` · `obrigatório`
As duas declaradas, apontando para endpoints que a aplicação **de fato expõe**.

O padrão adverte explicitamente: apontar as duas para o mesmo endpoint que checa banco
derruba a aplicação quando o banco fica lento. O critério:

- readiness **pode** tocar a dependência — falhar tira o pod do Service, o que é correto
- liveness **não deve** tocar a dependência — falhar reinicia o container, e reiniciar não
  traz o banco de volta

Não se aplica a `Job`, `CronJob` nem `initContainer`: container que roda e termina não tem
o que sondar.

**O Trivy não verifica nada desta regra.** O script verifica a parte mecânica — que as
duas probes existem (faltar uma **barra**), e se as duas testam exatamente a mesma coisa
(aí vira `recomendado`, porque depende do que o teste toca). O que sobra para leitura é
se o endpoint existe na aplicação e o que cada um acessa.

### 2.3 — `replicas >= 2` · `obrigatório em prod`
Vale só quando o ambiente derivado da regra 1.2 é `prod`. `replicas` ausente conta como 1,
porque o default do Kubernetes é 1. Com 1 réplica há indisponibilidade a cada deploy,
drain de nó e evicção.

### 2.4 — Estratégia de atualização · `obrigatório em prod`
Em `prod`: `RollingUpdate` com `maxUnavailable: 0` e `maxSurge: 1`, para a capacidade não
cair durante o rollout. `Recreate` em prod é `recomendado`/justificável — aceitável para
carga que não tolera duas instâncias simultâneas, como banco com volume único.

Os dois campos aceitam inteiro ou percentual: `maxUnavailable: 0` e `maxUnavailable: "0%"`
são equivalentes e os dois passam. `maxSurge: 0` junto com `maxUnavailable: 0` **trava o
rollout para sempre** — o controlador não pode criar pod novo nem derrubar o antigo.

> **Tensão conhecida no padrão, que o revisor precisa saber.** `maxUnavailable: 1` com 3
> réplicas barra, e `Recreate` — que derruba a capacidade inteira — só exige justificativa.
> Pelo motivo declarado da regra, `Recreate` é estritamente pior. O caminho mais fácil para
> um autor sair do bloqueio é trocar para `Recreate` e escrever um parágrafo, **e isso
> piora a disponibilidade real.** Quando vier um PR com essa troca, trate a justificativa
> com rigor: `Recreate` só se sustenta quando duas instâncias não podem coexistir.

### 2.5 — `PodDisruptionBudget` · `recomendado`
Esperado em `prod` com `replicas >= 2`, e o PDB precisa **cobrir os rótulos daquele pod**.
Sem PDB, uma manutenção de nó pode derrubar todas as réplicas de uma vez.

### 2.6 — `terminationGracePeriodSeconds` · `recomendado`
O valor precisa ser **deliberado**, não necessariamente diferente do default de 30s.
Depende de a aplicação tratar SIGTERM e de quanto tempo leva para drenar.
Exige ler o código.

## Seção 3 — Segurança

### 3.1 — Tag `:latest` · `proibido`
Toda imagem com tag fixa. `:latest` torna o rollback impossível e o deploy não
reproduzível. Coberto pelo Trivy (`KSV013`).

### 3.2 — `securityContext` · `obrigatório`
Cinco requisitos. **O nível em que cada um pode ser declarado não é o mesmo**, e é a
dúvida que mais aparece na revisão:

| Requisito | Valor exigido | Nível aceito |
|---|---|---|
| `runAsNonRoot` | `true` | **pod ou container** — o container herda do pod |
| `runAsUser` | acima de 10000, nunca 0 | **pod ou container** — o container herda do pod |
| `allowPrivilegeEscalation` | `false` | **só container** |
| `readOnlyRootFilesystem` | `true` | **só container** |
| `capabilities.drop` | contém `ALL` (no máximo `NET_BIND_SERVICE` em `add`) | **só container** |

Os três últimos **não existem** na API no nível do pod. O que acontece quando alguém os
declara ali depende do caminho do apply — medido contra apiserver v1.31.5, kubectl v1.33:

| Caminho do apply | Resultado |
|---|---|
| `kubectl apply` (strict, é o default) | **recusa**: `strict decoding error: unknown field "spec.template.spec.securityContext.allowPrivilegeEscalation"` |
| `kubectl apply --server-side` | **recusa**: `field not declared in schema` |
| `kubectl apply --validate=false` ou `--validate=ignore` | **aceita e descarta em silêncio** |

O terceiro caso é o perigoso, e é o que justifica a regra: o objeto armazenado fica sem os
três campos, **o container fica sem `securityContext` nenhum**, e o YAML no Git continua
dizendo que o workload está endurecido. Verificado — depois do apply permissivo, o
`securityContext` do pod guardou só `fsGroup`, `runAsGroup`, `runAsNonRoot`, `runAsUser` e
`seccompProfile`.

Na revisão isso muda a conversa com o autor do PR, não o veredito: **barra nos dois
cenários.** Se a esteira usa apply strict, o deploy falha e alguém investiga. Se usa
`--validate=false` ou uma ferramenta de GitOps sem strict decoding, sobe inseguro e
ninguém percebe.

No pod ficam `fsGroup` e `seccompProfile`, que não fazem parte dos cinco requisitos.

Forma que satisfaz a regra com os dois herdáveis no pod:

```yaml
spec:
  template:
    spec:
      securityContext:            # nível de POD
        runAsNonRoot: true
        runAsUser: 10001
        fsGroup: 10001            # não é requisito da 3.2, mas é de pod
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: api
          securityContext:        # nível de CONTAINER
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
```

Repetir `runAsNonRoot` e `runAsUser` no container também é válido e tem precedência.

`readOnlyRootFilesystem: true` costuma exigir `emptyDir` montado nos caminhos em que a
aplicação escreve — e **qual caminho** é informação que só sai do código. Esta é a única
parte da 3.2 que o script não decide.

**Quem julga esta regra é `scripts/conferir_manifesto.py`, não o Trivy.** O Trivy a cobre
de um jeito que não serve de veredito: campos espalhados por regras de severidade
diferente, e `KSV020`/`KSV021` cegos para a herança do pod. Ver `cobertura-do-trivy.md`.

### 3.3 — Segredo em texto puro · `proibido`
Senha, token ou chave nunca em `env.value`, `ConfigMap.data` ou `Secret.stringData`
versionado. Use `valueFrom.secretKeyRef`.

Inclui **senha embutida em string de conexão**, que é a forma mais comum e a que passa
despercebida:

```yaml
# PROIBIDO
- name: DATABASE_URL
  value: "postgres://nyx:s3nh4-do-banco@pg.nyx-prod.svc:5432/nyx"
```

**O Trivy não detecta este caso.** `trivy fs --scanners secret` acha credencial de formato
conhecido (`AKIA…`, `ghp_…`) e não acha senha dentro de URI. `trivy config` tem o
`AVD-KSV-01010`, que **parece** cobrir — só olha ConfigMap, casa por palavra-chave e não
aponta a senha. Demonstração com os três lugares em `cobertura-do-trivy.md`.

### 3.4 — `automountServiceAccountToken: false` · `obrigatório`
Obrigatório desde esta revisão (2026-07-29) quando a aplicação não fala com o apiserver.
Declare nos dois lugares: na ServiceAccount e no `spec.template.spec` do pod.

### 3.5 — ServiceAccount dedicada · `recomendado`
Uma por workload. Usar a `default` do namespace, ou omitir `serviceAccountName`, reprova.

### 3.6 — `hostNetwork`, `hostPID`, `privileged` · `proibido`
Também `hostIPC`. Coberto pelo Trivy (`KSV008`, `KSV009`, `KSV010`, `KSV017`).

### 3.7 — Imagem só do registry interno · `obrigatório`
Prefixo `registry.metacortex.io/`. Imagem pública entra pelo **Loom**, que espelha,
escaneia e republica. Reprova `docker.io/library/nginx`, `postgres:16-alpine`.

## Resumo por obrigatoriedade

| Nível | Regras | Total |
|---|---|---|
| `obrigatório` | 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3*, 2.4*, 3.2, 3.4, 3.7 | 11 |
| `proibido` | 3.1, 3.3, 3.6 | 3 |
| `recomendado` | 1.5, 1.6, 2.5, 2.6, 3.5 | 5 |

\* condicionadas a `prod`.

**14 regras barram o deploy. 5 exigem justificativa no PR.**

## Processo de exceção

Exceção a regra `obrigatório` ou `proibido` exige, no PR:

1. aprovação **escrita** de Segurança & Compliance
2. **prazo de validade** da exceção
3. o motivo técnico pelo qual cumprir a regra é pior que não cumprir

Enquanto os três não existem, **o achado é violação e não conforme**. Comentário no YAML
explicando o desvio é insumo para a aprovação, não a aprovação. Tratar desvio justificado
como conforme transforma a revisão em carimbo.
