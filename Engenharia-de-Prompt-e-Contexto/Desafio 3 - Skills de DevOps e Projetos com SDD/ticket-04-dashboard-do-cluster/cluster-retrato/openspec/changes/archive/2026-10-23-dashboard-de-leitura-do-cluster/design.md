# Design

## Context

As cinco decisões de fundo já estão fechadas em ADR, fora deste diretório, em
`../../docs/adr/`: Python 3 com `http.server` e HTML no servidor (ADR-001), `kubectl` como
subprocesso atrás de lista branca de verbos (ADR-002), consulta sob demanda (ADR-003),
`EndpointSlice` primário com `Endpoints` como alternativa (ADR-004) e o recorte desta fatia
(ADR-005). Este documento não as repete; descreve a estrutura que elas produzem e as
decisões menores que sobraram.

Três restrições do ambiente moldam o resto:

- quem mantém é um time de **infraestrutura**. Não há cadeia de build de front-end, e o
  Python com biblioteca padrão é o que já existe na estação de todo mundo
- a aplicação roda com **a credencial de quem a sobe**, lendo o cluster de um cliente
- o `kubectl` é a única interface com a API, e ele comunica falha por **texto em `stderr`**,
  não por código de saída: os nove modos de falha medidos devolvem `exit 1`

## Goals / Non-Goals

**Goals:**

- encurtar os primeiros minutos de um chamado, mostrando onde está o problema
- nunca mentir: o que é inferido aparece como inferido, o que não se sabe aparece como não
  sabido
- tornar a restrição de só-leitura **verificável por teste**, não declarada em comentário
- degradar de forma legível nas três falhas de ambiente, inclusive parcialmente
- zero dependência, zero estado, zero carga quando ninguém está olhando

**Non-Goals:**

- substituir o `kubectl` ou o `k9s`
- observabilidade: métrica, série temporal, alerta, histórico
- operar o cluster: `apply`, `delete`, `scale`, `exec`, edição de YAML
- multicluster e troca de contexto por dentro
- logs nesta fatia (primeiro candidato da próxima, e reabre o ADR-002)
- tela com atualização automática
- autenticação: a aplicação é local e **não autenticada** por decisão consciente

## Decisions

### Um arquivo, três camadas, sem estado

`cluster_retrato.py` com fronteiras internas claras:

```
coletar()     → fala com o cluster, devolve dado cru ou falha classificada
normalizar()  → dado cru vira estrutura interna única, sem HTML
renderizar()  → estrutura interna vira HTML, sem falar com o cluster
```

A separação não é estética: `normalizar()` é a camada que concentra todos os fatos
estranhos da API, e é a única que precisa de teste de unidade. Ela é função pura — recebe
dicionário, devolve dicionário. Os testes dos cenários de endpoint e de motivo de pod batem
nela com JSON fixo, sem cluster.

### O portão de verbos é um ponto, e é testado por varredura

Uma função `_kubectl(args, ...)` é o **único** lugar do arquivo que chama `subprocess`. Ela
compara `args[0]` com `VERBOS_PERMITIDOS = {"get", "version", "api-resources"}` e levanta
antes de criar processo.

Decisão menor: `api-resources` entra na lista porque o ADR-004 precisa dele **uma vez**, na
subida, para escolher a fonte dos endpoints. Incluí-lo custa um verbo a mais na lista branca
e economiza uma segunda porta de entrada para o `subprocess`.

A verificação do CA-08 é uma varredura do próprio fonte por verbo de escrita. Ela é mais
forte que inspeção e mais fraca que RBAC — ver em Risks.

### Dois tetos de tempo, e o grupo de processos

Medido contra `10.255.255.1` (endereço que não roteia, pacote cai no vazio):

| Como | Tempo medido |
|---|---|
| `kubectl get ns -o json` | travou **além de 70s** |
| `... --request-timeout=5s` | falhou em **25s**, não em 5 |

`--request-timeout` limita cada requisição, não o comando: o `kubectl` repete a descoberta
de grupos da API e os tempos somam. Então `--request-timeout=8s` **e** `subprocess` com
`timeout=20s`. No estouro, `start_new_session=True` na criação e
`os.killpg(os.getpgid(p.pid), SIGKILL)` no encerramento — matar o PID sozinho deixa filho
órfão. Verificado: depois de forçar os dois estouros, `pgrep -af kubectl` ficou vazio.

