# Proposal

## Why

Toda triagem de chamado começa com a mesma sequência de seis a dez comandos no terminal para
montar o retrato de um namespace. O Ticket 02 mediu isso: a triagem dos três chamados
consumiu 26 chamadas, e as primeiras de cada uma eram sempre o mesmo retrato.

O que existe hoje não resolve. O `kubectl` responde bem "como está este recurso" e responde
mal "onde está o problema no cluster". O `k9s` resolve, mas é um terminal interativo que não
se compartilha numa chamada de incidente e que não marca a diferença entre o que o cluster
sabe e o que ele está inferindo.

Três sintomas concretos, todos rodando no cluster de laboratório agora, mostram o custo de
ler o cluster de forma ingênua:

- pod em `CrashLoopBackOff` tem `status.phase: Running`. Quem lê `phase` vê tudo verde
- Service sem endpoint pronto tem **três** formas diferentes no JSON, e contar endpoints
  acusa só uma delas
- `ready: true` num pod sem readinessProbe não significa que a aplicação responde

Uma tela que erra qualquer um dos três é pior que não ter tela, porque confirma o
diagnóstico errado com mais confiança.

## What Changes

Nasce `cluster-retrato`, aplicação local de **leitura** do cluster corrente do kubeconfig.

- **leitura dos seis tipos** em uma tela: namespaces com contagem do que está quebrado,
  pods com estado e motivo real da falha, deployments com réplicas prontas sobre desejadas,
  services com endpoints **prontos sobre total**, eventos do namespace selecionado, e
  filtro por namespace mais busca por nome
- **distinção entre o que o cluster sabe e o que ele infere**: pod pronto com probe
  declarada é marcado de forma diferente de pod pronto sem probe nenhuma
- **garantia de só-leitura visível no projeto**, não na intenção: toda chamada passa por uma
  função única com lista branca de verbos, e um teste varre o próprio fonte procurando verbo
  de escrita
- **degradação honesta em falha de ambiente**: cluster que não responde, credencial
  rejeitada e permissão negada em um tipo produzem mensagem que explica, sem tela branca e
  sem stack trace. Permissão negada é parcial: os tipos acessíveis continuam na tela
- **consulta sob demanda**, com a hora da coleta impressa na tela, e zero carga no apiserver
  quando ninguém está olhando

Fora desta mudança: logs, `exec`, métricas, multicluster, edição de YAML, histórico, alerta
e tela com atualização automática.

## Capabilities

### New Capabilities

- `retrato-do-cluster`: leitura e apresentação do estado dos seis tipos de recurso numa
  tela, incluindo a normalização dos campos que o Kubernetes omite ou entrega como `null`,
  a extração do motivo real da falha de um pod, e a distinção entre prontidão verificada por
  probe e prontidão apenas presumida
- `acesso-ao-cluster`: como a aplicação fala com a API do Kubernetes, o portão de verbos
  que torna a restrição de só-leitura verificável, os dois tetos de tempo que impedem a
  requisição pendurada, e a classificação das falhas de ambiente em mensagem que distingue
  cluster inacessível de credencial rejeitada de permissão negada

## Impact

- **novo código:** `cluster_retrato.py`, arquivo único, só biblioteca padrão do Python 3
- **nenhuma dependência nova:** sem pacote do PyPI, sem cadeia de build de front-end
- **dependência externa de runtime:** o binário `kubectl` no PATH e um kubeconfig com
  contexto corrente válido
- **cluster:** nenhuma alteração. A aplicação não cria, não altera e não remove objeto
- **laboratório:** `preparar-cenarios-de-falha.sh` cria um ServiceAccount, um ClusterRole e
  um ClusterRoleBinding de leitura restrita no cluster de teste, e gera kubeconfigs
  quebrados de propósito fora do repositório
- **segurança:** a aplicação **não tem autenticação**. Bind em `127.0.0.1` por padrão, e
  aviso impresso quando o endereço configurado não é loopback
