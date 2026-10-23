# inventario-de-host Specification

## Purpose
TBD - created by archiving change inventario-e-drift-de-vm. Update Purpose after archive.

## Requirements

### Requirement: Coleta por SSH sem agente

A ferramenta SHALL coletar o estado de um host remoto por SSH, sem instalar nada no host
auditado.

#### Scenario: coleta com chave privada

- **WHEN** a ferramenta recebe endereço, usuário e caminho de chave privada
- **THEN** ela SHALL abrir uma sessão SSH e executar apenas comandos de leitura
- **AND** SHALL fechar a sessão ao fim da coleta

#### Scenario: a chave privada é credencial

- **WHEN** qualquer saída é produzida — relatório, log ou mensagem de erro
- **THEN** o conteúdo da chave privada SHALL NOT aparecer
- **AND** o caminho da chave SHALL NOT aparecer em mensagem de erro

### Requirement: Nove grupos de dados

A ferramenta SHALL coletar identificação, sistema operacional, kernel, serviços, swap,
portas em escuta, chaves SSH autorizadas, login de root no SSH e sincronização de tempo.

#### Scenario: serviços distinguem service de socket

- **WHEN** as unidades ativas são coletadas
- **THEN** cada unidade SHALL trazer seu tipo, `service` ou `socket`
- **AND** unidades do tipo `socket` SHALL ser coletadas, porque o baseline proíbe duas

#### Scenario: porta traz bind e processo

- **WHEN** uma porta em escuta é coletada
- **THEN** ela SHALL trazer número, endereço de bind e processo dono
- **AND** o bind SHALL ser classificado como público, loopback ou rede interna

#### Scenario: login de root vem da configuração efetiva

- **WHEN** o login de root no SSH é coletado
- **THEN** o valor SHALL vir da configuração efetiva do daemon
- **AND** SHALL NOT vir da leitura do arquivo de configuração

### Requirement: Conformidade com três vereditos

A ferramenta SHALL produzir uma entrada por regra do baseline, com a regra, o valor
esperado, o valor encontrado e o veredito.

#### Scenario: regra satisfeita

- **WHEN** o valor encontrado satisfaz o esperado
- **THEN** o veredito SHALL ser `conforme`

#### Scenario: regra violada

- **WHEN** o valor encontrado não satisfaz o esperado
- **THEN** o veredito SHALL ser `desvio`
- **AND** SHALL incluir a severidade que o baseline atribui àquela regra

#### Scenario: dado não coletado

- **WHEN** o dado necessário a uma regra não pôde ser coletado
- **THEN** o veredito SHALL ser `nao_verificado`
- **AND** SHALL incluir o motivo em texto legível
- **AND** SHALL NOT ser contado como `conforme` em nenhum lugar da saída

#### Scenario: a falha de um coletor não derruba os outros

- **WHEN** um coletor falha
- **THEN** os demais coletores SHALL continuar
- **AND** a execução SHALL produzir relatório com as regras que pôde julgar

#### Scenario: a severidade vem do baseline

- **WHEN** um desvio é classificado
- **THEN** a severidade SHALL vir do mapa de severidade do baseline
- **AND** SHALL NOT ser inferida pela ferramenta

### Requirement: Comparação de versão por componente

A ferramenta SHALL comparar versão por componente numérico, não lexicograficamente.

#### Scenario: versão com sufixo de fornecedor

- **WHEN** o kernel encontrado é `5.15.0-118-generic` e o mínimo é `6.5`
- **THEN** o veredito SHALL ser `desvio`

#### Scenario: comparação lexicográfica enganaria

- **WHEN** a versão encontrada é `22.04` e o mínimo é `9.10`
- **THEN** o veredito SHALL ser `conforme`

### Requirement: Duas saídas do mesmo dado

A ferramenta SHALL produzir JSON e Markdown a partir da mesma coleta.

#### Scenario: JSON para consumo automático

- **WHEN** a saída pedida é JSON
- **THEN** ela SHALL conter `host`, `inventario`, `conformidade` e `resumo`
- **AND** `resumo` SHALL conter a contagem por veredito e a contagem de desvios por
  severidade

#### Scenario: Markdown para o plantão

- **WHEN** a saída pedida é Markdown
- **THEN** os desvios SHALL vir primeiro, ordenados por severidade
- **AND** os não verificados SHALL vir em seção própria, com o motivo
- **AND** os conformes SHALL vir ao final

### Requirement: Só leitura

A ferramenta SHALL NOT instalar, escrever ou corrigir nada no host auditado.

#### Scenario: nenhum comando de escrita

- **WHEN** a coleta executa comandos no host
- **THEN** todos SHALL ser de leitura

### Requirement: Determinismo

Duas execuções seguidas SHALL devolver o mesmo veredito para cada regra.

#### Scenario: segunda execução

- **WHEN** a ferramenta roda duas vezes contra o mesmo host sem mudança
- **THEN** cada regra SHALL receber o mesmo veredito
- **AND** o único campo diferente SHALL ser o instante da coleta

### Requirement: Código de saída utilizável em pipeline

A ferramenta SHALL sair com código que distinga host fora do padrão de host não auditável.

#### Scenario: host conforme

- **WHEN** nenhuma regra recebe `desvio`
- **THEN** o código de saída SHALL ser `0`

#### Scenario: host com desvio

- **WHEN** ao menos uma regra recebe `desvio`
- **THEN** o código de saída SHALL ser `1`

#### Scenario: host inalcançável

- **WHEN** a sessão SSH não pode ser estabelecida
- **THEN** o código de saída SHALL ser `2`
- **AND** a mensagem SHALL explicar a categoria da falha, sem stack trace
- **AND** nenhum bloco de conformidade SHALL ser produzido
