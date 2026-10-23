# Checkpoint 07: A biblioteca vira código

Sétimo checkpoint, e o primeiro que não produz prompt. Os nove prompts dos checkpoints 01 a 06 estavam espalhados entre arquivos de documentação; o Nick Fury não aceita playbook assim. Aqui a coleção vira ativo versionado, com estrutura, metadados e índices: algo que sobrevive à saída de qualquer pessoa do time.

A estrutura não foi inventada: o checkpoint manda partir do template [`prompt-registry`](https://github.com/fabricioveronez/prompt-registry) e organizar os prompts nas convenções dele.

---

## O repositório

**Link:** https://github.com/brianmonteiro54/prompt-registry

O playbook é um **repositório próprio**, baseado no template, e vive em [`prompt-registry/`](./prompt-registry) dentro da pasta deste desafio. Essa decisão tem consequência técnica e está explicada na nota de mapeamento adiante.

Estado do repositório do playbook no commit de entrega deste checkpoint (`24e6ad4`). Os Checkpoints 08 a 10 acrescentam `promptfooconfig.yaml` por prompt, `scripts/`, `avaliacao/`, `.github/workflows/` e `package.json`, e sobem `triagem-de-pods` para `1.0.1`: então esta árvore é o retrato daqui, não o estado atual do repositório:

```
prompt-registry/
├── CLAUDE.md                 # convenções: atualizado (ver nota)
├── README.md                 # índice raiz: atualizado com os 9 prompts e a seção "Sobre este fork"
├── .claude/commands/catalogar.md
├── criacao-conteudo/README.md
├── desenvolvimento/README.md
├── financas/README.md
├── produtividade/README.md
└── devops/
    ├── README.md             # índice da categoria: atualizado
    ├── triagem-de-pods/              prompt.md + README.md
    ├── nota-de-triagem/              prompt.md + README.md
    ├── causa-raiz/                   prompt.md + README.md
    ├── estrategia-backpressure/      prompt.md + README.md
    ├── diagnostico-de-acoplamento/   prompt.md + README.md
    ├── plano-de-migracao-faseado/    prompt.md + README.md
    ├── detalhamento-de-fase/         prompt.md + README.md
    ├── networkpolicy-sentinel/       prompt.md + README.md
    └── revisao-de-networkpolicy/     prompt.md + README.md
```

Os nove prompts caíram todos em `devops/`, o que era esperado: o escopo declarado da categoria lista orquestração, observabilidade, SRE, análise de incidentes e segurança operacional, que é exatamente o domínio do playbook da Aegis.

---

## Um prompt no formato completo

O checkpoint pede um item completo como exemplo dos demais. Escolhi `triagem-de-pods`, o primeiro da biblioteca, porque tem um único parâmetro e deixa o padrão visível sem ruído.

### `devops/triagem-de-pods/prompt.md`

O arquivo tem o frontmatter, uma linha em branco, e o texto do prompt preservado integralmente. Nenhuma explicação sobre o prompt entra aqui: isso é regra do template e existe porque este arquivo é o que se copia e cola.

```yaml
---
nome: Triagem de Pods
descricao: Recebe um snapshot de kubectl e devolve a triagem dos pods problemáticos com causa provável, evidência e próxima ação do plantão
versao: 1.0.0
tags: [kubernetes, sre, plantao, triagem]
inputs:
  - nome: snapshot
    descricao: Saída bruta e colada de comandos kubectl (get pods, describe, logs) coletada por quem tem acesso ao cluster.
---
```

Seguido do corpo do prompt, que termina em:

```text
# ENTRADA

Analise o snapshot abaixo:

{{snapshot}}
```

O texto completo está em [`devops/triagem-de-pods/prompt.md`](./prompt-registry/devops/triagem-de-pods/prompt.md) e é byte a byte o mesmo que foi executado no Checkpoint 01: extraí os nove prompts programaticamente dos arquivos dos checkpoints justamente para não haver divergência entre o que foi testado e o que entrou na biblioteca.

### `devops/triagem-de-pods/README.md`

Mesmo frontmatter, seguido da camada humana:

````markdown
---
nome: Triagem de Pods
descricao: Recebe um snapshot de kubectl e devolve a triagem dos pods problemáticos com causa provável, evidência e próxima ação do plantão
versao: 1.0.0
tags: [kubernetes, sre, plantao, triagem]
inputs:
  - nome: snapshot
    descricao: Saída bruta e colada de comandos kubectl (get pods, describe, logs) coletada por quem tem acesso ao cluster.
---

# Triagem de Pods

## Objetivo

Dá ao plantonista uma triagem rápida e confiável da saúde dos pods de um namespace, a partir de um snapshot já coletado. Em vez de repetir a coluna STATUS, o prompt obriga o cruzamento de três camadas: listagem, `describe` e logs da aplicação, para chegar à causa provável de cada pod problemático, com a evidência que sustenta o diagnóstico e a próxima ação concreta.

## Quando usar

- Alerta de pod em falha chega no plantão e ninguém do time conhece o serviço em profundidade.
- É preciso decidir entre reiniciar, escalar ou investigar, com evidência em vez de intuição.
- Triagem precisa ser reproduzível entre plantonistas diferentes, com o mesmo critério.

## Exemplo de uso

Com `{{snapshot}}` contendo um pod em `CrashLoopBackOff` com `Last State: OOMKilled` e log de `out of memory`, a saída é:

```
VEREDITO: 1 POD(S) PROBLEMATICO(S)
POD: sentinel-api-7d9c8b6f4-h4m2t
SEVERIDADE: ALTA
SINTOMA: CrashLoopBackOff
CAUSA_RAIZ: OOMKilled - container encerrou por falta de memoria ao carregar cache
EVIDENCIA: Last State: Terminated Reason: OOMKilled e log [FATAL] out of memory
ACAO_RECOMENDADA: [AVISO DE IMPACTO] Aumentar limits de memoria do deployment apos avaliar uso.
CONFIANCA: ALTA - dados completos
```

Quando o snapshot não tem pod problemático, a saída é o veredito `NENHUM POD PROBLEMATICO` mais, no máximo, duas linhas de `OBSERVACOES`. Nenhum rótulo de diagnóstico aparece nesse caso, o que permite testar o caso saudável por ausência.

## Limitações conhecidas

- Depende de `metrics-server` no cluster se o snapshot incluir `kubectl top`.
- O critério de "pod problemático" cobre estado de infraestrutura, não saúde de aplicação: pod `Running` com deadlock ou devolvendo erro 500 é classificado como saudável.
- Snapshot muito extenso pode diluir a atenção do modelo. Truncar logs e omitir pods `Completed` antes de colar.
- Pendência conhecida (v1.0.1): a regra da tag `[AVISO DE IMPACTO]` enumera exemplos de ação destrutiva, e reverter imagem de deployment não está entre eles, na execução registrada essa ação saiu sem o aviso, apesar de disparar rollout.
````

Os outros oito seguem exatamente esta forma.

---

## Como o playbook foi mapeado nas convenções do template

**Os `{{placeholders}}` e o `inputs` são a mesma coisa, e agora isso é verificável.** Foi por isso que decidi, desde o Checkpoint 01, nomear os parâmetros no formato `{{nome}}` em vez de deixar para depois: a migração virou mecânica. Escrevi um verificador que extrai os placeholders do corpo de cada `prompt.md` por regex e compara com a lista `inputs` do frontmatter. Os nove passam. Sem isso, um placeholder renomeado no texto e esquecido no frontmatter é um erro que nenhuma leitura pega.

**Duas convenções do template que eu tinha escrito errado nos checkpoints, e corrigi aqui.** O campo `nome` é título humano capitalizado, não o slug da pasta: eu vinha escrevendo `nome: triagem-de-pods`, e o correto é `nome: Triagem de Pods`. E o frontmatter precisa dos delimitadores `---`, que faltavam nos blocos que registrei nos checkpoints. As duas correções valem para os nove itens.

**Nome de pasta pelo resultado, não pela técnica.** A regra do template vale mesmo quando a técnica é o assunto: o item do Checkpoint 05 que existe por causa de encadeamento de prompts se chama `plano-de-migracao-faseado` e não `prompt-chaining`. Uma exceção ficou registrada: `networkpolicy-sentinel` carrega o nome do caso de estreia, embora o corpo do prompt seja genérico e funcione para qualquer namespace. Mantive porque o Checkpoint 08 fixa esse caminho no arquivo de teste; `endurecimento-de-networkpolicy` descreveria melhor o que o item faz, e a tensão está anotada no `README.md` do prompt.

**Os dois padrões estruturais do playbook não cabiam nas convenções originais, então virei as convenções do lado delas.** O template pressupõe prompts independentes, e o playbook tem dois arranjos que quebram essa premissa: a cadeia de três elos do Checkpoint 05, onde a saída integral de um é a entrada do seguinte, e o par gerador/revisor do Checkpoint 06. Uma pasta isolada não revela nenhum dos dois. Acrescentei ao `CLAUDE.md` a seção **"Prompts que dependem de outros prompts"**, declarando os dois padrões e a obrigação de cada `README.md` dizer quem antecede e quem sucede. Sem isso, alguém que abrisse `detalhamento-de-fase` não teria como saber que ele espera a saída de outro item.

**Alterei o `CLAUDE.md` do template, e foi seguindo o próprio `CLAUDE.md`.** A seção de manutenção dele manda revisar as convenções sempre que o repositório mudar, e duas afirmações ficaram falsas com este desafio. A primeira: "não há código executável, build, testes ou pipeline, é um repositório documental". A partir do Checkpoint 08 cada prompt de saída estruturada carrega um `promptfooconfig.yaml`, e no Checkpoint 10 entra um pipeline. A segunda: a estrutura obrigatória listava dois arquivos por pasta, e passa a admitir um terceiro. Acrescentei também a seção **"Avaliação automatizada"** com as convenções de teste, incluindo uma que só aprendi na prática, assert de string sobre rótulo acentuado depende de normalização Unicode, então formato livre usa rótulo sem acento e formato imposto por padrão externo fixa a forma normalizada.

**As "Limitações conhecidas" não são genéricas.** O template sugere preencher com `_A preencher_` quando não houver base concreta. Aqui havia: cada item lista defeitos observados em execução real, incluindo as pendências v1.0.1 que decidi não aplicar para não invalidar as execuções registradas na documentação dos checkpoints. Isso põe no repositório a informação que normalmente fica só na cabeça de quem escreveu, que o `estrategia-backpressure` marcou ATENDE em células que dependiam de lacuna aberta, que o `detalhamento-de-fase` tratou reversão como gratuita, que o revisor de NetworkPolicy produziu um falso positivo quando rodado na mesma sessão do gerador.

**O playbook é repositório próprio e o repo da pós o ignora.** Esta é a decisão com consequência técnica. O playbook precisa ser repositório independente por duas razões: a entrega do checkpoint é o link dele, e o Checkpoint 10 vai rodar GitHub Actions sobre ele. Mas os arquivos ficam dentro da pasta deste desafio, por organização.

Um repositório git dentro de outro é um problema silencioso: o repo de fora cria um ponteiro (`gitlink`) em vez de versionar os arquivos, e a pasta aparece cinza e vazia no GitHub. Quem só olha a página web conclui que a entrega está incompleta. A solução foi adicionar o caminho ao `.gitignore` do repo da pós, com comentário explicando o motivo. Assim o playbook mantém `.git` próprio, remoto próprio e pipeline próprio, e o repo da pós não cria o ponteiro quebrado.

O remoto foi trocado do template original para o repositório de destino e o push está feito. Confirmado que o commit enviado contém os 18 arquivos dos prompts, mais o `CLAUDE.md`, o `README.md` raiz e o `devops/README.md` atualizados, ou seja, a página do GitHub mostra a biblioteca completa, e não a pasta cinza que o problema do repositório aninhado causaria.

---

## Verificação

Rodei um validador sobre os nove itens do catálogo:

| Verificação | Resultado |
|---|---|
| Frontmatter com delimitadores `---` em `prompt.md` e `README.md` | 9 de 9 |
| Frontmatter byte a byte idêntico nos dois arquivos | 9 de 9 |
| Campos obrigatórios (`nome`, `descricao`, `versao`, `tags`, `inputs`) | 9 de 9 |
| `nome` é título humano e não o slug da pasta | 9 de 9 |
| `tags` entre 2 e 5 termos | 9 de 9 |
| Placeholders `{{...}}` do corpo idênticos à lista `inputs` | 9 de 9 |
| Seções obrigatórias do `README.md` do prompt | 9 de 9 |
| `versao: 1.0.0` em todos, conforme a regra de versão inicial | 9 de 9 |
| Texto do prompt idêntico ao executado nos checkpoints | extraído programaticamente dos arquivos dos checkpoints |
| Índices atualizados | `devops/README.md` e `README.md` raiz, com os 9 itens |

O que **não** está feito e é o próximo checkpoint: nenhum prompt tem `promptfooconfig.yaml` ainda. Três deles (`nota-de-triagem`, `triagem-de-pods` e `networkpolicy-sentinel`) recebem suíte determinística no Checkpoint 08, e `causa-raiz` recebe o gate por juiz no Checkpoint 09.

Um ajuste já mapeado para o Checkpoint 08, que vem do Checkpoint 06: a proibição de chaves no prompt da NetworkPolicy precisa encolher para o padrão específico da regra vazia. O assert correspondente procura a **string exata** `- {}`, e não a presença de chaves. A instrução ampla que eu escrevi no meta-prompt levou o modelo a evitar chaves em todo lugar, o que tirou de circulação a forma documentada de seletor vazio e acabou produzindo um manifesto que depende de coerção de nulo. Com o assert preciso, a proibição no prompt encolhe e o seletor volta à forma idiomática.

---

## Commits

A primeira publicação saiu em um commit único chamado `first commit`, o que violava a convenção declarada no próprio template: commit semântico, mensagem de uma linha, escopo na categoria. E tinha um efeito colateral pior que a mensagem: aquele commit era raiz, ou seja, **o histórico dos quatro commits originais do autor do template havia sido descartado**. O fork perdia a atribuição de onde a estrutura veio.

O histórico foi reconstruído para corrigir as duas coisas de uma vez. Recuperei os commits originais adicionando o repositório do template como remoto `upstream`, reposicionei o trabalho do playbook em cima deles e dividi a entrega em quatro commits semânticos:

```
24e6ad4  docs: atualiza CLAUDE.md com convencoes de cadeia, par gerador/revisor e avaliacao
68b86de  docs: registra no README raiz a origem do fork e o indice dos prompts
3dc6337  docs(devops): atualiza indice da categoria com os prompts do playbook
cf43a64  feat(devops): adiciona os 9 prompts do playbook de IA operacional da Aegis
e32d679  docs: referencia a pós-graduação AIOps como origem do catálogo      <- template
5f7623d  chore: adiciona .gitignore para settings.local.json                  <- template
a1cbbbf  feat: adiciona comando /catalogar e padroniza frontmatter dos prompts <- template
9169efa  chore: inicializa catálogo com estrutura e categorias iniciais        <- template
```

A divisão não é decorativa: ela separa o que é prompt novo do que é atualização de índice e do que é mudança de convenção. Quem for revisar a alteração do `CLAUDE.md` (que é a mais delicada, porque muda regra do repositório) consegue olhar só `24e6ad4` em vez de caçar dentro de um commit de 1.209 linhas.

**Verificação da reescrita.** Reescrever histórico com force push tem um risco concreto: alterar conteúdo sem perceber. Comparei o hash da árvore antes e depois (`a14d54a361968ac31bbfe51bc40f70231e577b51` nos dois casos) e o diff entre o commit antigo e a nova ponta é vazio. Nenhum byte de arquivo mudou; só a forma como o histórico conta a mudança. O push usou `--force-with-lease`, que aborta se o remoto tiver avançado por outra via, e um branch de resguardo apontava para o commit antigo até a verificação fechar.

O remoto `upstream` ficou configurado, o que é útil num fork: permite acompanhar mudanças que o autor do template fizer depois. De aqui para frente os commits seguem a convenção, `test(devops): ...` para as suítes de avaliação do Checkpoint 08 e `ci: ...` para o pipeline do Checkpoint 10.
