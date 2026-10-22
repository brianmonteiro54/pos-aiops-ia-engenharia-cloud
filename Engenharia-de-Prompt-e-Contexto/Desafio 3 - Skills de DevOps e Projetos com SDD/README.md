# Desafio 3 — Skills de DevOps e Projetos com SDD

Quatro tickets da **Metacortex**, provedora de infraestrutura gerenciada que opera VMs e
clusters Kubernetes em nome de clientes. Os dois primeiros empacotam conhecimento
operacional em **skills do Kiro**; os dois últimos são projetos completos, com arco de
Spec-Driven Development e código rodando.

O fio que une os quatro é o mesmo: a diferença entre *saber fazer uma vez* e *deixar o
conhecimento utilizável por quem vem depois*.

## Agente e modelos

| | |
|---|---|
| **Agente** | Kiro (IDE), sessão em modo Autopilot |
| **Modelo principal** | Claude Opus 5 |
| **Sub-agentes** | `introspect` (formato de skill, configuração do Kiro), `general-task-execution` (testes cegos de validação das skills), `context-gatherer` (leitura dos projetos) |

As duas regras do desafio foram respeitadas: **toda skill nasceu de um fluxo executado** —
primeiro resolvi a tarefa com o agente, depois empacotei o que funcionou — e **nenhum
projeto começou pelo código**.

## Os tickets

| Ticket | Entrega | Estado |
|---|---|---|
| **01** — [Padrão de manifests](ticket-01-padrao-de-manifests/) | skill que aplica as 19 regras do padrão da casa, nos modos escrita e conferência | **concluído** |
| **02** — [Triagem de cluster](ticket-02-triagem-no-cluster/) | skill de triagem sobre `mcp-server-kubernetes` em modo não destrutivo, matriz de roteamento e medição com/sem skill | pendente |
| **03** — [Inventário e drift de VM](ticket-03-inventario-de-vm/) | ferramenta CLI que audita VM por SSH contra um baseline, com arco SDD completo | pendente |
| **04** — [Dashboard do cluster](ticket-04-dashboard-do-cluster/) | aplicação local de leitura do cluster pelo kubeconfig, com arco SDD e 5 ADRs | pendente |

## Onde as skills ficam, e por quê

As skills são entrega **funcional**, não documental. Elas vivem em `.kiro/skills/` **na raiz
do repositório**:

```
.kiro/skills/padrao-de-manifests-metacortex/     # Ticket 01
```

Não é escolha de organização, é requisito do Kiro: ele descobre skills apenas em
`<raiz-do-projeto>/.kiro/skills/` e em `~/.kiro/skills/`, sem varrer subpastas. Uma skill
dentro da pasta do Desafio 3 não carregaria — viraria markdown decorativo. Quem clonar este
repositório e abri-lo no Kiro tem as skills ativas sem configurar nada.

A pasta de cada ticket guarda a **curadoria** — o raciocínio sobre o que entrou, o que
ficou fora e a medição que sustenta cada corte — mais os fluxos manuais que originaram a
skill e as evidências das execuções.

## Ticket 01 em três linhas

Skill que julga 19 regras de manifesto: **script 15, Trivy 3, leitura do projeto 1**. O
número do Trivy saiu de experimento, não de documentação, e o achado que mais pesou é que a
regra mais perigosa do padrão — senha em texto puro — é **invisível** para as duas
invocações da ferramenta.

Validada em duas frentes. Três testes cegos — sub-agentes que só podiam usar a skill, contra
manifestos novos — acharam **15 defeitos** nela. E o confronto linha a linha com o anexo do
padrão achou **três regras que eu havia inventado** e que não existem no texto da casa.

## Ambiente

- cluster **k3d** `metacortex` (k3s v1.31.5), `kubectl` v1.33.13
- `trivy` 0.52.2, `python3` 3.10 com PyYAML
- Ubuntu 22.04 em WSL2
- projetos auditados: [`KubeDev/kube-news`](https://github.com/KubeDev/kube-news) (cliente
  nyx) e [`KubeDev/fake-shop`](https://github.com/KubeDev/fake-shop) (cliente orion)

## Nota sobre a localização deste desafio

O enunciado sugere `desafio-03/` na raiz do repositório. Esta entrega está em
`Engenharia-de-Prompt-e-Contexto/Desafio 3 - Skills de DevOps e Projetos com SDD/` para
seguir o padrão dos Desafios 1 e 2 do mesmo módulo. A estrutura interna — uma pasta por
ticket, cada uma com `README.md` próprio apontando os itens do `Entregue.` — é a que o
enunciado pede.
