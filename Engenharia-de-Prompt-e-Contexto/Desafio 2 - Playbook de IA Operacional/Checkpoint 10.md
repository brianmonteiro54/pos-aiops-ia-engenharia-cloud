# Checkpoint 10 — O playbook em produção contínua

Os checkpoints 08 e 09 cobriram quatro dos nove prompts e deixaram a suíte rodando na mão. Este fecha os dois lados: **cobertura nos nove** e **pipeline que roda sozinho a cada alteração**, barrando regressão.

O trabalho de desenho ficou todo numa pergunta: **o que faz o build falhar?** A resposta óbvia — "qualquer assert vermelho" — foi medida e descartada, porque com os nove prompts cobertos a suíte completa nasce com 8 de 31 casos falhando, e sete dessas oito são defeito legítimo — a oitava é oscilação do modelo, tratada adiante. Gate vermelho desde o primeiro dia não detecta regressão, só ensina o time a ignorar a suíte.

**Repositório:** https://github.com/brianmonteiro54/prompt-registry
**Workflow:** [`.github/workflows/avaliacao.yml`](./prompt-registry/.github/workflows/avaliacao.yml)

---

## Cobertura: 9 de 9

| Prompt | Casos × providers | Tipo de verificação |
|---|:---:|---|
| `nota-de-triagem` | 6 | determinística (CP08) |
| `triagem-de-pods` | 6 | determinística (CP08) |
| `networkpolicy-sentinel` | 2 | determinística + semântica sobre o YAML (CP08) |
| `causa-raiz` | 1 | juiz com rubrica, calibrado (CP09) |
| `revisao-de-networkpolicy` | 6 | determinística, 3 casos |
| `estrategia-backpressure` | 2 | determinística, inclui a aritmética |
| `diagnostico-de-acoplamento` | 2 | determinística, inclui regra de ordenação |
| `plano-de-migracao-faseado` | 2 | determinística, testa a cadeia |
| `detalhamento-de-fase` | 4 | determinística, 2 casos |

**31 casos no total.** O enunciado pede "determinístico onde der, com juiz onde precisar de julgamento", e a divisão caiu 30 para 1.

Isso surpreendeu. Os prompts do CP04 e CP05 são de saída aberta e eu esperava precisar de juiz neles. Olhando o que de fato produzem, não precisam: todos têm **títulos de seção literais e vocabulário fechado**, e a maior parte do que pode dar errado é verificável sem opinião — seção omitida, conta errada, classificação fora do vocabulário permitido, ordenação que contraria a regra declarada.

O que ficou para o juiz foi só `causa-raiz`, onde o objeto de medida é a **qualidade do raciocínio** e não a forma. E isso é consistente com o preço: a suíte de `causa-raiz` custa US$ 0,081 por execução, o dobro da segunda mais cara, e doze vezes mais por caso.

### Os asserts que valem mais que estrutura

Três exemplos de verificação determinística sobre saída aberta, que são o achado metodológico deste checkpoint.

**`estrategia-backpressure` — a aritmética.** O prompt exige três contas explícitas. Déficit = 320k − 180k = **140k msgs/s**; volume acumulado = 140k × 25min × 60s = **210M mensagens**. Os dois números são verificáveis por string, e errar o primeiro invalida toda a análise seguinte:

```javascript
      # 320k - 180k = 140k msgs/s. E a primeira conta da etapa 1, e todo o resto da
      # analise depende dela. Numero errado aqui invalida a recomendacao inteira.
      - type: javascript
        value: |
          const bloco = (output.split('RELOGIOS E RESTRICOES')[0] || '');
          const achou = /140[\s.,]?0?0?0?\s*(k|mil)?/i.test(bloco.replace(/\./g, '.'));
          return achou ? true : { pass: false, score: 0, reason: '...' };
```

**O que eu deliberadamente NÃO testei aqui** importa tanto quanto o que testei. O piso físico de drenagem dá ~19,4 minutos, e o SLA do Sentinel é 60 segundos. A tentação é assertar "declare o SLA violado". Seria premiar o erro: a etapa 2 do próprio prompt alerta que latência de um evento novo e tempo de drenagem de volume acumulado são **relógios diferentes**, e compará-los produz conclusão errada com aparência de rigor. Verificar a conta, sim; verificar a conclusão que depende da distinção de relógios, não — essa parte precisa de julgamento.

**`diagnostico-de-acoplamento` — risco silencioso vem primeiro.** A etapa 4 manda ordenar os riscos com os silenciosos à frente, porque dado errado que ninguém percebe é pior que alerta falso que todos veem. No cenário do Forge, o risco silencioso é a divergência contábil no billing da Pepper. Dá para verificar lendo a tabela:

```javascript
          const classe = dados.map((l) => (/silencioso/i.test(l) ? 'S' : /vis[ií]vel/i.test(l) ? 'V' : '?'));
          const primeiroVisivel = classe.indexOf('V');
          const ultimoSilencioso = classe.lastIndexOf('S');
          if (primeiroVisivel >= 0 && ultimoSilencioso > primeiroVisivel) {
            return { pass: false, score: 0, reason: `risco silencioso na posicao ${ultimoSilencioso + 1} aparece depois de risco visivel na posicao ${primeiroVisivel + 1}` };
          }
```

Isso não é formato, é decisão de engenharia — e o `gpt-4o-mini` reprova de forma reprodutível.

**`revisao-de-networkpolicy` — o revisor tem gabarito.** Três casos, e o segundo e o terceiro são o que falta na maioria das suítes de revisor:

1. política allow-all do CP06 → tem que **BARRAR**, nomear o tráfego indevido e numerar os apontamentos;
2. política gerada pelo par gerador/revisor → o veredito tem que ser **coerente com os apontamentos**;
3. política escrita à mão contra as cinco regras do padrão → **não pode BARRAR**.

O caso 3 existe porque revisor que sempre barra é tão inútil quanto revisor que sempre aprova, e o custo dele é o time parar de ler o parecer. E o caso 1 tem resposta única: `ingress: [- {}]` e `egress: [- {}]` liberam qualquer origem e qualquer destino, então não há julgamento envolvido.

### O caso 2 me provou errado, e o achado é sobre a suíte do CP08

Eu escrevi o caso 2 exigindo que o revisor **não** barrasse a política gerada por `networkpolicy-sentinel`, no raciocínio de que uma política aprovada pelos 15 asserts semânticos do CP08 não teria bloqueador a encontrar.

Os dois providers barraram, e os dois tinham razão:

- o `podSelector` cobre **todos** os pods do namespace e não só `app=sentinel`, de modo que as liberações de ingress do Sentinel valem para qualquer vizinho de namespace;
- as regras de ingress não restringem porta, liberando todas as portas dos pods alcançados para as origens declaradas.

**O achado não é sobre o revisor, é sobre a suíte do gerador.** Ela nunca verificou se o seletor alveja os pods certos. O par gerador/revisor do Checkpoint 06 existe justamente para isso, e aqui ele funcionou: o revisor pegou o que a suíte do gerador não olhava. Virou pendência da suíte de `networkpolicy-sentinel`.

Reescrevi o caso 2 para verificar o que de fato se pode exigir sem conhecer o veredito certo de antemão — **coerência interna**, que o veredito não contradiga os apontamentos — e movi o teste de "não pode barrar" para um fixture escrito à mão, com as premissas inevitáveis declaradas no cabeçalho. Esse passou nos dois providers.

---

## A consolidação que o CP08 deixou pendente

O Checkpoint 08 registrou três cópias byte a byte de `prompt.js` como duplicação deliberada, com a nota de revisitar quando a cobertura completasse. Completou, e as três viraram nove. O custo trocou de lado: nove arquivos idênticos divergem na primeira correção que alguém esquecer de propagar.

A solução preserva a propriedade que justificava a duplicação. O promptfoo resolve `file://prompt.js` relativo ao diretório do config, então `__dirname` aponta para a pasta do prompt e acha o `prompt.md` certo sem configuração. Cada prompt ficou com um `prompt.js` de uma linha que delega, passando o próprio `__dirname`:

```javascript
const { criarCarregador } = require('../../scripts/carregar-prompt.js');

module.exports = criarCarregador(__dirname);
```

O módulo não precisa saber o caminho por configuração e o YAML não carrega informação que o sistema de arquivos já tem. Rodei as três suítes do CP08 antes e depois: mesmo resultado, 6/6, 5/6 e 1/2.

---

## As verificações que custam zero

Antes de qualquer chamada paga, três scripts verificam o que dá para verificar de graça. Eles existem por dois motivos: pegam a classe de erro mais comum de manutenção de catálogo, e **rodam em PR de fork**, onde os segredos não estão disponíveis.

| Script | O que pega |
|---|---|
| `verificar-estrutura.js` | frontmatter divergente entre `prompt.md` e `README.md`, campo obrigatório ausente, `versao` fora de semver, **placeholder usado e não declarado em `inputs`** (e o inverso), corpo do prompt referenciando o README, prompt sem suíte, chave de API versionada |
| `verificar-carregadores.js` | carregador que não carrega, **frontmatter vazando para o modelo**, placeholder não substituído |
| `verificar-configs.js` | YAML inválido, campo estrutural ausente, **referência `file://` que não existe**, caso sem assert, assert JavaScript com sintaxe inválida |

