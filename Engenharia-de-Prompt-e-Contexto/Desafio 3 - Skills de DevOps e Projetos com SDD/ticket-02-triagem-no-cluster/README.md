# Ticket 02 — Skill de triagem de cluster

Escrever o método único de triagem da SRE numa skill que usa o `mcp-server-kubernetes` em
modo não destrutivo, executá-la em três chamados reais, e medir como as duas skills do
desafio se comportam juntas.

## Onde está cada item do `Entregue.`

| Item pedido | Onde está |
|---|---|
| **A skill completa** | `../../../.kiro/skills/triagem-de-cluster-metacortex/` — `SKILL.md`, `references/por-que-a-ordem-importa.md`, `references/leitura-da-api.md`. Configuração do MCP em `../../../.kiro/settings/mcp.json` |
| **A origem da skill: de qual fluxo nasceu, como foi produzida e com qual ferramenta** | `curadoria.md` seção 0, e `fluxos/fluxo-01-triagem-manual.md` |
| **A saída real da triagem dos três chamados, com a causa de cada um** | `execucao-da-skill.md`, e as evidências brutas da triagem manual em `evidencias/` |
| **O resultado da matriz de roteamento: o que disparou, o que errou, o que mudei** | `matriz-de-roteamento.md` |
| **A comparação com e sem skill (saída, custo e tempo)** | `com-e-sem-skill.md` |
| **Curadoria — o que o método fixou e o que ficou a critério do agente** | `curadoria.md` seções 1 e 2 |
| **Curadoria — como garanti que a skill não escreve no cluster** | `curadoria.md` seção 3 |

Extra, não pedido: `ferramentas/mcp.py`, o cliente MCP mínimo usado para executar a skill
pelo transporte real em vez de `kubectl` disfarçado.

## Os três chamados e as causas

Aplicados com `kubectl apply -f` no k3d `metacortex` e deixados nesse estado.

| Chamado | Sintoma para o cliente | Causa, e o campo exato |
|---|---|---|
| **1** `nyx-prod` | "a API reinicia sozinha" | `resources.limits.memory: 24Mi` para um processo Node. `lastState.terminated.reason: OOMKilled`, `exitCode: 137` |
| **2** `orion-stg` | "a loja parou depois de uma publicação" | a tag `v1.14.2` não existe. Evento do kubelet: `not found`. O registry tem 18 tags, nenhuma com ponto |
| **3** `nyx-stg` | "503 de fora, a aplicação está de pé" | `Service.spec.selector: app: nyx-api` contra `pod.metadata.labels: app: nyxapi`. Um hífen |

Nos três, o Postgres estava de pé e saudável — componente são ao lado do quebrado é a norma.

