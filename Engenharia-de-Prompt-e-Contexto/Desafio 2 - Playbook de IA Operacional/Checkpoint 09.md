# Checkpoint 09: Gate de qualidade com LLM-as-judge

O Checkpoint 08 cobriu o que se mede sem opinião: formato, latência, custo. Sobrou o que importa mais e não cabe em `contains`: se a análise está **certa**. A causa-raiz do Checkpoint 03 não tem resposta única verificável por regex: duas análises podem usar palavras completamente diferentes e as duas estarem corretas, ou usar as mesmas palavras e uma estar invertida. `contains: "cache"` não distingue "o cache caiu porque o heap saturou" de "o cache caiu e isso saturou o heap", e a segunda está de cabeça para baixo.

Este checkpoint monta o juiz, a rubrica e o gate. E o resultado mais útil não foi o gate funcionando: foi o juiz **discordando de mim duas vezes e estando certo nas duas**.

---

## A rubrica

Quatro critérios, escala 0 a 2, total de 0 a 8. **Corte: total ≥ 6 e nenhum critério zerado.**

A segunda condição não é redundante. Sem ela, uma análise 2+2+2+0 somaria 6 e passaria, e zero em qualquer destes quatro significa que a análise está errada em algo que importa. Zero em honestidade epistêmica é análise que apresenta suposição como evidência, e isso é pior que análise incompleta: leva alguém a agir com confiança indevida.

| Nota | Significado |
|:---:|---|
| **2** | Cumpre o critério integralmente. |
| **1** | Cumpre em parte, com falha identificável que não invalida a análise. |
| **0** | Não cumpre, ou cumpre de forma que induz o plantão a erro. |

Não existe meio ponto, e a ausência é deliberada: escala fina em julgamento qualitativo produz discordância entre avaliadores sem produzir informação, porque ninguém distingue 1,4 de 1,6 de forma reprodutível.

Os quatro critérios vivem em arquivos separados, um por critério, em [`devops/causa-raiz/criterios/`](./prompt-registry/devops/causa-raiz/criterios). A documentação humana está em [`rubrica.md`](./prompt-registry/devops/causa-raiz/rubrica.md).

### Onde a rubrica pode e não pode aparecer

Regra dura, e a razão vem do Checkpoint 03: o texto da rubrica **nomeia a cadeia causal do incidente**. Se ele entrar no `prompt.md`, o prompt passa a conter a resposta, e o item deixa de analisar para passar a recitar, ficando inútil para qualquer outro pacote de artefatos.

- **Proibido** no `prompt.md`, inclusive parafraseado.
- **Obrigatório** na configuração do juiz, que é onde a verdade de referência pertence: o juiz precisa saber a resposta para conseguir avaliar.

É essa separação que permite avaliar o prompt com rigor sem contaminá-lo.

### Fonte única, e por quê

Os quatro critérios e a instrução do juiz são lidos por `file://` tanto pelo gate quanto pelo harness de calibração:

```yaml
    - type: llm-rubric
      metric: c1-causa-raiz
      threshold: 0.5
      value: file://criterios/c1-causa-raiz.txt
```

A primeira versão tinha a rubrica escrita dentro de cada config. Tirei de lá porque **calibrar um juiz contra um texto e usar outro em produção é questão de tempo**: e o Checkpoint 08 já produziu exatamente esse defeito, com o prompt de `networkpolicy-sentinel` proibindo chaves e a suíte checando só `- {}`. A rubrica que calibrou o juiz precisa ser, byte a byte, a rubrica que o gate aplica.

### Os quatro critérios

**Critério 1: Causa-raiz correta.** 2 pontos exigem identificar o job de reindexação que não terminou como origem, a cadeia de job estagnado → heap esgotado → circuit breaker → timeout de busca e queda do cache, e a aritmética temporal explícita comparando o término previsto na config com o observado. 0 pontos para quem aponta a lentidão de busca, o pico de indexação ou o circuit breaker como causa: todos são elos posteriores, e tratá-los como origem leva a agir no lugar errado.

**Critério 2: Correlação × causa.** Três condições, todas necessárias: classificar a queda do cache como EFEITO; apresentar hipótese concorrente e descartá-la com evidência dos artefatos; e atribuir a cada sinal papel coerente com a sua posição no tempo.

**Critério 3: Ação proporcional.** Três condições: a contenção age sobre o job estagnado e não sobre o sintoma; a correção de fundo nomeia o parâmetro da config que muda; e a declaração de risco de **cada** ação identifica quem é afetado ou se declara provisória por ausência do mapa de dependências.

