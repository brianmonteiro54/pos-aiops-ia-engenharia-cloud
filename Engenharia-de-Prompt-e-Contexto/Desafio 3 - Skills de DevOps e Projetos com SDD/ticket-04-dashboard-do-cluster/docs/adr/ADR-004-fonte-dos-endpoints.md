# ADR-004: De onde vem a informação de endpoint

**Status:** aceito
**Contexto:** o RF-02 pede mostrar, para cada Service, **se ele tem endpoint**. A informação
existe em dois tipos: `Endpoints` (`v1`, em descontinuação) e `EndpointSlice`
(`discovery.k8s.io/v1`, o substituto). O ticket nomeia a escolha. O chamado 3 do Ticket 02
era exatamente este sintoma: pod `Running`, Service sem endpoint.

## Decisão

**`EndpointSlice` como fonte primária, `Endpoints` como alternativa quando o grupo
`discovery.k8s.io` não existe no cluster.**

**E a pergunta na tela mudou:** não é "tem endpoint?", é **"quantos endpoints prontos?"**.
A medição abaixo mostra por quê.

## O que eu medi, e o que isso desmentiu

Rodei os dois tipos contra os quatro estados que o cluster já tem. O PRD afirmava que
"ausência de endpoint é o que explica 'subiu mas não responde'". **Está incompleto, e a
medição mostra o tamanho do erro.**

| Namespace | Sintoma real | `Endpoints` | `EndpointSlice` |
|---|---|---|---|
| `nyx-dev/nyx-api` | saudável | `subsets` com 1 `addresses` | 1 endpoint, `ready: true` |
| `nyx-stg/nyx-api` | pod pronto, **selector não casa** | **chave `subsets` ausente** | chave presente, **valor `null`** |
| `nyx-prod/nyx-api` | `CrashLoopBackOff` | **`subsets` PRESENTE**, com 2 em `notReadyAddresses` | 2 endpoints, `ready: false` |
| `orion-stg/orion-web` | `ImagePullBackOff` | **`subsets` PRESENTE**, com 3 em `notReadyAddresses` | 3 endpoints, `ready: false` |

Três consequências, e nenhuma é cosmética:

**1. `len(endpoints)` responde a pergunta errada.** Nos três namespaces quebrados o Service
não entrega tráfego. Mas contar endpoints só acusa **um** deles: nos outros dois a lista
está cheia, de endereços que não servem. Quem escreve `if not subsets: "sem endpoint"`
acerta o chamado 3 e **passa batido** nos chamados 1 e 2. A pergunta certa é
`conditions.ready`.

**2. "Campo ausente não é campo vazio" é mais estreito do que parece.** O `KeyError` em
`subsets` acontece **só** no caso do selector que não casa. No caso do CrashLoop a chave
está lá. Então o mesmo tipo tem **dois modos de estar vazio**, e só um deles quebra o
código. É o tipo de bug que passa em teste e aparece no cliente.

**3. Os dois tipos quebram de formas diferentes.** `Endpoints` **omite a chave**;
`EndpointSlice` **entrega a chave com `null`**. `KeyError` num, `TypeError` no outro.
`len(obj.get("endpoints") or [])` é a única forma que sobrevive aos dois: `get` com
`default` não salva do `null`, e `or []` sozinho não salva da ausência.

## Alternativas consideradas

### A: só `Endpoints`

**O que se ganha:** funciona em qualquer cluster desde sempre, é 1:1 com o Service (mesmo
nome, mesmo namespace), e é o que aparece em toda documentação antiga e em todo runbook que
o time já tem escrito. `kubectl get endpoints` ainda é o comando que a maioria digita.

**O que se perde:**

- **está em descontinuação.** Escrever hoje contra o tipo que o Kubernetes está
  substituindo é dívida com data marcada.
- **agrupa pronto e não-pronto em duas listas sem nuance.** `addresses` e
  `notReadyAddresses` não distinguem "não está pronto" de "está terminando". Num rollout
  isso é a diferença entre um alarme e um não-evento.
