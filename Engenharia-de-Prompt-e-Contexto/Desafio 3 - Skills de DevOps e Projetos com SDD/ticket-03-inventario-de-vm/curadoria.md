# Curadoria — onde a spec precisou ser corrigida, e o que o agente entendeu diferente

O ticket pede duas coisas desta curadoria: **onde a spec precisou ser corrigida durante a
implementação** e **o que o agente entendeu diferente do que eu escrevi**. As duas abaixo,
com o que mudou em cada caso.

## 0. Como o projeto foi produzido

| | |
|---|---|
| **Agente** | Kiro (IDE), modo Autopilot |
| **Modelo** | Claude Opus 5 |
| **Ciclo de spec** | OpenSpec 1.14.3, schema `spec-driven`, via `npx @fission-ai/openspec` |
| **Laboratório** | dois containers Docker com systemd como PID 1 |
| **Ferramenta** | Python 3.10, biblioteca padrão + PyYAML |

A ordem foi a do desafio: brainstorm → PRD → TRD e ADRs → ciclo OpenSpec → implementação →
validação. **Nenhuma linha de `roster_inventario.py` foi escrita antes de `tasks.md`
existir.**

## 1. Onde a spec precisou ser corrigida durante a implementação

### 1.1 `dbus` não estava em lugar nenhum da spec, e sem ele metade das regras morria

**O que a spec dizia.** O TRD lista `systemctl list-units --type=service,socket` como o
comando de coleta de serviços, e o ADR-004 justifica container com systemd dizendo que
"`systemctl` responde".

**O que a primeira validação mostrou.** Quatro regras saíram como `nao_verificado`:

```
| servicos.ativos    | systemctl nao respondeu: Failed to connect to bus: No such file or directory |
| servicos.proibidos | systemctl nao respondeu: Failed to connect to bus: No such file or directory |
| ntp.sincronizado   | timedatectl nao respondeu |
```

**A causa.** `systemctl` e `timedatectl` falam com o systemd pelo **D-Bus do sistema**.
Root consegue pelo socket privado do systemd; **usuário comum precisa do `dbus`**, e eu não
o instalei na imagem base.

**Por que isso quase passou.** Durante a construção do laboratório eu validei com
`docker exec systemctl is-active`, que **roda como root** e funcionou. A falha só aparece
pelo caminho que a ferramenta usa: SSH com usuário sem privilégio.

**O que mudou.** `dbus` entrou no `Dockerfile.base`, com o motivo escrito em comentário. É
correção do **laboratório**, não da ferramenta: ela reportou `nao_verificado` com o motivo
real, que é o comportamento especificado em ADR-002.

**O que isso ensina sobre a spec.** O ADR-004 afirmava que o container entrega "systemd
respondendo a `systemctl`". Entregava — para root. A spec não distinguiu **quem** pergunta,
e a ferramenta pergunta como usuário comum de propósito. A premissa estava certa e
incompleta.

### 1.2 Host key de container recriado barra a ferramenta, e ela está certa

**O que a spec dizia.** O TRD fixa `StrictHostKeyChecking=accept-new`, com o motivo: aceita
host novo e **recusa host cuja chave mudou**.

**O que aconteceu.** Depois de reconstruir as imagens, a validação inteira falhou:

```
erro: a chave do host mudou desde a última conexão; o acesso foi recusado por segurança
codigo de saida: 2   (esperado 0)
```

Container recriado gera host key nova no mesmo `127.0.0.1:2201`.

**A decisão.** Não afrouxar. `StrictHostKeyChecking=no` faria a validação passar e
transformaria a ferramenta em algo que aceita man-in-the-middle. O que entrou foi
`ssh-keygen -R` no `subir.sh`, **com o motivo escrito**: é higiene do laboratório, não
concessão da ferramenta. Num parque de verdade, chave de host que muda sem reinstalação é
incidente.

**Efeito colateral útil.** Antes do conserto, o caso "chave recusada" do CA-04 reportava
`a chave do host mudou` em vez de `autenticação recusada`, porque a verificação de host key
acontece **antes** da autenticação. Depois, as quatro categorias de falha ficaram
distinguíveis — e isso é precisão que eu não teria testado se a validação tivesse passado
de primeira.

### 1.3 O CA-01 não era demonstrável como escrito, e o conserto foi na validação

**O que a spec dizia.** CA-01: *um host conforme sai sem nenhum desvio.*

