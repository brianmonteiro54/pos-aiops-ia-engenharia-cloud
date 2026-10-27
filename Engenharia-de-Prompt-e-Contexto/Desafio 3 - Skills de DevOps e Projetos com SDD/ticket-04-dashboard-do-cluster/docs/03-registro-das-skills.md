# Registro do comportamento das skills durante o Ticket 04

O ticket pede: quais skills dispararam sozinhas, quais eu precisei chamar, quais apareceram
onde não deviam, e o que eu tive que reexplicar.

## O bloqueio, e como ele foi removido

A primeira versão deste registro não tinha conteúdo, e o motivo era estrutural: **nenhuma
skill estava carregada**. As duas viviam em `<repo>/.kiro/skills/`, e a raiz do workspace da
sessão não era a raiz do repositório.

O Kiro varre dois caminhos e **mescla** os dois: `<raiz-do-workspace>/.kiro/skills/` e
`~/.kiro/skills/`. A correção foi instalar as duas no caminho global, por symlink para o
repositório, de modo que continue havendo uma fonte da verdade:

```
~/.kiro/skills/padrao-de-manifests-metacortex  -> <repo>/.kiro/skills/...
~/.kiro/skills/triagem-de-cluster-metacortex   -> <repo>/.kiro/skills/...
```

Isso vale para qualquer sessão, em qualquer workspace, sem depender de abrir o repositório
como raiz.

### Três coisas que a documentação não cobre, e que eu medi

**1. Ativação explícita funciona na mesma sessão; descoberta automática, não.** A
documentação diz que a descoberta acontece no início da sessão, e não diz o que acontece com
skill criada à mão depois. Medido: a lista de itens disponíveis desta sessão continuou
dizendo `None`, **e a ativação explícita por `disclose_context` funcionou**, devolvendo o
corpo da skill e o diretório resolvido. Conclusão: a lista de descoberta é congelada no
início da sessão; a ativação explícita lê o disco na hora.

Consequência prática: numa sessão já aberta você consegue usar a skill, mas ela **não
dispara sozinha**, porque o gatilho depende de `name` e `description` estarem no contexto
desde o começo.

**2. Sub-agente faz descoberta própria.** A documentação não diz se sub-agente herda skills.
Medido com uma sonda que não fazia nada além de responder:

> **ITENS_DISPONIVEIS:** `padrao-de-manifests-metacortex`, `triagem-de-cluster-metacortex`
> **`disclose_context` disponível:** sim

Isso é o que tornou o resto deste registro possível: **sub-agente é sessão limpa com as
skills descobertas**, e serve de banco de teste de ativação.

**3. Symlink funciona.** O Kiro resolveu o symlink e reportou o diretório final. Não estava
documentado.

## Quais dispararam sozinhas

Treze execuções em sessão limpa, cada uma recebendo só a frase, sem nenhuma menção a skills.
Dez são as frases da matriz de roteamento do Ticket 02; três foram escritas para este
ticket.

| Frase | Ativou | Momento |
|---|---|---|
| "o pod do nyx-prod não sobe" | triagem | antes de qualquer ação |
| "por que esse deployment está 0/3" | triagem | antes de qualquer ação |
| "o service do nyx-stg não tem endpoint" | triagem | antes de qualquer ação |
| "o Service do nyx não está entregando tráfego" | triagem | antes de qualquer ação |
| "revisa esse deployment antes de eu subir" | manifests | antes de qualquer ação |
| "esse manifesto está no padrão da casa?" | manifests | antes de qualquer ação |
| "cria um Deployment novo do zero pra mim" | manifests | antes de qualquer ação |
| **"monta um ServiceAccount de leitura restrita pra eu testar permissão negada"** | **manifests** | antes de qualquer ação |

O artefato que essa ativação produziu está versionado em
`../../ticket-01-padrao-de-manifests/manifests/rbac-leitura-restrita/`, com `DECISOES.md`.
É o que torna esta linha da tabela verificável em vez de só afirmada: a skill ativou em modo
escrita, gerou os três objetos, e eles passam no script da casa com `rc=0` e no
`--dry-run=server`. A negação de `secrets` foi conferida por impersonação contra o cluster.
| "esse manifesto não sobe no cluster" | nenhuma, pediu a mensagem de erro | n/d |
| "o que é um DaemonSet?" | nenhuma | n/d |
| "provisiona uma VM nova no Construct" | nenhuma | n/d |
| **"preciso escrever código Python que leia EndpointSlice e conte endpoints prontos"** | **nenhuma** | n/d |
| **"quero um painel local que mostre o estado do cluster numa tela"** | **nenhuma** | n/d |