Os três itens em negrito são erros que o CP08 descobriu pagando execução. O frontmatter vazando só apareceu ao ler a saída de uma eval paga; aqui custa zero.

```
=== ESTRUTURA DO CATALOGO
    prompts encontrados: 9
    com suite de teste:  9
=== VEREDITO
    OK: estrutura, frontmatter, parametros e cobertura consistentes.

=== CONFIGS DE AVALIACAO
    configs: 10   asserts javascript inline: 60
=== VEREDITO
    OK: configs validos, referencias resolvem e asserts compilam.
```

---

## Estratégia de gate

Cinco decisões, cada uma com ao menos duas alternativas descartadas e o motivo.

### Decisão 1 — o que conta como regressão

**Escolhido: falha quando um caso que passava passa a falhar**, comparado com [`avaliacao/baseline.json`](./prompt-registry/avaliacao/baseline.json), versionado no repositório.

O problema é medido. Com os nove prompts cobertos:

| Provider | Suítes que reprova |
|---|---|
| `gemini-3.5-flash` | 2 de 9 |
| `gpt-4o-mini` | 6 de 9 |

E as reprovações são legítimas: regra de severidade não aplicada, cerca de bloco de código numa saída que promete YAML colável, risco silencioso ordenado depois do visível, fase inexistente detalhada como se existisse, classificação fabricada para as 14 etapas do Spark. Nenhuma é bug de assert — todas foram investigadas uma por uma.

Um gate que exige verde total fica vermelho no dia um. E esse diagnóstico não é teórico: é o **mesmo erro que o CP08 cometeu** nos limites de latência e custo de `networkpolicy-sentinel`, e que o **CP09 repetiu** no limite de custo do gate de `causa-raiz`. Duas vezes eu fixei limite por intuição e a medição me corrigiu.

O enunciado define o que barrar: "quando um prompt regride (ou seja, quando uma mudança piora um prompt em relação à versão anterior)". **Regressão é comparação com o estado anterior, não com a perfeição.** O baseline torna isso executável.

Propriedade que fecha o desenho: **aceitar uma falha conhecida exige commit no baseline.** Ela deixa de ser silenciosa e passa a ser revisável — alguém olha o diff e pergunta por que.

> **Alternativa rejeitada 1 — gate só no provider de referência, segundo provider informativo.** Barato e sem falso positivo, porque o fornecedor recomendado reprova pouco. Perde o que o segundo fornecedor existe para medir: divergência entre eles é sinal de prompt frágil, e descartar o sinal no gate é manter o custo do segundo provider sem o benefício. Perde também a detecção de regressão no modelo barato, que é o que a maioria do time usa no dia a dia.
>
> **Alternativa rejeitada 2 — exigir verde total e corrigir os prompts antes de ligar o gate.** É o ideal e a conta não fecha: parte das reprovações é limitação do modelo barato e não defeito corrigível. A regra de severidade de `triagem-de-pods` foi reescrita três vezes no CP08 e o `gpt-4o-mini` continua errando. Ou o prompt vira sobreajuste ao modelo fraco, ou o gate fica desligado esperando. As duas saídas são piores que registrar a falha e barrar a piora.

### Decisão 2 — reprovação por flutuação

**Escolhido: repete apenas as suítes com regressão, uma vez; reprova de verdade só se a repetição confirmar.**

Medido no CP09: o **juiz é determinístico** (3 repetições contra entradas fixas, notas idênticas nos 4 critérios) e o **gerador não é** (totais 6, 7, 6, 6 contra corte 6). A flutuação que ameaça o build não vem do julgamento, vem da geração.

Ganha: elimina a reprovação de amostra única pagando repetição só quando algo falha. Perde sensibilidade: um defeito que aparece em metade das gerações só é barrado quando as duas passadas falham, ou seja, é detectado em 1 de 4 vezes (0,5 × 0,5) e escapa nas outras 3. Com passada única seria detectado em 1 de 2. Esse é o preço.

> **Alternativa rejeitada 1 — três gerações e mediana, sempre.** Elimina melhor a flutuação e triplica o custo de toda execução, inclusive das que iam passar de primeira.
>
> **Alternativa rejeitada 2 — baixar o corte do juiz de 6 para 5 no CI.** Resolve a flutuação e abre mão da sensibilidade de forma permanente: 5 de 8 é análise com dois critérios parciais, e deixar isso entrar derrota o propósito do gate.

### Decisão 3 — escopo: suíte inteira ou só o que mudou

