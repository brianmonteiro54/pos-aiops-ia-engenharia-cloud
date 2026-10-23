# Registro do comportamento das skills durante o Ticket 04

O ticket pede: quais skills dispararam sozinhas, quais eu precisei chamar, quais apareceram
onde não deviam, e o que eu tive que reexplicar.

A resposta honesta começa por um fato que invalida metade da pergunta.

## O fato que precisa vir primeiro: nenhuma skill foi carregada

Durante todo este ticket, **zero skills estavam ativas no runtime**. Não é
interpretação; é verificável de dois lados.

**Do lado do runtime:** a sessão lista os itens disponíveis para ativação como
`**Available Items:** None`.

**Do lado do disco:** existem 14 arquivos `SKILL.md` no repositório.

| Onde | Quantas | Quais |
|---|---|---|
| `<repo>/.kiro/skills/` | 2 | `padrao-de-manifests-metacortex`, `triagem-de-cluster-metacortex` |
| `ticket-03-.../roster-inventario/.kiro/skills/` | 6 | as do OpenSpec, instaladas pelo `init` |
| `ticket-04-.../cluster-retrato/.kiro/skills/` | 6 | idem |

O Kiro varre **duas** pastas: `<raiz-do-workspace>/.kiro/skills/` e `~/.kiro/skills/`. A
raiz do workspace desta sessão é `/home/brian/apagar/aiops`, e nenhuma das duas existe lá:

```
$ ls -d /home/brian/apagar/aiops/.kiro/skills/*
ls: cannot access ...: No such file or directory
$ ls -d ~/.kiro/skills/*
ls: cannot access ...: No such file or directory
```

As 2 skills que eu escrevi estão na raiz do **repositório**, que não é a raiz do
**workspace**. As 12 do OpenSpec estão em subpastas, e subpasta não é varrida.

### O que isso faz com as quatro perguntas do ticket

| Pergunta | Resposta honesta |
|---|---|
| quais dispararam sozinhas | **nenhuma.** Não havia nada carregado para disparar |
| quais eu precisei chamar | **nenhuma**, no sentido de ativar. Nenhuma estava disponível |
| quais apareceram onde não deviam | **nenhuma.** Zero ativações, zero falsos positivos |
| o que eu tive que reexplicar | **tudo o que as skills diriam**, porque elas não estavam lá |

Um relatório que dissesse "a skill de triagem disparou sozinha quando li o cluster" seria
mais bonito e seria falso. O que aconteceu é diferente, e é mais interessante.

## O que aconteceu de verdade: as skills viraram memória, não ferramenta

As duas skills que eu escrevi nos Tickets 01 e 02 **foram usadas** neste ticket. Só não
como skills. Elas funcionaram como documentos que eu já havia escrito e cujo conteúdo eu
carregava no contexto da conversa. Isso tem três consequências práticas.

### 1. O conhecimento aplicado é rastreável, a ativação não é

Dá para apontar onde cada skill influenciou o Ticket 04:

| Skill | Onde entrou no Ticket 04 | Como entrou |
|---|---|---|
| `padrao-de-manifests` | regra 3.7 (tag de imagem) ao subir o workload: `registry.metacortex.io` não existe, e `subir-workload.sh` faz `kubectl set image` depois do apply | conhecimento meu, não ativação |
| `padrao-de-manifests` | regra 2.2 (probes) virou o RF-03: a skill julga se a probe **existe no arquivo**; o dashboard mostra o efeito de ela **não existir** | o requisito nasceu da regra |
| `triagem-de-cluster` | os três fatos que moldaram a normalização: `phase: Running` em CrashLoop, `readyReplicas` ausente, endpoint vazio | medições do Ticket 02, recarregadas |
| `triagem-de-cluster` | os três chamados viraram os casos de teste do CA-03 e CA-04 | o cluster do Ticket 02 continuou no ar |

Mas **nenhuma dessas entradas é uma ativação de skill.** São eu lembrando do que escrevi.
Se outra pessoa abrisse este repositório como workspace, as 2 skills carregariam e o
comportamento poderia ser diferente — melhor ou pior. Eu não medi isso, e não posso
afirmar nada sobre ele.

### 2. A divergência mais útil deste ticket veio de uma skill não ter sido consultada

A skill do Ticket 01 julga **arquivo**. A do Ticket 02 lê **estado do cluster**. O
Ticket 04 esbarrou na costura entre as duas:

`subir-workload.sh` aplica manifests que satisfazem a regra 3.7 (tag fixa, sem `latest`) e
em seguida roda `kubectl set image` para uma imagem pública, porque
`registry.metacortex.io` não existe. Resultado: **a regra está satisfeita no artefato e
insatisfeita no cluster.** A skill do T01 aprovaria o arquivo; a do T02 veria uma imagem
que não é a declarada.

Isso não é defeito de nenhuma das duas. É que "conformidade" significa coisas diferentes
para quem lê arquivo e para quem lê cluster, e nenhuma das duas skills diz isso. **Está
registrado aqui porque é o tipo de lacuna que só aparece quando as duas são usadas no mesmo
trabalho** — e eu só percebi porque estava escrevendo as duas coisas, não porque alguma
skill avisou.

### 3. O OpenSpec foi conduzido pela CLI, não pelas skills que ele instalou

