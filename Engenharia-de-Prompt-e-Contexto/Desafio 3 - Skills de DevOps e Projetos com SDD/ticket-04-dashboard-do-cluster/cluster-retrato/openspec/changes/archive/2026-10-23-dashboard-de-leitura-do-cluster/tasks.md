# Tasks

## 1. Laboratório e cenários de falha

- [x] 1.1 Subir o workload dos dois projetos do Ticket 01 no cluster, cobrindo os quatro
      estados necessários: saudável, `CrashLoopBackOff`, `ImagePullBackOff` e selector que
      não casa
- [x] 1.2 Criar ServiceAccount, ClusterRole e ClusterRoleBinding de leitura restrita que
      concede cinco tipos e nega eventos, para o cenário de permissão negada
- [x] 1.3 Gerar os kubeconfigs quebrados de propósito fora do repositório: porta fechada,
      endereço não roteável, token inválido, token expirado, certificado de cliente
      expirado assinado pela CA real, plugin externo que falha informando expiração, e
      plugin ausente
- [x] 1.4 Medir a saída de erro e o código de saída de cada modo de falha, e registrar a
      tabela de padrões

## 2. Portão de acesso ao cluster

- [x] 2.1 Implementar `_kubectl` como único ponto de criação de subprocesso, com lista
      branca enumerada de verbos e recusa antes de criar o processo
- [x] 2.2 Implementar os dois tetos de tempo, com criação em sessão nova e encerramento do
      grupo de processos no estouro
- [x] 2.3 Implementar `classificar` com descarte do ruído de diagnóstico, tabela de padrões
      na ordem definida, e rótulo de falha não classificada
- [x] 2.4 Implementar a detecção da fonte de endpoints na subida, uma única vez

## 3. Coleta e normalização

- [x] 3.1 Implementar as seis consultas, com a de eventos condicionada a namespace
      selecionado e com falha por consulta em vez de falha global
- [x] 3.2 Normalizar endpoints das duas fontes para a mesma estrutura, contando prontos
      sobre total e agregando por rótulo de service
- [x] 3.3 Normalizar pods: motivo real na ordem definida, reinícios somados, e detecção de
      readinessProbe ignorando initContainers
- [x] 3.4 Normalizar deployments tratando réplica ausente como zero
- [x] 3.5 Montar a contagem de recursos quebrados por namespace

## 4. Tela

- [x] 4.1 Renderizar o HTML com CSS embutido e sem JavaScript, com escape em toda
      interpolação
- [x] 4.2 Cabeçalho com contexto, servidor e hora da coleta, presente inclusive nas telas de
      falha
- [x] 4.3 Filtro por namespace e busca por nome via query string
- [x] 4.4 Renderizar as falhas: globais como tela inteira, permissão negada como seção
      marcada, e a fonte dos endpoints declarada
- [x] 4.5 Servidor HTTP com bind em loopback por padrão e aviso na exposição não loopback

## 5. Validação

- [x] 5.1 CA-01: os seis itens aparecem contra o cluster real
- [x] 5.2 CA-02: `readyReplicas` ausente aparece como `0/N`
- [x] 5.3 CA-03: `0/0` no selector que não casa e `0/3` nos pods não prontos, sem exceção
- [x] 5.4 CA-04: `CrashLoopBackOff` com `OOMKilled` ao lado, apesar de `phase: Running`
- [x] 5.5 CA-05: cluster inacessível explicado, nos dois modos, sem rastro de exceção e sem
      processo órfão
- [x] 5.6 CA-06: credencial rejeitada distinguível de cluster fora, sem afirmar expiração
      nos casos em que o `kubectl` não distingue, e afirmando quando o provedor informa
- [x] 5.7 CA-07: eventos negados e as outras cinco seções preenchidas
- [x] 5.8 CA-08: varredura do fonte por verbo de escrita, e recusa do portão em tempo de
      execução
- [x] 5.9 Teste da normalização como função pura, com JSON fixo, incluindo o caminho de
      `Endpoints` por injeção
- [x] 5.10 Reunir a saída da validação como evidência

## 6. Fechamento

- [x] 6.1 README do ticket com como subir, como validar e as limitações conhecidas
- [x] 6.2 Registro do comportamento das duas skills durante o projeto
- [x] 6.3 Curadoria do ticket
- [x] 6.4 Validar e arquivar a mudança no OpenSpec
