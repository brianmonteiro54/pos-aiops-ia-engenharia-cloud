# Desafio 3: Skills de DevOps e Projetos com SDD

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

As duas regras do desafio foram respeitadas: **toda skill nasceu de um fluxo executado** (primeiro resolvi a tarefa com o agente, depois empacotei o que funcionou) e **nenhum
projeto começou pelo código**.

## Os tickets

| Ticket | Entrega | Estado |
|---|---|---|
| [**01** Padrão de manifests](ticket-01-padrao-de-manifests/) | skill que aplica as 19 regras do padrão da casa, nos modos escrita e conferência | **concluído** |
| [**02** Triagem de cluster](ticket-02-triagem-no-cluster/) | skill de triagem sobre `mcp-server-kubernetes` em modo não destrutivo, matriz de roteamento e medição com/sem skill | **concluído** |
| [**03** Inventário e drift de VM](ticket-03-inventario-de-vm/) | ferramenta CLI que audita VM por SSH contra um baseline, com arco SDD completo | **concluído** |
| [**04** Dashboard do cluster](ticket-04-dashboard-do-cluster/) | aplicação local de leitura do cluster pelo kubeconfig, com arco SDD e 5 ADRs | **concluído** |

## Onde as skills ficam, e por quê

As skills são entrega **funcional**, não documental. Elas vivem em `.kiro/skills/` **na raiz
do repositório**:

```
.kiro/skills/padrao-de-manifests-metacortex/     # Ticket 01
.kiro/skills/triagem-de-cluster-metacortex/      # Ticket 02
.kiro/settings/mcp.json                          # MCP em modo nao destrutivo
```

Não é escolha de organização, é requisito do Kiro: ele descobre skills apenas em
`<raiz-do-projeto>/.kiro/skills/` e em `~/.kiro/skills/`, sem varrer subpastas. Uma skill
dentro da pasta do Desafio 3 não carregaria: viraria markdown decorativo. Quem clonar este
repositório e abri-lo no Kiro tem as skills ativas sem configurar nada.

Se o repositório **não** for a raiz do workspace, instale no caminho global, que o Kiro
mescla com o do projeto:

```bash
for s in padrao-de-manifests-metacortex triagem-de-cluster-metacortex; do
  ln -sfn "$PWD/.kiro/skills/$s" ~/.kiro/skills/"$s"
done
```

Symlink, para continuar havendo uma fonte da verdade. A descoberta acontece no **início da
sessão**: depois de instalar, abra uma sessão nova, senão a skill fica ativável à mão e não
dispara sozinha. Isso está medido em
`ticket-04-dashboard-do-cluster/docs/03-registro-das-skills.md`.

A pasta de cada ticket guarda a **curadoria** (o raciocínio sobre o que entrou, o que
ficou fora e a medição que sustenta cada corte) mais os fluxos manuais que originaram a
skill e as evidências das execuções.

## Ticket 01 em três linhas

Skill que julga 19 regras de manifesto: **script 15, Trivy 3, leitura do projeto 1**. O
número do Trivy saiu de experimento, não de documentação, e o achado que mais pesou é que a
regra mais perigosa do padrão (senha em texto puro) é **invisível** para as duas
invocações da ferramenta.

Validada em duas frentes. Três testes cegos (sub-agentes que só podiam usar a skill, contra
manifestos novos) acharam **15 defeitos** nela. E o confronto linha a linha com o anexo do
padrão achou **três regras que eu havia inventado** e que não existem no texto da casa.

## Ticket 02 em três linhas

Método único de triagem, derivado do **sintoma relatado** em vez de uma ordem fixa de
comandos, porque nenhuma fonte resolve os três chamados: os logs do primeiro estão vazios,
o evento do segundo tem a causa inteira, e no terceiro tudo está verde e a resposta está na
ausência de um campo.

**Modo não destrutivo não é somente-leitura**: medi 23 ferramentas no default e 17 no modo
restrito, e as 17 incluem sete que escrevem. A garantia de só-leitura é da skill, em três
camadas, com uma quarta registrada como lacuna.

E a skill **custou mais do que improvisar** (8 e 12 chamadas contra 4 e 8) acertando as
mesmas causas. O que ela entregou a mais foi a fronteira da própria ignorância e a correção
de dois relatos de cliente que estavam errados.

## Ticket 03 em três linhas

`roster-inventario`: audita VM por SSH contra um baseline, com arco SDD completo e ciclo
OpenSpec arquivado. O transporte é o `ssh` do sistema como subprocesso (não paramiko)
para que `~/.ssh/config` com `ProxyJump` continue valendo e para não ter um segundo cliente
SSH a auditar.

A decisão menos confortável do projeto é o terceiro veredito: **`nao_verificado` com
motivo**, em vez de abortar, mentir "conforme" ou inventar "desvio". Código de saída `0`,
porque dado que não pôde ser coletado não é falha de conformidade.

**Dois baselines**, porque o laboratório não consegue provar duas das regras: `baseline.yaml`
para o parque e `baseline-laboratorio.yaml` sem kernel e swap. O CA-01 é validado nas duas
pontas: zero desvios contra o do laboratório, **exatamente 2** contra o do parque.

## Ticket 04 em três linhas

`cluster-retrato`: lê seis tipos de recurso do cluster corrente e monta o retrato numa tela,
sem dependência nenhuma. A garantia de só-leitura é **verificável**: lista branca de
comandos num ponto único e um teste que varre o próprio fonte por AST, que, na primeira
execução, **pegou um literal dentro do próprio auditor**.

Três coisas que eu havia escrito e a medição desmentiu: `--request-timeout` **não** limita o
comando (70s virando 25s contra IP não roteável); **"credencial expirada" não é afirmável**,
porque token inválido, JWT expirado e certificado expirado dão a mesma linha; e **contar
endpoints responde a pergunta errada**, porque pod em `CrashLoopBackOff` tem endpoint: ele
só não serve.

O registro das skills tem a resposta que o ticket pediu e que eu não poderia fabricar:
**nenhuma skill foi carregada neste ticket**, e isso é verificável dos dois lados: 14
`SKILL.md` no disco, zero num caminho que o runtime varre.

## Ambiente

- cluster **k3d** `metacortex` (k3s v1.31.5), `kubectl` v1.33.13
- `trivy` 0.52.2, `python3` 3.10 com PyYAML
- Ubuntu 22.04 em WSL2
- projetos auditados: [`KubeDev/kube-news`](https://github.com/KubeDev/kube-news) (cliente
  nyx) e [`KubeDev/fake-shop`](https://github.com/KubeDev/fake-shop) (cliente orion)
