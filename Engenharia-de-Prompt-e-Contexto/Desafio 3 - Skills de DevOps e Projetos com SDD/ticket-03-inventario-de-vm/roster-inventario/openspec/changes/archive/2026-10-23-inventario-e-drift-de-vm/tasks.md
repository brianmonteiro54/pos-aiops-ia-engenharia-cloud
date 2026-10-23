# Tarefas: inventário e drift de VM

Ordem deliberada: o laboratório primeiro, porque sem host auditável não há como validar
coletor; o julgamento depois da coleta, porque ele consome a estrutura dela.

## 1. Laboratório

- [x] 1.1 Dockerfile base com systemd, sshd, chrony e node_exporter
- [x] 1.2 Dockerfile do host **conforme**: containerd ativo, node_exporter em `127.0.0.1`,
      `PermitRootLogin no`, uma chave da plataforma
- [x] 1.3 Dockerfile do host **com desvios**: chrony inativo, `rpcbind.socket` ativo,
      node_exporter em `0.0.0.0`, `PermitRootLogin yes`, chave de origem desconhecida
- [x] 1.4 Gerar o par de chaves; a privada **fora** do repositório
- [x] 1.5 Subir os dois e confirmar SSH com usuário sem privilégio

## 2. Baseline

- [x] 2.1 `baseline.yaml` do parque, como o ticket entrega
- [x] 2.2 `baseline-laboratorio.yaml`, idêntico menos as duas regras de nível de host, com
      o motivo escrito dentro do arquivo: ADR-004
- [x] 2.3 Carregador que valida a estrutura e **falha com mensagem** se `PyYAML` faltar

## 3. Transporte

- [x] 3.1 Sessão SSH com `ControlMaster`, socket em diretório temporário próprio
- [x] 3.2 Opções fixadas: `BatchMode`, `StrictHostKeyChecking=accept-new`,
      `ConnectTimeout`, `IdentitiesOnly`
- [x] 3.3 Classificar falha de conexão nas três categorias, **sem repassar `stderr` cru**
- [x] 3.4 Remover o socket de controle ao fim, inclusive em caminho de erro

## 4. Coleta

- [x] 4.1 Contrato `Coletado`: valor **ou** motivo de falha, nunca exceção para cima
- [x] 4.2 identificação: hostname do host, endereço de quem chamou, instante
- [x] 4.3 sistema operacional: `ID` e `VERSION_ID` do `os-release`
- [x] 4.4 kernel: `uname -r`
- [x] 4.5 serviços: `--type=service,socket`, com o tipo de cada unidade
- [x] 4.6 swap: habilitado e tamanho; vazio é informação, não falha
- [x] 4.7 portas: número, bind e processo, com o bind **normalizado** em
      público/loopback/interno
- [x] 4.8 chaves SSH: quantidade e o **comentário** de cada uma
- [x] 4.9 login de root: `sshd -T`, e `nao_verificado` quando falta privilégio
- [x] 4.10 tempo: sincronizado e por qual mecanismo

## 5. Julgamento

- [x] 5.1 Invariante: `valor is None` produz `nao_verificado` **antes** de qualquer comparação
- [x] 5.2 Comparação de versão **por componente**, ignorando sufixo de fornecedor
- [x] 5.3 As onze regras do baseline
- [x] 5.4 Severidade vinda do mapa do baseline; regra sem severidade é **erro do baseline**
- [x] 5.5 Ordenar toda lista antes de comparar, para o determinismo

## 6. Apresentação

- [x] 6.1 JSON no formato do ticket, com `resumo.por_severidade` contando **desvios**
- [x] 6.2 Markdown: desvios por severidade, depois não verificados com motivo, depois conformes
- [x] 6.3 Código de saída `0` / `1` / `2`

## 7. Validação contra os critérios de pronto

- [x] 7.1 **CA-01** host conforme sem desvio, contra `baseline-laboratorio.yaml`, `rc=0`
- [x] 7.2 **CA-01b** o mesmo host contra o baseline do parque: **exatamente** os dois desvios
      previstos no ADR-004, e nada mais
- [x] 7.3 **CA-02** host com desvios, cada um com a severidade do baseline, conferida regra
      a regra
- [x] 7.4 **CA-03** `ssh.login_de_root` como `nao_verificado`, separado de conforme
- [x] 7.5 **CA-04** três falhas de conexão: endereço errado, chave recusada, SSH fora do ar.
      `rc=2`, sem stack trace, sem bloco de conformidade
- [x] 7.6 **CA-05** duas execuções, diff vazio exceto o instante da coleta
- [x] 7.7 **RE-03** nenhuma saída contém o conteúdo nem o caminho da chave privada

## 8. Fechamento

- [x] 8.1 README do projeto com pré-requisitos e como rodar
- [x] 8.2 Curadoria: onde a spec precisou ser corrigida durante a implementação, e o que o
      agente entendeu diferente do que eu escrevi
- [x] 8.3 `openspec archive`