**Critério 4: Honestidade epistêmica.** Três condições: nada qualificado como natural, normal ou sazonal sem baseline nos artefatos; confiança declarada compatível com os dados; e três ou mais lacunas, uma delas a limitação de escopo dos próprios artefatos.

---

## O juiz

```yaml
defaultTest:
  options:
    provider:
      id: google:gemini-3.5-flash
      config:
        temperature: 0
        generationConfig:
          thinkingConfig:
            thinkingBudget: 2048
    rubricPrompt: file://criterios/instrucao-do-juiz.txt
```

Três decisões aqui, todas com consequência.

**O juiz vai declarado, e não é preferência de estilo.** Lendo o promptfoo 0.123.1, sem `provider` explícito ele calcula `shouldPreferRemote = ... || !grading.provider`, o que abre caminho para a avaliação ser feita pelo serviço remoto da ferramenta. O insumo deste item é log e métrica de produção. Mandar a saída para endpoint de terceiro não é decisão que um arquivo de teste deve tomar em silêncio.

**Raciocínio fica ligado, ao contrário das suítes do Checkpoint 08.** Lá `thinkingBudget: 0` porque havia limite de 5s e as tarefas eram transformação de formato. Aqui não há limite de latência (o item roda durante investigação de incidente, não em caminho quente) e julgar honestidade epistêmica exige comparar afirmação contra evidência disponível, que é cadeia e não consulta.

**A escala discreta está na instrução do juiz.** O promptfoo trabalha com score contínuo de 0 a 1; a rubrica tem três níveis. A conversão fica declarada uma vez:

```text
A escala do critério tem exatamente três níveis, e você escolhe um deles:
  2 pontos -> responda score 1.0
  1 ponto  -> responda score 0.5
  0 pontos -> responda score 0.0

Não use nenhum outro valor de score. Não interpole. Se você hesitar entre dois níveis,
escolha o menor e explique a hesitação no campo reason.
```

Sem isso o juiz devolve 0,7 e 0,85: números que não correspondem a nível nenhum da rubrica e que tornam impossível comparar com a nota humana. A regra da hesitação apareceu funcionando na saída real: o juiz escreveu "Seguindo a regra de hesitação, optou-se pelo score menor".

### O corte não cabe na configuração, e descobrir isso deu trabalho

A primeira versão expressava o corte assim, e parecia elegante:

```yaml
  threshold: 0.75          # "total >= 6" -> media dos 4 asserts
  assert:
    - type: llm-rubric
      threshold: 0.5       # "nenhum zerado" -> reprova quando o critério zera
```

A ideia: com quatro asserts de peso igual, média 0,75 é exatamente 6 de 8; e `threshold: 0.5` por assert reprova quando o critério dá 0 pontos e passa quando dá 1, porque cumprir em parte não reprova isoladamente.

**Estava errado em dois níveis.**

**Primeiro, o assert de `cost` entrava na média.** Medido numa execução real: rubrica **7/8**, que passa o corte com folga, e o gate reprovou com score agregado 0,70, porque o custo estourou e virou 0 na média de cinco asserts. Custo derrubando nota de qualidade é conflação de duas coisas que precisam ser lidas separadas.

**Segundo, e pior:** o `threshold` de teste **sobrescreve** a reprovação dos asserts individuais. No promptfoo 0.123.1:

```javascript
let pass = !this.failedReason;
if (typeof this.threshold === "number" && !Number.isNaN(this.threshold)) {
  pass = score >= this.threshold;   // descarta o failedReason
}
```

Ligar o `threshold` desliga a única mecânica que pegaria o critério zerado. Com ele ativo, uma análise **2+2+2+0** soma 6, dá média 0,75 e **passaria**: exatamente o caso que a segunda condição do corte existe para barrar.

E o corte do enunciado não é expressável como média, por um motivo aritmético simples: **6 com um critério zerado e 6 sem nenhum zerado têm a mesma média.** São dois sinais independentes, e nenhuma média os separa.

Considerei `assert-set` com threshold próprio para isolar a média da rubrica do assert de custo. Resolve a conflação e não resolve o segundo problema: o threshold do set sobrescreve a reprovação dos filhos pela mesma lógica.

A solução foi tirar o `threshold` do teste e dividir a responsabilidade:

| Condição | Onde é aplicada |
|---|---|
| nenhum critério zerado | `threshold: 0.5` em cada assert de rubrica, o caso reprova no próprio assert |
| limite de custo | assert `cost`, reprova por conta própria |
| **total ≥ 6** | `aplicar-corte.js`, que lê a saída da eval, soma os quatro critérios e sai com código 1 |

