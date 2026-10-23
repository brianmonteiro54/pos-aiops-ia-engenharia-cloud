# retrato-do-cluster Specification

## Purpose
Define o que a tela mostra e como os dados crus da API do Kubernetes são normalizados antes
de chegar nela, cobrindo os campos que a API omite, os que ela entrega como `null`, e a
diferença entre prontidão verificada por probe e prontidão apenas presumida.

## Requirements

### Requirement: Leitura restrita ao contexto corrente

A aplicação SHALL ler o cluster apontado pelo contexto corrente do kubeconfig no momento em
que sobe, e SHALL NOT oferecer troca de contexto ou de cluster por dentro da interface.

#### Scenario: contexto corrente é usado sem seletor

- **WHEN** a aplicação sobe com um kubeconfig cujo contexto corrente é `k3d-metacortex`
- **THEN** a tela mostra o nome do contexto e o endereço do servidor no cabeçalho
- **AND** não existe na interface nenhum controle para trocar de cluster

#### Scenario: contexto inexistente é recusado na subida

- **WHEN** o kubeconfig não tem contexto corrente definido
- **THEN** a aplicação recusa subir com mensagem que nomeia o problema
- **AND** não abre porta de escuta

### Requirement: Retrato dos seis tipos numa tela

A aplicação SHALL apresentar, numa única tela, os namespaces do cluster com a contagem de
recursos quebrados em cada um, os pods com estado e contagem de reinícios, os deployments
com réplicas prontas sobre desejadas, os services com endpoints prontos sobre total, e os
eventos recentes do namespace selecionado.

#### Scenario: retrato contra cluster com namespaces saudáveis e quebrados

- **WHEN** o cluster tem `nyx-dev` saudável e `nyx-prod` com pods em `CrashLoopBackOff`
- **THEN** a lista de namespaces mostra `nyx-prod` com contagem de quebrados maior que zero
- **AND** mostra `nyx-dev` com contagem de quebrados igual a zero

#### Scenario: eventos só do namespace selecionado

- **WHEN** nenhum namespace está selecionado
- **THEN** a seção de eventos não é preenchida e explica que depende de seleção
- **WHEN** o namespace `orion-stg` é selecionado
- **THEN** a seção de eventos mostra os eventos de `orion-stg`

### Requirement: Filtro por namespace e busca por nome

A aplicação SHALL permitir filtrar o retrato por namespace e buscar recursos por nome, e o
estado do filtro SHALL estar na URL para que a tela seja compartilhável sem JavaScript.

#### Scenario: filtro e busca aparecem na URL

- **WHEN** o usuário filtra pelo namespace `nyx-prod` e busca por `api`
- **THEN** a URL contém `ns=nyx-prod` e `q=api`
- **AND** a tela mostra apenas recursos de `nyx-prod` cujo nome contém `api`

### Requirement: Réplica ausente é zero, não erro

A aplicação SHALL tratar a ausência de `status.readyReplicas` num Deployment como zero, e
SHALL tratar a ausência de `spec.replicas` como um.

#### Scenario: deployment com zero réplicas prontas

- **WHEN** um Deployment tem `spec.replicas: 2` e a API omite `status.readyReplicas`
- **THEN** a tela mostra `0/2`
- **AND** não ocorre erro nem aparece campo vazio

### Requirement: Endpoints contados por prontidão

A aplicação SHALL apresentar, para cada Service, a quantidade de endpoints **prontos** sobre
o total de endpoints conhecidos, e SHALL NOT decidir a disponibilidade pela simples
existência de endpoints.

#### Scenario: selector que não casa resulta em zero sobre zero

- **WHEN** um Service tem selector que não casa com nenhum pod, de modo que a chave
  `subsets` está ausente no objeto `Endpoints` e a chave `endpoints` vale `null` no objeto
  `EndpointSlice`
- **THEN** a tela mostra `0/0` para aquele Service
- **AND** a leitura não levanta `KeyError` nem `TypeError`

#### Scenario: pods existentes e não prontos resultam em zero sobre N

- **WHEN** um Service tem três pods em `ImagePullBackOff`, de modo que os endpoints existem
  com `conditions.ready` falso
- **THEN** a tela mostra `0/3` para aquele Service
- **AND** o Service é destacado como não atendendo tráfego

#### Scenario: endpoints prontos aparecem como N sobre N

- **WHEN** um Service tem um pod pronto e servindo
- **THEN** a tela mostra `1/1` e o Service não é destacado

### Requirement: Motivo real da falha de um pod

A aplicação SHALL extrair o motivo da falha de um pod dos campos de estado do container, e
SHALL NOT usar `status.phase` como indicador principal de saúde.

#### Scenario: CrashLoopBackOff com phase Running

- **WHEN** um pod tem `status.phase: Running` e um container com
  `state.waiting.reason: CrashLoopBackOff` e `lastState.terminated.reason: OOMKilled`
- **THEN** a tela mostra o pod como quebrado
- **AND** mostra `CrashLoopBackOff` como estado e `OOMKilled` como causa, os dois juntos

#### Scenario: reinícios somados entre containers

- **WHEN** um pod tem dois containers com `restartCount` 3 e 5
- **THEN** a tela mostra 8 reinícios para o pod

#### Scenario: motivo ausente cai para a condição do pod

- **WHEN** um pod não tem `containerStatuses` porque não foi agendado, e tem condição
  `PodScheduled` com `status: "False"`
- **THEN** a tela mostra a mensagem daquela condição como motivo

### Requirement: Prontidão presumida é marcada como presumida

A aplicação SHALL distinguir pod pronto cuja prontidão foi verificada por readinessProbe de
pod pronto que não tem readinessProbe declarada em nenhum container, porque no segundo caso
a prontidão significa apenas que o processo subiu.

#### Scenario: pronto com probe declarada

- **WHEN** um pod está pronto e tem `readinessProbe` declarada
- **THEN** a tela marca o pod como pronto, sem ressalva

#### Scenario: pronto sem probe declarada

- **WHEN** um pod está pronto e nenhum container tem `readinessProbe`
- **THEN** a tela marca o pod como pronto com ressalva explícita de que não há probe
- **AND** explica que o Kubernetes não está verificando a aplicação

#### Scenario: probe em initContainer não conta

- **WHEN** um pod tem `readinessProbe` apenas num `initContainer`
- **THEN** a tela trata o pod como pronto sem probe

### Requirement: A hora da coleta aparece na tela

A aplicação SHALL imprimir na tela o instante em que os dados foram coletados, porque a
consulta é sob demanda e o dado envelhece até o próximo carregamento.

#### Scenario: hora presente em toda resposta

- **WHEN** qualquer tela é carregada, inclusive uma em que a coleta falhou
- **THEN** o cabeçalho mostra a hora da coleta
