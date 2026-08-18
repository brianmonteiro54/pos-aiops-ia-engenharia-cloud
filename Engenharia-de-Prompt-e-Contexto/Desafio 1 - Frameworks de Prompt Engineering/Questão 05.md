# Questão 05 — Modernizar deployment legado

**Framework:** B-A-B (Before, After, Bridge)

---

## Prompt

````text
[BEFORE — estado atual problemático]
Em uma revisão de produção da Hill Valley Tech, Doc Brown (CTO) encontrou o manifest do Chronos, o API gateway que é ponto de entrada de todo o tráfego da empresa. O arquivo foi escrito pelo George há três anos e ninguém mexeu desde então. Ele está fora de várias práticas hoje obrigatórias no padrão interno.

Manifest legado atualmente aplicado no cluster:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chronos-api
  namespace: production
spec:
  replicas: 1
  selector:
    matchLabels:
      app: chronos-api
  template:
    metadata:
      labels:
        app: chronos-api
    spec:
      containers:
      - name: chronos-api
        image: chronos-api:latest
        ports:
        - containerPort: 8080
        env:
        - name: DB_PASSWORD
          value: "H1llV4ll3y2023!"
        - name: JWT_SECRET
          value: "flux-capacitor-secret-key"
        - name: LEDGER_HOST
          value: "ledger-db.internal.hvt.io"
```

Problemas conhecidos deste estado atual:

- replicas: 1, ou seja, ponto único de falha no serviço que recebe todo o tráfego.
- image: chronos-api:latest, sem versionamento, sem rollback confiável e sem política de pull previsível.
- DB_PASSWORD e JWT_SECRET em texto puro no manifest, versionados no Git.
- Nenhuma liveness ou readiness probe: o Kubernetes não sabe se o pod está saudável nem se pode receber tráfego.
- Nenhum resource requests/limits: o pod pode sofrer throttling ou ser morto por OOM sem previsibilidade, e o scheduler não tem informação para alocar.
- Nenhum securityContext: container roda como root.
- Nenhuma estratégia de rollout, disruption budget ou anti-afinidade definida.

[AFTER — estado desejado]
O mesmo Deployment, funcionalmente equivalente, mas aderente ao padrão de produção da empresa:

- Alta disponibilidade: múltiplas réplicas distribuídas entre nós e zonas, com PodDisruptionBudget e estratégia de rolling update sem downtime.
- Imagem versionada por tag imutável, nunca latest, com imagePullPolicy coerente.
- DB_PASSWORD e JWT_SECRET fora do manifest, referenciados a partir de Secret via secretKeyRef.
- resource requests e limits definidos para CPU e memória, com valores justificados.
- liveness e readiness probes configuradas (e startup probe se fizer sentido), com endpoints, thresholds e timeouts explicados.
- securityContext não-root: runAsNonRoot, runAsUser/runAsGroup, fsGroup, allowPrivilegeEscalation false, capabilities dropadas e readOnlyRootFilesystem quando viável.
- Labels padronizadas, anotações úteis para operação e serviceAccountName dedicada, sem uso da default.
- Manifest pronto para ser aplicado no namespace production sem interromper o tráfego atual.

[BRIDGE — o que você deve fazer para sair do Before e chegar no After]
Você é um engenheiro de plataforma sênior especializado em Kubernetes em produção. Faça a ponte entre os dois estados:

1. Entregue o manifest modernizado completo do Deployment chronos-api, aplicável no namespace production.
2. Entregue também os objetos auxiliares necessários para o After funcionar de verdade: o Secret (com placeholders, nunca com o valor real), o PodDisruptionBudget e a ServiceAccount.
3. Para cada mudança em relação ao manifest legado, explique em comentário no YAML o problema do Before que ela resolve.
4. Justifique os valores escolhidos de réplicas, requests, limits e thresholds das probes, sem inventar dados que não foram fornecidos: quando precisar assumir algo, marque como premissa a validar.
5. Descreva a ordem segura de migração, ou seja, o que aplicar primeiro para o serviço que recebe todo o tráfego não cair durante a transição, incluindo o que precisa ser feito fora do manifest (criar o Secret, escolher e publicar a tag da imagem, expor o endpoint de health).
6. Aponte o que ficou fora do escopo deste manifest mas continua sendo risco no padrão da empresa (por exemplo HPA, NetworkPolicy, rotação dos segredos), em uma lista curta ao final.

Formato: primeiro os blocos YAML comentados em português, na ordem em que devem ser aplicados. Depois, uma seção "Migração" com a sequência de passos e uma seção "Fora de escopo / riscos remanescentes" em lista.
````

---

## Modelo

**GPT-5.6 Sol Max (OpenAI)**

Escolhido porque a questão é a mais longa e mais interdependente do desafio: exige quatro objetos coerentes entre si, comentário justificando cada mudança contra o Before, marcação de premissa em todo valor assumido e uma ordem de migração que não derrube um serviço tier-0. É o tipo de tarefa em que o modelo mais forte em contexto longo e consistência interna paga o custo.

---

## Output

> Trace de tool calls e o painel de progresso da interface foram omitidos: não fazem parte da resposta do modelo.

Vou estruturar os quatro recursos na ordem segura de aplicação e explicitar, no próprio YAML, todas as premissas que precisam ser validadas antes do rollout.

```yaml
# 1/4 — Aplicar primeiro.
# O Deployment legado usa implicitamente a ServiceAccount "default".
# Uma identidade dedicada permite aplicar RBAC mínimo caso o Chronos precise,
# futuramente, acessar a API do Kubernetes.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: chronos-api
  namespace: production
  labels:
    # Labels recomendadas por Kubernetes para identificação operacional.
    app.kubernetes.io/name: chronos-api
    app.kubernetes.io/instance: chronos-api-production
    app.kubernetes.io/component: api-gateway
    app.kubernetes.io/part-of: hill-valley-tech
  annotations:
    hvt.io/description: "Identidade dedicada do API gateway Chronos"