- **tem limite de escala conhecido.** Um Service com milhares de pods vira um objeto único
  gigante. Não dói neste cluster de 2 nós, mas é o motivo pelo qual o tipo está sendo
  trocado, e o parque da Metacortex tem cluster de cliente.

### B: só `EndpointSlice`

**O que se ganha:** é o caminho para onde o Kubernetes foi, traz `conditions` com três
campos (`ready`, `serving`, `terminating`) e `addressType`, que é o que permite responder
"quantos prontos" sem inferência.

**O que se perde, e foi o que barrou o "só":**

- **o grupo `discovery.k8s.io/v1` não existe em cluster antigo.** Num cluster onde ele não
  está disponível, a aplicação não degrada: ela não mostra endpoint nenhum. O parque da
  Metacortex não é homogêneo, e a aplicação roda com o kubeconfig de quem está de plantão,
  pode apontar para qualquer cluster de cliente.
- **a relação com o Service não é por nome.** O slice se chama `<service>-<hash>`
  (`nyx-api-wszq8`), e a ligação vive no **label** `kubernetes.io/service-name`. Casar por
  nome é bug esperando a hora.
- **um Service pode ter vários slices.** Neste cluster todos têm exatamente 1 (medido: 14
  pares `(namespace, service)`, máximo de 1 slice cada), o que é justamente o motivo de
  **não** confiar na medição: um cluster grande, ou dual-stack, tem mais de um, e aí a
  agregação por label passa a ser obrigatória. Escrevi a agregação desde já, sabendo que
  neste cluster ela nunca é exercitada com N > 1. **Está registrado como caminho não
  coberto pelo teste.**

### C: primário com alternativa (escolhida)

Tenta `EndpointSlice`. Se o tipo não existir no cluster, cai para `Endpoints` e **diz na
tela qual fonte usou**.

**O que se ganha:**

- a informação boa (`conditions.ready`) onde ela existe, que é a esmagadora maioria dos
  clusters em operação
- a aplicação continua útil no cluster antigo, em vez de mostrar uma coluna vazia sem
  explicação
- **a fonte aparece na tela.** Quem lê "0 de 3 prontos (via EndpointSlice)" sabe que o dado
  é por endpoint. Quem lê "(via Endpoints)" sabe que `terminating` não está sendo
  distinguido

**O que se perde:**

- **dois caminhos de leitura para manter**, e um deles: o de `Endpoints`: quase nunca
  roda. Código que não roda é código que apodrece. Mitigação: a normalização converte os
  dois formatos para a **mesma estrutura interna** no ponto de entrada, então o resto da
  aplicação tem um só caminho. A duplicação fica confinada a uma função
- a detecção custa uma chamada a mais (`kubectl api-resources`) na subida. Feita **uma vez**,
  não por carregamento de página
- no modo alternativo `terminating` é invisível, porque `Endpoints` não tem o campo. Aceito
  e declarado na tela

## Consequências

- a estrutura interna normalizada é `{servico: {prontos: N, total: M, fonte: str}}`. Em
  `Endpoints`, `prontos` vem de `addresses` e `total` de `addresses + notReadyAddresses`
- **a coluna da tela é `prontos/total`, não um sim/não.** `0/3` num Service com 3 pods
  quebrados conta uma história diferente de `0/0` num Service cujo selector não casa, e
  essa diferença é exatamente o que separa o chamado 1 do chamado 3
- `len(x.get("endpoints") or [])` é o idioma obrigatório, nos dois tipos. Um `get` com
  `default=[]` passa no teste e quebra no `null`
- a agregação por `kubernetes.io/service-name` vale para N slices, mas **só foi exercitada
  com N = 1**. Limitação conhecida, não corrigida: construir o caso dual-stack num k3d para
  testar isso é desproporcional ao recorte
- `default/kubernetes` não tem selector e **tem** os dois objetos, mantidos pelo apiserver.
  Não é exceção a tratar: a leitura por label funciona igual