O `aplicar-corte.js` é o gate. Ele existe pelo mesmo motivo que o `calibrar.js`: a pergunta cruza asserts, e assert nenhum vê o vizinho. Validado contra as seis execuções registradas, reprova a de 5/8 por total, reprova a de 7/8 por custo (e reporta as duas coisas separadas), aprova as de 6/8 e 7/8 com custo dentro do teto.

---

## Calibração

O enunciado pede pontuar algumas saídas à mão e ajustar o juiz até ele ficar a no máximo 1 ponto em cada critério. O Checkpoint 03 já tinha deixado esse par pronto de propósito: duas execuções do **mesmo** pacote de artefatos com o prompt em dois estágios de refino, pontuadas por mim antes de existir juiz.

### O harness avalia o juiz, não o prompt

```
devops/causa-raiz/
├── prompt.md                     # inalterado (v1.0.0)
├── README.md                     # inalterado
├── prompt.js                     # carregador: le o prompt.md real, descarta frontmatter
├── promptfooconfig.yaml          # O GATE
├── aplicar-corte.js              # aplica "total >= 6 e nenhum zerado", exit 1 = reprova
├── rubrica.md                    # documentacao humana da rubrica
├── criterios/                    # FONTE UNICA, lida pelo gate e pela calibracao
│   ├── instrucao-do-juiz.txt     # escala discreta e formato de resposta
│   ├── c1-causa-raiz.txt
│   ├── c2-correlacao-vs-causa.txt
│   ├── c3-acao-proporcional.txt
│   └── c4-honestidade-epistemica.txt
├── casos/cerebro-2026-05-13/     # os 3 artefatos do CP03, byte a byte
│   ├── config.txt
│   ├── metricas.txt
│   └── logs.txt
└── calibracao/
    ├── promptfooconfig.yaml      # a suite de calibracao
    ├── replay.js                 # provider que devolve saida JA REGISTRADA
    ├── execucao-1.txt            # saida do CP03, referencia 6/8
    ├── execucao-2.txt            # saida do CP03, referencia 8/8
    ├── referencia-humana.json    # fonte unica das notas humanas
    └── calibrar.js               # compara juiz x humano, exit 1 = nao calibrado
```

Os três artefatos ficam em arquivo, e não embutidos no YAML, por uma razão de integridade: a calibração do juiz foi feita contra saídas geradas por **este** pacote. Reescrever os artefatos invalidaria a referência humana sem deixar rastro.

> **Ressalva de fidelidade.** As duas saídas reaproveitadas foram extraídas do Checkpoint 03, e ao extrair descobri que o título `SINAIS OBSERVADOS` havia se perdido na transcrição original: a tabela aparecia solta depois de `CADEIA CAUSAL`. Reinseri o título nos dois arquivos, porque o prompt exige as seis seções literais e eu havia pontuado as duas execuções como tendo a coluna de papel. Nenhum valor, papel ou justificativa foi alterado. É reconstrução declarada, não captura byte a byte.

A entrada não vem de modelo, vem de arquivo. Esse é o ponto do desenho: rodar a rubrica contra um modelo de verdade mistura duas variações ("o modelo escreveu uma análise pior" e "o juiz pontuou diferente") e o resultado não permite concluir nada sobre nenhuma das duas. Com entrada fixa, se a nota muda entre execuções a variação é do juiz, e só dele.

```javascript
module.exports = class ProviderDeReplay {
  async callApi(_prompt, context) {
    const arquivo = context?.vars?.execucao;
    if (!arquivo) {
      return { error: 'variavel `execucao` ausente: informe o arquivo da saida registrada' };
    }
    const caminho = path.join(__dirname, arquivo);
    let texto;
    try {
      texto = fs.readFileSync(caminho, 'utf8');
    } catch (e) {
      return { error: `nao foi possivel ler ${arquivo}: ${e.message}` };
    }
    return {
      output: texto,
      // Custo e tokens zerados de proposito: nenhuma chamada de geracao acontece aqui.
      // O custo desta suite e inteiramente o do juiz, e e isso que se quer medir.
      tokenUsage: { total: 0, prompt: 0, completion: 0, numRequests: 0 },
      cost: 0,
    };
  }
};
```

### A verificação que nenhum assert consegue fazer

As duas execuções empatam em critérios e diferem em outros. **O que qualifica um juiz não é acertar uma nota isolada, é reproduzir a diferença.** Um juiz que dá a mesma nota às duas passaria em qualquer assert individual e seria inútil.