# O gateway não declarou necessidade de acessar a API do Kubernetes.
# Não montar o token reduz a superfície de ataque caso o container seja comprometido.
automountServiceAccountToken: false
```

```yaml
# 2/4 — Aplicar depois da ServiceAccount e antes do Deployment.
#
# ATENÇÃO:
# - Estes valores são placeholders deliberados; nunca devem chegar assim à aplicação.
# - O Secret deve ser materializado por um gerenciador de segredos ou pipeline seguro.
# - Não substituir os placeholders por valores reais em um arquivo versionado no Git.
# - stringData evita colocar base64 manual no exemplo. Base64 não é criptografia.
apiVersion: v1
kind: Secret
metadata:
  name: chronos-api-secrets
  namespace: production
  labels:
    app.kubernetes.io/name: chronos-api
    app.kubernetes.io/instance: chronos-api-production
    app.kubernetes.io/component: api-gateway
    app.kubernetes.io/part-of: hill-valley-tech
  annotations:
    hvt.io/description: "Referências secretas consumidas pelo Chronos"
type: Opaque
stringData:
  # Resolve o problema do Before em que a senha estava em texto puro
  # dentro do Deployment e versionada no Git.
  DB_PASSWORD: "__INJETAR_DB_PASSWORD_POR_CANAL_SEGURO__"

  # Resolve o mesmo problema para a chave usada na validação/assinatura de JWT.
  JWT_SECRET: "__INJETAR_JWT_SECRET_POR_CANAL_SEGURO__"
```

```yaml
# 3/4 — Aplicar antes da alteração do Deployment.
#
# Este PDB passa a proteger tanto o pod legado quanto os novos pods porque usa
# a label histórica app=chronos-api, presente nos dois modelos.
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: chronos-api
  namespace: production
  labels:
    app.kubernetes.io/name: chronos-api
    app.kubernetes.io/instance: chronos-api-production
    app.kubernetes.io/component: api-gateway
    app.kubernetes.io/part-of: hill-valley-tech
  annotations:
    hvt.io/description: "Proteção contra indisponibilidade por interrupções voluntárias"
spec:
  # Com 3 réplicas, permite no máximo uma interrupção voluntária por vez.
  # PREMISSA A VALIDAR: duas instâncias suportam o tráfego durante manutenção.
  #
  # Enquanto existir somente o pod legado, disruptionsAllowed será zero.
  # Isso protege o singleton durante a migração, embora possa bloquear um drain
  # até que pelo menos dois novos pods estejam saudáveis.
  minAvailable: 2
  selector:
    matchLabels:
      # A label legada é intencional: protege pods antigos e novos.
      app: chronos-api
