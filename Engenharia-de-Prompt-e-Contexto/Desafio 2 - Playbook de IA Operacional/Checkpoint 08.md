# Checkpoint 08: A biblioteca passa a ser testada

O Checkpoint 07 transformou o playbook em repositório. Isso resolve versionamento e descoberta, e não resolve a pergunta que o Nick Fury vai fazer na primeira vez que um prompt der resposta errada em produção: *como vocês sabem que ele ainda funciona?*

Este checkpoint responde com teste automatizado. Três prompts do catálogo ganharam suíte de avaliação em [promptfoo](https://www.promptfoo.dev/), executada de verdade contra dois fornecedores de modelo, com os números registrados abaixo. Nenhum resultado deste arquivo é estimado.

O que a suíte encontrou foi mais interessante que um selo verde: **quatro defeitos reais de prompt** (três em `triagem-de-pods` e um em `networkpolicy-sentinel`), **quatro bugs no meu próprio código de teste**, **dois limites que eu mesmo havia copiado sem medir** e **quatro comportamentos de plataforma que quebram pipeline sem ninguém tocar em prompt nenhum**. Está tudo documentado, incluindo os meus erros.

---

## Por que promptfoo, e por que só três prompts

A ferramenta foi escolhida por uma característica específica: a suíte é **arquivo versionado ao lado do prompt**, não configuração em interface. Isso é pré-requisito do Checkpoint 10, sem o teste no repositório, não existe pipeline que barre regressão no momento do pull request.

Dos nove prompts do catálogo, três entraram nesta rodada. O critério foi **testabilidade por asserção determinística**:

| Prompt | Entra? | Motivo |
|---|---|---|
| `nota-de-triagem` | Sim | Saída de 5 rótulos fixos. Testável por string, sem julgamento. |
| `triagem-de-pods` | Sim | Saída estruturada com regra de severidade objetiva e ordenação verificável. |
| `networkpolicy-sentinel` | Sim | Saída é YAML. Dá para **parsear e verificar efeito**, não só presença de texto. |
| `causa-raiz` | Não | Saída é análise em prosa. Precisa de juiz, e juiz é o Checkpoint 09. |
| `estrategia-backpressure`, `diagnostico-de-acoplamento`, `plano-de-migracao-faseado`, `detalhamento-de-fase`, `revisao-de-networkpolicy` | Não | Idem: qualidade é de raciocínio, não de formato. Cobertura completa é o Checkpoint 10. |

Os três escolhidos cobrem os três níveis de rigor que existem no catálogo: string simples, regra de negócio derivada, e correção semântica de artefato executável. Se a abordagem funciona nesses três, escala para o resto.

---

## Estrutura criada no repositório

```
prompt-registry/
├── package.json                  # promptfoo 0.123.1 pinado, js-yaml, scripts de eval
├── package-lock.json
├── .gitignore                    # + node_modules/, .promptfoo/, .env*
└── devops/
    ├── nota-de-triagem/
    │   ├── prompt.md             # inalterado
    │   ├── prompt.js             # carregador (ver adiante)
    │   └── promptfooconfig.yaml  # a suíte
    ├── triagem-de-pods/
    │   ├── prompt.md             # v1.0.1: três correções vindas da suíte
    │   ├── README.md             # v1.0.1 + histórico de versões
    │   ├── prompt.js
    │   └── promptfooconfig.yaml
    └── networkpolicy-sentinel/
        ├── prompt.md             # inalterado
        ├── prompt.js
        ├── asserts.js            # asserts semânticos em arquivo separado
        └── promptfooconfig.yaml
```

A versão do promptfoo está **pinada em `0.123.1`**, sem faixa de versão. Suíte de teste que muda de comportamento porque a ferramenta subiu de minor deixa de ser referência. A decisão se confirmou útil: a seção de curadoria mostra três comportamentos específicos desta versão que mudam o resultado.

Segredos ficam **fora do repositório**, em `~/.aegis-playbook.env` com permissão `600`, carregado por `source` antes de rodar. O `.gitignore` passou a cobrir `.env` e `.env.*` para que a próxima pessoa não descubra esse requisito do jeito ruim.

```bash
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh"; nvm use 22   # promptfoo exige node >= 22.22
source ~/.aegis-playbook.env
npx promptfoo eval -c devops/nota-de-triagem/promptfooconfig.yaml --no-cache
```

O `--no-cache` não é detalhe. Resultado servido de cache responde em milissegundos, e o assert de latência passaria sem medir nada.

---

## O carregador `prompt.js`

Os três diretórios têm o mesmo arquivo, byte a byte. Ele existe por um motivo que só apareceu na primeira execução: **o promptfoo enviava o frontmatter YAML ao modelo**. O frontmatter é metadado do catálogo, não faz parte do prompt, e mandá-lo junto suja o teste e gasta token.

```javascript
/**
 * Carregador do prompt para a suite de avaliacao.
 *
 * Existe por um motivo unico: `prompt.md` carrega frontmatter YAML, que e metadado
 * do catalogo e nao faz parte do prompt. Enviar o frontmatter ao modelo sujaria o
 * teste e gastaria tokens. Este arquivo le o proprio `prompt.md` do diretorio,
 * descarta o frontmatter e substitui os placeholders pelos valores do caso de teste.
 *
 * Le o arquivo real, e nao uma copia: alterar `prompt.md` muda o que a suite testa,
 * que e a condicao para o pipeline barrar regressao.
 */
const fs = require('node:fs');
const path = require('node:path');

const SEM_FRONTMATTER = /^---\r?\n[\s\S]*?\r?\n---\r?\n/;
const PLACEHOLDER = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g;

module.exports = async function ({ vars }) {
  const corpo = fs
    .readFileSync(path.join(__dirname, 'prompt.md'), 'utf8')
    .replace(SEM_FRONTMATTER, '')
    .trimStart();

  // Placeholder sem valor no caso de teste vira string vazia. Isso e intencional:
  // parametro opcional ausente precisa exercitar o caminho de fallback do prompt.
  return corpo.replace(PLACEHOLDER, (_, nome) =>
    vars[nome] === undefined || vars[nome] === null ? '' : String(vars[nome]),
  );
};
```

**Decisão registrada: ler o `prompt.md` real em vez de copiar o texto para dentro do config.**

A alternativa (declarar o prompt inline no YAML da suíte) foi rejeitada porque anularia o propósito. Se o texto do prompt vive em dois lugares, alterar `prompt.md` não dispara o teste, e a suíte passa a certificar uma cópia congelada enquanto o arquivo que as pessoas usam segue à deriva. O Checkpoint 10 depende exatamente disso: mudou o prompt, roda o teste.

O placeholder ausente virar string vazia também é deliberado. `nota-de-triagem` tem o parâmetro opcional `mapa_escalacao`, e os três casos de teste o omitem de propósito para exercitar o caminho de fallback ao mapa padrão declarado no corpo do prompt, que é o caminho que o plantão vai usar de fato.

---

## Suíte 1: `nota-de-triagem`

Saída de formato fixo, então os asserts são quase todos de string. O valor aqui está menos nos asserts e mais em **dois casos-armadilha**.

```yaml
# yaml-language-server: $schema=https://promptfoo.dev/config-schema.json

description: Nota de triagem padronizada a partir de alerta bruto de monitoracao

# Execucao sequencial, e nao por economia de tempo: o assert de latencia so tem
# significado quando as chamadas nao competem entre si. Medido nesta suite, com
# concorrencia 4 o mesmo prompt que responde em ~1s passou a levar 21s por fila do
# lado do provedor. Isso reprovaria o build por carga da API, nao por regressao do
# prompt. A garantia fica no arquivo de teste, e nao na linha de comando, para nao
# depender de quem executa.
evaluateOptions:
  maxConcurrency: 1

prompts:
  - id: file://prompt.js
    label: nota-de-triagem

providers:
  # Dois fornecedores distintos de proposito: o mesmo prompt precisa sobreviver a
  # troca de modelo. Divergencia entre eles e sinal de prompt fragil, nao de modelo ruim.
  - id: openai:gpt-4o-mini
    config:
      temperature: 0
      # Temperatura 0 nao garante determinismo nesta API. Sem seed, o mesmo caso
      # alternou entre acertar e errar a regra de severidade entre execucoes.
      seed: 42

  - id: google:gemini-3.5-flash
    config:
      temperature: 0
      generationConfig:
        thinkingConfig:
          # Raciocinio estendido vem ligado por padrao e ameaca o limite de 5s. A tarefa
          # e transformacao de uma linha de texto: nao depende de cadeia longa.
          thinkingBudget: 0

# Asserts que valem para TODA saida, independente do alerta de entrada.
defaultTest:
  assert:
    # 1. Os cinco rotulos do padrao definido pela Head of Product.
    - type: contains
      value: 'ALERTA:'
    - type: contains
      value: 'IMPACTO:'
    - type: contains
      value: 'HIPÓTESE INICIAL:'
    - type: contains
      value: 'AÇÃO IMEDIATA:'
    - type: contains
      value: 'ESCALAR PARA:'

    # 2. O campo de escalonamento tem handle no formato arroba mais palavra.
    - type: regex
      value: 'ESCALAR PARA:.*@\w+'

    # 3. A nota e concisa: no maximo 8 linhas.
    - type: javascript
      value: |
        const linhas = output.trim().split('\n').filter((l) => l.trim() !== '');
        return linhas.length <= 8
          ? true
          : { pass: false, score: 0, reason: `nota com ${linhas.length} linhas, maximo permitido 8` };

    # 4. Nenhum preambulo: a saida comeca no rotulo ALERTA.
    - type: javascript
      value: |
        return output.trimStart().startsWith('ALERTA:')
          ? true
          : { pass: false, score: 0, reason: `saida nao comeca em "ALERTA:" e sim em "${output.trimStart().slice(0, 40)}"` };

    # Limites operacionais. Latencia e custo sao parte da qualidade do item de playbook:
    # nota de triagem lida em plantao que demora 20s ou custa caro nao serve.
    - type: latency
      threshold: 5000
    - type: cost
      threshold: 0.01

tests:
  - description: Sentinel com autoscaler no teto e fila crescendo
    vars:
      # mapa_escalacao fica ausente de proposito nos tres casos: e o caminho de
      # fallback para o mapa padrao declarado no corpo do prompt, e e ele que o
      # plantao vai usar na pratica.
      alerta_cru: >-
        2026-05-12 14:02:09 UTC [Sentinel] autoscaler hit max replicas (60/60)
        on sentinel-api, queue depth on Relay growing 2k/min, CPU avg 88%,
        tenant stark-industries sending 4x baseline volume after onboarding new region
    assert:
      # O alerta cita tres sistemas. O handle tem que sair do sistema emissor,
      # que e o da tag entre colchetes, e nao de um dos sistemas mencionados.
      - type: contains
        value: '@sentinel-core'

  - description: Relay com rejeicao de ingestao apos deploy
    vars:
      alerta_cru: >-
        2026-05-13 03:11:00 UTC [Relay] ingest reject rate 6% for 8min,
        tenant wakanda-systems, buffer saturated after deploy 02:55
    assert:
      - type: contains
        value: '@relay-core'
      # Este caso e a armadilha de contaminacao: o exemplo de formato embutido no
      # prompt descreve o MESMO incidente, com numeros e ferramenta proprios.
      # Nada dele pode aparecer na nota.
      - type: not-contains
        value: '09:14'
      - type: not-contains
        value: 'Argo CD'
      - type: not-contains
        value: '12%'
      # O horario do alerta real precisa aparecer.
      - type: contains
        value: '02:55'

  - description: Forge com lag de consumer apos falha de job
    vars:
      alerta_cru: >-
        2026-05-13 11:40:22 UTC [Forge] consumer lag 9min and climbing,
        batch forge-batch-ingest delayed after previous job failure,
        downstream Sentinel starting to lag
    assert:
      - type: contains
        value: '@data-platform'
      # Dado retido no pipeline, apenas atrasado: a regra de reversibilidade do
      # dano manda 20min, nao 10min.
      - type: regex
        value: 'ESCALAR PARA:.*em 20min'
```

As duas armadilhas testam coisas que só aparecem quando o prompt é usado a sério:

- **Handle do sistema emissor, não do mencionado.** O primeiro alerta cita Sentinel, Relay e um tenant. O rótulo `ESCALAR PARA:` tem que apontar para o time do sistema que emitiu o alerta, identificado pela tag entre colchetes. `contains: '@sentinel-core'` verifica que o modelo não escalou para o time do sistema que apenas apareceu na descrição.
- **Contaminação pelo exemplo.** O prompt embute um exemplo de formato que descreve um incidente do Relay, com horário `09:14`, ferramenta `Argo CD` e taxa `12%`. O segundo caso de teste é *também* um incidente do Relay. Os três `not-contains` verificam que o modelo copiou o **formato** do exemplo e não os **dados** dele. Esse é o erro mais comum em prompt com exemplo embutido, e é silencioso: a nota sai bem formatada e com número errado.

### Resultado medido

```
Total Tokens: 10,496
  ✓ 6 passed (100%)
  0 failed (0%)
  0 errors (0%)
Duration: 11s (concurrency: 1)
```

| Caso | Provider | Asserts | Latência | Custo |
|---|---|---|---|---|
| Sentinel / autoscaler | `gpt-4o-mini` | 11/11 | 2640ms | US$0,000185 |
| Sentinel / autoscaler | `gemini-3.5-flash` | 11/11 | 1455ms | US$0,003729 |
| Relay / rejeição | `gpt-4o-mini` | 15/15 | 2033ms | US$0,000180 |
| Relay / rejeição | `gemini-3.5-flash` | 15/15 | 1298ms | US$0,003473 |
| Forge / lag | `gpt-4o-mini` | 12/12 | 2031ms | US$0,000175 |
| Forge / lag | `gemini-3.5-flash` | 12/12 | 1135ms | US$0,003488 |

**6 de 6, incluindo as duas armadilhas, nos dois fornecedores.** Este é o prompt mais maduro do catálogo e o resultado é consistente com isso.

Um número que vale reter: o `gemini-3.5-flash` responde mais rápido e custa **cerca de 20x mais** por chamada. Os dois ficam abaixo do limite de 1 centavo com folga, então aqui é indiferente. Na terceira suíte deixa de ser.

---

## Suíte 2: `triagem-de-pods`

Aqui os asserts deixam de verificar formato e passam a verificar **regra de negócio derivada do insumo**. A regra de severidade do prompt diz: `CRITICA` quando nenhum pod do mesmo serviço está saudável, `ALTA` quando existe réplica atendendo. Isso não é formato, é contagem sobre o snapshot, e é o que separa um triador útil de um formatador de texto.

Os três casos, com os asserts que importam:

```yaml
  # ---------------------------------------------------------------------------
  - description: Entrada 2 - dois pods que nao sobem, por causas diferentes
    vars:
      snapshot: |
        $ kubectl get pods -n sentinel-prod
        NAME                            READY   STATUS             RESTARTS   AGE
        sentinel-api-7d9c8b6f4-2xk9p    1/1     Running            0          6d
        sentinel-api-7d9c8b6f4-zzp10    0/1     ImagePullBackOff   0          8m
        sentinel-ingest-8f7a9c5b-4dkqm  0/1     Pending            0          8m
        sentinel-scheduler-6c4d7f-nn8vx 1/1     Running            0          6d
        ... (describe dos dois pods em falha)
    assert:
      # Os dois pods problematicos, nomeados.
      - type: contains
        value: 'sentinel-api-7d9c8b6f4-zzp10'
      - type: contains
        value: 'sentinel-ingest-8f7a9c5b-4dkqm'
      # Causa do primeiro: a tag que nao existe no registry.
      - type: javascript
        value: |
          const t = output.toLowerCase();
          return t.includes('2.9.2') || t.includes('manifest unknown')
            ? true
            : { pass: false, score: 0, reason: 'causa do ImagePullBackOff nao cita a tag 2.9.2 nem manifest unknown' };
      # Causa do segundo: falta de cpu no cluster.
      - type: javascript
        value: |
          const t = output.toLowerCase();
          return t.includes('insufficient') || t.includes('cpu')
            ? true
            : { pass: false, score: 0, reason: 'causa do Pending nao cita Insufficient nem cpu' };
      - type: contains
        value: '2 POD(S) PROBLEMATICO(S)'
      # O servico de ingestao nao tem replica saudavel, entao e o mais grave e vem
      # primeiro. Verifica que a regra de severidade por sobrevivencia do servico
      # produziu a ordenacao esperada.
      - type: javascript
        value: |
          const i = output.indexOf('sentinel-ingest-8f7a9c5b-4dkqm');
          const a = output.indexOf('sentinel-api-7d9c8b6f4-zzp10');
          return i >= 0 && a >= 0 && i < a
            ? true
            : { pass: false, score: 0, reason: 'o pod de ingestao (sem replica saudavel) deveria vir antes do pod de api' };
      - type: contains
        value: 'CRITICA'
```

O snapshot foi montado para que a regra tenha consequência visível. `sentinel-api` tem um pod saudável e um quebrado, então o quebrado é `ALTA`. `sentinel-ingest` tem **um único pod, e ele está `Pending`**: o serviço está inteiro fora, então é `CRITICA`, e tem que vir primeiro na saída. Um modelo que ignora a regra classifica os dois como `ALTA` e emite na ordem em que aparecem no `kubectl get pods`.

O terceiro caso é o oposto: **cluster saudável**. Ele testa que o prompt não força diagnóstico quando não há problema, e testa por ausência:

```yaml
    assert:
      - type: contains
        value: 'NENHUM POD PROBLEMATICO'
      # E nao classifica nenhum pod como em falha. Isto so e testavel por ausencia
      # porque o prompt reserva os rotulos de diagnostico ao caso com problema:
      # o vocabulario do caso saudavel e disjunto do vocabulario do caso com falha.
      - type: not-contains
        value: 'CAUSA_RAIZ:'
      - type: not-contains
        value: 'SEVERIDADE:'
      - type: not-contains
        value: 'ACAO_RECOMENDADA:'
      # O restart antigo do worker e observacao, nao falha: nao pode virar diagnostico.
      - type: javascript
        value: |
          const linhas = output.trim().split('\n').filter((l) => l.trim() !== '');
          return linhas.length <= 3
            ? true
            : { pass: false, score: 0, reason: `caso saudavel com ${linhas.length} linhas; esperado o veredito mais no maximo 2 linhas de observacoes` };
```

Esses três `not-contains` só funcionam por uma propriedade de projeto do prompt: **o vocabulário do caso saudável é disjunto do vocabulário do caso com falha.** Se o prompt usasse `SEVERIDADE: NENHUMA` no caso saudável, não haveria como testar ausência de diagnóstico por string. Testabilidade não é acidente de quem escreve o teste, ela é decidida na hora de escrever o prompt.

### Resultado medido

```
Total Tokens: 13,059
  ✓ 5 passed (83.33%)
  ✗ 1 failed (16.67%)
Duration: 12s (concurrency: 1)
```

| Caso | Provider | Asserts | Latência | Custo |
|---|---|---|---|---|
| 1: OOMKilled | `gpt-4o-mini` | 8/8 | 2275ms | US$0,000396 |
| 1: OOMKilled | `gemini-3.5-flash` | 8/8 | 1656ms | US$0,004578 |
| 2: dois pods, causas diferentes | `gpt-4o-mini` | **9/11** | 2559ms | US$0,000380 |
| 2: dois pods, causas diferentes | `gemini-3.5-flash` | 11/11 | 2051ms | US$0,005461 |
| 3: cluster saudável | `gpt-4o-mini` | 9/9 | 1741ms | US$0,000229 |
| 3: cluster saudável | `gemini-3.5-flash` | 9/9 | 1073ms | US$0,003431 |

As duas falhas, ambas no caso 2 e ambas no `gpt-4o-mini`:

```
X assert#10 javascript -> o pod de ingestao (sem replica saudavel) deveria vir antes do pod de api
X assert#11 contains [CRITICA] -> Expected output to contain "CRITICA"
```

E a saída que causou:

```text
VEREDITO: 2 POD(S) PROBLEMATICO(S)
POD: sentinel-api-7d9c8b6f4-zzp10
SEVERIDADE: ALTA
...
POD: sentinel-ingest-8f7a9c5b-4dkqm
SEVERIDADE: ALTA
...
```

**Os dois pods saíram como `ALTA`, e o mais grave saiu por último.** Todo o resto está correto: os dois pods nomeados, as duas causas certas (`manifest unknown` e `Insufficient cpu`), a contagem certa, a evidência citada. O modelo fez a triagem e **não fez a contagem de réplicas por serviço**. Em plantão isso significa que o pior caso está na segunda metade da tela.

O `gemini-3.5-flash` acerta os 11 asserts, incluindo a ordenação e o `CRITICA`. Isso é o achado de modelo desta suíte, e está tratado na curadoria.

---

## Suíte 3: `networkpolicy-sentinel`

Esta é a suíte que justifica o esforço. As outras duas verificam texto; esta **parseia o YAML e verifica o efeito da política**. A diferença não é acadêmica: `contains: "5432"` passa se o número aparecer em qualquer lugar da saída, inclusive num item de regra que libera aquela porta para o destino errado, que foi exatamente o defeito bloqueador encontrado na revisão manual do Checkpoint 06.

Os asserts semânticos ficam em `asserts.js`, por um motivo técnico e um de projeto.

```javascript
/**
 * Asserts semanticos da suite de `networkpolicy-sentinel`.
 *
 * Ficam em arquivo separado por uma razao tecnica: assert inline no YAML e avaliado
 * em contexto sem `require`, o que impede parsear o YAML da saida de verdade. Aqui
 * da para carregar um parser e verificar EFEITO da politica, e nao presenca de texto.
 *
 * A diferenca importa neste item: `contains: "5432"` passa se o numero aparecer em
 * qualquer lugar, inclusive num item que libera aquela porta para o destino errado.
 */
const yaml = require('js-yaml');

const falha = (reason) => ({ pass: false, score: 0, reason });

/**
 * Parseia a saida e NUNCA lanca.
 *
 * Assert que lanca excecao aborta a avaliacao inteira em vez de reprovar o caso: no
 * pipeline isso viraria "erro" no lugar de "falha", e erro informa menos que falha
 * porque nao diz qual requisito nao foi cumprido. Toda funcao daqui devolve motivo.
 */
function politicas(output) {
  try {
    const docs = yaml.loadAll(output).filter((d) => d && d.kind === 'NetworkPolicy');
    return { docs, erro: null };
  } catch (e) {
    return { docs: [], erro: e.message.split('\n')[0] };
  }
}
```

O assert central é o que reproduz o defeito do Checkpoint 06:

```javascript
/**
 * Cada par destino-porta esperado existe, com a porta no MESMO item do destino.
 *
 * Item com varios destinos e varias portas libera o produto cartesiano entre eles:
 * foi o defeito bloqueador encontrado na revisao da primeira versao, em que o mesmo
 * item liberava o warehouse na porta da busca e a busca na porta do warehouse.
 */
function egressPorParDestinoPorta(output) {
  const { docs, erro } = politicas(output);
  if (erro) return falha(`saida nao parseia como YAML: ${erro}`);
  const itens = docs.flatMap((d) => d.spec?.egress || []);
  const problemas = [];

  const temPar = (destino, porta) =>
    itens.some((it) => {
      const alvo = JSON.stringify(it.to || []);
      const portas = (it.ports || []).map((p) => String(p.port));
      return alvo.includes(destino) && portas.includes(String(porta));
    });

  if (!temPar('forge', 5432)) problemas.push('falta egress para forge na 5432');
  if (!temPar('cerebro', 9200)) problemas.push('falta egress para cerebro na 9200');

  const cruzados = itens.filter(
    (it) => (it.to || []).length > 1 && (it.ports || []).length > 1,
  );
  if (cruzados.length > 0) {
    problemas.push(
      `${cruzados.length} item(ns) de egress com multiplos destinos E multiplas portas, ` +
        'o que libera todos os cruzamentos entre eles',
    );
  }
  return problemas.length === 0 ? true : falha(problemas.join('; '));
}
```

E o do DNS, que existe por causa de uma classe de falha específica:

```javascript
/**
 * DNS interno precisa dos dois protocolos na porta 53.
 *
 * Liberar so um produz falha intermitente: o caminho normal continua funcionando e a
 * falha aparece apenas em parte das consultas, o que a torna caro de diagnosticar.
 */
function dnsComOsDoisProtocolos(output) {
  const { docs, erro } = politicas(output);
  if (erro) return falha(`saida nao parseia como YAML: ${erro}`);
  const dns = docs
    .flatMap((d) => d.spec?.egress || [])
    .find((it) => JSON.stringify(it.to || []).includes('kube-dns'));

  if (!dns) return falha('nenhuma regra de egress para o DNS interno');

  const protos = new Set(
    (dns.ports || []).filter((p) => String(p.port) === '53').map((p) => p.protocol),
  );
  return protos.has('UDP') && protos.has('TCP')
    ? true
    : falha(`DNS na 53 sem os dois protocolos: encontrado ${[...protos].join(', ') || 'nenhum'}`);
}
```

Mais três: `semRegraQueLiberaTudo` (nenhum item de regra vazio, em qualquer direção), `todaRegraComentada` (comentário na linha imediatamente acima de cada `- from:` ou `- to:`) e `saidaEhYamlPuro` (sem cerca de bloco de código, sem prosa antes).

### O assert que NÃO varre chaves

```yaml
      # --- 2. Nao ha regra allow-all ---
      # Assert por STRING EXATA da regra vazia, e nao por presenca de chaves.
      # A distincao importa: `podSelector: {}` e a forma documentada do seletor que
      # cobre todos os pods do namespace, e e exatamente o que a politica de negacao
      # padrao precisa. Procurar chaves reprovaria a forma correta junto com a errada.
      - type: not-contains
        value: '- {}'
```

Este assert aplica direto o achado do Checkpoint 06. `podSelector: {}` é **cobertura**, não permissão: é a forma documentada de dizer "esta política se aplica a todos os pods do namespace", e é o que uma política de negação padrão precisa ter. `ingress: [- {}]` é **permissão total**. As duas usam chaves. Um assert que procurasse chaves reprovaria a forma correta junto com a errada, e o efeito colateral seria pior que o bug: empurraria quem escreve o prompt a estreitar o escopo, que é precisamente o erro que o prompt foi construído para evitar.

### Resultado medido

```
Total Tokens: 6,904
  ✓ 1 passed (50%)
  ✗ 1 failed (50%)
Duration: 18s (concurrency: 1)
```

| Provider | Asserts | Latência | Custo |
|---|---|---|---|
| `gemini-3.5-flash` | **15/15** | 5982ms | US$0,015155 |
| `gpt-4o-mini` | **10/15** | 6517ms | US$0,000596 |

As cinco falhas do `gpt-4o-mini`:

```
X assert#4  yamlValidoComAsDuasDirecoes -> saida nao parseia como YAML: end of the stream or a document separator is expected (1:1)
X assert#6  semRegraQueLiberaTudo       -> saida nao parseia como YAML: end of the stream or a document separator is expected (1:1)
X assert#10 egressPorParDestinoPorta    -> saida nao parseia como YAML: end of the stream or a document separator is expected (1:1)
X assert#11 dnsComOsDoisProtocolos      -> saida nao parseia como YAML: end of the stream or a document separator is expected (1:1)
X assert#13 saidaEhYamlPuro             -> saida veio dentro de cerca de bloco de codigo; o prompt exige YAML puro
```

A saída começou assim:

````text
```yaml
# Conferencia:
# - O escopo da política é amplo, mas não há regras de permissão, portanto, a negação por padrão é mantida.
...
````

O prompt tem uma seção de formato que diz, literalmente, que o primeiro caractere da resposta é o primeiro caractere do YAML e que cerca de bloco de código é proibida. O modelo embrulhou a saída de todo jeito. **A promessa do item de playbook é YAML colável, então a cerca é defeito, não estilo.**

O `gemini-3.5-flash` passou os 15. A saída dele acerta tudo o que o prompt foi engenheirado para garantir: `ports` como irmão de `to` (e não dentro do item de peer), `namespaceSelector` e `podSelector` no mesmo item de peer, DNS com UDP **e** TCP na 53, comentário nomeando origem/destino/propósito em cada regra, premissas declaradas (CNI stateful, label de namespace) e lacunas declaradas onde o mapa não informa porta:

```yaml
    # Origem: Sentinel (sentinel-prod) -> Destino: DNS Interno (kube-system)
    # Proposito: Permitir resolucao de nomes DNS internos do cluster.
    # Protocolo: UDP e TCP (Premissa: resolucao DNS utiliza prioritariamente UDP, mas pode recorrer a TCP para respostas grandes).
    - to:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: kube-system
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
```

---

## Curadoria

### 1. Quatro bugs no meu próprio código de teste

Registro porque cada um deles produz um modo de falha diferente, e três seriam invisíveis num teste que só olha o verde/vermelho final.

**1.1: Assert JS devolvendo string.** A primeira versão do assert de ordenação devolvia a mensagem de erro direto:

```
Custom function threw error: Custom function must return a boolean, number, or
GradingResult object. Got type string: "o pod de ingestao (sem replica saudavel)
deveria vir antes do pod de api"
```

O caso reprovava, mas por motivo errado: o relatório dizia que a função de teste estava quebrada, e não que a política de severidade não foi aplicada. Assert precisa devolver `{ pass, score, reason }`.

**1.2: `require is not defined` em assert inline.** Asserts JS embutidos no YAML são avaliados num contexto sem `require`, então não dá para carregar um parser de YAML. Foi o que forçou o `asserts.js` externo, referenciado como `file://asserts.js:nomeDaFuncao`. O que começou como contorno virou decisão melhor: os asserts semânticos ficam testáveis e documentados isoladamente.

**1.3: Assert que lança exceção aborta a avaliação inteira.** A primeira versão do parser deixava o `yaml.loadAll` lançar. Resultado: `Provider call failed during eval` e a suíte inteira parava. **Erro informa menos que falha**, porque não diz qual requisito não foi cumprido. Daí a função `politicas()` devolver `{ docs, erro }` e nunca lançar.

**1.4: O frontmatter ia para o modelo.** Já descrito acima. Foi o que gerou o `prompt.js`.

### 2. A cerca de bloco de código mascara defeito semântico

Este é o achado que mais muda como eu leio um relatório de suíte.

Das cinco falhas do `gpt-4o-mini`, **quatro dizem a mesma coisa**: `saida nao parseia como YAML`. É uma causa única com quatro sintomas. Só que a mensagem é enganosa, ela sugere que não há informação sobre o conteúdo, quando na verdade o conteúdo tem defeito próprio.

Verifiquei removendo a cerca da saída registrada e rodando os mesmos asserts contra o texto resultante:

```
=== ASSERTS COM A SAIDA SEM A CERCA ===
PASS  yamlValidoComAsDuasDirecoes
PASS  semRegraQueLiberaTudo
FAIL  egressPorParDestinoPorta  -> falta egress para forge na 5432; falta egress para cerebro na 9200
FAIL  dnsComOsDoisProtocolos    -> DNS na 53 sem os dois protocolos: encontrado nenhum
PASS  todaRegraComentada
PASS  saidaEhYamlPuro
```

Sem a cerca, dois asserts continuam reprovando, **por defeito real**. O YAML do `gpt-4o-mini` colocou `ports` **dentro do item de peer**, e não como irmão de `to`:

```yaml
    - to:
        - namespaceSelector:
            matchLabels:
              name: forge-prod
          podSelector:
            matchLabels:
              app: forge
          ports:            # <-- nivel errado: ports nao pertence ao peer
            - port: 5432
              protocol: TCP
```

`NetworkPolicyPeer` não tem campo `ports`. Com validação de campo no servidor, o `kubectl apply` rejeita. Sem ela, o campo é **descartado em silêncio** e a regra passa a liberar o warehouse em **todas as portas**. É uma política de segurança que parece mais restritiva do que é. E o DNS saiu só com UDP.

Duas consequências práticas:

- **A ordem em que os asserts falham não é a ordem de gravidade.** A cerca é trivial de corrigir; o `ports` no nível errado é falha de segurança. O relatório mostra os dois com o mesmo peso, e a cerca aparece primeiro.
- **Rejeitei usar `transform` para remover a cerca antes dos asserts.** Isso deixaria o relatório mais informativo e apagaria um defeito real: o prompt promete YAML colável e a entrega não é colável. A cerca fica como falha.

### 3. O assert de latência mede condição do provedor, não qualidade do prompt

Este limite quase entrou errado na suíte.

Com a concorrência padrão do promptfoo, o mesmo caso de `nota-de-triagem` mediu **21744ms**. Com `maxConcurrency: 1`, o mesmo caso, mesmo prompt, mesmo modelo: **1005ms**. A diferença é fila do lado do provedor, e reprovaria o build por carga de API.

A dispersão é maior que isso. O caso 3 de `triagem-de-pods`, mesmo provider e mesmo config, mediu **989ms** numa execução e **122881ms** em outra. Com concorrência 1 a faixa cai para 1073ms-2051ms nesse mesmo provider, que é utilizável como limite.

Por isso `maxConcurrency: 1` está **no arquivo de teste**, e não na linha de comando: garantia que depende de quem executa não é garantia. Alternativas rejeitadas: subir o limite (anula o assert), aceitar a instabilidade (quebra o Checkpoint 10), remover o assert de latência (latência é requisito real de item de plantão).

### 4. Dois limites que eu mesmo copiei sem medir

`networkpolicy-sentinel` nasceu com `latency: 5000` e `cost: 0.01`, copiados das outras duas suítes antes de existir qualquer medição.

Medido depois em três execuções, o modelo que acerta **100% do conteúdo** entrega em 5319ms, 5945ms e 5982ms, custando US$0,0137, US$0,0152 e US$0,0152. Ou seja: **os limites herdados reprovavam o baseline correto, de forma consistente e não por azar de uma execução.**

Limite que já está vermelho no baseline não detecta regressão nenhuma, só ensina o time a ignorar a suíte. Corrigi com números vindos da medição: `latency: 10000` (cerca de 70% acima do pior tempo medido) e `cost: 0.03` (cerca de 2x o pior custo medido). Folga para variação normal, aperto suficiente para pegar o dobro.

A alternativa considerada foi manter 5000ms e US$0,01 e registrar a reprovação como dívida. Rejeitada porque aqui o artefato novo é a própria suíte: não há execução anterior dela para preservar, e porque dois alarmes falsos permanentes esconderiam os alarmes verdadeiros que a suíte de fato encontrou. Depois da correção, o `gemini-3.5-flash` fica 15/15 e o `gpt-4o-mini` segue vermelho **pelo motivo certo**: a cerca de código.

Este é o único item em que eu mudei um número para o teste passar, e é por isso que ele está registrado com a medição ao lado.

### 5. Três correções no prompt `triagem-de-pods` → v1.0.1

A suíte encontrou três defeitos no prompt. Todos corrigidos, com versão subida para `1.0.1`.

**5.1: O literal `POD(S) PROBLEMATICO(S)` não era declarado como literal.** Na primeira execução o `gpt-4o-mini` emitiu `VEREDITO: 1 POD PROBLEMATICO`: ele "corrigiu" a concordância para o singular. A saída é lida por ferramenta antes de ser lida por pessoa, e concordância corrigida quebra o parse. O prompt passou a declarar o trecho como literal e não ajustável.

**5.2: A contagem de réplicas vazava para a classificação.** A primeira tentativa de reforçar a regra de severidade produziu um efeito colateral: o `gpt-4o-mini` passou a incluir um pod **saudável** no resultado, com `CAUSA_RAIZ: Dados ausentes`:

```text
VEREDITO: 3 POD(S) PROBLEMATICO(S)
...
POD: sentinel-api-7d9c8b6f4-2xk9p
SEVERIDADE: MEDIA
SINTOMA: Running
CAUSA_RAIZ: Dados ausentes
```

A instrução de contar réplicas por serviço foi interpretada como autorização para reavaliar quais pods entram. A correção restringe a contagem explicitamente à **atribuição de severidade**: a seção anterior já decidiu quais pods são problemáticos e esta não altera a lista.

**5.3: A ordenação valia para a análise, não para a saída.** O prompt mandava ordenar por severidade, e o modelo ordenava internamente e emitia na ordem do snapshot. A correção diz que a ordenação vale para a emissão, mesmo quando diferente da ordem da listagem.

Depois das três, o literal do veredito parou de reprovar e o pod fantasma não voltou a aparecer. O caso 2 no `gpt-4o-mini`, que antes oscilava entre 8/11 e 9/11, passou a oscilar entre 9/11 e 10/11: a falha que sobra é a regra de severidade em si, e ela é reprodutível em todas as execuções registradas.

**Onde eu parei, e por quê.** A tentação era continuar ajustando o prompt até o `gpt-4o-mini` passar. Rejeitei: seria **sobreajuste do prompt a um modelo fraco**. A regra de severidade está expressa em linguagem direta, com o critério de decisão explícito; o `gemini-3.5-flash` a executa sem dificuldade. Continuar reescrevendo pioraria o prompt para o modelo bom em troca de fazer o modelo ruim passar num caso.

### 6. O trade-off de modelo, medido

O enunciado pede o trade-off explícito. Ele apareceu nos três níveis de rigor:

| Suíte | `gpt-4o-mini` | `gemini-3.5-flash` |
|---|---|---|
| `nota-de-triagem` (formato) | todos os asserts em todos os 3 casos | idem |
| `triagem-de-pods` (regra derivada) | 9/11 no caso com regra de severidade | 11/11 |
| `networkpolicy-sentinel` (artefato executável) | 10/15 | 15/15 |
| Custo por chamada | US$0,000175, US$0,000596 | US$0,003431, US$0,015155 |

A leitura: **quanto mais o prompt exige do modelo, mais o modelo barato custa em outra moeda.** Em formato simples os dois empatam e o barato ganha por preço. Em regra de negócio derivada o barato já erra. Em artefato executável ele entrega YAML que não cola e política com `ports` no nível errado.

Do outro lado, o modelo que acerta tudo custa de **cerca de 12x a 25x mais** por chamada, dependendo do caso e é o que pressiona o limite de latência, em `networkpolicy-sentinel` ele gasta 5982ms e US$0,0152, o que só cabe porque os limites foram recalibrados com medição.

A recomendação foi registrada no README de `triagem-de-pods`, junto ao prompt, e não neste arquivo: quem for usar o item precisa da informação no ponto de uso.

### 7. Quatro comportamentos de plataforma que quebram pipeline sem ninguém tocar em prompt

Todos encontrados durante a execução desta suíte, e todos relevantes para o Checkpoint 10.

**7.1: Modelo fixado em config tem prazo de validade.** A suíte rodou primeiro em `gemini-2.5-flash`. Durante o próprio desenvolvimento, esse id passou a devolver 404 para projeto novo:

```
404 This model models/gemini-2.5-flash is no longer available to new users.
Please update your code to use models/gemini-3.8-flash
```

O projeto antigo seguia funcionando por antiguidade; um projeto criado depois não. Em pipeline isso é o pior tipo de quebra: **o build falha sem ninguém ter tocado no prompt, e a falha não se parece com falha de qualidade.**

**7.2: O substituto sugerido pelo Google descarta silenciosamente o `temperature`.** O caminho óbvio era migrar para `gemini-3.8-flash`, como a mensagem indica. Rejeitei depois de ler o código do promptfoo 0.123.1. A função `removeDeprecatedGeminiGenerationParams` apaga `temperature`, `topP` e `topK` do corpo da requisição para essa família de modelos, e o provider monta o corpo assim:

```javascript
generationConfig: {
  ...config.temperature !== void 0 && { temperature: config.temperature },
  ...
}
body.generationConfig = removeDeprecatedGeminiGenerationParams(this.modelName, body.generationConfig);
```

Declarar `temperature: 0` seria **aceito pelo schema do config e descartado antes do envio**. O arquivo de teste ficaria afirmando um controle que não existe, o que é pior que não ter o controle.

**7.3, E recusa desligar o raciocínio.** O mesmo modelo rejeita `thinkingBudget` e aceita só `thinkingLevel`, com mínimo `LOW`:

```
Error: gemini-3.8-flash does not support thinkingBudget. Use thinkingLevel (LOW, MEDIUM, or HIGH).
```

Não há como zerar o raciocínio, então o orçamento de latência passaria a incluir tokens de raciocínio obrigatórios.

Por isso a escolha final foi **`gemini-3.5-flash`**, que fica fora daquela lista: preserva temperatura e aceita `thinkingBudget: 0`. Os dois controles de que a suíte precisa continuam existindo. A justificativa está escrita no config, não só aqui.

**7.4: A camada de teste mascara o erro do provedor.** Três execuções falharam com:

```
Error: No candidates returned in API response.
Got response: {"error":{"code":503,"message":"This model is currently experiencing high demand..."}}
```

O promptfoo reporta como "sem candidatos na resposta", quando é um **503 de capacidade**: transitório, e que deveria ser tentado de novo, não tratado como falha de conteúdo. O mesmo prompt passou na execução seguinte sem alteração alguma. Num gate de CI isso é reprovação falsa, e a mensagem não ajuda a diagnosticar.

### 8. A cota do provedor virou o fator que mais travou a execução, e não era limite técnico

Boa parte do tempo desta suíte foi gasta com a API do Google recusando chamadas. Registro o diagnóstico completo porque o erro apontava para o lugar errado, e porque a conclusão mudou no meio do caminho.

O sintoma era `429 RESOURCE_EXHAUSTED`, e a mensagem de erro dava a cota exata:

```
quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
metric : generativelanguage.googleapis.com/generate_content_free_tier_requests
value  : 20 {'model': 'gemini-3.5-flash', 'location': 'global'}
```

**20 requisições por dia, por projeto, por modelo.** As três suítes juntas consomem 7 chamadas no provider Google por execução completa, então isso dava menos de três execuções por dia, e a cota é compartilhada com qualquer desenvolvimento local no mesmo projeto.

Chequei em dois projetos diferentes e os dois respondiam `-FreeTier`, mesmo depois de a conta ter faturamento. Minha leitura na hora foi que habilitar faturamento na conta não migra o projeto da chave, e que o pipeline do Checkpoint 10 teria que caber em 20 chamadas diárias.

**Essa leitura estava errada, e o registro fica porque o erro é instrutivo.** A causa era uma pendência de faturamento não resolvida. Depois de regularizada, medi de novo: 10 chamadas consecutivas no mesmo modelo, todas `200`, com o consumo do dia já bem acima de 20. O projeto saiu do free tier e o teto diário deixou de existir.

O que sobrevive da investigação, e que vale para o Checkpoint 10:

- **A cota não é limite técnico, é estado de conta.** Nada no repositório muda quando ela estoura, e nada no repositório conserta. Isso torna a classe de falha especialmente ruim num gate de CI: a suíte fica vermelha, o diff está correto, e a correção é em outro sistema.
- **Um pipeline que só funciona no projeto certo não é um pipeline confiável.** Fork do repositório, contribuidor novo ou rotação de chave para outro projeto reproduzem o 429 sem nenhuma alteração de prompt. O gate precisa distinguir "reprovou o teste" de "não conseguiu executar o teste", e a mensagem do promptfoo não faz essa distinção sozinha (ver item 7.4).
- **O limite era por modelo**, então trocar de modelo renovava a cota. Usei isso como contorno para conseguir medir, e não serve como desenho: CI que troca de modelo para não bater na cota deixa de testar o que está em produção.

Com tier pago, o Checkpoint 10 pode rodar a suíte completa. A decisão de gate seletivo: rodar só o prompt alterado, passa a ser sobre tempo de feedback e custo por pull request, não sobre teto de requisições.

### 9. Divergência entre o prompt e a própria suíte

Achado que só apareceu porque escrevi as duas coisas.

O prompt de `networkpolicy-sentinel` proíbe chaves em **qualquer lugar** da saída, inclusive em comentário, e justifica dizendo que um teste automatizado procura essa sequência. O teste que eu escrevi depois é mais estreito: procura a string exata `- {}`, pela razão da seção do assert acima, `podSelector: {}` é forma legítima e documentada.

Ou seja: **o prompt está mais restrito do que o teste que existe.** A proibição total empurra o modelo para longe do idioma documentado do Kubernetes. Deu para ver no efeito: o `gemini-3.5-flash` produziu `podSelector:` com `matchLabels:` sem valor em vez de `podSelector: {}`. Funciona, um seletor de label sem `matchLabels` e sem `matchExpressions` casa todos os pods, mas é forma menos idiomática, escolhida para atender uma regra do prompt que o teste não exige mais.

Vira pendência v1.0.1 de `networkpolicy-sentinel`, documentada e não aplicada, pela mesma razão dos checkpoints anteriores: alterar o prompt agora invalidaria as execuções registradas acima.

### 10. Três cópias idênticas do `prompt.js`

Os três `prompt.js` têm o mesmo hash (`062d29bd259ac191115548523146b7c9`). É duplicação consciente.

Um carregador compartilhado precisaria saber qual `prompt.md` ler, e o promptfoo resolve `file://prompt.js` relativo ao diretório do config, o que faz `__dirname` apontar para a pasta do prompt, que é exatamente o mecanismo usado para achar o `prompt.md` correto. Um módulo único em `scripts/` perderia essa referência e precisaria receber o caminho por configuração, movendo informação do código para o YAML.

Mantive a duplicação nesta rodada e registro a decisão como ponto a revisitar no Checkpoint 10, quando os nove prompts tiverem suíte e a duplicação passar de três para nove cópias. Aí o custo muda de lado.

---

## Estado final da suíte

| Suíte | Casos × providers | Passa | Falha | Motivo das falhas |
|---|---|---|---|---|
| `nota-de-triagem` | 6 | 6 | 0 | n/d |
| `triagem-de-pods` | 6 | 5 | 1 | `gpt-4o-mini` não aplica a regra de severidade |
| `networkpolicy-sentinel` | 2 | 1 | 1 | `gpt-4o-mini` embrulha a saída em cerca de código |

**12 de 14 combinações passam. As duas falhas são defeitos reais e reproduzíveis**, confirmados em execuções independentes, e estão registradas como tal: não foram contornadas por ajuste de assert.

Uma suíte que passasse 14 de 14 na primeira tentativa diria que os asserts são frouxos. Estes encontraram, no total: uma política de rede que não cola e libera portas demais, uma triagem que esconde o pior caso no fim da lista, um prompt que perdia a concordância do veredito, um prompt que inventava pod problemático, quatro erros no meu código de teste e dois limites que eu havia copiado sem medir.

---

## Pendências registradas (v1.0.1, documentadas e não aplicadas)

- **`networkpolicy-sentinel`**: a proibição total de chaves na saída ficou mais restrita que o teste que existe, e empurra o modelo para longe de `podSelector: {}`. Relaxar para proibir apenas o item de regra vazio.
- **`triagem-de-pods`**: a regra da tag `[AVISO DE IMPACTO]` enumera exemplos de ação destrutiva e reverter imagem de deployment não está entre eles, pendência herdada do Checkpoint 01, ainda aberta.
- **Suíte**: `egressPorParDestinoPorta` reporta "falta egress para forge na 5432" quando a porta existe no nível errado do YAML. A mensagem subdescreve o defeito. Distinguir "ausente" de "presente no nível errado".
- **Repositório**: as três cópias de `prompt.js` viram nove quando a cobertura completar. Revisitar no Checkpoint 10.
