# Brainstorm — escopo do substituto do Roster

Antes do PRD: o que entra, o que fica de fora, e as perguntas que precisaram de resposta
antes de qualquer linha de spec. Escrito em conversa com o agente, registrando as ideias
descartadas porque elas é que explicam o recorte.

## O problema, como ele chega

O Roster é uma página de wiki mantida à mão. Os sintomas que o ticket nomeia:

- hosts que mudaram de papel e o inventário não acompanhou
- agentes instalados e nunca registrados
- chaves SSH que ficaram para trás
- **ninguém consegue dizer quantas VMs estão fora do padrão**

A última é a que importa. As três primeiras são consequências de a fonte da verdade ser
uma página que alguém edita. A pergunta "quantas VMs estão fora do padrão" não tem resposta
porque não existe nada que compare o estado real com o padrão escrito.

## O que isto NÃO é

Decidir isto primeiro economizou metade das discussões.

| Ideia levantada | Por que ficou fora |
|---|---|
| **um agente nas VMs** | o ticket é explícito: as VMs não têm agente e nenhum será instalado. E a decisão é boa — agente é software para manter, atualizar e auditar em cada host, e o Roster está desatualizado justamente por falta de alguém mantendo coisa |
| **corrigir o desvio que encontrar** | auditoria que conserta não é auditoria. E mais: conserto exige saber o que o host faz, qual cliente usa, e qual janela de manutenção existe. Nada disso está no baseline |
| **varrer o parque inteiro de uma vez** | é a segunda peça. Esta é a primeira: **uma VM**. Paralelizar antes de a coleta de uma estar correta multiplica o erro |
| **servir uma API ou um banco** | o consumidor é o Roster, que já existe. A ferramenta produz JSON; quem orquestra é outro problema |
| **descobrir hosts na rede** | sem lista de hosts, descoberta é varredura de rede, que é problema de segurança e não de inventário. O endereço vem de quem chama |
| **histórico e tendência de drift** | exige armazenamento e versionamento de coleta. Útil, e não é o primeiro corte |

## O que isto é, em uma frase

**Uma ferramenta de linha de comando que entra numa VM por SSH, coleta nove grupos de dados,
compara com um baseline versionado e devolve o veredito de cada regra em JSON e em
Markdown.**

## As perguntas que precisaram de decisão

### 1. Como falar com o host?

Três caminhos reais, e a escolha muda a dependência da ferramenta:

- biblioteca SSH na linguagem (paramiko, golang.org/x/crypto/ssh)
- o binário `ssh` do sistema, como subprocesso
- um transporte de orquestração pronto (Ansible, pssh)

→ **ADR-001.**

### 2. O que acontece quando um dado não volta?

O ticket já decidiu a forma — `nao_verificado` — mas não o mecanismo. As opções que
apareceram:

- abortar a execução inteira
- reportar como `conforme` (mentira)
- reportar como `desvio` (também mentira, e pior: gera trabalho falso)
- **um terceiro veredito**, com o motivo

O caso típico é concreto: a coleta entra com usuário comum e `sshd -T` exige privilégio.

→ **ADR-002.**

### 3. Em que linguagem?

O mantenedor é um time de infraestrutura, não um time de produto. Isso pesa mais que
preferência técnica.

→ **ADR-003.**

### 4. Como testar isto sem uma frota de VMs?

Apareceu durante o brainstorm e virou decisão própria, porque afeta o que os critérios de
pronto conseguem demonstrar: **container com systemd não é VM**, e duas regras do baseline
são de nível de host.

→ **ADR-004.**

## A decisão de desenho que organiza o resto

**Coleta e julgamento são etapas separadas.**

A ferramenta primeiro coleta — nove grupos de dados, cada um com sucesso ou falha — e só
depois compara com o baseline. Duas consequências que valem o esforço:

1. **O inventário tem valor sem o baseline.** O Roster quer saber o que existe, não só o
   que está errado. O JSON entrega `inventario` e `conformidade` em blocos separados de
   propósito.
2. **Trocar o baseline não mexe na coleta.** Baseline v2 exigindo kernel 6.8 não muda uma
   linha de coletor.

O inverso — julgar durante a coleta — economizaria código e amarraria as duas coisas. É a
troca que o ticket paga pelos dois formatos de saída saírem "do mesmo dado".

## Riscos que eu enxerguei antes de começar

| Risco | O que fiz |
|---|---|
| **a chave privada vazar em log ou erro** | restrição explícita no PRD e critério de pronto próprio. É credencial, não parâmetro |
| **a ferramenta parecer determinística e não ser** | critério de pronto: duas execuções, mesmo veredito. O único campo que muda é o instante da coleta |
| **confundir "não coletei" com "está conforme"** | é o ADR-002, e é o erro que torna uma auditoria pior que nenhuma |
| **comando de coleta que escreve no host** | restrição de só-leitura. Nada é instalado, escrito ou corrigido |
| **`systemctl` distinguir `.service` de `.socket`** | o baseline proíbe dois **sockets**. Coletar só serviços deixaria passar os dois |

## O que eu deixei explicitamente para depois

- varredura de frota e paralelismo
- histórico de drift
- baseline por papel de host (`aplica_a` existe no baseline e hoje só tem um valor)
- correção automática, que não deve existir nunca nesta ferramenta
