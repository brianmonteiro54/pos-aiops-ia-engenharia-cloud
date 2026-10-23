# ADR-005: O recorte da primeira fatia

**Status:** aceito
**Contexto:** o ticket pede explicitamente que a primeira fatia seja recortada, e deixa a
escolha aberta. O PRD define o mínimo (RF-02), a distinção entre saber e inferir (RF-03) e
os três cenários de falha de ambiente (RF-04). A pergunta é **o que entra primeiro**, não o
que existe no papel.

## Decisão

**Entra o mínimo do RF-02 inteiro, o RF-03, e os três cenários do RF-04. Nada além.**

A parte que custa ser dita: **os três cenários de falha entram na primeira fatia, no mesmo
nível dos dados.** Não são acabamento. Uma tela que mostra página em branco quando a
credencial expirou é **pior que não ter tela**, porque quem está de plantão gasta os
primeiros minutos (os que a aplicação prometeu encurtar) se perguntando se o cluster caiu
ou se o painel está quebrado.

## Alternativas consideradas

### A: fatia em profundidade: um namespace, retrato completo

Um namespace por vez, escolhido na subida, com tudo que o RF-02 pede mais o que der.

**O que se ganha:** é o caminho mais curto até algo útil. Numa triagem você já sabe o
namespace: o chamado vem com ele. E a consulta cai de 6 `LIST` de cluster para 6 `LIST` de
namespace, que é mais barato e precisa de menos permissão.

**O que se perde:**

- **mata o item mais útil do RF-02**, que é a lista de namespaces com a contagem do que está
  quebrado em cada um. Esse é o único item da tela que responde uma pergunta que o terminal
  responde mal: "onde está o problema". Os outros cinco só condensam o que `kubectl get` já
  diz
- o chamado nem sempre vem com o namespace certo. Dos três chamados do Ticket 02, o do
  `nyx-stg` chegou como "a API não responde": descobrir **qual** `nyx` era parte do
  trabalho
- obriga reiniciar a aplicação para trocar de namespace, o que é pior que o terminal

### B: fatia em largura: cluster todo, só pods

Todos os namespaces, só a lista de pods com estado e motivo.

**O que se ganha:** é a fatia mais rápida de escrever e cobre o chamado 1 sozinha,
`CrashLoopBackOff` com `OOMKilled` aparece na tela.

**O que se perde, e foi decisivo:** **não cobre o chamado 3.** Pod `Running`, `2/2`,
`ready: true`, e a aplicação não responde. Uma tela só de pods mostra tudo verde e **confirma
a conclusão errada**: a mesma conclusão que o relato do cliente já trazia. Uma ferramenta
que corrobora o diagnóstico errado com mais confiança é prejuízo, não ganho. O Service sem
endpoint pronto não é o sexto item em importância; é o item que justifica a tela existir.

### C: incluir logs desde já

**O que se ganha:** é o primeiro pedido que vai chegar depois da demo. Quem vê o
`CrashLoopBackOff` na tela quer clicar e ver por quê.

**O que se perde:**

- `kubectl logs` não é `kubectl get`. Fura a lista branca de verbos do ADR-002, que é a
  camada **visível** da garantia de só-leitura. Furar a camada visível na primeira fatia
  gasta a única coisa que esta aplicação tem de diferente
- log é volume: paginação, limite de linhas, container anterior, multi-container. É mais
  trabalho que os seis tipos juntos
- `logs` exige o subrecurso `pods/log`, que **nem todo contexto de leitura concede**. A
  tela passaria a ter uma seção que falha em parte dos clusters, no mesmo ticket em que estou
  tratando permissão negada como requisito

**Registrado como o primeiro candidato da fatia seguinte**, com a ressalva de que ele reabre
o ADR-002.

### D: o mínimo do RF-02 + RF-03 + RF-04 (escolhida)

**O que entra:**

| Item | Por que está dentro |
|---|---|
| namespaces com contagem de quebrado | responde "onde está o problema", que o terminal responde mal |
| pods com estado, reinícios e **motivo** | o motivo vive em `state.waiting.reason` e `lastState.terminated.reason`: cobre o chamado 1 |
| deployments `prontas/desejadas` | `readyReplicas` ausente é zero (CA-02) |
| services com **endpoints prontos/total** | cobre o chamado 3, e pelo ADR-004 distingue os três modos de "não responde" |
| eventos do namespace selecionado | cobre o chamado 2 (`ImagePullBackOff` com a tag errada no texto do evento) |
| filtro por namespace e busca por nome | sem isso a lista de pods de cluster inteiro é ilegível |
| marcar pronto-sem-probe (RF-03) | **custa pouco** e é o que impede a tela de mentir |
| os três cenários do RF-04 | ver acima |

**O que se perde, aceito:** a fatia é maior que A e B, e vai levar mais tempo. A troca é
deliberada: é a menor fatia que **cobre os três chamados que o Ticket 02 já triou de
verdade**. Qualquer coisa menor deixa um chamado conhecido fora, e eu não tenho desculpa
para isso: os três estão rodando no cluster agora.

## Fora da primeira fatia, com o motivo

| Fora | Motivo |
|---|---|
| **logs** | fura a lista branca do ADR-002 e exige `pods/log`. Primeiro da próxima fatia |
| **`exec`** | escrita disfarçada. Nunca entra |
| **métricas** | outro produto. Depende de `metrics-server`, que não é garantido |
| **multicluster** | fora de escopo pelo RF-01 |
| **YAML view** | só-leitura seria possível, mas é o convite óbvio para o botão de editar |
| **histórico e alerta** | exige persistência, e a aplicação não tem estado por decisão do ADR-003 |
| **tela viva / auto-refresh** | ADR-003 |
| **paralelizar os 6 `LIST`** | ganho imperceptível em cluster local |
| **StatefulSet, DaemonSet, Ingress, PVC** | o parque usa Deployment. Entram quando um chamado exigir, não antes |

## Consequências

- **os critérios de aceite da primeira fatia são CA-01 a CA-08 inteiros.** O CA-05, CA-06 e
  CA-07 não são opcionais, e o CA-07 exige construir um contexto de leitura restrita no
  laboratório: trabalho de ambiente que não produz linha de código visível
- o CA-08 (nenhum caminho executa verbo de escrita) é verificado por **teste que varre o
  próprio fonte**, não por inspeção. É a razão de a lista branca do ADR-002 viver num único
  ponto
- **a fatia seguinte começa por logs**, e quando começar vai ter que reabrir o ADR-002. Está
  dito aqui para que a próxima pessoa não descubra sozinha
- se o recorte estourar o tempo, **o que sai é largura** (tipos de recurso), **não o RF-04**.
  Menos recurso na tela com erro honesto é entregável; tela completa que mostra branco na
  credencial expirada não é
