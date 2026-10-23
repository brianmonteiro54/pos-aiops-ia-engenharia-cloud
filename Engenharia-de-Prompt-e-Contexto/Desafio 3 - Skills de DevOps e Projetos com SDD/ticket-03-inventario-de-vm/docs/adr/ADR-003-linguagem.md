# ADR-003: Em que linguagem a ferramenta é escrita

**Status:** aceito
**Contexto:** quem vai manter é o time de **infraestrutura** da Metacortex, não um time de
produto. A ferramenta roda na estação de quem opera e em esteira de CI.

## Decisão

**Python 3, com biblioteca padrão apenas.** A única dependência externa é `PyYAML`, para ler
o baseline, e com degradação declarada se ela faltar.

## Alternativas consideradas

### A: Go

**O que se ganha, e é muito:**

- **binário único, sem runtime.** Copia e roda. Para ferramenta que vai para estação de
  várias pessoas e para imagem de CI, isso vale mais do que parece.
- `golang.org/x/crypto/ssh` é maduro e tira a dependência do `ssh` do sistema, se um dia
  isso virar desejável
- compilação cruzada trivial
- tipagem forte, que ajuda numa ferramenta cujo dado tem três estados por regra

**O que se perde, e foi decisivo:**

- **o time de infraestrutura lê e escreve Python e shell.** Go é linguagem que eles
  consomem como binário, não que mantêm. Uma ferramenta que o dono não consegue mudar vira
  ferramenta de uma pessoa, e o Roster está desatualizado **exatamente** por depender de
  manutenção manual que ninguém faz.
- **o ciclo de mudança fica mais longo.** Ajustar o parsing de `ss` porque o formato mudou
  numa distro é edição de uma linha em Python e um `git pull`. Em Go é editar, compilar,
  distribuir binário.
- a vantagem do binário único é menor do que parece: `python3` **já está** em qualquer host
  e estação Linux do parque.

### B: Shell (bash)

**O que se ganha:** é a linguagem nativa do problema. Os comandos de coleta já são shell, e
não haveria tradução nenhuma. Zero dependência, nem `python3`.

**O que se perde:**

- **JSON em shell é sofrimento ou `jq`.** O PRD exige JSON estruturado com aninhamento e
  listas. Montar isso com `printf` é frágil em escape; usar `jq` troca a dependência de
  `python3` por `jq`, sem ganho.
- **comparação de versão por componente**, que o TRD exige, é desconfortável em bash e fácil
  de errar, e `"22.04" < "9.10"` é verdade em comparação de string
- **três estados por regra** em estrutura de dados que bash não tem. Seria array associativo
  com chave composta, ilegível em um mês
- erro silencioso é o default. `set -euo pipefail` ajuda e não resolve pipeline com `grep`
  que não casa

### C: Python 3, biblioteca padrão (escolhida)

**O que se ganha:**

- **o time mantém.** É o critério de maior peso, e o contexto o define
- `python3` está em toda estação e host Linux do parque: nada para instalar
- `json`, `argparse`, `subprocess`, `re` e `dataclasses` cobrem tudo que a ferramenta faz
- o código é inspecionável no host onde está. Para ferramenta de plantão, ler a fonte é
  parte da depuração

**O que se perde, e como foi tratado:**

| Perda | Tratamento |
|---|---|
| sem binário único; exige `python3` | pré-requisito declarado. `python3` é mais presente que um binário distribuído por nós |
| tipagem fraca para dado com três estados | `dataclass` nas estruturas de veredito, e nome de campo explícito em vez de dicionário solto |
| **`PyYAML` não é biblioteca padrão** | abaixo |

## A exceção: `PyYAML`

O baseline é YAML, e YAML não está na biblioteca padrão do Python. Três saídas:

| Saída | Avaliação |
|---|---|
| baseline em JSON | tiraria a dependência, e **pioraria o artefato**. O baseline é editado por humano, tem comentário explicando cada regra, e o ticket o entrega em YAML. JSON não tem comentário |
| escrever um parser mínimo de YAML | reinventar roda com risco de divergir do YAML de verdade em caso de borda |
| **depender de `PyYAML`** | escolhida |

`PyYAML` é a dependência mais comum do ecossistema de infraestrutura: já está instalada
nesta estação, e Ansible a traz. E a falha é **declarada**: se ela faltar, a ferramenta sai
com código `2` e a mensagem diz o que instalar, em vez de estourar `ImportError`.

## Consequências

- pré-requisitos: `python3` ≥ 3.9 (por `dict | dict` e tipagem com `|`), `PyYAML`, `ssh`
- o parsing de saída de comando é por regex e `split`, que é frágil por natureza. O
  tratamento é cada coletor falhar para `nao_verificado` em vez de quebrar: **ADR-002**
- se a ferramenta crescer para varrer frota em paralelo, Python entrega isso com
  `concurrent.futures` da biblioteca padrão, sem mudar a decisão
- **se o requisito mudar para "distribuir sem runtime"**, esta decisão se inverte e Go passa
  a ser a escolha certa. O recorte por etapas do TRD ajuda: transporte, coleta, julgamento e
  apresentação são substituíveis um a um
