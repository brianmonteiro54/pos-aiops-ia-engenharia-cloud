# ADR-003: Como manter a tela atualizada

**Status:** aceito
**Contexto:** a tela mostra o estado de seis tipos de recurso. O ticket pede a comparação de
**carga sobre o apiserver**, **complexidade** e **atraso do que aparece na tela**.

## Decisão

**Consulta sob demanda: a tela busca os dados quando alguém carrega a página, e só então.
O botão de recarregar é o navegador.**

## As três opções, nos três eixos que o ticket nomeia

| | sob demanda | intervalo fixo | `watch` |
|---|---|---|---|
| **carga no apiserver** | ~6 `LIST` por carregamento, **zero quando ninguém olha** | ~6 `LIST` a cada N segundos, **para sempre** | 1 `LIST` + conexão longa por tipo |
| **complexidade** | nenhuma. Requisição, resposta, HTML | timer, e decidir o que fazer com requisição sobreposta | reconexão, `resourceVersion`, expiração, estado em memória, concorrência |
| **atraso na tela** | zero no instante do carregamento; cresce até você recarregar | até N segundos | ~tempo de rede |

## Alternativas consideradas

### A: intervalo fixo (polling a cada N segundos)

**O que se ganha:** a tela "vive". Durante uma triagem, ver o `restartCount` subindo sem
tocar em nada é informação de verdade.

**O que se perde:**

- **carga constante independente de uso.** Uma aba esquecida aberta na sexta consulta o
  apiserver todo fim de semana. Com `kubectl` como transporte (ADR-002), cada ciclo são
  **seis processos**, não seis requisições.
- escolher N é escolher entre atraso e carga, sem número certo. 5s é agressivo para um
  painel de leitura; 60s não "vive".
- requisição sobreposta quando o cluster está lento, justamente quando se está triando.

### B: `watch` (observação de mudanças)

**O que se ganha:** o menor atraso possível e a menor carga em regime. É o que `k9s` e
`kubectl get -w` fazem, e o mecanismo que o Kubernetes oferece para isso.

**O que se perde, e foi decisivo:**

- **complexidade desproporcional ao recorte.** `watch` exige guardar `resourceVersion`,
  tratar `410 Gone` quando ela expira, reconectar com backoff, e manter estado em memória
  para seis tipos. É a parte mais difícil de escrever e a mais difícil de depurar.
- **briga com o transporte escolhido.** `kubectl get -w` com `-o json` emite um fluxo que eu
  teria que parsear incrementalmente de um processo que nunca termina, com seis processos
  vivos em paralelo. É o pior encaixe possível com o ADR-002.
- **exigiria push para o navegador**: SSE ou WebSocket, e o ADR-001 escolheu HTML no
  servidor sem JavaScript. Trazer `watch` arrastaria a decisão do ADR-001 junto.
- **o recorte não precisa.** Isto encurta os **primeiros minutos** de um chamado. Quem quer
  acompanhar em tempo real tem `kubectl get -w`, e a aplicação não substitui o terminal.

### C: sob demanda (escolhida)

**O que se ganha:**

- **zero carga quando ninguém está olhando.** É a propriedade que mais vale num cluster de
  cliente.
- **complexidade nenhuma.** Nem timer, nem estado, nem reconexão. A página é o estado.
- **o atraso é sempre conhecido**, porque a hora da coleta está impressa na tela. Numa tela
  com polling, o que se vê pode ter até N segundos e ninguém sabe quanto.
- combina com o ADR-001 e o ADR-002 sem arrastar nenhum dos dois.

**O que se perde, e como foi tratado:**

| Perda | Tratamento |
|---|---|
| a tela "congela" até alguém recarregar | **a hora da coleta é impressa**, para ninguém ler dado velho achando que é atual |
| recarregar é manual | aceito e declarado. `F5` é gesto conhecido, e o ticket não pede tela viva |
| dado inconsistente entre tipos: os seis `LIST` não são atômicos | o atraso entre a primeira e a última consulta é de dezenas de ms. Se um pod nascer no meio, aparece na próxima carga. **Registrado como limitação**, porque uma tela com polling tem o mesmo problema e esconde melhor |

## Consequências

- a hora da coleta vai no cabeçalho de toda tela, sempre
- os seis `LIST` são sequenciais. Paralelizar com `concurrent.futures` é melhoria conhecida
  e não aplicada: em cluster local o ganho é imperceptível, e seria complexidade sem motivo
- **se o requisito mudar para "acompanhar rollout em tempo real"**, esta decisão se inverte,
  e provavelmente arrasta o ADR-001 e o ADR-002 com ela. É sinal de que o produto virou
  outro