```

```yaml
# 4/4 — Aplicar somente após:
# - substituir a tag e o digest da imagem;
# - criar o Secret com valores reais por canal seguro;
# - confirmar que a imagem implementa os três endpoints de health;
# - validar execução como UID/GID 10001 e filesystem raiz somente leitura.
apiVersion: apps/v1
kind: Deployment
metadata:
  name: chronos-api
  namespace: production
  labels:
    # Labels padronizadas substituem a identificação baseada somente em "app".
    app.kubernetes.io/name: chronos-api
    app.kubernetes.io/instance: chronos-api-production
    app.kubernetes.io/component: api-gateway
    app.kubernetes.io/part-of: hill-valley-tech
    # Substituir pelo mesmo valor da tag imutável usada em spec.template.
    app.kubernetes.io/version: "SUBSTITUIR_TAG_IMUTAVEL"
  annotations:
    # Anotações úteis para inventário e histórico operacional.
    hvt.io/description: "API gateway de entrada do tráfego de produção"
    hvt.io/criticality: "tier-0"
    kubernetes.io/change-cause: "Alta disponibilidade, probes, recursos e hardening de segurança"
spec:
  # Três réplicas eliminam o singleton e permitem manter duas disponíveis
  # durante uma interrupção voluntária.
  #
  # PREMISSA A VALIDAR: o cluster possui capacidade para 3 pods mais 1 pod
  # temporário de surge, e pelo menos 2 zonas/nós scheduláveis.
  replicas: 3

  # Mantém versões anteriores para rollback; o Before não estabelecia limite.
  revisionHistoryLimit: 10

  # Um pod precisa permanecer Ready por 10 segundos antes de ser considerado
  # disponível pelo rollout, evitando avançar com uma prontidão instável.
  minReadySeconds: 10

  # Se a versão não progredir em 10 minutos, o Deployment é marcado como falho.
  # Isso não remove automaticamente os pods antigos que ainda estejam saudáveis.
  progressDeadlineSeconds: 600

  strategy:
    type: RollingUpdate
    rollingUpdate:
      # O Before não definia estratégia explícita. Zero indisponíveis faz o
      # controller manter os pods antigos até os novos ficarem Ready.
      maxUnavailable: 0
      # Cria somente um pod adicional por vez, limitando consumo temporário
      # e permitindo observar a nova versão gradualmente.
      maxSurge: 1

  selector:
    matchLabels:
      # NÃO adicionar labels padronizadas a este seletor.
      # O seletor de um Deployment é imutável; manter app=chronos-api permite
      # atualizar o objeto existente e preserva compatibilidade com o Service atual.
      app: chronos-api

  template:
    metadata:
      labels:
        # Mantida para compatibilidade com o selector imutável e com o Service legado.
        app: chronos-api
        app.kubernetes.io/name: chronos-api
        app.kubernetes.io/instance: chronos-api-production
        app.kubernetes.io/component: api-gateway
        app.kubernetes.io/part-of: hill-valley-tech
        app.kubernetes.io/version: "SUBSTITUIR_TAG_IMUTAVEL"
      annotations:
        hvt.io/health-endpoints: "/health/startup,/health/ready,/health/live"
    spec:
      # Resolve o uso implícito da ServiceAccount "default".
      serviceAccountName: chronos-api
      automountServiceAccountToken: false

      # Dá tempo para o processo tratar SIGTERM e drenar conexões.
      # PREMISSA A VALIDAR: 30 segundos cobrem a duração normal das requisições.
      terminationGracePeriodSeconds: 30

      securityContext:
        # O Before não possuía securityContext e podia executar como root.
        runAsNonRoot: true

        # PREMISSA A VALIDAR: a imagem e seus arquivos são compatíveis com estes IDs.
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
        fsGroupChangePolicy: OnRootMismatch

        # Aplica o perfil seccomp padrão do runtime para restringir syscalls.
        seccompProfile:
          type: RuntimeDefault

      # Distribui réplicas de maneira equilibrada entre zonas e nós.
      #
      # PREMISSA A VALIDAR: todos os nós elegíveis possuem as labels
      # topology.kubernetes.io/zone e kubernetes.io/hostname.
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: chronos-api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: chronos-api

      affinity:
        podAntiAffinity:
          # O Before não tinha anti-afinidade. As preferências reforçam que
          # réplicas não devem compartilhar domínio de falha.
          #
          # Elas são "preferred", e não "required", para não impedir o pod de
          # surge durante o rollout. O maxSkew acima continua impondo equilíbrio.
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: chronos-api
                topologyKey: kubernetes.io/hostname
            - weight: 50
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: chronos-api
                topologyKey: topology.kubernetes.io/zone

      containers:
        - name: chronos-api
          # Substituir:
          # 1. SUBSTITUIR_TAG_IMUTAVEL por uma tag única, como uma tag derivada
          #    do commit/build, protegida contra sobrescrita no registry;
          # 2. o digest zerado pelo sha256 real publicado.
          #
          # A combinação tag+digest mantém legibilidade e garante que o conteúdo
          # executado não mude mesmo se a política do registry falhar.
          # O digest zerado é apenas um placeholder sintaticamente válido.
          image: "chronos-api:SUBSTITUIR_TAG_IMUTAVEL@sha256:0000000000000000000000000000000000000000000000000000000000000000"

          # É coerente com uma referência imutável: reutiliza a imagem local
          # somente quando ela possui exatamente o digest solicitado.
          imagePullPolicy: IfNotPresent

          securityContext:
            # Impede elevação de privilégio via setuid, setgid ou mecanismos similares.
            allowPrivilegeEscalation: false
            privileged: false

            # Remove todas as capabilities Linux herdadas por padrão.
            capabilities:
              drop:
                - ALL

            # Impede gravação no filesystem da imagem.
            # PREMISSA A VALIDAR: a aplicação escreve somente em /tmp.
            readOnlyRootFilesystem: true

          ports:
            - name: http
              containerPort: 8080
              protocol: TCP

          env:
            # Substitui os dois valores secretos em texto puro do Before
            # por referências obrigatórias ao Secret criado anteriormente.
            - name: DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: chronos-api-secrets
                  key: DB_PASSWORD
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: chronos-api-secrets
                  key: JWT_SECRET

            # Não é um segredo e permanece funcionalmente igual ao Before.
            - name: LEDGER_HOST
              value: "ledger-db.internal.hvt.io"

          resources:
            # PREMISSA A VALIDAR: não há telemetria ou teste de carga fornecido.
            # Estes valores são um baseline inicial, não um dimensionamento definitivo.
            requests:
              # Reserva 1/4 de core para o scheduler não tratar o gateway como
              # workload sem custo, mantendo espaço para várias réplicas.
              cpu: "250m"
              # Reserva inicial para processo, runtime e buffers.
              memory: "256Mi"
            limits:
              # Permite burst de até 1 core, limitando interferência com outros pods.
              # Validar throttling de CPU em carga real.
              cpu: "1"
              # Fornece 2x a memória reservada. Validar working set e eventos OOM.
              memory: "512Mi"

          # A startup probe impede que liveness/readiness atuem durante uma
          # inicialização potencialmente lenta.
          #
          # PREMISSA A VALIDAR: /health/startup existe e retorna sucesso somente
          # depois de concluída a inicialização necessária.
          # 30 falhas x 5s concedem aproximadamente 150s para iniciar.
          startupProbe:
            httpGet:
              path: /health/startup
              port: http
              scheme: HTTP
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 30
            successThreshold: 1

          # PREMISSA A VALIDAR: /health/ready indica que a instância consegue
          # receber tráfego. Evitar depender indiscriminadamente de todos os
          # downstreams, pois isso poderia retirar simultaneamente todos os pods.
          #
          # Três falhas em intervalos de 5s retiram o pod dos endpoints em cerca
          # de 15s; uma resposta bem-sucedida permite sua recuperação.
          readinessProbe:
            httpGet:
              path: /health/ready
              port: http
              scheme: HTTP
            periodSeconds: 5
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1

          # PREMISSA A VALIDAR: /health/live testa somente a saúde interna do
          # processo. Não deve falhar por indisponibilidade do banco ou Ledger,
          # pois isso causaria reinícios em cascata.
          #
          # Três falhas em intervalos de 10s reiniciam um processo travado após
          # aproximadamente 30s. A startup probe torna initialDelay desnecessário.
          livenessProbe:
            httpGet:
              path: /health/live
              port: http
              scheme: HTTP
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
            successThreshold: 1

          volumeMounts:
            # Oferece o único caminho de escrita esperado, mantendo o restante
            # do filesystem somente leitura.
            - name: tmp
              mountPath: /tmp

      volumes:
        - name: tmp
          emptyDir:
            # Limita crescimento acidental de temporários.
            sizeLimit: 64Mi
