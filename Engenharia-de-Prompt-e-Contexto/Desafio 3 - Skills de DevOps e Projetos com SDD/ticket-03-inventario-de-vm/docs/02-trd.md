# TRD — Inventário e drift de VM

Como a ferramenta funciona por dentro. As quatro decisões que o ticket manda registrar
estão em ADRs próprios, em `adr/`.

## Arquitetura

Quatro etapas, nesta ordem, e a separação entre a 2 e a 3 é deliberada:

```
  1. transporte      abre uma sessao SSH e executa comando de leitura
  2. coleta          nove coletores, cada um com sucesso OU falha com motivo
  3. julgamento      compara o coletado com o baseline, regra por regra
  4. apresentacao    o mesmo veredito em JSON e em Markdown
```

**Por que coleta e julgamento são separados.** O Roster quer saber o que existe, não só o
que está errado — o inventário tem valor sem o baseline. E trocar o baseline não deve mexer
em coletor: um baseline v2 exigindo kernel 6.8 muda uma linha de YAML, não código.

O custo: duas estruturas de dados em vez de uma, e um passo a mais. É o que faz os dois
formatos de saída saírem do mesmo dado, como o PRD exige.

## Etapa 1 — transporte

Uma sessão SSH, **n comandos**, sessão fechada. Ver **ADR-001** para a escolha do
mecanismo.

Opções do cliente, fixadas e com motivo:

| Opção | Valor | Por quê |
|---|---|---|
| `BatchMode` | `yes` | nunca pedir senha. Em pipeline, prompt de senha é travamento silencioso |
| `StrictHostKeyChecking` | `accept-new` | aceita host novo e **recusa host cuja chave mudou**. `no` aceitaria man-in-the-middle; `yes` exigiria known_hosts pré-populado para todo host do parque |
| `ConnectTimeout` | 10s | host fora do ar precisa falhar rápido, não pendurar a esteira |
| `IdentitiesOnly` | `yes` | usa só a chave passada. Sem isso o agente SSH da estação pode autenticar com outra chave, e o resultado deixa de ser reproduzível |

**Nenhum comando de coleta escreve.** São `cat`, `uname`, `systemctl`, `ss`, `swapon`,
`hostname`, `timedatectl`, `sshd -T`. A restrição RE-01 é propriedade dos comandos
escolhidos, não de uma verificação em tempo de execução.

## Etapa 2 — coleta

Nove coletores independentes. Cada um devolve **dado** ou **falha com motivo legível** — e
a falha de um não derruba os outros, que é o mecanismo do `nao_verificado` (**ADR-002**).

| Coletor | Comando | Nota |
|---|---|---|
| identificação | `hostname -f` | o endereço vem de quem chamou; o hostname vem do host |
| sistema operacional | `cat /etc/os-release` | `ID` e `VERSION_ID` |
| kernel | `uname -r` | |
| serviços | `systemctl list-units --type=service,socket --state=active` | **`--type=service,socket`**: sem o `socket` os dois proibidos passam |
| swap | `swapon --show --bytes` | vazio significa desabilitado, e é informação, não falha |
| portas em escuta | `ss -lntupH` | traz bind e processo. `-H` tira o cabeçalho e simplifica o parsing |
| chaves SSH | `cat ~/.ssh/authorized_keys` | o **comentário** da chave é o que identifica a origem |
| login de root | `sshd -T \| grep permitrootlogin` | ver abaixo |
| sincronização de tempo | `timedatectl show` | `NTPSynchronized` e o serviço ativo dizem o mecanismo |

### Por que `sshd -T` e não ler o arquivo

O PRD exige **a configuração efetiva, não a escrita no arquivo**. Os dois divergem com
facilidade: `sshd_config.d/*.conf` sobrepõe, `Match` cria bloco condicional, e a primeira
diretiva é que vence em caso de repetição. Ler `/etc/ssh/sshd_config` com `grep` responde o
que alguém escreveu, não o que o daemon aplica.

`sshd -T` imprime a configuração resolvida. **E exige privilégio** — é exatamente o caso
típico de `nao_verificado` que o PRD descreve, e por isso o usuário da coleta no laboratório
é sem privilégio de propósito.

### Portas: a porta sozinha não decide

O baseline separa `publicas_permitidas: [22]` de `somente_rede_interna: [9100]`. Então o
coletor precisa de **três** campos por porta: número, endereço de bind e processo dono.