**Escolhido: só o que mudou, com escalonamento para a suíte inteira quando o arquivo é compartilhado.**

| Escopo | Casos | Custo | Tempo |
|---|:---:|---:|---:|
| um prompt alterado | 1 a 6 | US$ 0,011 a 0,081 | 9s a 52s |
| suíte inteira | 31 | **US$ 0,269** | **3,4 min** |

Em repositório de prompt a maioria dos PRs toca um item, então o escopo seletivo paga uma fração. Mas prompt não é tão isolado quanto parece, e há três acoplamentos reais aqui:

- `scripts/carregar-prompt.js` é lido pelos nove — e foi consolidado **neste checkpoint**, num commit que toca um arquivo e afeta nove suítes;
- `devops/causa-raiz/criterios/` é lido pelo gate **e** pelo harness de calibração;
- os elos da cadeia do CP05 recebem a saída registrada do elo anterior, em `casos/`.

Por isso qualquer mexida em `scripts/`, `package.json`, `avaliacao/`, `casos/`, `criterios/` ou `.github/` dispara tudo. Funcionando na prática:

```
=== ESCOPO: arquivo compartilhado alterado (.github/workflows/avaliacao.yml): escalonado para a suite inteira
    9 de 9 suite(s): causa-raiz, detalhamento-de-fase, diagnostico-de-acoplamento, ...
```

> **Alternativa rejeitada 1 — sempre a suíte inteira.** Mais segura e previsível, custa cerca de 20x mais por PR. O efeito colateral conhecido é o time desligar o gate quando a fatura chega.
>
> **Alternativa rejeitada 2 — só o que mudou, sem escalonamento.** Mais barata ainda e genuinamente insegura aqui: a consolidação do carregador passaria sem teste nenhum.

### Decisão 4 — quando rodar

**Escolhido: pull request e push em `main`, com filtro de caminho.** Mais `workflow_dispatch` para forçar a suíte inteira à mão.

> **Alternativa rejeitada 1 — rodar em todo push de toda branch.** Dá o retorno mais cedo e multiplica o custo pelo número de commits de trabalho em progresso, que em repositório de prompt é alto porque se itera no texto. O retorno antecipado não compensa, porque as verificações que pegam erro de estrutura rodam de graça.
>
> **Alternativa rejeitada 2 — rodar só em `main`, depois do merge.** O mais barato e transforma o gate em alarme: a regressão já entrou quando o build falha.

### Decisão 5 — onde ficam as chaves dos provedores

**Escolhido: secrets de repositório**, `OPENAI_API_KEY` e `GOOGLE_API_KEY`, com o pipeline dividido em dois jobs. PR vindo de fork não recebe segredos, por desenho do GitHub — então o job de estrutura roda sempre e o job pago é pulado. Mesma coisa para PR do Dependabot, pelo motivo descrito adiante.

Ganha: simplicidade, e qualquer mantenedor com acesso de escrita consegue rodar a avaliação. Perde: toda pessoa com permissão de escrita pode disparar gasto, e não há aprovação no caminho.

> **Alternativa rejeitada 1 — `pull_request_target`.** Rodaria com os segredos do repositório base e resolveria o caso do fork, que é o furo da opção escolhida. Rejeitada por segurança: ela executa o workflow no contexto do base **com acesso aos segredos**, e este repositório executa código do PR (`prompt.js`, `asserts.js`, `aplicar-corte.js`, `calibrar.js`). Um PR malicioso exfiltraria as duas chaves de API. O furo do fork é menos grave que o risco de exfiltração.
>
> **Alternativa rejeitada 2 — environment protegido com revisor obrigatório.** Os segredos ficariam num *environment* do GitHub com `required reviewers`, e cada execução esperaria aprovação humana. Resolve o controle de gasto e permitiria até avaliar PR de fork com segurança, porque a aprovação é o ponto de controle. Rejeitada para este tamanho de projeto: ela coloca uma pessoa no caminho crítico de todo PR, e um gate que depende de alguém clicar deixa de ser automático — exatamente o que o Checkpoint 10 existe para eliminar. Vale reconsiderar se o repositório passar a receber contribuição de fora do time.

### O que exatamente faz o build falhar

Reunindo tudo, são cinco gatilhos independentes, e os cinco reprovam:

| Gatilho | Onde é aplicado |
|---|---|
| Erro de estrutura: frontmatter divergente, parâmetro não declarado, prompt sem suíte, segredo versionado | `verificar-estrutura.js` |
| Carregador quebrado ou frontmatter vazando para o modelo | `verificar-carregadores.js` |
| Config inválido, referência `file://` inexistente, assert JS com sintaxe inválida | `verificar-configs.js` |
| **Regressão:** caso que passava no baseline passa a falhar (depois da repetição) | `baseline.js --comparar` |
| **Caso novo que falha** e não está no baseline | `baseline.js --comparar` |
| **Não conseguiu avaliar:** relatório ausente ou zero casos executados | `rodar-suites.js` |
| Segredo ausente | passo `Conferir que os segredos estao configurados` |

Os dois primeiros blocos rodam em qualquer PR, de graça. Os três últimos são o gate pago. O item "caso novo que falha" é o que impede a lacuna óbvia do desenho por baseline: adicionar um prompt com suíte que já nasce vermelha e não registrar no baseline não passa em silêncio — ou se corrige, ou se registra com commit.

### Por que não a action oficial

A `promptfoo/promptfoo-action@v1` foi o ponto de partida e três coisas a inviabilizaram como gate:

1. Ela recebe **um** `config` e um glob de `prompts`. O desenho aqui é um `promptfooconfig.yaml` por prompt, ao lado do `prompt.md`, para o teste viajar junto com o prompt. São 9 configs, com providers e limites diferentes entre si.
2. O gate de `causa-raiz` **não cabe na configuração do promptfoo** — detalhe adiante — e precisa de script depois da eval.
3. Ela é orientada a relatório: roda a comparação antes/depois e publica o link. O que falta é reprovar o build com regra de escalonamento e repetição.

Dela foram adotados o padrão de cache, a publicação do resultado como comentário no PR e a exigência de Node ≥ 22.22 no runner.

---

## Dois defeitos que o próprio pipeline revelou

Os dois apareceram rodando de verdade no GitHub Actions, e nenhum apareceria em execução local.

### O gate estava fail-open

A primeira execução no Actions rodou **sem os segredos configurados** — eu os cadastrei depois do push. As nove suítes falharam em 2 segundos cada, nenhum JSON foi produzido, a comparação não gerou relatório. **E o job passou.**

A causa estava no meu código:

```javascript
const reprova = Boolean(rel && rel.reprova);   // relatorio ausente => nao reprova
```

Gate que passa quando a avaliação não roda é pior que gate nenhum: produz sinal verde que ninguém vai conferir. Falta de chave, cota estourada, modelo descontinuado e erro de sintaxe em assert são todos "não consegui avaliar", e **"não consegui avaliar" nunca é "está tudo bem"**.

Corrigido para fechar com diagnóstico, e verificado rodando sem chave:

```
=== VEREDITO DO GATE
    REPROVADO: a comparacao com o baseline nao produziu relatorio.
    Isso indica falha de infraestrutura e nao ausencia de regressao.
    Causas tipicas: chave de API ausente ou invalida, cota do provedor
    estourada, modelo descontinuado, erro de sintaxe em assert.
   >>> exit=1
```

Mais um passo no workflow que confere os segredos antes de gastar qualquer coisa, falhando com mensagem clara em vez de 9 reprovações confusas.

### PR do Dependabot não recebe segredos

Logo depois de eu cadastrar os secrets, o Dependabot abriu três PRs de bump de versão de action. Eles dispararam o workflow e **passaram com check verde** — ainda na versão fail-open, com as nove suítes falhando por falta de chave.

A causa é específica e não estava na minha leitura: os PRs do Dependabot vêm do **próprio repositório**, então a condição de fork não os pega, mas workflow disparado pelo Dependabot roda com escopo de segredo separado e não recebe os segredos de Actions.

Com o gate fechado, o Dependabot passaria a reprovar todo PR de bump. Então ele é tratado como fork: estrutura sim, avaliação paga não.

```yaml
    if: |
      github.actor != 'dependabot[bot]' &&
      (github.event_name != 'pull_request' ||
       github.event.pull_request.head.repo.full_name == github.repository)
```

### E o baseline estava tirado de amostra única

Com o gate fechado e os segredos no lugar, a execução seguinte **reprovou a `main`** — por um caso de `diagnostico-de-acoplamento` no `gemini-3.5-flash` que o baseline dizia que passava.

Não era regressão. O caso oscila: em parte das gerações o modelo classifica as 14 etapas do Spark como `INDETERMINADO`, que é a resposta honesta, e em parte classifica como `INCREMENTAL`. Eu havia gravado o baseline de **uma** execução, e ela pegou esse caso no dia bom.

Baseline tirado de amostra única transforma instabilidade do modelo em regressão inexistente, e é o caminho mais curto para o time desligar o gate. Corrigido com gravação **por consenso**: um caso entra como `passa: true` somente se passou em **todas** as execuções agregadas, e caso que oscila é registrado como falha conhecida com a marca `instavel`.