**O problema, percebido ainda no brainstorm.** Container compartilha kernel e namespace de
swap do host. Esta estação tem kernel 5.15 e 4 GiB de swap ligados. Contra o baseline do
parque, o host "conforme" sai com **dois desvios verdadeiros**.

**O que eu rejeitei.** Afrouxar `baseline.yaml` para o teste passar. Seria mentir sobre o
padrão do parque para um critério de aceite ficar verde.

**O que entrou.** `baseline-laboratorio.yaml`, idêntico ao do parque **menos** as duas
regras de nível de host, com o motivo dentro do arquivo, e **CA-01 demonstrado em duas
partes**:

| Parte | Baseline | Resultado medido |
|---|---|---|
| CA-01 | laboratório | **0 desvios, rc=0** — prova a lógica de julgamento |
| CA-01b | parque | **exatamente 2 desvios**: `swap.habilitado` crítico e `kernel.versao_minima` médio | 

A segunda parte é a que vale: ela prova que os dois desvios são **os previstos pelo
ADR-004** e não um defeito escondido. A diferença entre os dois arquivos é auditável por
`diff`.

Isso virou o ADR-004, que **não estava na lista de decisões que o ticket manda registrar**.
Entrou porque limita o que os critérios de aceite conseguem demonstrar, e deixar implícito
seria apresentar como provado algo que não foi.

### 1.4 O código de saída com `nao_verificado` ficou sem resposta na spec

**O que a spec dizia.** O PRD define `0` conforme, `1` com desvio, `2` inalcançável. E
define `nao_verificado` como veredito que não é desvio.

**O que faltava.** Um host com 10 conformes e 1 `nao_verificado` sai com qual código? A
spec não respondia, e os três candidatos têm problema:

| Opção | Problema |
|---|---|
| `0` | a esteira promove host que não foi auditado por inteiro |
| `1` | reintroduz "não sei" como "está errado", que é o erro que o ADR-002 evita |
| quarto código | a esteira passa a ter quatro casos, e `2` já significa "não consegui olhar" |

**O que entrou.** `0`, com duas condições que tornam a lacuna impossível de ignorar: o
`resumo` do JSON conta `nao_verificado` à parte, e o Markdown tem seção própria com motivo.

O raciocínio: o código de saída responde **"este host está fora do padrão?"**. Dado não
coletado não é resposta afirmativa. A pergunta "a auditoria foi completa?" é outra e tem
campo próprio.

**Registrado no ADR-002 como a decisão menos confortável do projeto.** Se a casa decidir
que auditoria incompleta barra promoção, a mudança é uma condição no código de saída, e o
dado já está na saída.

## 2. O que o agente entendeu diferente do que eu escrevi

### 2.1 "A configuração efetiva, não a escrita no arquivo" — e eu quase implementei o arquivo

O PRD diz, sobre login de root: *a configuração efetiva (a que vale), não a que está escrita
no arquivo.*

Minha primeira leitura, ao escrever o TRD, foi `grep PermitRootLogin /etc/ssh/sshd_config`.
Funciona, e é a resposta errada: `sshd_config.d/*.conf` sobrepõe, `Match` cria bloco
condicional, e em repetição **a primeira diretiva vence**, não a última.

O que a frase exige é `sshd -T`, que imprime a configuração resolvida pelo daemon. E é por
isso que a regra cai em `nao_verificado` no laboratório — `sshd -T` exige privilégio.

**A frase da spec estava certa e eu quase a implementei ao contrário.** Os dois hosts do
laboratório têm `PermitRootLogin` em `sshd_config.d/00-metacortex.conf`, que é exatamente
o arquivo que um `grep` no `sshd_config` principal não veria.

### 2.2 "Distinguindo service de socket" parecia detalhe de formatação

O PRD pede que os serviços voltem *distinguindo `service` de `socket`*. Na primeira leitura
eu entendi como campo informativo do inventário.

É filtro de coleta. `systemctl list-units --type=service` é o default que a mão digita, e
`telnet.socket` e `rpcbind.socket` — **os dois únicos itens de `servicos.proibidos`** — não
aparecem ali. Sem `--type=service,socket`, a regra `servicos.proibidos` sempre diria
"nenhum ativo".

A validação confirma que o filtro é necessário: o host de desvios tem `rpcbind.socket`
**ativo**, e aparece como desvio alto.

