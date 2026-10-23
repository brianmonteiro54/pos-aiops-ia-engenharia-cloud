# TRD — cluster-retrato

Documento técnico da primeira fatia definida no ADR-005. As decisões de fundo estão nos
ADR-001 a ADR-005; aqui está **como** elas viram código, e o que eu medi contra o cluster
antes de escrever.

## Arquitetura

```
navegador ──HTTP──▶ ThreadingHTTPServer (1 processo, 1 thread por requisição)
                         │
                         ├─ coletar()  ──▶ 6 × subprocess kubectl get -o json
                         │                   (lista branca de prefixos, 2 tetos de tempo)
                         ├─ normalizar() ─▶ estrutura interna única (função pura)
                         └─ renderizar() ─▶ HTML montado no servidor
```

`ThreadingHTTPServer` e não `HTTPServer`: uma requisição que estoura o teto de 20s num
cluster inacessível bloquearia a fila inteira — inclusive o pedido de favicon do navegador,
que o usuário veria como a página não carregando. Não há estado compartilhado, então a
troca custa uma palavra.

Um arquivo, `cluster_retrato.py`. Sem dependência externa: `http.server`, `subprocess`,
`json`, `html` e `datetime` são da biblioteca padrão (ADR-001). Sem estado entre
requisições (ADR-003).

## Etapa 1 — o portão do `kubectl`

Toda chamada ao cluster passa por **uma função só**, e ela é o lugar onde a garantia de
só-leitura do RE-01 fica visível:

```python
PREFIXOS_PERMITIDOS = frozenset({
    ("get",), ("version",), ("api-resources",), ("config", "view"),
})

def _kubectl(args, teto_externo=20, teto_requisicao=8):
    if not _permitido(args):
        raise VerboProibido(" ".join(args[:2]) if args else "<vazio>")
    ...
```

Quatro propriedades que vêm disso:

- a lista é **enumerada**, não uma lista negra. Comando novo é proibido por omissão, que é
  o lado certo para errar
- são **prefixos**, não verbos soltos, por causa de `config`: `kubectl config` tem
  subcomando que escreve no kubeconfig (`set-context`, `use-context`, `unset`). Liberar o
  verbo inteiro abriria mais do que o necessário, então só `config view` entra
- `api-resources` serve ao ADR-004 (escolha da fonte de endpoints) e `config view` serve
  a descobrir qual cluster o contexto corrente aponta — as duas rodam **uma vez**, na subida
- o CA-08 é verificado por **varredura do próprio fonte**, não por inspeção visual

### Por que a varredura é por AST e não por `grep`

O teste procura **literais de string iguais a verbo de escrita**, porque um verbo só chega
ao `kubectl` como string. `grep` não serve: acusaria `frozenset` por conter `set`, e
`.replace(` por conter `replace`. A varredura percorre a árvore sintática e compara
`ast.Constant` de tipo `str` com a lista de verbos de escrita. A segunda checagem confirma
que nenhuma função além de `_kubectl` chama `subprocess.*` ou `os.system`.

Na **primeira execução** a varredura falhou, acusando o literal `"run"` — dentro do próprio
auditor, no conjunto de nomes de método de `subprocess` que ele procura. Verdadeiro positivo
da regra aplicado ao vocabulário de quem a aplica. A saída foi isentar o auditor (que não
chama `kubectl` e segue coberto pela segunda checagem) em vez de encurtar a lista de verbos.
A isenção está declarada no código.

O teste tem um teste: `test_a_varredura_realmente_pega_algo` passa um arquivo com
`subprocess.run(["kubectl", "delete", ...])` e exige que a varredura acuse as duas coisas.
Um auditor que nunca acusa nada passa em silêncio para sempre.

### Os dois tetos de tempo, e por que um não basta

Isto é o achado que mais mudou a implementação. Medido contra um IP não roteável
(`10.255.255.1`), onde o pacote não volta nem com recusa:

| Como | Resultado medido |
|---|---|
| `kubectl get ns -o json` | **travou além de 70s**, morto por `timeout` externo |
| `kubectl get ns -o json --request-timeout=5s` | falhou em **25s**, não em 5 |

`--request-timeout` limita **cada requisição**, não o comando. O `kubectl` repete a
descoberta de grupos da API algumas vezes antes de desistir, e os tempos somam. Numa
aplicação web isso é a tela branca do CA-05: o handler fica pendurado e o navegador gira.

Então são dois tetos:

1. `--request-timeout=8s` no `kubectl`, para a requisição individual
2. `subprocess` com `timeout=20s` do meu lado, para o comando inteiro

O processo é criado com `start_new_session=True` e, no estouro, morto com
`os.killpg(os.getpgid(p.pid), SIGKILL)`. Matar só o PID deixaria filho órfão.
**Verificado:** depois de forçar os dois estouros, `pgrep -af kubectl` não devolveu nada.

## Etapa 2 — classificar a falha

Os três cenários do RF-04 precisam virar mensagem diferente na tela. Medi **nove** modos de
falha contra o cluster. O resultado:

| Modo | `exit` | primeira linha útil do `stderr` |
|---|---|---|
| porta fechada | 1 | `The connection to the server HOST:PORT was refused - did you specify the right host or port?` |
| IP não roteável | 1 | `Unable to connect to the server: context deadline exceeded` |
| CA errada | 1 | `Unable to connect to the server: tls: failed to verify certificate: x509: certificate signed by unknown authority` |
| token inválido | 1 | `error: You must be logged in to the server (Unauthorized)` |
| **token expirado** | 1 | **idem** |
| **certificado de cliente expirado** | 1 | **idem** |
| exec plugin ausente | 1 | `Unable to connect to the server: getting credentials: exec: executable X not found` |
| exec plugin falhou | 1 | `could not get token: ExpiredTokenException: ...` |
| permissão negada num tipo | 1 | `Error from server (Forbidden): events is forbidden: User "..." cannot list resource "events"` |

Duas consequências pesadas:

**O código de saída não carrega informação.** Todos os nove são `exit 1`. A classificação
sai de casar padrão no `stderr` de outra ferramenta, o que é frágil entre versões do
`kubectl`. Fica declarado: medido com **v1.33.13**. Quando o padrão não casar, a aplicação
cai num rótulo `falha não classificada` e **mostra o `stderr` cru** — feio, mas honesto, e
melhor que classificar errado.

**A aplicação não pode dizer "credencial expirada".** Token inválido, token expirado e
certificado de cliente expirado produzem **exatamente a mesma linha**. O apiserver responde
401 nos três e o `kubectl` imprime igual. Dizer "expirada" seria inventar. A tela diz:

> **O cluster rejeitou a credencial (401).** Pode estar expirada, inválida ou revogada — o
> `kubectl` não distingue os três casos. Verifique com `kubectl auth whoami`.

A exceção é o exec plugin: ali o **provedor** diz `ExpiredTokenException`, e aí a tela pode
nomear a expiração, porque a informação existe. É também o caso mais comum em cluster
gerenciado de verdade.

Isto cumpre o CA-06 no que ele pode ser cumprido: a falha de credencial é **distinguível de
cluster fora**, que é o que o critério pede. **Não** é distinguível de credencial inválida,
e isso é limitação do `kubectl`, não escolha minha. Está registrado em vez de escondido.

### Permissão negada é parcial, não fatal

O CA-07 é o único cenário em que a coleta **continua**. Cada um dos seis `LIST` é
independente: o que der `Forbidden` virá marcado como negado, e os outros cinco aparecem.
Medido com o `kubeconfig-restrito.yaml` do laboratório, que concede cinco tipos e nega
eventos:

```
namespaces      exit=0
pods            exit=0
services        exit=0
deployments     exit=0
endpointslices  exit=0
events          exit=1  Error from server (Forbidden): events is forbidden...
```

A seção de eventos da tela mostra o aviso de permissão com o nome do usuário extraído da
mensagem. Não é erro da aplicação; é informação sobre o contexto em uso.

### O ruído do `kubectl` não vai para a tela

Em falha de conexão o `kubectl` escreve 2 a 4 linhas de
`E1023 ... "Unhandled Error" err="couldn't get current server API group list..."` antes da
mensagem útil. São detalhe de implementação dele. A classificação descarta linha que começa
com `E<dígitos>` e `"Unhandled Error"` antes de casar padrão.

## Etapa 3 — as seis consultas

Mais duas na subida, uma vez cada: `api-resources --api-group=discovery.k8s.io` para a
escolha do ADR-004, e `config view --minify -o json` para descobrir contexto e servidor.
`version -o json` traz a versão do servidor para o cabeçalho — num parque com k3s, EKS e
kubeadm misturados, saber de qual se trata é informação de triagem, não enfeite.

| # | Comando | Serve a |
|---|---|---|
| 1 | `get namespaces -o json` | lista de namespaces |
| 2 | `get pods -A -o json` | pods, estado, reinícios, motivo |
| 3 | `get deployments -A -o json` | réplicas prontas/desejadas |
| 4 | `get services -A -o json` | lista de services |
| 5 | `get endpointslices -A -o json` **ou** `get endpoints -A -o json` | ADR-004 |
| 6 | `get events -n <ns> -o json` | eventos do namespace selecionado |

Sequenciais, por decisão do ADR-003. A consulta 6 só roda quando há namespace selecionado —
`get events -A` num cluster grande é a consulta mais cara da lista e quase sempre inútil.

## Etapa 4 — normalizar

Aqui vivem os fatos que o Ticket 02 mediu e que quebram código ingênuo.

### Endpoints: a pergunta é "quantos prontos"

Medido nos quatro estados do cluster:

| Namespace | Sintoma | `Endpoints` | `EndpointSlice` |
|---|---|---|---|
| `nyx-dev/nyx-api` | saudável | `subsets` com 1 endereço | 1 endpoint `ready: true` |
| `nyx-stg/nyx-api` | selector não casa | **chave `subsets` ausente** | chave presente, **valor `null`** |
| `nyx-prod/nyx-api` | `CrashLoopBackOff` | **`subsets` presente**, 2 em `notReadyAddresses` | 2 endpoints `ready: false` |
| `orion-stg/orion-web` | `ImagePullBackOff` | **`subsets` presente**, 3 em `notReadyAddresses` | 3 endpoints `ready: false` |