Isso cruza casos de teste, e um assert do promptfoo só vê o próprio caso. Daí o `calibrar.js`, que lê a saída da eval inteira, converte score em pontos, compara com a referência humana, roda os testes de discriminação e **sai com código 1 quando a calibração falha**: pronto para servir de gate no Checkpoint 10.

A referência humana fica em `referencia-humana.json`, e não no metadado do caso de teste. O motivo virou prático no meio do trabalho: uma nota humana foi corrigida depois de o juiz já ter rodado, e com a referência num arquivo separado deu para reavaliar a concordância sem gastar chamada de API de novo.

### Três candidatos, medidos contra a mesma referência

| Juiz | Notas iguais à humana | Discrimina C3 | Discrimina C4 | Decisão de corte | Veredito |
|---|:---:|:---:|:---:|---|---|
| **`gemini-3.5-flash`** (thinking 2048) | **7 de 8** | OK | OK | igual nos dois casos | **CALIBRADO** |
| `gpt-4o` | 7 de 8 | falha | OK | igual nos dois casos | não calibrado |
| `gpt-4o-mini` | 2 de 8 | falha | falha | **invertida nos dois** | não calibrado |

Custo e tempo para julgar as duas análises:

| Juiz | Tokens | Raciocínio | Duração | Custo |
|---|---:|---:|---:|---:|
| `gemini-3.5-flash` | 18.860 | 4.898 | 32s | ~US$ 0,076 |
| `gpt-4o` | 12.487 | 0 | 15s | ~US$ 0,039 |
| `gpt-4o-mini` | 12.267 | 0 | 12s | ~US$ 0,002 |

**O `gpt-4o-mini` é o caso que mais ensina.** Ele atribuiu **1 ponto a todos os quatro critérios das duas execuções**, sem exceção. Total 4/8 nas duas, reprovando inclusive a análise que eu pontuei 8/8. Coincide com a referência humana em apenas 2 das 8 posições, e por acidente: os dois critérios da execução 1 que de fato valem 1 ponto. Nota uniforme no meio da escala parece julgamento e não carrega informação nenhuma: é o modo de falha mais perigoso de um juiz, porque produz número, tabela e relatório sem produzir medida.

O juiz escolhido custa o dobro do `gpt-4o` e demora o dobro. O gasto se justifica porque este item roda durante investigação de incidente, e porque juiz que não distingue análise boa de análise mediana transforma o gate em enfeite.

---

## O juiz discordou de mim, e estava certo

Duas vezes. É o resultado mais valioso deste checkpoint.

### Primeira: minha nota de Ação proporcional estava leniente

Na primeira rodada, o juiz deu 1 ao critério 3 da execução 1 onde eu havia dado 2. A justificativa dele:

> A contenção age corretamente sobre o job estagnado ('Cancelar ativamente a reindex task (88123)') e a correção de fundo propõe um limite de duração. No entanto, houve hesitação em atribuir a nota máxima porque a análise de risco da correção de fundo ('Altera apenas configuração de cronograma/comportamento preventivo') não identifica claramente quem ou o que é afetado.

Fui conferir o texto. A execução 1 escreve:

```text
- Correção de fundo: Alterar a config do reindex_job implementando um timeout ou
  cancelamento automático caso ultrapasse a janela esperada de 90min.
  Risco em produção: Baixo - Altera apenas configuração de cronograma/comportamento preventivo.
```

E a execução 2, no mesmo lugar:

```text
  Risco em produção: Provisório (mapa de dependências ausente nos artefatos) -
  Falhas sistemáticas por timeout podem estagnar a versão dos índices consumida pela aplicação.
```

O nível 2 do meu próprio critério exige que o risco de cada ação identifique quem é afetado **ou** se declare provisório. A execução 1 não faz nenhum dos dois. **A nota certa é 1, e eu fui leniente**: eu até havia anotado a ressalva no Checkpoint 03, e registrado que ela "não alterou a nota".

Corrigi a referência para 6/8, registrei a correção no Checkpoint 03 em vez de reescrever em silêncio, e a correção **inverteu o ranking dos juízes**: com a nota original o `gpt-4o` batia 8 de 8 e o Gemini parecia ter errado. Com a nota corrigida, o `gpt-4o` só concordava comigo porque repetia a minha leniência.

Isso é a parte que importa: **um juiz que concorda perfeitamente com um humano leniente herda a leniência**, e nenhuma métrica de concordância mostra isso. A concordância é alta justamente porque os dois erram junto.

### Segunda: a execução 2 quebra a taxonomia de papéis

Depois de ajustar o critério 2, o juiz passou a dar 1 à execução 2 onde eu dei 2, de forma estável:

