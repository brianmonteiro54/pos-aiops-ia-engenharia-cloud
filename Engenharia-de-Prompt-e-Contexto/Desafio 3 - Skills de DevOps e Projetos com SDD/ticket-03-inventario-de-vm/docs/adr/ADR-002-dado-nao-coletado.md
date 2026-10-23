# ADR-002 — O que acontece quando um dado não pode ser coletado

**Status:** aceito
**Contexto:** a coleta entra com usuário comum. Parte dos dados exige privilégio — o caso
concreto é `sshd -T`, que responde a configuração efetiva do SSH e precisa de root.

## Decisão

**Um terceiro veredito, `nao_verificado`, com o motivo, na mesma lista dos outros. A falha
de um coletor não derruba os outros, e a execução segue até o fim.**

E a consequência de projeto: `nao_verificado` **não conta como conforme em nenhum lugar** —
nem no resumo, nem no código de saída, nem na seção de conformes do Markdown.

## Alternativas consideradas

### A — abortar a execução inteira

**O que se ganha:** a saída nunca é parcial. Ou se audita o host todo, ou não se audita.
Honesto por construção, e simples de implementar.

**O que se perde, e é decisivo:** uma regra que exige privilégio **derruba o relatório
inteiro**. O operador não descobre que há swap ligado e chave de origem desconhecida, porque
a ferramenta parou em `sshd -T`. Dez dados coletáveis perdidos por um que não era.

O ticket diz isso com precisão: *abortar a execução inteira não ajudaria ninguém.*

### B — reportar como `conforme`

**O que se ganha:** nada. Está aqui porque é o default acidental de quem escreve
`if deu_erro: pass`.

**O que se perde:** é mentira, e é a pior das três. Uma auditoria que diz "root login está
desabilitado" quando na verdade diz "não consegui olhar" é **pior que não ter auditoria** —
ela produz confiança falsa, e alguém decide com base nela.

O ticket também nomeia: *reportar isso como conforme seria falso.*

### C — reportar como `desvio`

**O que se ganha:** falha para o lado seguro. Nenhum host passa com dado faltando, e o
código de saída fica `1`, barrando promoção em pipeline.

**O que se perde:**

- **gera trabalho falso.** O operador vai conferir um desvio que pode não existir. Com
  frota, é um campo de desvios fantasma que ninguém consegue limpar.
- **apaga a diferença entre "está errado" e "não sei".** As duas exigem ações diferentes:
  desvio se conserta no host; `nao_verificado` se resolve dando privilégio à coleta ou
  mudando o método.
- **a severidade fica sem sentido.** `ssh.login_de_root` é `alto` no baseline. Contar como
  desvio alto um dado não coletado contamina a contagem por severidade, que é o número que
  prioriza o plantão.

### D — terceiro veredito, com motivo (escolhida)

**O que se ganha:**

- **diz a verdade**, que é o requisito de uma auditoria
- **separa duas ações diferentes**: conserte o host x dê acesso à coleta
- **a contagem por severidade continua significando** desvio real
- a saída é parcial **e declarada como parcial**, o que é diferente de parcial e silenciosa

**O que se perde, e foi aceito:**

| Perda | Por que aceitável |
|---|---|
| três estados em vez de dois, em toda a lógica e nos dois formatos | é o requisito; o ticket já decidiu a forma |
| `nao_verificado` pode se acumular e ninguém olhar | o Markdown dá seção própria e o JSON conta no resumo. Visível, não escondido |
| o código de saída não distingue "conforme com lacuna" de "conforme" | decidido abaixo |

## O código de saída, que foi a parte difícil

`nao_verificado` não é desvio, então um host com 10 conformes e 1 não verificado sai com
código... qual?

| Opção | Efeito |
|---|---|
| `0` (como conforme) | a esteira promove um host que **não foi auditado por inteiro** |
| `1` (como desvio) | reintroduz a alternativa C pela porta dos fundos |
| um quarto código | a esteira passa a ter quatro casos para tratar, e `2` já significa "não consegui olhar" |

**Escolhido: `0`**, com duas condições que tornam a lacuna impossível de ignorar:

1. o `resumo` do JSON traz `nao_verificado` como contagem própria, então a esteira **pode**
   barrar com uma linha de `jq` se a política da casa quiser
2. o Markdown tem seção própria de não verificados, com o motivo de cada um

O raciocínio: o código de saída responde **"este host está fora do padrão?"**. Dado não
coletado não é resposta afirmativa a essa pergunta. A pergunta "a auditoria foi completa?" é
outra, e tem campo próprio no JSON.

É a decisão menos confortável deste ADR, e a registro como tal: se a casa decidir que
auditoria incompleta barra promoção, a mudança é uma condição no código de saída, e o dado
para isso já está na saída.

## Consequências

- todo coletor devolve **dado ou falha com motivo legível**, e nunca exceção que suba
- o motivo é texto para humano: `"exige privilegio que o usuario da coleta nao tem"`
- CA-03 valida isto diretamente, e o laboratório usa usuário sem privilégio de propósito
- **falha de conexão é outra coisa.** Se o SSH não conecta, não há coleta nenhuma e o
  código é `2`, sem bloco de conformidade. `nao_verificado` é para dado individual num host
  alcançável
