# ADR-001: Como a ferramenta se comunica com o host remoto

**Status:** aceito
**Contexto:** a ferramenta roda na estação de quem opera e audita VMs sem agente.

## Decisão

**O binário `ssh` do sistema, invocado como subprocesso, com uma sessão por execução e
multiplexação de comandos por `ControlMaster`.**

## Alternativas consideradas

### A: biblioteca SSH na linguagem (`paramiko`)

**O que se ganha:** controle fino da sessão, uma conexão para n comandos sem truque,
exceções tipadas em vez de parsing de `stderr`, e nenhuma dependência do `ssh` do sistema.

**O que se perde, e foi decisivo:**

- **uma dependência externa para instalar.** `paramiko` não está na biblioteca padrão, e
  neste ambiente não está instalado: conferido. Uma ferramenta de plantão que precisa de
  `pip install` antes de rodar é uma ferramenta que não roda na hora em que se precisa dela.
- **duas implementações de SSH para auditar.** `paramiko` tem CVE próprio, política própria
  de algoritmo e de verificação de host key. A estação já confia no `ssh` do sistema; somar
  um segundo cliente SSH é somar superfície.
- **a configuração de SSH da casa deixa de valer.** `~/.ssh/config` com `ProxyJump` para o
  bastião, algoritmo restrito por política, `Match host`: tudo isso é do `ssh` do sistema.
  Numa provedora de infraestrutura gerenciada, acesso a VM de cliente passa por bastião, e
  reimplementar `ProxyJump` é reimplementar o que já funciona.

### B: transporte de orquestração pronto (Ansible, `pssh`)

**O que se ganha:** inventário, paralelismo e idempotência de graça. Ansible tem módulo de
fatos que coleta boa parte dos nove grupos.

**O que se perde:**

- **traz um modelo de execução inteiro para resolver uma leitura.** Ansible quer inventário,
  playbook e, em vários módulos, Python no host remoto, que é quase um agente, exatamente o
  que o ticket proíbe.
- **o veredito fica dentro do modelo dele.** Transformar `ansible_facts` em conformidade com
  severidade da casa é escrever a mesma lógica de julgamento, com uma dependência grande por
  baixo.
- **o paralelismo é o atrativo, e está fora de escopo.** Esta peça audita **uma** VM. Trazer
  Ansible agora é pagar pela segunda peça antes de a primeira estar certa.

### C: `ssh` como subprocesso (escolhida)

**O que se ganha:**

- **zero dependência além do que a estação já tem.** `ssh` existe em qualquer máquina de
  quem opera infraestrutura.
- **`~/.ssh/config` continua valendo.** Bastião, `ProxyJump`, algoritmo por política: tudo
  herdado.
- **um cliente SSH para auditar**, o que a casa já audita.
- **o comportamento é inspecionável.** Dá para rodar o comando à mão e ver o mesmo
  resultado, o que importa quando alguém contesta um veredito.

**O que se perde, e como foi tratado:**

| Perda | Tratamento |
|---|---|
| sem exceção tipada: é preciso classificar `stderr` | três categorias por padrão de texto, em **ADR-002** e no TRD. Mais frágil que exceção, e aceitável porque as mensagens do OpenSSH são estáveis há anos |
| um processo por comando seria lento e abriria n conexões | **`ControlMaster`**: a primeira conexão abre um socket de controle, as seguintes reusam. Uma autenticação por execução |
| `stderr` pode conter o caminho da chave | nunca repassado cru. Classificado e substituído por mensagem própria (RE-03) |

## Consequências

- a ferramenta **não funciona** sem `ssh` no PATH, e isso é declarado em pré-requisito
- erro de conexão vira categoria, não exceção: o teste de CA-04 valida as três
- o socket de controle vive em diretório temporário próprio e é removido ao fim. Socket de
  controle esquecido é conexão aberta para VM de cliente
- se um dia a ferramenta precisar auditar frota em paralelo, esta decisão **não** atrapalha:
  `ssh` paraleliza por processo
