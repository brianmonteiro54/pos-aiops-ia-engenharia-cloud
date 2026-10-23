# Spec Delta

## Purpose

Define como a aplicação fala com a API do Kubernetes: o portão de verbos que torna a
restrição de só-leitura verificável por teste, os limites de tempo que impedem a requisição
pendurada, e a classificação das falhas de ambiente em mensagens que distinguem cluster
inacessível de credencial rejeitada de permissão negada.

## ADDED Requirements

### Requirement: Só leitura, verificável no projeto

A aplicação SHALL executar exclusivamente verbos de leitura contra o cluster. A restrição
SHALL ser imposta por uma lista branca enumerada num único ponto do código, e SHALL ser
verificável por teste automatizado, não por inspeção visual.

#### Scenario: verbo de escrita é recusado antes de executar

- **WHEN** qualquer caminho do código tenta executar `kubectl` com verbo fora da lista
  branca, como `delete`, `apply`, `scale` ou `patch`
- **THEN** a chamada é recusada antes de o processo ser criado
- **AND** o erro nomeia o verbo recusado

#### Scenario: o fonte é varrido por verbo de escrita

- **WHEN** a suíte de validação roda
- **THEN** ela varre o próprio fonte da aplicação procurando verbo de escrita do `kubectl`
- **AND** falha se encontrar algum fora do contexto da própria lista branca e dos testes

#### Scenario: lista branca é fechada por omissão

- **WHEN** um verbo de leitura novo e legítimo é necessário
- **THEN** ele precisa ser acrescentado explicitamente à lista branca para funcionar

### Requirement: Nenhuma consulta fica pendurada

A aplicação SHALL limitar o tempo de cada consulta ao cluster em duas camadas: um limite por
requisição passado ao `kubectl` e um limite para o comando inteiro imposto pela aplicação.
Ao estourar o limite externo, a aplicação SHALL encerrar o grupo de processos criado, não
apenas o processo direto.

#### Scenario: cluster em endereço não roteável não pendura a tela

- **WHEN** o contexto corrente aponta para um endereço que não responde nem recusa, caso em
  que o `kubectl` sozinho ultrapassa setenta segundos
- **THEN** a aplicação desiste dentro do limite externo configurado
- **AND** a tela é devolvida com a falha explicada

#### Scenario: nenhum processo sobrevive ao estouro

- **WHEN** o limite externo estoura e a aplicação encerra a consulta
- **THEN** nenhum processo `kubectl` permanece em execução

### Requirement: Falha de ambiente vira mensagem, não stack trace

A aplicação SHALL classificar a falha de acesso ao cluster e apresentar mensagem que explica
o que aconteceu. A aplicação SHALL NOT devolver tela em branco e SHALL NOT expor rastro de
exceção na interface.

#### Scenario: cluster que não responde

- **WHEN** o contexto corrente aponta para um cluster inacessível
- **THEN** a tela explica que o cluster não respondeu e mostra o endereço tentado
- **AND** nenhum rastro de exceção aparece

#### Scenario: credencial rejeitada é distinguível de cluster inacessível

- **WHEN** o cluster responde e rejeita a credencial com 401
- **THEN** a tela explica que a credencial foi rejeitada pelo cluster
- **AND** a mensagem é diferente da mensagem de cluster inacessível

#### Scenario: credencial rejeitada não é afirmada como expirada

- **WHEN** a credencial é rejeitada com 401, caso em que token inválido, token expirado e
  certificado de cliente expirado produzem mensagem idêntica no `kubectl`
- **THEN** a tela declara que a credencial foi rejeitada e que pode estar expirada, inválida
  ou revogada
- **AND** a tela não afirma qual dos três é

#### Scenario: expiração afirmada quando o provedor a informa

- **WHEN** a credencial vem de um plugin de autenticação externo que falha informando que o
  token expirou
- **THEN** a tela nomeia a expiração e repassa a mensagem do provedor

#### Scenario: falha não reconhecida é mostrada crua

- **WHEN** a saída de erro do `kubectl` não casa com nenhum padrão conhecido
- **THEN** a tela marca a falha como não classificada e mostra a saída de erro original
- **AND** não arrisca uma classificação errada

#### Scenario: ruído de diagnóstico do kubectl não chega à tela

- **WHEN** o `kubectl` emite linhas de erro interno sobre descoberta de grupos da API antes
  da mensagem útil
- **THEN** essas linhas são descartadas na classificação e não aparecem na tela

### Requirement: Permissão negada degrada em parte, não no todo

Quando o contexto corrente não tem permissão de leitura sobre um tipo de recurso, a
aplicação SHALL continuar apresentando os tipos acessíveis e SHALL marcar o tipo negado como
negado.

#### Scenario: um tipo negado, os outros na tela

- **WHEN** o contexto tem permissão de leitura sobre namespaces, pods, services, deployments
  e endpointslices, e não tem sobre eventos
- **THEN** as cinco seções acessíveis aparecem preenchidas
- **AND** a seção de eventos mostra que a permissão foi negada, com o usuário identificado
  na mensagem do cluster
- **AND** o restante da tela permanece utilizável

### Requirement: Fonte dos endpoints escolhida na subida e declarada na tela

A aplicação SHALL usar `EndpointSlice` como fonte primária da informação de endpoint, SHALL
cair para `Endpoints` quando o grupo `discovery.k8s.io` não existir no cluster, e SHALL
declarar na tela qual fonte está em uso.

#### Scenario: EndpointSlice disponível

- **WHEN** o cluster expõe `discovery.k8s.io/v1`
- **THEN** a aplicação usa `EndpointSlice`
- **AND** a tela declara a fonte em uso

#### Scenario: cluster sem EndpointSlice

- **WHEN** o cluster não expõe o grupo `discovery.k8s.io`
- **THEN** a aplicação usa `Endpoints`
- **AND** a tela declara a fonte em uso e que `terminating` não é distinguido nessa fonte

#### Scenario: vários slices por service são somados

- **WHEN** um Service tem mais de um `EndpointSlice` associado
- **THEN** a contagem de prontos e de total soma todos os slices daquele Service
- **AND** a associação é feita pelo rótulo `kubernetes.io/service-name`, não pelo nome do
  objeto

### Requirement: Escuta local por padrão, exposição explícita e avisada

A aplicação não tem autenticação. Ela SHALL escutar em endereço de loopback por padrão, e
SHALL imprimir aviso quando configurada para escutar em endereço que não seja de loopback.

#### Scenario: padrão é loopback

- **WHEN** a aplicação sobe sem endereço configurado
- **THEN** ela escuta em `127.0.0.1`

#### Scenario: exposição na rede avisa

- **WHEN** a aplicação é configurada para escutar em endereço que não é de loopback
- **THEN** ela imprime aviso de que o acesso não é autenticado antes de abrir a porta