O `openspec init` instalou 6 skills e 6 prompts em
`cluster-retrato/.kiro/skills/` e `.kiro/prompts/`. Nenhuma foi usada. Todo o ciclo foi
feito pela linha de comando:

```
openspec new change "dashboard-de-leitura-do-cluster"
openspec validate dashboard-de-leitura-do-cluster --strict
openspec status --change dashboard-de-leitura-do-cluster
openspec archive dashboard-de-leitura-do-cluster
```

Duas coisas que só a CLI me deu, e que a skill não teria dado tão rápido:

- **`openspec templates`** imprime o caminho dos gabaritos. Ler o gabarito resolveu de uma
  vez a dúvida de formato que no Ticket 03 eu errei: os cabeçalhos do `proposal.md` são
  `## Why` e `## What Changes`, **em inglês**, mesmo com o projeto configurado em `pt-BR`.
  No Ticket 03 eu os escrevi em português e o `validate` reclamou
- **`openspec new`** sem subcomando devolve `error: unknown command`. O comando é
  `new change <nome>`. Descobri com `--help`, não com a skill

## O que eu tive que reexplicar a mim mesmo, e que deveria estar numa skill

Esta é a parte aproveitável do registro. Três coisas que eu redescobri neste ticket e que
nenhuma das duas skills cobre:

**1. `--request-timeout` do `kubectl` não limita o comando.** Medido: sem teto, travou além
de 70s contra endereço não roteável; com `--request-timeout=5s`, levou 25s. A skill de
triagem recomenda comandos de leitura e não diz nada sobre teto de tempo — e qualquer
ferramenta que chame `kubectl` de dentro de um handler HTTP precisa saber disso. **Candidato
a entrar na skill de triagem.**

**2. Os nove modos de falha de acesso devolvem `exit 1`, e três deles a mesma mensagem.**
Token inválido, token expirado e certificado de cliente expirado são indistinguíveis.
A skill de triagem assume cluster acessível em todos os seus caminhos. **Candidato a uma
seção nova: "quando o `kubectl` não fala com o cluster".**

**3. A skill de triagem fazia a pergunta errada sobre endpoint — e eu errei duas vezes
antes de chegar nisso.**

Primeiro escrevi aqui que "a reference do Ticket 02 registrou a chave ausente e não a chave
nula". **Falso.** Fui conferir antes de corrigir e `references/leitura-da-api.md` já tinha
os dois modos, a comparação lado a lado e o idioma `len(x.get("endpoints") or [])`. A
reference estava certa; minha memória dela, não. Fica registrado porque é o mesmo erro que
o Ticket 01 cometeu três vezes: afirmar sobre um documento meu sem reler o documento.

A lacuna real é outra, e é no `SKILL.md`, não na reference. O Passo 5 dizia:

> A pergunta é uma só: **o Service tem endpoint?**

Sim-ou-não é a pergunta errada. Medido nos quatro estados do cluster: no `CrashLoopBackOff`
e no `ImagePullBackOff` o Service **tem** endpoints — existem e não servem. `len()` devolve
2 e 3, e quem pergunta "tem endpoint?" ouve "sim" e segue adiante.

A skill escapava disso por acidente: o Passo 5 só é alcançado quando os passos 3 e 4 não
acusaram nada, ou seja, com pod pronto. Dentro do roteiro, a pergunta funciona. **Fora do
roteiro, engana** — e foi exatamente o que me fez escrever `prontos/total` no dashboard em
vez de um sim/não.

**Corrigido nos dois arquivos**, com a tabela de medição anexa: a pergunta passou a ser
"quantos endpoints prontos", e a reference ganhou a seção
"contar endpoints não é contar endpoints prontos".

E uma correção ao PRD deste próprio ticket, que a medição produziu: eu havia escrito que
"ausência de endpoint explica 'subiu mas não responde'". Errado nos chamados 1 e 2, onde o
objeto `Endpoints` **tem** `subsets`, populado com `notReadyAddresses`. A pergunta certa é
**quantos prontos**. Corrigido no PRD, no RF-02 e no CA-03.

## Conclusão do registro

O ticket pede observação de comportamento de skill em uso. **Eu não consigo entregar essa
observação para este ticket**, porque o ambiente não carregou nenhuma skill, e eu prefiro
dizer isso a inventar ativações.

O que o ticket rendeu, e que vale mais que um relato fabricado:

- **uma medição de onde skill é carregada e onde não é**, verificada dos dois lados
- **uma lacuna real entre as duas skills** — conformidade de arquivo contra conformidade de
  cluster — que só aparece usando as duas no mesmo trabalho
- **três itens concretos para a próxima revisão das skills**, todos com medição anexa
- **uma correção aplicada à skill do Ticket 02**: o Passo 5 perguntava "o Service tem
  endpoint?" e passou a perguntar "quantos prontos", com a tabela de medição
- **um erro meu, pego e registrado**: afirmei que a reference de triagem estava incompleta
  sem reler a reference. Ela não estava

Para observar ativação de verdade, o teste tem que ser: abrir
`/home/brian/pos-aiops-ia-engenharia-cloud` **como raiz do workspace** e repetir uma tarefa
de triagem. Não fiz isso neste ticket. Fica dito como o experimento que falta, não como
resultado.
