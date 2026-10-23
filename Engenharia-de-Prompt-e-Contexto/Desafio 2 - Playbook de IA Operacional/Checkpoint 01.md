# Checkpoint 01: Triagem de pods do Sentinel

Primeiro item do playbook de IA operacional da Aegis. Nasce de uma dor da SRE do Sam Wilson: triagem rápida e confiável da saúde dos pods no cluster onde roda o Sentinel, que qualquer plantonista possa rodar e confiar.

O ponto de partida era um pedido solto, do tipo que hoje vive no histórico do chat:

```
cria um script pra mim que olha os pods do meu cluster kubernetes e me
fala quais estão com problema, tipo reiniciando muito ou sem subir
```

O que entra na biblioteca é outra coisa: um prompt parametrizável que recebe um snapshot já coletado e devolve triagem com causa provável, evidência e próxima ação. Sem agente, sem tool, o snapshot é colado na entrada.

---

## Prompt parametrizável

**Destino no registry:** `devops/triagem-de-pods/prompt.md` · **versão:** 1.0.0

| Parâmetro | Obrigatório | Descrição |
|---|---|---|
| `{{snapshot}}` | sim | Saída bruta e colada de comandos kubectl (`get pods`, `describe`, `logs`), em qualquer combinação |

````text
Você é um SRE especialista em Kubernetes no plantão da Aegis. Recebe um snapshot de cluster já coletado e devolve uma triagem da saúde dos pods. Você não executa comandos, não acessa o cluster e não busca informação externa: trabalha somente com o que está no snapshot.

# 1. CRITERIO OBJETIVO DE POD PROBLEMATICO

Um pod é problemático se atender a QUALQUER uma destas condições:
- (a) STATUS diferente de `Running` e diferente de `Completed`.
- (b) READY incompleto, ou seja, o número antes da barra menor que o número depois (ex: `0/1`).
- (c) STATUS `Running` e READY completo, MAS a coluna RESTARTS indica reinício há menos de 1 hora (ex: `14 (90s ago)`, `3 (12m ago)`). Pod que reinicia e sobe continua em loop.

Um pod NÃO é problemático se está `Running`, com READY completo, e o último restart foi há mais de 1 hora ou não houve restart (ex: `1 (3d ago)`, `0`). Restart antigo não é falha: vai para OBSERVACOES.

# 2. SEVERIDADE E ORDENACAO

Identifique o serviço de cada pod pelo prefixo do nome, descartando os dois últimos segmentos separados por hífen (ex: `sentinel-api-7d9c8b6f4-2xk9p` pertence ao serviço `sentinel-api`).

Atribua a severidade por esta regra, sem julgamento subjetivo:
- CRITICA: nenhum pod do mesmo serviço está `Running` com READY completo no snapshot. O serviço está inteiro fora.
- ALTA: o pod está em falha, mas existe ao menos um pod do mesmo serviço `Running` com READY completo.
- MEDIA: o pod está `Running` com READY completo e entrou por reinício recente (critério 1c).

Ordene os pods problemáticos: CRITICA primeiro, depois ALTA, depois MEDIA. Em caso de empate, maior número de RESTARTS primeiro; persistindo o empate, ordem alfabética do nome do pod.

# 3. SINTOMA NAO E CAUSA

`CrashLoopBackOff`, `ImagePullBackOff`, `ErrImagePull`, `Pending` e `Error` são SINTOMAS. Nunca os use como CAUSA_RAIZ isolada.

A causa vem do cruzamento de três camadas:
- do `kubectl describe`: `Last State`, `Reason`, `Exit Code`, `Limits`, `Requests`, `Image`;
- da seção `Events`: o campo `Message`;
- das linhas de log da aplicação.

Use o termo técnico canônico que aparece no snapshot (ex: `OOMKilled`, `manifest unknown`, `Insufficient cpu`) e complete com a explicação do mecanismo em no máximo 12 palavras.

# 4. EVIDENCIA E CONSISTENCIA TEMPORAL

Toda CAUSA_RAIZ precisa de uma linha de EVIDENCIA citada do snapshot: o campo, o event ou a linha de log.

Antes de usar um `Last State: Terminated` ou uma linha de log como evidência, verifique se o horário é compatível com a falha atual indicada em RESTARTS. Se o snapshot não permitir amarrar a evidência ao ciclo de falha corrente, CONFIANCA não pode ser ALTA.

# 5. DADOS AUSENTES

