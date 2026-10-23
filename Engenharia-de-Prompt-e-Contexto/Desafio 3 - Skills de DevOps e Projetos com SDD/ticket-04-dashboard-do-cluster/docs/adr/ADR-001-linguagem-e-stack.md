# ADR-001: Linguagem e stack

**Status:** aceito
**Contexto:** quem vai manter é o **time de infraestrutura**, não um time de produto. A
aplicação roda na estação de quem opera, local, para uma pessoa por vez.

## Decisão

**Python 3 com biblioteca padrão apenas: `http.server` e HTML renderizado no servidor.
Zero dependência, zero etapa de build, zero JavaScript.**

## Alternativas consideradas

### A: SPA em React ou Vue, com TypeScript

**O que se ganha:** a tela é um painel de verdade. Atualização parcial sem recarregar,
componente reusável, ecossistema enorme de tabela e filtro prontos. É o que a maioria
escolheria.

**O que se perde, e é decisivo:**

- **o time de infraestrutura não mantém cadeia de build de frontend.** `npm`, bundler,
  versão de Node, `node_modules` que quebra em seis meses. A ferramenta que o dono não
  consegue mudar vira ferramenta de uma pessoa: o mesmo argumento do Ticket 03, e ele vale
  mais aqui, porque frontend tem mais partes móveis que CLI.
- **exigiria um backend de qualquer forma.** O navegador não fala com o apiserver usando o
  kubeconfig da estação: certificado de cliente, `exec` plugin de provedor de nuvem, token
  que renova. Então seria SPA **mais** servidor: duas coisas para manter em vez de uma.
- **`npm install` antes de usar.** Para ferramenta de plantão, é a diferença entre abrir e
  não abrir.

### B: Go com `html/template` embutido

**O que se ganha:** binário único, sem runtime. `client-go` é o cliente mais maduro que
existe. Copia e roda, e é tentador para ferramenta que vai para várias estações.

**O que se perde:**

- **o mesmo motivo do ADR-003 do Ticket 03**: o time lê e escreve Python e shell. Go é
  linguagem que eles consomem como binário, não que mantêm. Ajustar uma coluna da tabela
  passa a ser editar, compilar e distribuir.
- **`client-go` tem curva própria**: informers, listers, scheme, tipagem gerada. Para ler
  seis tipos de recurso, é muito aparato.
- a vantagem do binário único é menor do que parece: `python3` **já está** em qualquer
  estação Linux do parque, e `kubectl` também.

### C: TUI no terminal (`curses`, Textual, ou estilo `k9s`)

**O que se ganha:** mesmo ambiente do plantão, que já está no terminal. `k9s` prova que o
formato funciona.

**O que se perde:**

- **`k9s` já existe e é melhor do que isto seria.** Construir uma TUI pior que uma
  ferramenta madura e gratuita é desperdício.
- o ticket pede "aplicação local que mostre o retrato **na tela**", com filtro e busca. Em
  navegador isso é `<input>`; em TUI é gerenciamento de foco e teclado.
- tabela larga em terminal de 80 colunas força decisões de corte que o navegador não impõe.

### D: Python + biblioteca padrão, HTML no servidor (escolhida)

**O que se ganha:**

- **o time mantém.** Critério de maior peso, e o contexto o define.
- **zero dependência e zero build.** `python3 cluster_retrato.py` e abre o navegador.
- `http.server` é suficiente para **um usuário local**. Não é servidor de produção, e não
  precisa ser.
- HTML no servidor significa **uma linguagem**, um arquivo, um lugar para depurar.
- filtro e busca em HTML puro: `<input>` com `?busca=` na query string. Sem estado no
  cliente.

**O que se perde, e como foi tratado:**

| Perda | Tratamento |
|---|---|
| sem atualização parcial: recarrega a página inteira | é consequência do ADR-003, que escolheu consulta sob demanda. A página é pequena |
| `http.server` é single-thread e não é para produção | **é o requisito**: aplicação local, um usuário. E ela escuta em `127.0.0.1` por padrão |
| CSS e HTML embutidos no `.py` ficam feios de ler | aceito. A alternativa: arquivos separados, troca legibilidade por "copia e roda" |

## Consequências

- pré-requisitos: `python3` ≥ 3.9 e `kubectl` no PATH. Nada de `pip install`
- a aplicação escuta em `127.0.0.1` por padrão. Não é servidor de rede, é janela local
- **sem autenticação, e por desenho**: ela roda na estação de quem opera e usa o kubeconfig
  **daquela pessoa**. Expor em `0.0.0.0` daria a qualquer um na rede o acesso de leitura ao
  cluster que o kubeconfig concede, **sem autenticação nenhuma**. Está no README como aviso,
  e o bind é parâmetro com default seguro
- se o requisito mudar para "muitas pessoas acessam um painel comum", esta decisão se
  inverte inteira: passaria a precisar de autenticação, autorização por usuário e um
  servidor de verdade. É produto diferente