> para o item (c), o sinal de 09:00 ("indexed_docs_per_s vai a 9800") recebeu o papel de "HIPÓTESE" em vez de um dos três papéis definidos pelo critério (causa, efeito ou contexto).

Está certo. O template do prompt define a coluna como `Papel (CAUSA, EFEITO, CONTEXTO)`, e a execução 2 escreveu `HIPÓTESE: Aumento de carga. Sem baseline nos artefatos, assume-se tráfego sazonal concorrente.`

E aqui o achado é melhor que a nota: **duas regras do prompt entram em conflito.** A regra de honestidade epistêmica, adicionada no refino do Checkpoint 03, manda marcar como hipótese o que não tem baseline. A execução 2 obedeceu, e obedeceu *substituindo* o papel. Ela cumpriu o critério 4 quebrando o critério 2.

Mantive minha nota 2 e registrei a divergência de 1 ponto, que está dentro da tolerância do enunciado. O motivo de não corrigir aqui é que a discordância aponta para defeito no **prompt**, não no juiz: a coluna de papel deveria sempre carregar um dos três papéis, com a marcação de hipótese ao lado e não em lugar dele. Virou pendência v1.0.1 de `causa-raiz`.

---

## Três iterações na rubrica

A calibração não converge de primeira, e cada volta ensinou uma coisa diferente sobre escrever rubrica.

### v1 → v2: tornar o critério fiel ao enunciado enterrou uma condição

O enunciado define o critério 3 como "propõe uma ação coerente com o diagnóstico (ex.: conter ou reagendar a reindexação, **rever heap/limites**), sem sobre nem subdimensionar". Minha v1 zerava quem propusesse aumentar memória, o que é mais estrito que o enunciado. Corrigi acrescentando um parágrafo permissivo sobre o tipo de ação.

Resultado medido: **os dois juízes bons pararam de distinguir as execuções no critério 3.** Ambos passaram a dar 2 à execução 1.

O parágrafo permissivo deslocou a atenção do juiz para o *tipo de ação* e enterrou a condição do *risco declarado*. Rubrica é prompt: adicionar texto permissivo em uma dimensão muda o que o juiz olha nas outras.

### v2 → v3: condições explícitas em vez de prosa

O critério 4 nunca teve esse problema, e a diferença é estrutural: ele é escrito como `2 pontos: TODAS as condições a seguir: (a)... (b)... (c)...`. O critério 3 era prosa corrida.

Reescrevi o 3 na mesma forma, preservando a permissividade do enunciado sobre tipo de ação e transformando o risco declarado na condição (c), com uma instrução extra:

```text
Confira a condição (c) ação por ação, e não no conjunto. Uma ação com risco bem descrito
não compensa a outra. Risco declarado apenas como "Baixo", "Médio" ou "Alto" seguido de
justificativa que fala do que a mudança altera, sem dizer quem sofre o efeito, NÃO cumpre
a condição (c): descrever a natureza da mudança não é identificar o afetado.
```

Discriminação restaurada, e o `gemini-3.5-flash` voltou a bater a referência.

### v3 → v4: a rubrica premiava um caminho só

O gate ao vivo reprovou com 5/8, e uma das deduções era esta:

> para atingir a nota máxima, o argumento utilizado para descartar essa hipótese deveria apontar explicitamente que 'o gargalo está na fila de escrita, não na de busca', enquanto o texto utilizou a precedência temporal do estouro do circuit breaker.

A análise descartou a hipótese concorrente mostrando que a degradação de busca vem **depois** da saturação de memória. Isso é raciocínio causal correto, e minha rubrica exigia um argumento específico, o da fila de escrita.

Era sobreajuste da rubrica aos exemplos de calibração: eu escrevi o critério olhando o argumento que as duas execuções do CP03 usaram, e transformei um caminho válido em *o* caminho. Reescrevi para exigir que o argumento se sustente nos artefatos, listando os dois caminhos como aceitáveis e dizendo explicitamente para não exigir um argumento específico.

---

## O juiz é determinístico. O gerador não é.

Essa separação decide o desenho do gate, e ela foi medida, não suposta.

**Juiz contra entradas fixas, 3 repetições, mesma rubrica:**

| Repetição | exec1 (C1/C2/C3/C4) | exec2 (C1/C2/C3/C4) |
|---|---|---|
| a | 2 / 2 / 1 / 1 | 2 / 1 / 2 / 2 |
| b | 2 / 2 / 1 / 1 | 2 / 1 / 2 / 2 |
| c | 2 / 2 / 1 / 1 | 2 / 1 / 2 / 2 |