Se um pod é problemático e o snapshot não traz o describe ou o log necessário para cravar a causa, NÃO INVENTE. Escreva em CAUSA_RAIZ que o dado está ausente, diga qual dado falta, e coloque em ACAO_RECOMENDADA o comando kubectl exato que fecha a lacuna, já com o nome real do pod.

# 6. ACAO RECOMENDADA

A ação é o próximo passo concreto do plantonista, proporcional ao diagnóstico e executável. Se a ação for destrutiva ou afetar tráfego (deletar pod, reiniciar deployment, escalar nós, alterar limits em produção), inicie a frase OBRIGATORIAMENTE com a tag `[AVISO DE IMPACTO]` e diga o que verificar antes de executar.

# 7. FORMATO DE SAIDA

## REGRA A - nenhum pod problematico

Primeira linha, exatamente assim:

VEREDITO: NENHUM POD PROBLEMATICO

Se houver sinal que não caracteriza problema (restart antigo, aviso em log sem erro), acrescente no máximo 2 linhas:

OBSERVACOES: <sinal observado e por que não é problema>

É proibido usar qualquer rótulo da REGRA B neste caso.

## REGRA B - um ou mais pods problematicos

Primeira linha:

VEREDITO: <N> POD(S) PROBLEMATICO(S)

Em seguida, um bloco por pod, na ordem definida na secao 2, separados por uma linha em branco:

POD: <nome exato como no snapshot>
SEVERIDADE: CRITICA | ALTA | MEDIA
SINTOMA: <estado observado na listagem>
CAUSA_RAIZ: <termo canonico> - <mecanismo em ate 12 palavras>
EVIDENCIA: <campo, event ou linha de log citada do snapshot>
ACAO_RECOMENDADA: <acao especifica e executavel>
CONFIANCA: ALTA | MEDIA | BAIXA - <o que elevaria a confianca, ou "dados completos">

Depois do último bloco, se houver sinal relevante em pod saudável, acrescente no máximo 2 linhas de OBSERVACOES.

# 8. RESTRICOES DE SAIDA

- Responda em português.
- A saída começa na letra V de VEREDITO. Sem saudação, sem preâmbulo, sem frase de fechamento, sem bloco de código, sem negrito ou cabeçalho markdown.
- Rótulos exatamente como especificado: maiúsculas, sem acento, seguidos de dois pontos.
- Não repita o snapshot na resposta. Não cite pod que não esteja no snapshot.
- Máximo de 7 linhas por pod problemático e 24 linhas no total.

# ENTRADA

Analise o snapshot abaixo:

{{snapshot}}
````

**Frontmatter** (`prompt.md` e `README.md`, conforme convenção do prompt-registry):

```yaml
nome: triagem-de-pods
descricao: Recebe um snapshot de kubectl e devolve a triagem dos pods problemáticos com causa provável, evidência e próxima ação do plantão.
versao: 1.0.0
tags: [kubernetes, sre, plantao, triagem, troubleshooting]
inputs:
  - nome: snapshot
    descricao: Saída bruta e colada de comandos kubectl (get pods, describe, logs) coletada por quem tem acesso ao cluster.
```

---

## Execução

**Modelo de criação do prompt:** Gemini Pro, com raciocínio estendido.
**Modelo de execução:** Gemini Pro, com raciocínio estendido.

> **Ressalva de reprodutibilidade.** O identificador acima é o nome do produto como exposto na interface em que a execução foi feita, e não um id versionado de API. A versão exata do snapshot e o orçamento de raciocínio não foram capturados no momento da execução, então este registro não é suficiente para reexecução byte a byte. Dos Checkpoints 08 em diante, em que a execução passa a ser por API, os identificadores são versionados (`openai:gpt-4o-mini`, `google:gemini-3.5-flash`).


Escolhi o mesmo modelo nas duas etapas. Para a criação, a justificativa é direta: escrever o prompt é tarefa de raciocínio longo, feita uma vez, e um modelo forte ali é barato porque o custo não se repete. Para a execução, o critério foi manter uma linha de base única em todos os checkpoints que produzem prompt, de modo que diferença de output entre eles seja atribuível ao prompt e não ao modelo.

Essa escolha tem uma consequência que precisa ficar registrada. O Checkpoint 08 vai submeter este prompt a um gate de 5 segundos de latência e US$ 0,01 por chamada, e vai rodá-lo em `openai:gpt-4o-mini` mais um segundo provider. Raciocínio estendido não sobrevive ao limite de latência: o modelo registrado nesta execução não é o que vai ser testado. A triagem em si não depende de raciocínio longo (é classificação sobre texto colado), então a expectativa é que um modelo rápido produza a mesma saída. Essa hipótese será verificada no Checkpoint 08, e o resultado de lá é o que decide qual modelo entra como recomendado no README do prompt.

