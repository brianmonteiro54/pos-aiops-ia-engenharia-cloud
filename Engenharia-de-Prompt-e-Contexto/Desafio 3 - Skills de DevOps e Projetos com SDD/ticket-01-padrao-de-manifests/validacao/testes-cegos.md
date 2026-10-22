# Validação da skill — três testes cegos

Escrever a skill e declarar que funciona não é evidência. O método foi despachar
sub-agentes que **só podiam usar a skill**, contra manifestos que não existiam quando os
fluxos manuais foram feitos.

## Protocolo

Cada sub-agente recebeu:

- **fonte única**: `.kiro/skills/padrao-de-manifests-metacortex/`, incluindo os
  `references/` que o `SKILL.md` indicasse
- **proibição explícita** de ler `fluxo-01-conferencia-manual.md`, qualquer coisa em
  `manifests-gerados/`, as sondas e os `.json` do laboratório — ou seja, o gabarito
- um manifesto novo
- perguntas dirigidas às armadilhas que eu queria testar
- instrução final de reportar **atrito**: onde a skill foi ambígua, incompleta ou
  contraditória, com a ressalva de não inventar atrito para parecer útil

O atrito era o objetivo. Veredito certo prova pouco; onde o executor hesitou mostra o
defeito.

## Os manifestos

### `teste-cego-01-vega-stg.yaml`

Cliente `vega`, ambiente **stg**, workload Redis de terceiro. Quatro armadilhas:

| Armadilha | O que testa |
|---|---|
| `replicas: 1` e `strategy` com `maxUnavailable: 1` em **stg** | 2.3/2.4 só valem em prod — reportar aqui é erro |
| `runAsNonRoot`/`runAsUser` no **pod**, os outros três no container | a 3.2 está cumprida, e o Trivy acusa KSV020/KSV021 |
| `mysql://vega:T0rr3-f0rt3@…` em `ConfigMap.data` | a 3.3, que o Trivy não pega |
| `instance: vega-staging` no Service x `vega-stg` no pod | a 1.4, um caractere de diferença |

Mais dois achados reais: ConfigMap sem os quatro rótulos (1.3) e sem dono (1.5), e imagem
`docker.io/redis:7-alpine` (3.7).

### `teste-cego-02-atlas-prod.yaml`

Cliente `atlas`, ambiente **prod**. Testa o oposto do primeiro:

| Armadilha | O que testa |
|---|---|
| `allowPrivilegeEscalation`, `readOnlyRootFilesystem` e `capabilities` no **pod** | a violação silenciosa da 3.2 — campos que não existem naquele nível |
| readiness **e** liveness em `httpGet /healthz` | a 2.2, exatamente o cenário que o padrão adverte |
| `replicas: 3` com `maxUnavailable: 1` | 2.3 passa, 2.4 barra |
| `terminationGracePeriodSeconds: 45` sem corpo de PR | a 2.6 e o veredito "pendente" |
| `runAsUser: 10002` no pod, acima de 10000 | KSV020 dispara, e é falso positivo |

## Resultados

| Teste | Manifesto | Vereditos | Atritos | Defeitos reais |
|---|---|---|---|---|
| 1 | `vega-stg` | corretos | 5 | 5 |
| 2 | `vega-stg`, após as correções do teste 1 | corretos | 6 | 4 |
| 3 | `atlas-prod` | corretos | 5 | 4 |

Os três chegaram aos vereditos certos, inclusive nos casos em que o certo é **não**
reportar: nenhum dos três cobrou `replicas >= 2` em `stg`, e os três identificaram
`KSV020` como falso positivo em vez de pedir correção do UID.

## Os treze defeitos encontrados, e o que mudou

### Teste 1

| # | Defeito | Correção |
|---|---|---|
| 1 | **A 3.2 não tinha juiz.** O script delegava ao Trivy, que não modela herança nem o bloco inteiro. E os dois references se contradiziam sobre o nível dos campos | `regra_3_2_security_context` + tabela campo por campo em `padrao-completo.md` |
| 2 | **A 1.4 não dizia se é igualdade ou subconjunto.** O script comparava por subconjunto, a reference dizia "igualdade" | reference explicitou subconjunto, como o Kubernetes faz |
| 3 | **Regra `recomendado` e "não conferível" ao mesmo tempo não tinha bloco** no relatório | passo 4 passou a definir o bloco do "pendente" |
| 4 | **O passo 3 pressupunha aplicação própria.** Com imagem de terceiro não há repositório, e a 3.7 torna esse caso comum | seção "quando o workload é imagem de terceiro" |
| 5 | **O passo 1 se contradizia em quinze linhas**: "rode sempre antes" e "não precisa repetir" | reescrito: rode uma vez para conhecer a fronteira, e volte quando alguém contestar |

Um achado de bônus: o script **engolia em silêncio** qualquer `KSV` que não estivesse nos
seus mapas. Foi assim que o `AVD-KSV-01010` passou despercebido. Virou o terceiro balde,
`TRIVY APONTOU E O MAPA NÃO CONHECE`.

### Teste 2