**Variância zero.** Três repetições, um único padrão de notas por caso, nos quatro critérios.

**Gate ao vivo, 6 execuções:**

| Execução | C1 | C2 | C3 | C4 | Total | Veredito do corte | Latência | Custo |
|---|:---:|:---:|:---:|:---:|:---:|---|---:|---:|
| 1 | 2 | 1 | 1 | 1 | **5** | reprova por total | 28.541ms | US$ 0,0740 |
| 2 | 2 | 2 | 2 | 1 | 7 | reprova por custo | 31.231ms | US$ 0,0811 |
| 3 | 2 | 2 | 1 | 1 | **6** | aprova | 29.644ms | US$ 0,0740 |
| 4 | 2 | 2 | 2 | 1 | **7** | aprova | 30.368ms | US$ 0,0740 |
| 5 | 2 | 1 | 2 | 1 | **6** | aprova | 30.984ms | US$ 0,0811 |
| 6 | 2 | 1 | 2 | 1 | **6** | aprova | n/d | US$ 0,0740 |

> A execução 1 rodou com a versão anterior do critério 2: é o 5/8 que motivou a correção. A 2 estourou o limite de custo que eu havia fixado antes de medir. A 6 é a configuração final ponta a ponta, já com o corte aplicado por `aplicar-corte.js`.

Com a configuração final o total fica em **6, 7, 6, 6**. Como o juiz não varia, essa oscilação é inteiramente do gerador: cada execução do gate produz uma análise diferente, e as diferenças são reais, o juiz está respondendo corretamente a textos distintos.

O que oscila é C2 e C3, entre 1 e 2, de forma independente. C1 fica em 2 nas seis execuções e C4 fica em **1 nas seis**.

Três consequências diretas para o Checkpoint 10:

1. **O risco de "reprovar build por flutuação" não está no juiz.** Está no gerador. Isso muda a mitigação: não faz sentido amostrar o juiz várias vezes e tirar média; faz sentido dar margem ao corte, ou comparar contra uma saída registrada em vez de gerar de novo.
2. **A margem do baseline é de um ponto.** O total fica em 6 ou 7 contra um corte de 6. C2 e C3 oscilam entre 1 e 2 de forma independente; se as duas caírem na mesma execução, o total é 5 e o build falha sem ninguém ter tocado no prompt.
3. **Custa US$ 0,074 a US$ 0,081 por execução**, 1 geração com raciocínio estendido mais 4 julgamentos com raciocínio estendido, somando cerca de 50 segundos de execução da suíte. É o item mais caro do catálogo por execução, e o Checkpoint 10 vai rodar isso a cada alteração.

---

## O gate encontrou um defeito estável no prompt

O critério 4 vale **1 em todas as seis execuções**. Não é ruído, é reprodutível. A razão, nas palavras do juiz:

> declara 'Confiança: ALTA' apesar de a conclusão depender de uma premissa não verificada descrita nas lacunas: 'O agendamento "0 2 * * *" não especifica fuso horário. Assumiu-se UTC para coincidir com as métricas.' Se o fuso horário real for diferente, o cálculo do atraso de 6h28m é afetado. Além disso, apresenta o 'pico de tráfego matinal' como fato sem demonstrar uma baseline de dias anteriores.

É o **mesmo modo de falha** que a execução 1 do Checkpoint 03 apresentou, e que eu achei resolvido pelo refino. O prompt manda declarar a premissa de fuso e manda não qualificar comportamento como natural sem baseline. O modelo declara a premissa na seção de lacunas, e mantém `Confiança: ALTA`, como se declarar a lacuna dispensasse ajustar a confiança.

Vale registrar a diferença de modelo: o Checkpoint 03 rodou em Gemini Pro com raciocínio estendido e alcançou 8/8; aqui o gate roda em `gemini-3.5-flash`, e o mesmo prompt entrega 6 a 7. **A qualidade deste item é dependente de modelo, e o gate transformou isso em número.**

A correção vai para v1.0.1 de `causa-raiz`, documentada e não aplicada, pelo padrão dos checkpoints anteriores: alterar o prompt agora invalidaria as execuções registradas acima.

---

## Curadoria

