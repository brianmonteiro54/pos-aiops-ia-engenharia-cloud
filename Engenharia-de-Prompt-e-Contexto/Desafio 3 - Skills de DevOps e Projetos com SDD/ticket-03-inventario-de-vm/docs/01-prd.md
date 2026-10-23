# PRD: Inventário e drift de VM

**Produto:** `roster-inventario`, primeira peça do substituto do Roster.
**Dono:** Plataforma.
**Consumidor:** o Roster (automático) e o plantão (humano).

## O problema

O Roster é mantido à mão e está desatualizado. Hosts mudaram de papel, há agentes
instalados e nunca registrados, e chaves SSH que ficaram para trás. A consequência que dói:
**ninguém consegue dizer quantas VMs estão fora do padrão.**

Não existe nada que compare o estado real de um host com o padrão escrito do parque.

## O que o produto faz

Uma ferramenta de linha de comando que:

1. roda **na máquina de quem opera**, não no host auditado
2. recebe endereço, usuário e chave privada
3. conecta por SSH e coleta o estado real
4. compara com um baseline versionado
5. devolve inventário e conformidade em **JSON** e em **Markdown**

## Usuários e o que cada um precisa

| Usuário | Precisa | Formato |
|---|---|---|
| **o Roster** | consumir inventário e conformidade sem humano no meio | JSON estável |
| **o plantão** | ler no terminal, de madrugada, e saber o que está grave | Markdown, desvios primeiro |
| **a esteira de CI** | barrar promoção de host fora do padrão | código de saída |

## Requisitos funcionais

### RF-01: Coleta por SSH, sem agente

A ferramenta conecta por SSH com chave privada. **Nada é instalado no host auditado.**

### RF-02: Nove grupos de dados coletados

| Grupo | O que volta |
|---|---|
| **identificação** | endereço usado na conexão, hostname reportado pelo host, instante da coleta |
| **sistema operacional** | distribuição e versão |
| **kernel** | versão em execução |
| **serviços** | unidades ativas, **distinguindo `service` de `socket`** |
| **swap** | habilitado e, se estiver, o tamanho |
| **portas em escuta** | porta, endereço de bind, processo dono |
| **chaves SSH autorizadas** | quantidade e identificação de cada uma |
| **login de root no SSH** | a configuração **efetiva**, não a escrita no arquivo |
| **sincronização de tempo** | sincronizado, e por qual mecanismo |

Dois detalhes que não são decoração:

- **`service` x `socket`**: o baseline proíbe `telnet.socket` e `rpcbind.socket`. Coletar só
  `.service` deixaria os dois passarem.
- **endereço de bind**: "porta 9100 em `0.0.0.0`" e "porta 9100 só no endereço interno" têm
  **vereditos diferentes**. A porta sozinha não decide.

### RF-03: Conformidade com três vereditos

Uma entrada por regra do baseline, com quatro informações: a regra, o valor esperado, o
valor encontrado e o veredito.

| Veredito | Quando |
|---|---|
| `conforme` | o encontrado satisfaz o esperado |
| `desvio` | não satisfaz. **Acompanhado da severidade que o baseline atribui** |
| `nao_verificado` | o dado não pôde ser coletado. **Com o motivo** |

`nao_verificado` existe porque reportar como `conforme` seria falso e abortar a execução
inteira não ajudaria ninguém. O caso típico: a coleta entra com usuário comum e o dado
exige privilégio.

### RF-04: Dois formatos, do mesmo dado

**JSON** para o Roster, com `host`, `inventario`, `conformidade` e `resumo`.

**Markdown** para o terminal, com os desvios primeiro, ordenados por severidade, depois os
não verificados com o motivo, e os conformes em uma linha.

Os dois saem do mesmo dado coletado. Não há segunda coleta para o segundo formato.

### RF-05: Baseline versionado e externo

O baseline é arquivo YAML com `versao`, e a versão aparece na saída. Trocar o baseline não
exige mexer na ferramenta.

### RF-06: Código de saída utilizável em pipeline

| Código | Significa |
|---|---|
| `0` | host conforme: nenhum desvio |
| `1` | há desvio |
| `2` | host inalcançável, ou erro de uso |

Distinguir `1` de `2` é o que permite a esteira tratar "host fora do padrão" e "não
consegui olhar o host" de formas diferentes.

## Restrições

### RE-01: Só leitura

Nada é instalado, escrito ou corrigido no host auditado.

### RE-02: Determinismo

**Duas execuções seguidas devolvem o mesmo veredito para cada regra.** Só o instante da
coleta muda.

### RE-03: A chave privada é credencial

Ela **não aparece na saída, no log nem em mensagem de erro**. Nem o caminho dela em
mensagem de erro de conexão, porque caminho de chave em log de CI é meio caminho para o
conteúdo.

### RE-04: Roda na máquina de quem opera

Sem agente, sem daemon, sem estado entre execuções.

## Critérios de aceite

| # | Critério | Como se verifica |
|---|---|---|
| **CA-01** | um host conforme sai **sem nenhum desvio** | executar contra o host conforme do laboratório |
| **CA-02** | um host com desvios sai com **cada desvio classificado pela severidade do baseline** | executar contra o host de desvios e conferir regra a regra |
| **CA-03** | regra não verificável aparece como `nao_verificado`, **separada de `conforme`** | o usuário da coleta é sem privilégio; `sshd -T` exige root |
| **CA-04** | host inalcançável falha com mensagem que **explica o que houve, sem stack trace**, e **não é confundido com host conforme** | endereço errado, chave recusada, SSH fora do ar: três execuções |
| **CA-05** | a segunda execução devolve **o mesmo resultado** | executar duas vezes e comparar, ignorando o instante da coleta |

## Fora de escopo

- varredura de frota e paralelismo
- histórico e tendência de drift
- baseline por papel de host
- **correção automática de desvio**, que não deve existir nesta ferramenta
- descoberta de hosts na rede