### 2.3 "Porta 9100 em 0.0.0.0 e porta 9100 só no endereço interno têm vereditos diferentes"

Esta frase do ticket eu li três vezes antes de entender que ela obriga **três campos por
porta**, não dois. Porta e processo não bastam — sem o endereço de bind, as duas situações
são indistinguíveis.

E obriga uma **normalização**: `0.0.0.0`, `*`, `::` são o mesmo escopo com três grafias. O
`ss` reporta `*` em alguns casos e `0.0.0.0` em outros, e a evidência mostra o host de
desvios com `9100 em *`.

Sem a normalização, a regra `somente_rede_interna` passaria dependendo da grafia que o `ss`
escolheu naquela execução — e seria um bug intermitente, do pior tipo.

### 2.4 A comparação de versão: `"22.04" < "9.10"`

O TRD diz "comparação de versão por componente". Escrevi isso sabendo o motivo e ainda
assim vale registrar, porque é o erro que eu teria cometido sem pensar: em comparação de
string, `"22.04" < "9.10"` é **verdadeiro**, e o host Ubuntu 22.04 sairia como desvio contra
um mínimo de 9.10.

E o kernel exige descartar o sufixo do fornecedor: `5.15.167.4-microsoft-standard-WSL2`
contra `6.5` precisa virar `(5,15,167,4)` contra `(6,5)`.

## 3. Saídas ruins, que também contam

| O que deu errado | O que eu faria diferente |
|---|---|
| **validei o laboratório como root** e só descobri o problema do `dbus` na primeira execução da ferramenta | validar o laboratório pelo **mesmo caminho** que a ferramenta usa — SSH, usuário comum — desde o primeiro minuto |
| o `validar.sh` teve **dois bugs de quoting** de f-string em heredoc de shell, que estouraram `SyntaxError` e `JSONDecodeError` no meio da validação | não misturar f-string de Python com escape de shell. Virou heredoc com `<<'PY'` e `.format()` |
| gastei uma rodada inteira de validação com as **host keys obsoletas**, e a saída ficou ilegível | o `subir.sh` agora limpa, e a limpeza tem o motivo escrito |

Nenhuma das três foi defeito da ferramenta. As três foram defeito do **arredor** — do
laboratório e do script de validação — e as três só apareceram porque a validação é
execução real contra host real, não mock.

É o argumento do ADR-004 contra a alternativa C: mock testaria o meu entendimento do
formato, não o formato.

### 3.1 E uma quarta: escrevi os cabeçalhos estruturais no idioma errado

O `openspec/config.yaml` gerado pelo `init --language pt-BR` diz, em inglês:

> Keep OpenSpec structural headings and SHALL/MUST keywords in English.

Escrevi `## Por quê` e `## O quê` no `proposal.md`. O `validate` passou — os cabeçalhos
estruturais não são validados na proposta — e o **`archive` avisou**:

```
⚠ Change must have a Why section. Missing required sections.
  Expected headers: "## Why" and "## What Changes"
```

Não bloqueou, e por isso quase passou. Corrigido para `## Why` e `## What Changes`, com o
corpo em português, que é o que a config pede.

Vale como registro porque é o tipo de erro que o arco de spec existe para pegar: **a
ferramenta sabia a regra, a regra estava escrita no arquivo de configuração que eu mesmo
gerei, e eu não li.** Um aviso não bloqueante é fácil de ignorar, e foi só porque eu leio a
saída do `archive` que ele apareceu.

## 4. O que ficou de fora, e não é esquecimento

| Fora | Por quê |
|---|---|
| **varredura de frota e paralelismo** | esta é a primeira peça: uma VM. A separação coleta/julgamento é o que permite a segunda reusar tudo |
| **histórico de drift** | exige armazenamento entre execuções, e muda o produto de "ferramenta" para "serviço" |
| **correção de desvio** | não deve existir nesta ferramenta. Auditoria que conserta não é auditoria |
| **baseline por papel de host** | `aplica_a` existe no baseline e hoje tem um valor. Quando houver dois papéis, a decisão é onde o papel do host é declarado — e isso não está resolvido |
| **PID do processo dono da porta** | identificaria melhor e **muda a cada reinício**, quebrando o determinismo do RE-02. O nome basta para o julgamento |
| **`uptime`, uso de memória, disco** | não estão no baseline e tornariam a saída instável entre execuções |