**A skill corrigiu os dois relatos do cliente que estavam errados:** não existe `LimitRange`
em `nyx-prod` (o 24Mi está no template do Deployment, não numa política de namespace), e não
existe ReplicaSet anterior em `orion-stg` (então não é "a nova não entrou", é "a loja está
fora", 0 de 3).

## O achado que organizou o método

**Nenhuma fonte resolve os três chamados.**

| Fonte | Chamado 1 | Chamado 2 | Chamado 3 |
|---|---|---|---|
| `get pod` STATUS | `CrashLoopBackOff` | `ImagePullBackOff` | **`Running`, 1/1** |
| status do container | **`OOMKilled`** | `lastState` vazio | `ready=True` |
| logs | **vazios** | **impossíveis** | sem erro |
| eventos | só `BackOff` | **`not found`** | nada |
| endpoints | em branco | em branco | **`subsets` ausente** |

"Sempre comece pelos logs" falha em 2 de 3. "Sempre pelos eventos" também. Por isso o método
deriva a camada do **sintoma relatado** e desce dali, em vez de fixar uma ordem de comandos.

## Modo não destrutivo não é somente-leitura

Medido pelo protocolo, não lido no README: **23 ferramentas no modo default, 17 no modo não
destrutivo.** Ele remove 6 e **deixa 7 que escrevem no cluster** — `kubectl_apply`, `create`,
`patch`, `scale`, `rollout` e os dois Helm.

Um agente de triagem poderia consertar o OOM do chamado 1 com `kubectl_patch`, e o servidor
deixaria. A garantia de só-leitura tem três camadas, detalhadas em `curadoria.md` seção 3, e
fica registrada uma quarta que **não** implementei: RBAC somente-leitura no kubeconfig, que
em produção seria a primeira e não a quarta.

## Roteamento entre as duas skills

Três rodadas, com sub-agentes lendo **apenas o frontmatter** — porque é o único insumo do
roteamento real. **Confiança alta: 6 → 8 → 9 de 10.**

Nove defeitos nas descriptions, e quatro deles eu introduzi consertando os outros. A frase
"esse manifesto não sobe no cluster" ficou em `AMBAS` de propósito: o critério existe e está
escrito, mas depende de saber qual foi o erro, e a frase não diz. As duas descriptions
passaram a instruir "peça a mensagem antes de rotear". Detalhe em `matriz-de-roteamento.md`.

## A skill vale o custo?

**Custou mais e entregou mais.** Sem a skill foram **4 e 8** chamadas MCP; com a skill, **8 e
12**. As duas execuções acertaram as duas causas.

O que a skill entregou a mais: a fronteira da própria ignorância declarada por chamado, a
correção sistemática do relato do cliente, e o conserto como recomendação. O relatório sem
skill afirma "proxy/ingress devolve 503" tendo confirmado nas próprias chamadas que não
existe Ingress em namespace nenhum.

Metade do custo extra era defeito meu — os comandos estavam escritos contra o `kubectl` e não
contra o MCP — e já está corrigido. A outra metade é rigor, e é escolha. Veredito por
cenário em `com-e-sem-skill.md`.

## Onde eu errei

A execução da skill achou **nove atritos**, todos corrigidos. Três mudariam o resultado de
uma triagem real:

- os comandos do método estavam escritos contra a saída do `kubectl`, não do MCP
- a skill afirmava que toda imagem vem de `registry.metacortex.io`, e as do cluster vêm de
  `docker.io` — mandaria o plantonista ao registry errado
- a `leitura-da-api.md` dizia que a chave `endpoints` do `EndpointSlice` não aparece quando
  vazia. **Aparece, com valor `null`.** Só `Endpoints.subsets` some de verdade. O erro veio do
  meu script de coleta, que usou `or "AUSENTE"` — e `[]`, `None` e chave ausente são todos
  falsy

O último é o mais incômodo: é uma regra de leitura errada dentro do arquivo que existe para
ensinar regras de leitura.

E um erro de desenho: a reference que justifica o método **é a solução trabalhada dos três
chamados**, e a skill mandava lê-la antes de triar. O executor apontou que isso impede
triagem cega e contamina a medição da Parte C. Hoje as references estão explicitamente fora
do caminho de execução.

## Reproduzir

```bash
# os tres ambientes
kubectl apply -f chamados/chamado-01-nyx-prod.yaml
kubectl apply -f chamados/chamado-02-orion-stg.yaml
kubectl apply -f chamados/chamado-03-nyx-stg.yaml

# o cliente MCP, em modo nao destrutivo
cd ferramentas
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22.23.3

./mcp.py tools                     # 17 ferramentas; 23 com --com-destrutivas
./mcp.py call kubectl_get '{"resourceType":"all","namespace":"nyx-prod"}'

# a prova de que o irreversivel e bloqueado
./mcp.py call kubectl_delete '{"resourceType":"pod","name":"x","namespace":"nyx-prod"}'
#   -> RECUSADA: Tool 'kubectl_delete' is not allowed under the current server configuration
```

Requer `node >= 18` (usei 22.23.3), `kubectl` e um cluster alcançável pelo kubeconfig.