```

### Migração

**1. Validar o ambiente antes de alterar produção**

- Confirme que o Service existente seleciona `app: chronos-api`. Essa label foi preservada deliberadamente; não altere simultaneamente o selector do Service.
- Confirme que o selector atual do Deployment é exatamente `app: chronos-api`. Alterá-lo exigiria criar outro Deployment, pois o campo é imutável.
- Verifique capacidade para quatro pods durante o surge, considerando os requests definidos.
- Verifique as labels de zona e hostname dos nós. Para cumprir a alta disponibilidade pretendida, deve haver pelo menos dois domínios de falha, idealmente três zonas e três ou mais nós.
- Confirme que nenhuma manutenção ou drain ocorrerá durante a migração.

**2. Preparar a aplicação e a imagem fora do manifest**

- Implemente `/health/startup`, `/health/ready` e `/health/live` com os contratos documentados no YAML.
- Faça a aplicação tratar SIGTERM: parar de aceitar novas requisições, concluir as requisições em andamento e encerrar dentro de 30 segundos.
- Teste a imagem com UID/GID 10001, sem capabilities e com filesystem raiz somente leitura. Toda escrita deve usar `/tmp` ou outro volume explicitamente declarado.
- Execute teste de carga e valide os valores iniciais de CPU, memória e probes.
- Publique a imagem com uma tag única de build/commit, habilite imutabilidade de tags no registry e obtenha seu digest SHA-256.
- Substitua a tag e o digest em `metadata.labels`, `template.labels` e `containers[].image`.

**3. Provisionar os segredos**

- Considere os valores anteriormente versionados como comprometidos.
- Materialize `chronos-api-secrets` por um cofre, External Secrets Operator, Sealed Secrets ou pipeline com acesso protegido. Não exponha valores em argumentos de shell, logs ou arquivos temporários.
- Para uma primeira migração sem quebra, os valores precisam ser compatíveis com a aplicação e os sistemas atuais.
- Faça a rotação posterior de forma coordenada. A troca da chave JWT pode invalidar sessões; prefira suporte temporário a chaves antiga e nova. A senha do banco exige alteração coordenada com o banco.

**4. Aplicar os objetos auxiliares na ordem apresentada**

- ServiceAccount;
- Secret já materializado com segurança;
- PodDisruptionBudget.

Depois do PDB, o pod legado fica protegido contra interrupções voluntárias. Como ainda existe somente uma réplica, um drain ficará bloqueado até que novos pods estejam disponíveis.

**5. Validar antes do rollout**

- Execute validação client-side e server-side dos manifests.
- Confirme que o Secret contém as duas chaves esperadas sem imprimir os valores.
- Confirme que a imagem e o digest existem no registry.
- Confirme que a ServiceAccount existe e que a imagem não depende do token da API do Kubernetes.

**6. Aplicar o Deployment**

- O selector legado permanece inalterado, permitindo atualizar o mesmo Deployment.
- `maxUnavailable: 0` mantém o pod antigo enquanto os novos não estiverem Ready.
- A startup probe protege inicializações lentas; a readiness probe impede que o Service envie tráfego prematuramente.
- Se a imagem, o Secret, o security context ou os endpoints estiverem incorretos, o rollout deverá parar sem remover o último pod saudável.

**7. Acompanhar e validar**

- Observe rollout status, eventos, reinícios, falhas de probes e ImagePullBackOff.
- Confirme três pods Ready, distribuídos entre os nós e zonas esperados.
- Confirme que o PDB passa a mostrar duas instâncias mínimas e permite somente uma interrupção voluntária.
- Compare taxa de erros, latência, throughput, consumo, throttling e OOM com a linha de base.
- Faça uma requisição funcional passando pelo mesmo Service/Ingress usado pelos clientes.
- Só considere a migração concluída depois de os três pods permanecerem estáveis durante uma janela operacional adequada.

**8. Falha e rollback**

- Não delete manualmente o pod/ReplicaSet legado enquanto o rollout estiver incompleto.
- Se os novos pods não estabilizarem, interrompa o rollout e restaure uma revisão conhecida.
- O rollback para a revisão original é apenas contingência: ela volta a usar `latest`, execução sem hardening e segredos no template histórico. Depois da primeira implantação segura, os rollbacks devem apontar somente para imagens imutáveis conhecidas.

### Fora de escopo / riscos remanescentes

- **HPA e capacidade:** faltam métricas, testes de carga, autoscaling e definição de capacidade para picos.
- **NetworkPolicy:** o gateway ainda não possui políticas explícitas de entrada e saída para banco, Ledger, DNS e observabilidade.
- **Gestão e rotação de segredos:** Secret nativo não resolve cofre externo, rotação automática, criptografia do etcd ou invalidação segura de chaves JWT.
- **Service/Ingress/LB:** TLS, timeouts, connection draining, retries e proteção contra overload precisam ser revisados separadamente.
- **Observabilidade:** faltam SLOs, alertas, métricas, logs estruturados, tracing e monitoramento de probes/PDB.
- **Supply chain:** assinatura e verificação da imagem, SBOM, scanning e políticas de admissão não estão cobertos.
- **RBAC:** nenhuma permissão foi concedida à ServiceAccount. Se o Chronos precisar da API Kubernetes, deve receber apenas Role/RoleBinding mínimos.

---

## Justificativa

**Before:** o prompt não só colou o YAML legado, ele nomeou os 7 problemas do estado atual (réplica única, `:latest`, segredos em texto puro, ausência de probes, de resources, de securityContext e de estratégia de rollout). Esse inventário virou a régua do output: quase todo comentário do YAML entregue referencia explicitamente o que o Before tinha de errado ("O Before não possuía securityContext", "O Before não definia estratégia explícita", "Substitui os dois valores secretos em texto puro do Before").

**After:** o estado desejado foi descrito como lista de propriedades verificáveis, não como "melhore o manifest". Por isso o output cobre item a item: 3 réplicas com topology spread e PDB, tag imutável com digest, `secretKeyRef` no lugar dos valores, requests/limits justificados, startup/readiness/liveness com threshold explicado, securityContext não-root completo, labels padronizadas e ServiceAccount dedicada.

**Bridge:** a Bridge é o que diferencia esta questão de um pedido de refactor comum: ela pediu a travessia, não só o destino. O resultado tem ordem de aplicação numerada nos próprios blocos (1/4 a 4/4), oito etapas de migração incluindo o que precisa acontecer fora do manifest (implementar os endpoints de health, tratar SIGTERM, publicar a tag e obter o digest, materializar o Secret), e o cuidado central para um serviço tier-0: preservar o selector legado `app: chronos-api`, que é imutável, para atualizar o mesmo Deployment em vez de criar um novo e ter que migrar tráfego.

**Validação executada:** os quatro manifests do output foram validados contra os schemas do Kubernetes em modo estrito (kubeconform): 4 recursos válidos, 0 inválidos, nenhum campo desconhecido ou tipo incorreto. O YAML aplica; as ressalvas abaixo são de projeto, não de sintaxe.

**Onde eu discordo do output:** quatro pontos que eu mudaria antes de aplicar em produção:

1. **Falta `preStop`.** O YAML confia só no `terminationGracePeriodSeconds: 30` e no tratamento de SIGTERM. Num serviço atrás de Service/Ingress existe uma corrida: o kubelet manda SIGTERM antes de a remoção do endpoint terminar de propagar, e requisições em voo caem. Para um gateway tier-0 eu adicionaria um `preStop` com espera curta antes do shutdown.
2. **Memória com request diferente do limit.** `256Mi` de request e `512Mi` de limit deixa o pod em QoS Burstable. Para o ponto de entrada de todo o tráfego eu igualaria request e limit de memória, para evitar OOM kill do gateway quando o nó estiver sob pressão.
3. **`DoNotSchedule` no spread por hostname.** Garante distribuição, mas se um nó cair e não houver nó sobrando o pod fica Pending em vez de subir concentrado. Para tier-0 eu manteria `DoNotSchedule` na zona e trocaria para `ScheduleAnyway` no hostname: distribuição é desejável, indisponibilidade não.
4. **PDB `minAvailable: 2` aplicado enquanto existe 1 réplica.** O modelo documenta o efeito, mas o resultado é `disruptionsAllowed: 0` durante toda a janela de migração, o que travaria um drain de emergência. Eu aplicaria o PDB depois do Deployment já estar com 3 pods Ready, ou usaria `maxUnavailable: 1`.

O `sha256:0000...` na imagem é placeholder sintaticamente válido e o próprio comentário diz para substituir, então não conta como defeito, mas é o item que mais provavelmente causaria `ImagePullBackOff` se alguém aplicasse o manifest sem ler os comentários.