Daí sai a coluna `prontos/total` em vez de um sim/não, e sai o idioma obrigatório:

```python
# get(…, []) NÃO salva do null; "or []" sozinho não salva da chave ausente
eps = objeto.get("endpoints") or []
```

Ligação slice → service pelo label `kubernetes.io/service-name`, nunca por nome: o slice se
chama `<service>-<hash>`. A agregação soma N slices por service; neste cluster N é sempre 1
(medido: 14 pares, máximo 1), então **esse caminho não é exercitado com N > 1**.

### Pod: o motivo não está em `status.phase`

Medido no Ticket 02: pod com container em `CrashLoopBackOff` tem `status.phase: Running`.
Ler `phase` mostra tudo verde no chamado 1. A ordem de busca do motivo:

1. `status.containerStatuses[].state.waiting.reason` → `CrashLoopBackOff`, `ImagePullBackOff`
2. `status.containerStatuses[].lastState.terminated.reason` → `OOMKilled`, que é **a causa**
3. `status.conditions[]` com `status: "False"` → o `message` do `PodScheduled`
4. `status.phase` como último recurso

O CA-04 exige os dois primeiros juntos: a tela mostra `CrashLoopBackOff` com
`OOMKilled` ao lado, porque um é o sintoma e o outro é a causa.

`restartCount` é somado entre containers do pod.

### Deployment: ausente é zero

`status.readyReplicas` **não vem** quando é zero. `spec.replicas` omitido vale 1.

```python
prontas  = dep.get("status", {}).get("readyReplicas") or 0
desejadas = dep.get("spec", {}).get("replicas", 1)
```

### Pronto sem probe (RF-03)

`ready: true` só significa que a readinessProbe passou. Se não existe probe, significa que
o processo subiu — e o fake-shop é exatamente esse caso. A tela marca os dois de forma
diferente:

- probe declarada e passando → `pronto`
- **sem** `readinessProbe` em nenhum container → `pronto (sem probe)`, com nota explicando
  que o Kubernetes não está verificando nada

`initContainers` não contam: probe neles não diz nada sobre o container principal.

## Etapa 5 — a tela

HTML montado no servidor, CSS embutido, **zero JavaScript** (ADR-001). Toda interpolação
passa por `html.escape`: nome de namespace, mensagem de evento e `stderr` de `kubectl` são
dados que eu não controlo, e o `stderr` pode conter o que estiver num campo do cluster.

- cabeçalho com contexto corrente, servidor e **hora da coleta** (ADR-003)
- filtro por namespace e busca por nome via query string (`?ns=nyx-prod&q=api`), porque sem
  JavaScript o estado tem que caber na URL
- a fonte dos endpoints aparece no rodapé: `via EndpointSlice` ou `via Endpoints`

### O defeito que a primeira versão do cabeçalho tinha

A primeira versão lia o kubeconfig como texto e pegava o primeiro `server:` do arquivo. No
kubeconfig real da estação, que tem vários clusters, isso é o servidor **errado**: a tela
anunciou um endpoint de EKS enquanto lia o k3d local. Passou pelos critérios de aceite,
porque nenhum deles olhava o cabeçalho — apareceu ao ler a saída.

A correção foi trocar o parsing por `kubectl config view --minify -o json`, que responde a
pergunta certa e de graça resolve a mesclagem de vários arquivos em `KUBECONFIG`, que o
parsing ingênuo também errava. Foi o que trouxe `config view` para a lista branca.

Fica registrado porque é o tipo de defeito que o teste não pega: a informação estava
**presente, formatada e errada**.

## Rede e autenticação

**A aplicação não tem autenticação.** Quem alcança a porta lê o cluster inteiro com a
credencial de quem a subiu. Por isso:

- **bind em `127.0.0.1` por padrão.** Não em `0.0.0.0`
- expor na rede exige `--endereco` explícito, e a aplicação **imprime um aviso** quando o
  endereço não é loopback
- não há sessão, cookie nem cabeçalho de autorização para gerenciar

Isto é adequado para ferramenta local de plantão e **inadequado para qualquer uso
compartilhado**. Se alguém quiser rodar isso num bastion para o time, autenticação deixa de
ser opcional — e aí a decisão volta para a mesa.

## O que a validação não consegue provar

- **a credencial expirada não é distinguível da inválida.** Limite do `kubectl`, medido
- **a agregação de N > 1 `EndpointSlice` por service** não é exercitada: o cluster tem 1
- **o caminho alternativo de `Endpoints`** só roda se eu forçar, porque este cluster tem
  `discovery.k8s.io/v1`. Vou forçar por injeção no teste, o que valida a normalização mas
  **não** valida a detecção contra um cluster realmente antigo
- **a classificação depende do texto do `kubectl` v1.33.13.** Outra versão pode mudar as
  mensagens e cair no rótulo não classificado
- **cluster grande.** Tudo medido contra 2 nós e 14 services. `get pods -A` num cluster de
  milhares não foi medido, e o ADR-003 admite que a leitura é sequencial