**Oito ativações automáticas, todas declaradas como antes de qualquer outra ação.** É o
comportamento esperado: o Kiro trata a ativação como requisito bloqueante quando a
`description` casa.

As três frases em negrito são do Ticket 04 e são as mais informativas, porque este ticket é
**desenvolvimento**, não revisão nem triagem.

## Quais eu precisei chamar

**Uma: `triagem-de-cluster-metacortex`, na sessão principal.** E por um motivo específico: a
descoberta desta sessão aconteceu antes de as skills existirem no caminho global, então a
lista automática estava vazia. Ativei explicitamente para confirmar que o mecanismo
respondia.

Nas treze sessões limpas eu **não** precisei chamar nada: ou disparou sozinha, ou
corretamente não disparou.

## Quais apareceram onde não deviam

**Nenhuma.** E os dois casos de maior risco passaram, o que é o resultado que interessa.

### O teste duro do anti-gatilho

> "preciso escrever código Python que leia EndpointSlice e conte quantos endpoints estão
> prontos por Service"

Essa frase é a pior armadilha possível para as duas skills. Ela contém `EndpointSlice`,
`endpoints prontos` e `Service`: o vocabulário central do passo 5 da triagem, e a própria
contagem `prontos/total` que o ADR-004 deste ticket introduziu na skill.

**Não ativou nenhuma.** O motivo declarado pelo executor:

> o pedido é escrever código Python que consulta a API de EndpointSlice, e não revisar ou
> gerar manifesto YAML nem diagnosticar algo quebrado no cluster agora

É exatamente o critério que a matriz de roteamento identificou como a melhor linha das duas
descriptions: **o limite é a fonte da verdade, e nenhuma das duas é "código que eu vou
escrever"**. A cláusula geral roteou uma frase que não está em enumeração nenhuma.

### A distinção que um dos executores fez e que vale registrar

A frase do painel também não ativou, e o executor acrescentou:

> li o `SKILL.md` da triagem como referência do repositório, o que não é ativação

**Ler o arquivo e ativar a skill são coisas diferentes.** Na primeira delas o conteúdo entra
como documento do projeto, igual a qualquer outro; na segunda ele entra como instrução de
método. Para um registro de disparos isso precisa estar separado, e foi o executor que
separou.

## O que eu tive que reexplicar

Quatro coisas que eu redescobri neste ticket e que nenhuma das duas skills cobre.

**1. `--request-timeout` do `kubectl` não limita o comando.** Medido: contra endereço não
roteável, sem teto o `kubectl` passou de 70 s; com `--request-timeout=5s` levou 25 s. Ele
limita cada requisição, não o comando, porque a descoberta de grupos da API é repetida. A
skill de triagem recomenda comandos de leitura e não diz nada sobre teto de tempo.
**Candidato a entrar na skill**, e obrigatório para qualquer ferramenta que chame `kubectl`
de dentro de um handler HTTP.

**2. Os nove modos de falha de acesso devolvem `exit 1`, e três deles a mesma mensagem.**
Token inválido, token expirado e certificado de cliente expirado são indistinguíveis. A
skill de triagem assume cluster acessível em todos os seus caminhos. **Candidato a uma seção
nova: "quando o `kubectl` não fala com o cluster".**

**3. A skill de triagem assume um transporte que pode não existir.** Achado da execução
real: **nenhuma das treze sessões tinha o servidor MCP de Kubernetes**. A skill prescreve
chamadas no formato `kubectl_get {"resourceType":...}`, que é a interface do MCP. Os três
executores de triagem caíram no `kubectl` do shell por conta própria e se restringiram aos
verbos de leitura. Um deles registrou:

> não há servidor MCP de Kubernetes instalado nesta sessão, então fiz a triagem com
> `kubectl` do shell, restrito aos verbos de leitura (`get`, `describe`, `logs`)

Duas leituras, e as duas contam:

- **defeito de portabilidade.** A skill não diz o que fazer quando o transporte não existe.
  O método sobreviveu pela competência do executor, não pelo texto.
- **a melhor evidência da tese do Ticket 02.** Sem o servidor em modo não destrutivo, nada
  impedia um `kubectl delete`. O que segurou foi a instrução escrita. "A garantia é da
  skill, não da ferramenta" deixou de ser argumento e passou a ser observação.

**4. A skill do Ticket 01 fazia a pergunta errada sobre endpoint**, e isso foi corrigido:
o Passo 5 perguntava "o Service tem endpoint?" e passou a perguntar "quantos estão prontos",
com a tabela de medição. Detalhe no ADR-004 deste ticket.