`9100` em `127.0.0.1` é conforme. `9100` em `0.0.0.0` é **desvio crítico**. É a mesma porta.

Normalização do bind, para o julgamento não depender de formato:

| Bind observado | Classificação |
|---|---|
| `0.0.0.0`, `*`, `::`, `[::]` | **público** |
| `127.0.0.1`, `::1`, `[::1]` | **loopback** |
| qualquer outro IP | **rede interna** |

## Etapa 3 — julgamento

Uma entrada por regra do baseline. Onze regras, nos três níveis de severidade que o
baseline define.

| Regra | Comparação |
|---|---|
| `so.distribuicao` | igualdade com `ID` do `os-release` |
| `so.versao_minima` | comparação de versão, **por componente numérico** |
| `kernel.versao_minima` | idem, ignorando o sufixo do fornecedor (`-118-generic`) |
| `servicos.ativos` | todos os esperados estão na lista de ativos |
| `servicos.proibidos` | nenhum proibido está ativo |
| `swap.habilitado` | igualdade com booleano |
| `portas_em_escuta.publicas_permitidas` | nenhuma porta em bind público fora da lista |
| `portas_em_escuta.somente_rede_interna` | as da lista **não** estão em bind público |
| `chaves_ssh.emitidas_por` | toda chave tem o emissor esperado no comentário |
| `ssh.login_de_root` | igualdade com booleano |
| `ntp.sincronizado` | igualdade com booleano |

**Comparação de versão é por componente, não lexicográfica.** `"22.04" < "9.10"` é verdade
em comparação de string e falso no mundo. `5.15.0-118-generic` contra mínimo `6.5` precisa
virar `(5,15,0)` contra `(6,5)`.

Severidade **nunca é inferida** — vem do mapa `severidade` do baseline. Se uma regra não
aparecer em nenhum dos três níveis, isso é erro do baseline e a ferramenta diz, em vez de
assumir um nível.

## Etapa 4 — apresentação

Os dois formatos consomem a mesma estrutura.

**JSON**: `host`, `inventario`, `conformidade`, `resumo`. `resumo` traz as contagens por
veredito e, dentro de `por_severidade`, a contagem **dos desvios** — não de todas as regras.

**Markdown**: desvios primeiro, ordenados por severidade (`critico`, `alto`, `medio`),
depois `nao_verificado` com o motivo, depois os conformes em uma linha. O plantão lê de cima
para baixo e para quando quiser.

## Determinismo

RE-02 exige que duas execuções devolvam o mesmo veredito. Três fontes de variação, e o que
cada uma exigiu:

| Fonte | Tratamento |
|---|---|
| ordem de saída de `systemctl` e `ss` | **ordenar** tudo que é lista antes de comparar e de imprimir |
| o instante da coleta | é o único campo que muda, e é declarado assim no PRD |
| `uptime`, PID, uso de memória | **não coletados.** Não estão no baseline e tornariam a saída instável |

Não coletar PID foi decisão: ele identificaria o processo dono da porta com mais precisão, e
muda a cada reinício. O **nome** do processo basta para o julgamento.

## Segredo

RE-03: a chave privada não aparece em saída, log nem erro.

- a chave é passada por **caminho**, nunca por conteúdo
- erro de conexão reporta **categoria**, não o comando que falhou. "chave recusada pelo
  host" e não a linha de `ssh -i /caminho/para/chave`
- o `stderr` do `ssh` é **classificado**, não repassado cru, porque ele pode conter o
  caminho da chave

## Falha de conexão

CA-04 exige mensagem que explica, sem stack trace, e que **não** seja confundida com host
conforme. Três categorias distinguíveis pelo `stderr` do `ssh`:

| Categoria | Sinal |
|---|---|
| host inalcançável | `No route to host`, `Connection refused`, `timed out` |
| autenticação recusada | `Permission denied`, `publickey` |
| chave do host mudou | `REMOTE HOST IDENTIFICATION HAS CHANGED` |

As três saem com **código 2** e nenhuma produz bloco de conformidade — é o que impede
confundir com `conforme`.

## O que o laboratório não consegue provar

**ADR-004**: o laboratório usa containers com systemd, e duas regras do baseline são de
nível de host — `kernel.versao_minima` e `swap.habilitado`. Container compartilha o kernel e
o namespace de swap do host.

Isso não é limitação da ferramenta. Ela coleta e reporta o que encontra, e o que encontra é
o kernel e o swap do host. Mas afeta o que o CA-01 consegue demonstrar, e está tratado lá.