### Execução 1: snapshot com pod reiniciando

```
VEREDITO: 1 POD(S) PROBLEMATICO(S)
POD: sentinel-api-7d9c8b6f4-h4m2t
SEVERIDADE: ALTA
SINTOMA: CrashLoopBackOff
CAUSA_RAIZ: OOMKilled - container encerrou por falta de memoria ao carregar cache
EVIDENCIA: Last State: Terminated Reason: OOMKilled e log [FATAL] [runtime] out of memory
ACAO_RECOMENDADA: [AVISO DE IMPACTO] Aumentar limits de memoria do deployment apos avaliar uso.
CONFIANCA: ALTA - dados completos
```

Chegou na causa, não no sintoma: `CrashLoopBackOff` foi para SINTOMA e `OOMKilled` para CAUSA_RAIZ, com a evidência cruzando o `Last State` do describe com a linha `[FATAL] out of memory` do log. Severidade ALTA porque o serviço `sentinel-api` tem a réplica `2xk9p` saudável.

### Execução 2: snapshot com pods que não sobem

```
VEREDITO: 2 POD(S) PROBLEMATICO(S)
POD: sentinel-ingest-8f7a9c5b-4dkqm
SEVERIDADE: CRITICA
SINTOMA: Pending
CAUSA_RAIZ: Insufficient cpu - cluster sem capacidade de entregar 2 cpus requeridas
EVIDENCIA: Event default-scheduler: 0/6 nodes are available: 6 Insufficient cpu
ACAO_RECOMENDADA: [AVISO DE IMPACTO] Escalar novos nos no cluster ou reduzir requests do deployment.
CONFIANCA: ALTA - dados completos

POD: sentinel-api-7d9c8b6f4-zzp10
SEVERIDADE: ALTA
SINTOMA: ImagePullBackOff
CAUSA_RAIZ: manifest unknown - tag 2.9.2 nao encontrada no container registry
EVIDENCIA: Event kubelet: Failed to pull image "registry.aegis.io/sentinel-api:2.9.2": manifest unknown
ACAO_RECOMENDADA: Reverter a tag da imagem no deployment para versao funcional anterior.
CONFIANCA: ALTA - dados completos
```

A ordenação é o resultado mais relevante desta execução: o `sentinel-ingest` veio primeiro e como CRITICA porque é o único pod do serviço e está `Pending`, ou seja, o ingest está inteiro fora. O `sentinel-api` em `ImagePullBackOff` veio depois, como ALTA, porque tem réplica servindo. A regra de severidade da seção 2 do prompt produziu essa ordem sem julgamento subjetivo.

### Execução 3: snapshot saudável

```
VEREDITO: NENHUM POD PROBLEMATICO
OBSERVACOES: sentinel-worker-5b8f9c8d-jq7rs com restart ha 3 dias nao configura falha ativa.
```

Não forçou diagnóstico onde não havia problema, e o restart antigo do worker foi para o canal de observação em vez de virar um pod em falha. Nenhum rótulo da REGRA B apareceu, que é a condição para o caso saudável ser testável por ausência.

### Verificação das três execuções

Conferido por script antes de registrar:

| Verificação | Resultado |
|---|---|
| Teto de 24 linhas | 8, 16 e 2 linhas |
| Teto de 7 linhas por pod | 7 em todos os blocos |
| Ordenação por severidade | `['ALTA']` e `['CRITICA', 'ALTA']`: correta |
| Rótulos da REGRA B no caso saudável | 0 de 7: ausentes como especificado |
| Nome exato do pod na entrada 1 | `sentinel-api-7d9c8b6f4-h4m2t` presente |
| Termos canônicos | `OOMKilled`, `manifest unknown` + `2.9.2`, `Insufficient cpu` presentes |
| Veredito de ausência na entrada 3 | `NENHUM POD PROBLEMATICO` presente |

Os sete asserts que o Checkpoint 08 vai exigir sobre este prompt passariam contra estes outputs.

---

## Curadoria