### A classificação de falha é tabela de padrões, e admite não saber

`classificar(stderr)` descarta primeiro o ruído de diagnóstico do `kubectl` — linhas
`E<dígitos> ...` e `"Unhandled Error"` — e só então casa padrão, nesta ordem:

| Rótulo | Padrão |
|---|---|
| `credencial_expirada` | `ExpiredToken`, ou o plugin externo falhando |
| `plugin_ausente` | `executable ... not found` |
| `credencial_rejeitada` | `You must be logged in to the server` |
| `tls_desconhecido` | `certificate signed by unknown authority` |
| `cluster_inacessivel` | `connection to the server ... refused`, `context deadline exceeded` |
| `permissao_negada` | `Error from server (Forbidden)` |
| `configuracao_invalida` | `Error in configuration` |
| `nao_classificada` | nada casou |

A ordem importa: `ExpiredToken` vem **antes** de `credencial_rejeitada` porque o caso do
plugin externo é o único que diz o motivo, e perder isso seria perder a única informação boa
que existe.

`nao_classificada` é a decisão deliberada: quando nada casa, a tela mostra o `stderr` cru e
diz que não classificou. É a mesma escolha do `nao_verificado` do Ticket 03 — admitir
ignorância em vez de produzir um rótulo que pode estar errado.

### A tela não pode afirmar "expirada"

Medi nove modos de falha. Token inválido, token expirado e certificado de cliente expirado
assinado pela CA real do cluster produzem **a mesma linha**:
`error: You must be logged in to the server (Unauthorized)`. O apiserver responde 401 nos
três, e o `kubectl` imprime igual.

Então `credencial_rejeitada` diz "expirada, inválida ou revogada — o `kubectl` não
distingue". O CA-06 pede que seja distinguível de cluster fora, e é. Não pede o que não dá.

### Permissão negada é por consulta, não global

As seis consultas são independentes e cada uma carrega seu próprio resultado ou sua própria
falha. Só `cluster_inacessivel` e as falhas de credencial são globais — se a primeira
consulta falhar por um desses, as outras cinco são puladas, porque repetir seis vezes uma
falha de conexão custa seis estouros de teto.

`permissao_negada`, ao contrário, é **local à consulta**. O tipo negado aparece negado e os
outros aparecem preenchidos.

### Estado na URL, porque não há JavaScript

`?ns=nyx-prod&q=api`. Sem JavaScript, não há outro lugar para o filtro morar, e o efeito
colateral é bom: a URL de uma triagem é compartilhável. Toda interpolação passa por
`html.escape` — nome de namespace, `message` de evento e `stderr` do `kubectl` são dados
que eu não controlo.

## Risks / Trade-offs

**A varredura do fonte não é a garantia forte.** O CA-08 prova que não existe verbo de
escrita escrito no arquivo. Não prova que a credencial em uso não poderia escrever. A
garantia forte é RBAC somente-leitura, e ela está **fora desta fatia** — exatamente a mesma
quarta camada que o Ticket 02 identificou e não implementou. Em produção seria a primeira.
Registrado como dívida consciente, não como esquecimento.

**Casar padrão em `stderr` de outra ferramenta é frágil.** Medido com `kubectl` v1.33.13.
Outra versão pode reescrever as mensagens, e o efeito é cair em `nao_classificada` — degrada
para feio, não para errado. É o motivo de esse rótulo existir.

**O caminho de `Endpoints` quase nunca roda.** Este cluster tem `discovery.k8s.io/v1`, então
a alternativa só é exercitada por injeção no teste. Isso valida a normalização e **não**
valida a detecção contra um cluster realmente antigo.

**A soma de N slices por service não é exercitada com N maior que 1.** Medido: 14 pares
`(namespace, service)` no cluster, máximo de 1 slice cada. O código soma, o teste não prova.

**Sem autenticação.** Mitigado por bind em loopback e aviso na exposição, não resolvido.
Rodar isso num bastion compartilhado exigiria autenticação de verdade, e aí a decisão volta
para a mesa.

**Leitura sequencial.** Seis `LIST` em série, por decisão do ADR-003. Imperceptível em
cluster de 2 nós; não medido em cluster grande.

**`get pods -A` não pagina.** Num cluster com milhares de pods a resposta é um JSON único e
grande, carregado inteiro na memória. Fora do recorte, e conhecido.