**O corte que eu escrevi na configuração não era o corte do enunciado.** É o erro mais grave deste checkpoint e passou por duas execuções sem eu notar, porque o gate estava reprovando e aprovando nas horas certas *por coincidência aritmética*. Com `threshold: 0.75` ativo, o promptfoo descartava a reprovação dos asserts individuais, e a regra "nenhum critério zerado" simplesmente não existia, uma análise 2+2+2+0 passaria. Só apareceu quando fui conferir por que o score agregado era 0,80 e não 0,75, e a resposta estava no assert de custo entrando na média. A lição que fica: **conferir se o número que a ferramenta reporta é o número que você acha que pediu.** O score estava lá, visível, em todas as execuções, e eu li o veredito em vez de ler a conta.

**O limite de custo foi fixado antes de medir. Outra vez.** Escrevi `threshold: 0.08` copiando a lógica de "um pouco acima do esperado" e a segunda execução veio com US$ 0,0811. Exatamente o erro que o Checkpoint 08 registrou na suíte de `networkpolicy-sentinel`, repetido por mim num checkpoint de distância. O valor final é 0,15, tirado das seis medições (0,0740 e 0,0811 alternando), com folga para variação e aperto suficiente para pegar o dobro. Fica registrado porque o padrão é meu, não da ferramenta: eu escrevo limite operacional por intuição e a medição me corrige.

**Nenhum assert de latência neste gate, e a ausência é decidida.** As três suítes do Checkpoint 08 têm limite de 5s porque são itens de plantão, lidos com incidente aberto. Este roda durante investigação, quando alguém já separou os artefatos e vai ler a análise com calma. A geração levou 28 a 31 segundos nas execuções registradas, e a suíte completa com os quatro julgamentos levou cerca de 50s. Isso não é defeito: é o custo de raciocínio estendido numa tarefa que depende dele. Medir latência aqui produziria reprovação que não corresponde a requisito nenhum.

**Um provider só no gate, ao contrário do Checkpoint 08.** Lá o objetivo era comparar fornecedores, porque divergência entre eles indica prompt frágil. Aqui o objetivo é decidir se a análise tem qualidade para entrar. Cada provider a mais multiplica por cinco as chamadas (1 geração mais 4 julgamentos) e num gate que roda a cada alteração isso vira custo recorrente sem responder pergunta nova. A decisão de quando vale rodar a matriz inteira é do Checkpoint 10.

**A rubrica é um prompt, e se comporta como um.** Foi a lição mais transferível daqui. Três coisas que valem para qualquer rubrica de juiz:

- Critério escrito como **condições explícitas numeradas** é aplicado de forma mais consistente que critério escrito em prosa. O critério 4 nunca oscilou; o 3 só parou de oscilar quando virou `(a) (b) (c)`.
- Adicionar texto permissivo em uma dimensão **desloca a atenção** do juiz e pode desligar outra condição sem que você perceba. Só apareceu porque havia teste de discriminação.
- Escrever o critério olhando os exemplos de calibração produz **sobreajuste**: eu transformei o argumento que as duas execuções usaram em requisito, e uma análise com raciocínio igualmente válido foi penalizada.

**Instrumento de medida precisa de instrumento de medida.** O `calibrar.js` existe porque a pergunta que qualifica um juiz não é respondível por assert: é relativa e cruza casos. E o teste de discriminação foi o que pegou três das quatro falhas de calibração, em dois casos o juiz estava dentro de 1 ponto em todos os critérios, que é o critério do enunciado, e ainda assim era inútil porque empatava as duas execuções.

Vale a distinção explícita: **o enunciado pede concordância dentro de 1 ponto por critério, e o `gpt-4o` cumpre isso.** O teste de discriminação é exigência minha, acrescentada porque o Checkpoint 03 já havia escrito que "um juiz que atribuir a mesma nota aos dois não está calibrado, está sendo generoso". Foi ele que separou os dois juízes que passavam no critério do enunciado.

**O que o gate garante e o que não garante.** Ele garante que uma análise que perca um critério inteiro não entra, e que a nota não caia abaixo de 6. Não garante que a análise esteja certa: o juiz sabe a resposta do incidente do Cerebro porque a rubrica conta, e num incidente novo ele não terá essa referência. Isso não é falha do desenho, é o limite dele, e a alternativa (juiz sem verdade de referência) mede coerência interna, não correção. A generalização deste gate para outros pacotes de artefatos exige uma rubrica por pacote, e esse custo precisa estar visível antes de alguém prometer o contrário.

---

## Execução registrada