| # | Defeito | Correção |
|---|---|---|
| 6 | **`AVD-KSV-01010` estava sob o cabeçalho "FORA DO PADRÃO DA CASA"**, afirmação falsa sobre a 3.3, que é `proibido`. Quem lesse o cabeçalho concluiria o oposto do padrão | novo mapa `TRIVY_CORROBORA`, com cabeçalho que diz "a casa adota estas regras" |
| 7 | **A presença das probes é parsing e estava fora do script** | `regra_2_2_probes`: presença (barra) + probes idênticas (recomendado) |
| 8 | **O escopo da 1.5 era inconsistente** com a própria justificativa do runbook | reference separou owner (todo objeto) de runbook (não exigido) |
| 9 | **O `compatibility` contradizia o corpo**: dizia que sem Trivy a 3.2 não é conferida, quando é o script que a julga | frontmatter corrigido |

Mais um: a skill não dizia se `tcpSocket` serve para **liveness** de componente de
prateleira. Passou a dizer, com a troca explícita.

### Teste 3

| # | Defeito | Correção |
|---|---|---|
| 10 | **"Declarados no pod são silenciosamente ignorados" estava factualmente errado** | medido contra o apiserver; ver abaixo |
| 11 | **`maxUnavailable: "0%"` era marcado como violação.** A comparação era com `(0, "0")` e o campo aceita percentual | função `e_zero`, que normaliza inteiro e percentual |
| 12 | **`maxSurge` não era conferido de forma alguma**, embora a regra 2.4 o inclua | conferido, com o caso `maxSurge: 0` + `maxUnavailable: 0` que **trava o rollout** |
| 13 | **`KSV021` cobra GID, e a 3.2 não tem requisito de `runAsGroup`.** Eu havia movido `KSV020` e `KSV021` juntos | `KSV021` voltou para `TRIVY_FORA_DO_PADRAO` |

### O defeito 10 em detalhe

Eu havia escrito que declarar os três campos no nível do pod "não dá erro, e o Kubernetes
simplesmente ignora". O sub-agente contestou dizendo que com validação estrita de campos o
apiserver tende a recusar, e que não podia testar porque a skill proíbe usar estado de
cluster como fonte.

Testei. Contra apiserver v1.31.5 com kubectl v1.33:

| Caminho do apply | Resultado |
|---|---|
| `kubectl apply` (strict, é o default) | **recusa**: `strict decoding error: unknown field "spec.template.spec.securityContext.allowPrivilegeEscalation"` |
| `kubectl apply --server-side` | **recusa**: `field not declared in schema` |
| `kubectl apply --validate=false` ou `--validate=ignore` | **aceita e descarta em silêncio** |

E confirmei o efeito do terceiro caso: depois do apply permissivo, o `securityContext`
armazenado do pod guardou só `fsGroup`, `runAsGroup`, `runAsNonRoot`, `runAsUser` e
`seccompProfile`, e **o container ficou sem `securityContext` nenhum**.

As duas metades são verdadeiras, dependendo do caminho. O veredito não muda — barra nos
três — mas a consequência que o relatório descreve muda de "sobe inseguro em silêncio"
para "nem passa do apply", e são conversas diferentes com o autor do PR.

## O atrito que não era defeito

O teste 3 observou que a regra 2.4 **premia a opção pior**: `maxUnavailable: 1` com 3
réplicas mantém 2 pods servindo e **barra**, enquanto `Recreate` — que derruba a
capacidade inteira — só exige justificativa. Pelo motivo declarado da própria regra,
`Recreate` é estritamente pior, e o caminho mais fácil para o autor sair do bloqueio
piora a disponibilidade real.

Isso é tensão no padrão da casa, não na skill, e não está no meu alcance mudar. Ficou
documentado em `padrao-completo.md` como nota ao revisor, com a instrução de tratar a
justificativa de `Recreate` com rigor.

## Regressão depois de todas as correções

| Alvo | rc | Barra | Recomendado |
|---|---|---|---|
| `manifests/nyx-api-barrado.yaml` | 1 | **20** | 3 |
| `manifests/fake-shop/` (orion-prod) | 1 | 2 | 2 |
| `manifests/kube-news/` (nyx-dev) | 1 | 1 | 1 |
| `validacao/teste-cego-01-vega-stg.yaml` | 1 | 4 | 1 |
| `validacao/teste-cego-02-atlas-prod.yaml` | 1 | 4 | 2 |

O manifesto barrado foi de 19 para 20 porque a 2.2 passou a ser conferida. Os achados que
sobram nos manifests gerados são os dois desvios documentados do Postgres — `replicas: 1`
em prod e `runAsUser: 70` — que continuam barrando porque desvio documentado não é exceção
aprovada.

Saídas completas em `../evidencias/relatorios/`.

## Reproduzir

```bash
S=../../../../.kiro/skills/padrao-de-manifests-metacortex/scripts/conferir_manifesto.py
python3 "$S" ../manifests/nyx-api-barrado.yaml
python3 "$S" ../manifests/fake-shop/
python3 "$S" ../manifests/kube-news/
python3 "$S" teste-cego-01-vega-stg.yaml
python3 "$S" teste-cego-02-atlas-prod.yaml
```
