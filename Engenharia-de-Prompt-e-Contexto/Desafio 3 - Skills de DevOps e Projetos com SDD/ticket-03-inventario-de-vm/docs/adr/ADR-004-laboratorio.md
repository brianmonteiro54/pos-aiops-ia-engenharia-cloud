# ADR-004 — Como validar a ferramenta sem uma frota de VMs

**Status:** aceito
**Contexto:** os critérios de aceite exigem um host **conforme**, um host **com desvios**, um
host **inalcançável** e uma regra **não verificável**. Não há frota de VMs disponível.

Este ADR não estava na lista de decisões que o ticket manda registrar. Entrou porque ele
**limita o que os critérios de aceite conseguem demonstrar**, e deixar isso implícito seria
apresentar como provado algo que não foi.

## Decisão

**Dois containers Docker privilegiados com systemd como PID 1, um ajustado para
conformidade e um com desvios deliberados, auditados por SSH em portas diferentes do
loopback. E o registro explícito de duas regras do baseline que o laboratório não consegue
satisfazer.**

## Alternativas consideradas

### A — VM de verdade, com Vagrant ou multipass

**O que se ganha:** é o alvo real. Kernel próprio, swap próprio, systemd de verdade,
`/proc` próprio. **Todas as onze regras do baseline seriam demonstráveis**, incluindo
kernel e swap.

**O que se perde:**

- o ambiente é **WSL2**, e virtualização aninhada ali é instável quando funciona
- uma VM Ubuntu 22.04 com os quatro serviços do baseline leva minutos para subir e ocupa
  GB. Dois hosts dobram
- o ciclo de iteração fica longo o bastante para desencorajar refazer a validação, que é
  justamente o que CA-05 exige fazer duas vezes

### B — `localhost` via SSH contra a própria estação

**O que se ganha:** zero infraestrutura. Kernel e swap reais, porque é a máquina real.

**O que se perde, e é fatal:**

- **não há dois hosts.** Um host conforme e um com desvios exigiriam reconfigurar a estação
  entre as execuções, o que destrói CA-05 — a segunda execução deixaria de ser comparável
- **exigiria mudar a estação para criar desvio**: habilitar `PermitRootLogin yes`, instalar
  `rpcbind`, adicionar chave de origem desconhecida ao próprio `authorized_keys`. Degradar a
  máquina de quem opera para testar uma auditoria é precisamente o contrário do objetivo
- `sshd -T` como o próprio usuário poderia funcionar, e **CA-03 deixaria de ser
  exercitável**

### C — mock do transporte, sem SSH

**O que se ganha:** teste rápido, determinístico e sem infraestrutura. Cobriria coleta,
julgamento e apresentação com saída gravada.

**O que se perde:** **a parte que mais erra.** `ss -lntupH` muda de formato entre versões,
`systemctl list-units` tem colunas que variam, `sshd -T` falha de um jeito específico sem
privilégio. Mock testa o meu entendimento do formato, não o formato.

Serve como complemento — e não substitui a execução real que o ticket pede como evidência.

### D — containers com systemd (escolhida)

**O que se ganha:**

- **systemd de verdade.** `systemctl list-units --type=service,socket` responde, e a
  distinção `service` x `socket` que o baseline exige é exercitável — o host de desvios tem
  `rpcbind.socket` **ativo**
- **sshd de verdade**, com `sshd_config.d/` e configuração efetiva. `sshd -T` falha por
  privilégio exatamente como numa VM
- **dois hosts simultâneos**, em portas 2201 e 2202, sem tocar a estação
- sobem em segundos, então refazer a validação é barato
- os dois são **construídos por Dockerfile versionado**: a diferença entre conforme e
  desvio é diff de arquivo, não configuração manual esquecida

**O que se perde, e é o ponto deste ADR:**

| Regra do baseline | Por que o container não satisfaz |
|---|---|
| `kernel.versao_minima: "6.5"` | container **compartilha o kernel do host**. Aqui é `5.15.167.4-microsoft-standard-WSL2`. Nenhuma configuração do container muda isso |
| `swap.habilitado: false` | `/proc/swaps` mostra o swap do **host**. Esta estação tem 4 GiB ligados |

As duas são de **nível de host**, não de nível de container. E as duas são de severidade
alta no baseline — `swap.habilitado` é `critico`, `kernel.versao_minima` é `medio`.

## O que isso faz com CA-01

CA-01 diz: *um host conforme sai sem nenhum desvio.*

Contra o baseline do parque, o host "conforme" do laboratório sai com **dois desvios** —
kernel e swap — e os dois são verdadeiros: o kernel é 5.15 e há swap ligado. **A ferramenta
está certa; o laboratório é que não é uma VM do parque.**

Então CA-01 é demonstrado em duas partes, e as duas estão na evidência:

1. **contra `baseline-laboratorio.yaml`**, idêntico ao do parque exceto por não ter as duas
   regras de nível de host — o host conforme sai com **zero desvios e código 0**. Isso prova
   a lógica de julgamento.
2. **contra `baseline.yaml` do parque**, o mesmo host sai com **exatamente dois desvios**,
   kernel e swap, e nada mais. Isso prova que os dois desvios são os previstos por este ADR
   e não um defeito escondido.

O baseline do laboratório tem o motivo escrito dentro dele. **Não é o baseline do parque
afrouxado para o teste passar** — é o baseline do parque menos as regras que o meio de teste
não pode responder, e a diferença é auditável por `diff`.

## Consequências

- a validação roda com `docker build` e `docker run`, reproduzível por quem clonar o repo
- `chaves/*.pub` entram no repositório porque o build precisa delas; **as privadas ficam
  fora**, geradas por script
- quando houver VM de verdade, CA-01 passa a ser demonstrável em uma parte só. O caminho é
  trocar o alvo, porque a ferramenta não sabe o que há do outro lado do SSH
- o `--privileged` dos containers é do **laboratório**, não da ferramenta. A ferramenta
  entra por SSH com usuário comum, e é justamente a falta de privilégio dela que exercita
  CA-03