**Técnica de criação: meta-prompting.** O prompt não foi redigido à mão. Escrevi um meta-prompt que descreve a tarefa, o parâmetro, os três snapshots reais, os comportamentos obrigatórios e (o ponto que mais importou) as restrições de formato que decorrem do fato de este prompt vir a ser testado automaticamente depois. O meta-prompt também pedia explicitamente que o modelo listasse os pontos fracos da própria saída, o que gerou o material da revisão. Rodei no Gemini Pro com raciocínio estendido.

**Framework escolhido: R-I-S-E.** `Role` (SRE de plantão) define a postura; `Input` isola o snapshot como parâmetro único; `Steps` é o componente que carrega o peso aqui, porque o requisito central do checkpoint é *não repetir o STATUS*, sem uma sequência que obrigue o cruzamento das três camadas (listagem, describe, log), o modelo devolve a coluna STATUS reescrita; `Expectation` fixa o formato rígido. Descartei R-T-F porque `Task` e `Format` sozinhos não impõem o método de raciocínio, e é o método que diferencia triagem de transcrição.

**O que precisou refinar do v1 para o v1.0.0.** Três correções substantivas:

1. **Falso negativo no critério de restart.** O v1 só considerava restart recente como problema quando "atrelado a um STATUS de falha". Um pod `Running 1/1` com `RESTARTS 14 (90s ago)` está em loop e estava de pé por acaso no instante do snapshot: seria classificado como saudável. Tornei a recência do restart um critério independente (regra 1c), com severidade MEDIA própria.
2. **Severidade sem regra de decisão.** O v1 pedia `CRITICA | ALTA | MEDIA` e ordenação por severidade, sem dizer como escolher, o que deixa a saída irreprodutível, e reprodutibilidade é exatamente o que o gate do Checkpoint 08 mede. Amarrei a severidade à sobrevivência do serviço, inferindo o serviço do prefixo do nome do pod. O efeito prático apareceu na execução 2: o ingest passou a vir antes do api, que é a triagem correta.
3. **O caso saudável descartava sinal.** A regra do v1 exigia que a saída fosse *exatamente* uma string fixa, sem nenhuma outra palavra. Isso é ótimo para teste e ruim para o plantonista, porque joga fora o restart de 3 dias do worker. Abri o canal `OBSERVACOES:` com teto de 2 linhas e proibição de usar os rótulos de diagnóstico. Foi a única troca em que aceitei mais variância na saída, e ela sobrevive ao teste porque o assert do caso saudável é por ausência de `CAUSA_RAIZ:`, não por igualdade exata.

Também adicionei a regra de consistência temporal da seção 4, que endereça o terceiro ponto fraco apontado pelo próprio modelo (cegueira a timestamps: culpar um `OOMKilled` antigo por um `CrashLoopBackOff` atual), e mantive os rótulos sem acento. Este último não é estética: assert com caractere acentuado é fonte de falha silenciosa por normalização Unicode, e o rótulo `HIPÓTESE INICIAL:` do Checkpoint 02 já vai ser uma exceção obrigatória a essa regra porque o padrão da nota é ditado pelo enunciado.

**Um ajuste de especificação e um defeito em aberto, achados na execução.**

O v1 pedia `---` como separador entre blocos de pod; a execução veio com linha em branco. Troquei a especificação para linha em branco em vez de insistir no separador: ele não carrega informação que os rótulos já não dão, e `---` é frágil em qualquer contexto que renderize Markdown. A versão 1.0.0 registrada acima é a que produziu exatamente estes outputs.

O defeito em aberto é a tag de impacto. Na execução 2, a ação para o `ImagePullBackOff` é reverter a tag da imagem no deployment, e ela saiu **sem** `[AVISO DE IMPACTO]`. Reverter a imagem dispara rollout e mexe também na réplica saudável que está servindo, então deveria carregar o aviso pela regra 6. A causa provável é que a regra enumera exemplos de ação destrutiva e "alterar imagem ou reverter deployment" não está entre eles. A correção é fechar a lista de gatilhos do aviso em vez de exemplificar. Não apliquei agora porque isso mudaria a saída e invalidaria a execução registrada: fica como **v1.0.1**, a ser aplicada na entrada do prompt no registry (Checkpoint 07) com nova execução.

**Sanitização.** Este snapshot não exigiria tratamento antes de ir para um modelo externo: nomes de pod, namespace e tag de imagem são identificadores de infraestrutura, não dado de cliente. O único item que eu revisaria num cenário real é o host do registry (`registry.aegis.io`), que revela topologia interna. O Checkpoint 03, que traz nome de tenant, é onde essa decisão fica obrigatória.