```
$ node scripts/baseline.js --gravar /tmp/base-r1 /tmp/base-r2 /tmp/base-r3
baseline gravado em avaliacao/baseline.json
  execucoes agregadas: 3
  31 caso(s): 23 passando sempre, 8 com falha conhecida
  1 caso(s) instavel(eis) (passam em parte das geracoes)
```

Três execuções completas do catálogo, e o consenso achou um caso que oscila entre passar e falhar na mesma suíte e no mesmo modelo — o mesmo que havia reprovado a `main`. Dois outros casos do `gpt-4o-mini` falham na primeira passada e passam na repetição, mas falharam em todas as três rodadas da primeira tentativa, então entram como falha estável e não recebem a marca. As três passam contra o baseline resultante.

---

## O gate de `causa-raiz` não cabe no YAML

Achado do CP09 que o pipeline herda, e vale repetir porque muda o desenho.

O corte da rubrica é **total ≥ 6 E nenhum critério zerado**. A primeira versão expressava isso com `threshold: 0.75` no teste, na conta de que a média de quatro asserts de peso igual corresponde a 6 de 8. Estava errado em dois níveis:

1. o assert de `cost` entrava na média — uma execução com rubrica **7/8** reprovou com score agregado 0,70 porque o custo estourou e virou 0 na média;
2. pior, no promptfoo 0.123.1 o `threshold` de teste **sobrescreve** a reprovação dos asserts individuais:

```javascript
let pass = !this.failedReason;
if (typeof this.threshold === "number" && !Number.isNaN(this.threshold)) {
  pass = score >= this.threshold;   // descarta o failedReason
}
```

Ligar o threshold desligava a única mecânica que pegaria o critério zerado. E o corte não é expressável como média, por aritmética simples: **6 com um critério zerado e 6 sem nenhum zerado têm a mesma média.** São dois sinais independentes.

A divisão final: `threshold: 0.5` por assert cobre "nenhum zerado", `cost` reprova por conta própria, e `aplicar-corte.js` soma os quatro critérios e aplica o total. É ele o gate, e o orquestrador o chama depois da eval.

---

## Evidência de execução

### Pipeline aprovando