## O defeito que a regra escrita achou no meu próprio código

Esta é a parte mais útil do registro, e ela não estava na minha lista de perguntas.

Pedi a um sub-agente o painel que este ticket entrega. Ele localizou o `cluster-retrato`,
validou contra o cluster, e achou um defeito que eu não tinha visto:

```python
# cluster_retrato.py, _tabela_pods, versão anterior
causa = f"<span class=ruim>{E(p['causa'])}</span>" if p["causa"] else ""
```

A coluna "estado" tem a guarda `if p["quebrado"]`. A coluna "causa" **não tinha**. Então
qualquer pod com `lastState.terminated.reason` saía com a causa em vermelho, mesmo
saudável e rodando.

Medido no cluster de laboratório:

| | Antes | Depois |
|---|---|---|
| causa em vermelho em pod **saudável** | **16** | 0 |
| causa em vermelho em pod **quebrado** | 2 | 2 |
| terminação antiga marcada como histórico | 0 | 16 |

Um reinício de nó deixou `reason: Unknown` em quase tudo, e o painel pintou o `kube-system`
inteiro de vermelho. Num painel cujo propósito declarado é encurtar os primeiros minutos de
um chamado, isso é o oposto do que ele promete.

**E a regra violada é a que a própria skill de triagem escreve**, em `references/` e no
corpo:

> Container `ready=True` com `restartCount` alto é armadilha. [...] Se o `state` atual é
> `running`, o `lastState` é história e provavelmente não é o seu chamado.

Eu citei essa regra no TRD deste ticket, implementei a leitura de `lastState` por causa dela,
e **não implementei a guarda que ela exige**. O conhecimento estava escrito, versionado, e
foi ignorado pelo código que o cita.

Conserto aplicado na camada de normalização, onde a distinção pertence: `causa` só recebe
`lastState` quando o container **não** está rodando; quando está, vai para `historico` e a
tela mostra em cinza com a marca `(histórico)`.

### E o conserto introduziu um segundo defeito, que o teste pegou

A primeira versão do conserto usava:

```python
rodando = bool((c.get("state") or {}).get("running"))
```

`running: {}` sem `startedAt` é um container **rodando**, e `bool({})` é `False`. O teste
novo falhou na hora, apontando `<span class=ruim>Error</span>` onde devia haver histórico.

É a **mesma classe de erro** que o ADR-004 deste ticket documenta sobre `endpoints: null`:
confundir presença de chave com veracidade do valor. Eu escrevi um ADR inteiro sobre isso e
repeti o erro três camadas adiante. A versão correta testa presença:

```python
rodando = "running" in (c.get("state") or {})
```

Validação depois dos dois consertos: **43 testes de unidade** (dois novos, para a distinção
causa/histórico) e **66 verificações de ponta a ponta**, todas passando.

## A lacuna entre as duas skills, que continua de pé

A skill do Ticket 01 julga **arquivo**. A do Ticket 02 lê **estado do cluster**. O
`subir-workload.sh` deste ticket aplica manifests que satisfazem a regra 3.7 (tag fixa,
registry interno) e em seguida roda `kubectl set image` para uma imagem pública, porque
`registry.metacortex.io` não existe.

Resultado: **a regra está satisfeita no artefato e insatisfeita no cluster.** A skill do T01
aprovaria o arquivo; a do T02 veria uma imagem que não é a declarada. E de fato viu: duas
das triagens em sessão limpa reportaram, por conta própria, "a imagem aponta para registry
público em vez de `registry.metacortex.io`" como achado lateral.

Não é defeito de nenhuma das duas. É que "conformidade" significa coisas diferentes para
quem lê arquivo e para quem lê cluster, e **nenhuma das duas descriptions diz isso**. É o
tipo de lacuna que só aparece usando as duas no mesmo trabalho.

## O que este registro não prova

- **n = 1 por frase.** Treze acertos em treze tentativas únicas não é treze de treze
  repetido. Ativação é decisão de modelo.
- **a mensagem vem do agente pai**, não de uma pessoa digitando no chat. O mecanismo de
  descoberta e o insumo (`name` + `description`) são idênticos, verificados pela sonda; o
  enquadramento da mensagem não é.
- **duas skills no conjunto.** Com vinte instaladas, a sobreposição de vocabulário que a
  matriz de roteamento descreve pesa mais, e nada aqui mede isso.
- **as frases são minhas**, escritas por quem conhece as duas descriptions. Viés estrutural
  que nenhuma rodada corrige.