```
############ CALIBRACAO ############
=== Execucao 1 do CP03: referencia humana 6/8 (c3 = 1, c4 = 1)
    C1 causa-raiz correta        juiz 2  humano 2  -> igual
    C2 correlacao x causa        juiz 2  humano 2  -> igual
    C3 acao proporcional         juiz 1  humano 1  -> igual
    C4 honestidade epistemica    juiz 1  humano 1  -> igual
    TOTAL: juiz 6/8  humano 6/8
    CORTE (>=6 e nenhum zero): juiz aprova, humano aprova
=== Execucao 2 do CP03: referencia humana 8/8
    C1 causa-raiz correta        juiz 2  humano 2  -> igual
    C2 correlacao x causa        juiz 1  humano 2  -> dentro de 1
    C3 acao proporcional         juiz 2  humano 2  -> igual
    C4 honestidade epistemica    juiz 2  humano 2  -> igual
    TOTAL: juiz 7/8  humano 8/8
    CORTE (>=6 e nenhum zero): juiz aprova, humano aprova
=== TESTES DE DISCRIMINACAO
    C4 honestidade epistemica    Execucao 1 = 1, Execucao 2 = 2  -> OK
    C3 acao proporcional         Execucao 1 = 1, Execucao 2 = 2  -> OK
=== VEREDITO DA CALIBRACAO
    CALIBRADO: concordancia dentro de 1 ponto em todos os critérios,
    discriminacoes reproduzidas e decisao de corte igual a humana.
   exit=0

############ GATE AO VIVO, PONTA A PONTA ############
$ npx promptfoo eval -c devops/causa-raiz/promptfooconfig.yaml --no-cache -o /tmp/gateF.json
  ✓ 1 passed (100%)
  0 failed (0%)
  0 errors (0%)
Duration: 54s (concurrency: 1)

$ node devops/causa-raiz/aplicar-corte.js /tmp/gateF.json
=== Cerebro 2026-05-13: reindexacao estagnada saturando o heap
    provider: google:gemini-3.5-flash
    c1-causa-raiz                2 ponto(s)
      A análise identifica o job de reindexação como a origem do incidente, apresenta a
      cadeia causal correta (job estagnado -> saturação de heap/GC -> circ...
    c2-correlacao-vs-causa       1 ponto(s)
      Hesitação entre os níveis de 2 pontos e 1 ponto. Embora a análise descarte
      corretamente a hipótese de vazamento de memória no cache de busca ('Veredit...
    c3-acao-proporcional         2 ponto(s)
      A análise atende a todos os critérios para a nota máxima. (a) A contenção age
      diretamente sobre o job estagnado ao propor "Cancelar a tarefa de reinde...
    c4-honestidade-epistemica    1 ponto(s)
      A análise declara 'Confiança: ALTA', mas isso viola a condição (b) do critério,
      pois a conclusão de que o job atrasou depende da premissa não verifica...
    cost                         ok
    TOTAL: 6/8   (corte >= 6 e nenhum zerado)
    APROVA
=== VEREDITO DO GATE
    APROVADO: todos os casos com total >= 6, nenhum critério zerado e
    limites operacionais dentro do teto.
exit do gate: 0
```

E o gate reprovando, na execução que rodou com a versão anterior do critério 2:

```
$ node devops/causa-raiz/aplicar-corte.js /tmp/gate1.json
    c1-causa-raiz                2 ponto(s)
    c2-correlacao-vs-causa       1 ponto(s)
    c3-acao-proporcional         1 ponto(s)
    c4-honestidade-epistemica    1 ponto(s)
    cost                         ok
    TOTAL: 5/8   (corte >= 6 e nenhum zerado)
    REPROVA: total abaixo do corte
=== VEREDITO DO GATE
    REPROVADO:
      - Cerebro 2026-05-13 ...: total 5/8 abaixo do corte de 6
exit do gate: 1
```

---

## Pendências registradas (v1.0.1, documentadas e não aplicadas)

- **`causa-raiz`, conflito entre duas regras:** a coluna de papel da tabela de sinais deve sempre carregar CAUSA, EFEITO ou CONTEXTO, com a marcação de hipótese ao lado e não em vez dela. Hoje a regra de honestidade epistêmica induz o modelo a substituir o papel, e isso custa ponto no critério 2.
- **`causa-raiz`, confiança versus premissa declarada:** o prompt precisa dizer que declarar a premissa em LACUNAS **não** dispensa ajustar o nível de confiança. Defeito reprodutível em 6 de 6 execuções do gate.
- **Rubrica, generalização:** os quatro critérios nomeiam a verdade do incidente do Cerebro. Avaliar outro pacote de artefatos exige outra rubrica, e esse custo precisa entrar na conta antes de estender o gate.
- **Gate, margem:** o baseline fica a um ponto do corte. Ou o prompt sobe de patamar (v1.0.1), ou o Checkpoint 10 precisa de estratégia explícita para flutuação do gerador.
