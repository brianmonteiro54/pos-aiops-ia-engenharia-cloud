# Desafio 3 — Skills de DevOps e Projetos com SDD

Quatro tickets da **Metacortex**, uma consultoria que opera plataforma para clientes
diferentes. Dois deles empacotam conhecimento operacional em **skills do Kiro**; dois
constroem projetos completos com arco de **Spec-Driven Development**.

O fio que une os quatro é o mesmo: a diferença entre *saber fazer uma vez* e *deixar o
conhecimento utilizável por quem vem depois*.

## Os tickets

| Ticket | Entrega | Estado |
|---|---|---|
| **01** — [Padrão de Manifests](ticket-01-padrao-de-manifests/) | skill para conferir e gerar manifests de Kubernetes contra as 19 regras da casa | **concluído** |
| **02** — [Triagem no Cluster](ticket-02-triagem-no-cluster/) | skill de triagem sobre MCP de Kubernetes, em modo não destrutivo | pendente |
| **03** — [Inventário de VM](ticket-03-inventario-de-vm/) | projeto com arco SDD completo: ferramenta de inventário por SSH | pendente |
| **04** — [Dashboard do Cluster](ticket-04-dashboard-do-cluster/) | projeto com arco SDD: dashboard sobre os dois tickets anteriores | pendente |

## Onde as skills ficam

As skills são entrega **funcional**, não documental. Elas vivem em
`.kiro/skills/` na raiz do repositório, porque é de onde o Kiro as carrega:

```
.kiro/skills/padrao-de-manifests-metacortex/     # Ticket 01
```

A pasta de cada ticket aqui guarda a **curadoria** — o raciocínio sobre o que entrou na
skill, o que ficou fora, e a medição que sustenta cada corte — mais os fluxos manuais que
originaram a skill e as evidências das execuções.

## Ticket 01 em uma linha

Skill que julga 19 regras de manifesto: **script 15, Trivy 3, leitura 1**. O número do
Trivy saiu de experimento, não de documentação — e o achado que mais pesou é que a regra
mais perigosa do padrão, senha em texto puro, é **invisível** para as duas invocações da
ferramenta.

Validada com três testes cegos que acharam treze defeitos na própria skill, incluindo uma
afirmação factual minha que estava errada sobre o comportamento do apiserver.

## Ambiente

- cluster **k3d** `metacortex` (k3s v1.31.5), namespaces `orion-prod` e `nyx-dev`
- `trivy` 0.52.2, `kubectl` v1.33.13, `python3` 3.10 com PyYAML
- projetos auditados: [`KubeDev/kube-news`](https://github.com/KubeDev/kube-news) e
  [`KubeDev/fake-shop`](https://github.com/KubeDev/fake-shop)