Execução [36882075642](https://github.com/brianmonteiro54/prompt-registry/actions/runs/36882075642), push em `main`:

```
✓ main Avaliacao do playbook · 36882075642
JOBS
✓ Estrutura do catalogo in 45s
✓ Suites de avaliacao

    OK: estrutura, frontmatter, parametros e cobertura consistentes.
segredos presentes
=== ESCOPO: escopo completo
    9 de 9 suite(s): causa-raiz, detalhamento-de-fase, diagnostico-de-acoplamento, ...
--- causa-raiz ... asserts ok
--- detalhamento-de-fase ... com falha(s)
--- diagnostico-de-acoplamento ... com falha(s)
--- estrategia-backpressure ... com falha(s)
--- networkpolicy-sentinel ... com falha(s)
--- nota-de-triagem ... asserts ok
--- plano-de-migracao-faseado ... com falha(s)
--- revisao-de-networkpolicy ... com falha(s)
--- triagem-de-pods ... com falha(s)
    casos executados: 31   consistentes com o baseline: 29
    MELHORIAS (1) — falhavam no baseline e agora passam:
      diagnostico-de-acoplamento / google:gemini-3.5-flash / Forge em lote horario com tres consumidores acoplados
    REGRESSOES (1) — passavam no baseline e agora falham:
      estrategia-backpressure / openai:gpt-4o-mini / Relay com pico de 320k msgs/s sobre capacidade de 180k
    REPROVADO:
=== REPETINDO 1 suite(s) com regressao: estrategia-backpressure
--- estrategia-backpressure (2a tentativa) ... asserts ok
=== REAVALIANDO APOS A REPETICAO
    casos executados: 31   consistentes com o baseline: 30
    APROVADO: nenhuma regressao em relacao ao baseline.
    (1 melhoria(s) detectada(s); vale regravar o baseline)
```

A repetição da Decisão 2 funcionando: uma regressão na primeira passada em `estrategia-backpressure`, repetiu a suíte afetada, a segunda tentativa passou, aprovou. E detectou uma melhoria em `diagnostico-de-acoplamento` sem reprovar por ela — é o caso instável do baseline acertando nesta geração.

Sete das nove suítes aparecem como "com falha(s)" e o gate aprova. Não é contradição, é o desenho da Decisão 1: essas falhas estão registradas no baseline e o que o gate mede é piora em relação a ele. O veredito sai da linha `consistentes com o baseline`, não da contagem de asserts verdes.

### Gate barrando regressão provocada

Renomeei o rótulo `ESCALAR PARA:` para `ESCALONAR:` no `prompt.md` de `nota-de-triagem`, sem tocar no teste — a classe de regressão mais comum em catálogo de prompt:

```
=== ESCOPO: 1 prompt(s) alterado(s) em 1 arquivo(s)
    1 de 9 suite(s): nota-de-triagem
--- nota-de-triagem ... com falha(s)
    REPROVADO:
      - 6 regressao(oes)
=== REPETINDO 1 suite(s) com regressao: nota-de-triagem
--- nota-de-triagem (2a tentativa) ... com falha(s)
=== REAVALIANDO APOS A REPETICAO
    casos executados: 6   consistentes com o baseline: 0
    REGRESSOES (6) — passavam no baseline e agora falham:
      nota-de-triagem / openai:gpt-4o-mini / Sentinel com autoscaler no teto e fila crescendo
             Expected output to match regex "ESCALAR PARA:.*@\w+"
      nota-de-triagem / google:gemini-3.5-flash / Sentinel com autoscaler no teto e fila crescendo
             Expected output to match regex "ESCALAR PARA:.*@\w+"
      ... (6 casos, os dois providers)
=== VEREDITO DO GATE
    REPROVADO:
      - 6 regressao(oes)
   >>> exit=1
```

Seis regressões nos dois providers, repetição confirmou, `exit=1`. O escopo ficou em uma suíte porque só um prompt mudou.

E o comentário que vai para o PR:

```markdown
## Avaliacao do playbook

**Escopo:** 1 prompt(s) alterado(s) em 1 arquivo(s)

### Gate reprovado: houve regressao em relacao ao baseline

Casos executados: **6** · consistentes com o baseline: **0**

Suites repetidas automaticamente: `nota-de-triagem`

#### Regressoes
| Suite | Provider | Caso | Motivo |
|---|---|---|---|
| `nota-de-triagem` | `openai:gpt-4o-mini` | Sentinel com autoscaler... | Expected output to match regex "ESCALAR PARA:.*@\w+" |
...

> O gate reprova REGRESSAO, e nao imperfeicao: falha conhecida fica registrada em
> `avaliacao/baseline.json` e aceita-la exige commit.
```

### Custo e tempo de uma execução completa

| Suíte | Casos | Tokens | Custo | Duração |
|---|---:|---:|---:|---:|
| `causa-raiz` | 1 | 24.818 | US$ 0,08110 | 51,7s |
| `revisao-de-networkpolicy` | 6 | 19.713 | US$ 0,03899 | 35,1s |
| `estrategia-backpressure` | 2 | 8.060 | US$ 0,03374 | 26,2s |
| `detalhamento-de-fase` | 4 | 11.037 | US$ 0,02809 | 25,7s |
| `plano-de-migracao-faseado` | 2 | 6.305 | US$ 0,02538 | 19,0s |
| `diagnostico-de-acoplamento` | 2 | 4.259 | US$ 0,01986 | 16,1s |
| `networkpolicy-sentinel` | 2 | 6.863 | US$ 0,01590 | 13,0s |
| `triagem-de-pods` | 6 | 13.017 | US$ 0,01442 | 10,5s |
| `nota-de-triagem` | 6 | 10.498 | US$ 0,01138 | 8,7s |
| **Total** | **31** | **104.570** | **US$ 0,269** | **3,4 min** |

Média de **US$ 0,0087 por caso**. O item mais caro do catálogo custa 7x o mais barato, e a razão é inteira: `causa-raiz` paga uma geração com raciocínio estendido mais quatro julgamentos com raciocínio estendido.

Para dimensionar: ~US$ 0,27 por PR que toque arquivo compartilhado, e centavos por PR que toque um prompt. A conta que a Pepper Potts olharia é de 100 PRs por mês escalonados = cerca de US$ 27, e o cenário realista é bem abaixo disso porque a maioria dos PRs é de escopo único.

---

## Curadoria

**O erro que eu cometi três vezes.** CP08: limites de latência e custo de `networkpolicy-sentinel` fixados antes de medir, vermelhos no baseline. CP09: limite de custo do gate de `causa-raiz`, mesma coisa. CP10: baseline gravado de uma execução, tratando caso instável como estável. O padrão é meu e é sempre o mesmo — **escrevo o número por intuição e a medição me corrige.** O que mudou ao longo dos checkpoints não foi parar de errar, foi passar a medir antes de afirmar. Os três ficaram registrados porque o registro é o que impede a quarta vez.

**Gate que não pode falhar aberto.** Foi a lição mais dura deste checkpoint e só apareceu porque algo deu errado por acidente — eu cadastrei os secrets depois do push. Se tivesse cadastrado antes, o pipeline teria passado nos testes que eu fiz e o fail-open ficaria lá, esperando a primeira cota estourada ou o primeiro modelo descontinuado para dar verde num PR que ninguém avaliou. **Toda condição de erro de infraestrutura precisa de um caminho explícito para reprovar**, e isso vale para qualquer gate, não só para avaliação de prompt.

**Separar "não consegui medir" de "medi e está ruim".** É a mesma ideia do item anterior vista do outro lado, e aparece em três lugares deste repositório: o `politicas()` do CP08 que devolve `{docs, erro}` em vez de lançar, porque erro informa menos que falha; o gate fechando quando não há relatório; e a marca `instavel` no baseline, que distingue "falha sempre" de "falha às vezes". Relatório que mistura as três coisas obriga quem lê a investigar tudo de novo.

**Determinismo sobre saída aberta vai mais longe do que eu esperava.** Eu entrei neste checkpoint achando que precisaria de juiz em cinco prompts e precisei em zero — os quatro de saída aberta do CP04 e CP05 ficaram cobertos por asserts determinísticos que verificam aritmética, vocabulário fechado e regras de ordenação. A condição que torna isso possível foi decidida **na escrita dos prompts**, não na escrita dos testes: título de seção literal, vocabulário de classificação fechado, e no caso de `triagem-de-pods` um vocabulário do caso saudável disjunto do vocabulário do caso com falha. **Testabilidade não é acidente de quem escreve o teste.** Prompt que devolve prosa livre só se mede com juiz, e juiz custa o dobro por execução, doze vezes por caso, e precisa de calibração própria.

**O que o pipeline garante e o que não garante.** Garante que nenhuma alteração piore um caso que passava, que prompt novo entre com suíte, que frontmatter e parâmetros não divirjam, e que falha conhecida só seja aceita por commit revisável. Não garante que os prompts estejam corretos: 8 dos 31 casos falham hoje, de forma documentada, e o gate os mantém falhando em vez de os corrigir. Não garante comportamento em insumo diferente do registrado — a rubrica de `causa-raiz` nomeia a verdade do incidente do Cerebro, e outro pacote de artefatos exigiria outra rubrica. E não protege contra o fornecedor mudar o modelo por baixo: o CP08 registrou `gemini-2.5-flash` sendo descontinuado no meio do trabalho, e nenhuma suíte detecta isso como regressão de prompt porque não é.

---

## Pendências registradas

- **`networkpolicy-sentinel`, suíte:** não verifica se o `podSelector` alveja `app=sentinel` em vez do namespace inteiro, nem se as regras de ingress restringem porta. O revisor encontrou as duas coisas numa política que a suíte aprovou.
- **`diagnostico-de-acoplamento`, prompt v1.0.1:** a classificação das 14 etapas do Spark oscila entre `INDETERMINADO` e `INCREMENTAL` no mesmo modelo. A definição de `INDETERMINADO` precisa dizer explicitamente que grupo de etapas sem descrição individual nos insumos cai ali.
- **`plano-de-migracao-faseado`, prompt v1.0.1:** os dois providers declaram "Nenhuma" discordância diante de um diagnóstico que classifica a ingestão de forma contraditória com o requisito principal. O CP05 observou a autocorreção uma vez e concluiu que a cadeia se autocorrige; medido em dois fornecedores, **não reproduz**. A seção de discordâncias precisa de instrução mais forte sobre conferir a classificação herdada contra os requisitos.
- **`detalhamento-de-fase`, prompt v1.0.1:** a regra 1 manda recusar fase inexistente e o formato exige as sete seções sempre. As duas se contradizem nesse caso, e falta dizer o que vai nas seções de execução quando a fase não existe.
- **`revisao-de-networkpolicy` v1.0.1, aplicada:** a regra de severidade da seção 6 estava truncada ("não promova apontamento de forma a bloqueador", sem o nível de origem). Corrigida e validada com a suíte — 6 casos consistentes com o baseline, sem regressão. É a única pendência de prompt que saiu da fila, justamente porque a cobertura deste checkpoint permite validar a correção em vez de só documentá-la.
- **`causa-raiz`, prompt v1.0.1:** as duas pendências do CP09 seguem abertas — coluna de papel versus marcação de hipótese, e confiança declarada versus premissa não verificada.
- **Baseline:** o caso instável de `diagnostico-de-acoplamento` está registrado como falha conhecida. Quando o prompt v1.0.1 sair, regravar por consenso de três execuções e o commit deve explicar a mudança.
