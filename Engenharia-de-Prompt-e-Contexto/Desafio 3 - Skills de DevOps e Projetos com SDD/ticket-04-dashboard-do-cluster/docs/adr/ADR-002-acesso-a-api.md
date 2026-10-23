# ADR-002 — Como falar com a API do Kubernetes

**Status:** aceito
**Contexto:** a aplicação lê seis tipos de recurso do contexto corrente do kubeconfig da
estação. O kubeconfig do parque pode ter certificado de cliente, token, ou `exec` plugin de
provedor de nuvem.

## Decisão

**`kubectl` como subprocesso, com `-o json`, e uma lista branca de verbos aplicada em um
único ponto do código.**

## Alternativas consideradas

### A — cliente oficial da linguagem (`kubernetes` do PyPI)

**O que se ganha:** objetos tipados, paginação, `watch` de graça, e tratamento de erro por
exceção em vez de parsing. É o caminho "certo" para uma aplicação que cresce.

**O que se perde, e foi decisivo:**

- **autenticação é o problema difícil, e o cliente resolve só parte.** Certificado de
  cliente e token ele faz. **`exec` plugin** — o que EKS, GKE e AKS usam — tem suporte
  parcial e historicamente irregular. Numa provedora que opera cluster de cliente, o
  kubeconfig com `exec` é o caso comum, não a exceção.
- **dependência grande, com versão amarrada à do cluster.** O pacote tem política de
  compatibilidade por versão de API, e a frota tem clusters em versões diferentes.
- contraria o ADR-001: `pip install` antes de usar.

### B — HTTP direto contra o apiserver

**O que se ganha:** controle total, zero dependência além da biblioteca padrão, e nenhum
processo externo.

**O que se perde:**

- **seria reimplementar a autenticação do `kubectl`.** Parsear o kubeconfig, resolver
  `current-context`, carregar CA e certificado de cliente, executar `exec` plugin e cachear
  o token que ele devolve, renovar quando expira. Isso é um projeto, não uma etapa.
- `urllib` com certificado de cliente e CA própria é desconfortável o suficiente para
  render bug de TLS que ninguém vai depurar.
- **a credencial passaria pelo meu código.** Hoje ela não passa: o `kubectl` a usa e eu
  nunca a vejo. Para uma ferramenta que lê cluster de cliente, isso é redução de superfície
  que vale muito.

### C — `kubectl` como subprocesso (escolhida)

**O que se ganha:**

- **autenticação, contexto e `exec` plugin resolvidos de graça**, e resolvidos pelo binário
  que a casa já audita e já confia
- **zero dependência** além do que a estação de quem opera já tem
- **a credencial nunca passa pelo meu código**
- **inspecionável**: dá para rodar o mesmo comando à mão e ver o mesmo JSON, o que importa
  quando alguém duvida do que a tela mostra
- consistente com o ADR-001 do Ticket 03, que escolheu `ssh` como subprocesso pelo mesmo
  raciocínio. Duas ferramentas da casa com o mesmo padrão de transporte é menos coisa para
  aprender

**O que se perde, e como foi tratado:**

| Perda | Tratamento |
|---|---|
| um processo por consulta | o ADR-003 escolheu consulta sob demanda, então são ~6 processos por carregamento de página. Em cluster local, dezenas de ms |
| erro vira texto de `stderr`, não exceção tipada | classificação por padrão de texto. **É frágil, e a medição confirmou que é pior do que eu supunha ao escrever este ADR** — ver a nota de implementação no fim |
| `kubectl` pode escrever | **é o ponto crítico**, e é o que a decisão abaixo trata |

## A garantia de só leitura, que é requisito e não intenção

O RE-01 exige que a garantia esteja **visível no projeto**. `kubectl` é a mesma ferramenta
que faz `delete`, então "não vou chamar delete" não é garantia — é promessa.

O que foi implementado:

1. **Um único ponto de saída.** Toda chamada passa por uma função, e só ela constrói linha
   de comando. Não há `subprocess` em nenhum outro lugar do arquivo.
2. **Lista branca de verbos**, e não lista negra. Verbo fora da lista levanta exceção
   **antes** de o processo existir. Lista negra esqueceria `replace`, `edit`, `annotate`,
   `label`, `cordon`, `drain`. A lista final tem quatro entradas e está na nota de
   implementação abaixo.
3. **`--request-timeout`** fixo, para a tela não pendurar em cluster que não responde.
4. **Teste que varre o próprio código-fonte** procurando verbo de escrita, e falha se achar.
   É o que torna a garantia verificável por quem lê o repositório em vez de confiar em mim.

A camada que isto **não** substitui, e está registrada: um kubeconfig com RBAC de leitura.
A garantia acima é do lado da aplicação; RBAC é do lado do apiserver, e é a única que não
depende do meu código estar correto. O ticket oferece o `platform-ro` justamente como esse
caso, e o CA-07 o exercita.

## Nota de implementação — o que mudou depois de escrever este ADR

Registrado aqui porque o ADR foi escrito antes do código, e o código discordou dele em três
pontos. A decisão de fundo não mudou; os detalhes abaixo mudaram.

### A lista branca virou lista de prefixos, com quatro entradas

Escrevi "só `get` e `version`". A lista final é:

```python
PREFIXOS_PERMITIDOS = {("get",), ("version",), ("api-resources",), ("config", "view")}
```

- **`api-resources`** entrou porque o ADR-004 precisa dele uma vez, na subida, para decidir
  entre `EndpointSlice` e `Endpoints`.
- **`config view`** entrou por causa de um defeito que o código real revelou. A primeira
  versão lia o kubeconfig como texto e pegava o primeiro `server:` do arquivo. Num
  kubeconfig com vários clusters isso é o servidor **errado**: a tela anunciou um endpoint
  de EKS enquanto lia um k3d local. Um painel que mente sobre qual cluster está lendo é
  pior que um painel que não diz nada. `kubectl config view --minify` responde a pergunta
  certa, e de graça resolve a mesclagem de vários arquivos em `KUBECONFIG`, que eu teria
  que reimplementar.
- por isso a lista passou a ser de **prefixos** em vez de verbos: `kubectl config` tem
  subcomando de escrita (`set-context`, `use-context`, `unset`). Liberar o verbo inteiro
  abriria escrita no kubeconfig. Só `config view` entra, e há teste para os cinco
  subcomandos de escrita serem recusados.

### Um `--request-timeout` não basta

O ADR dizia "`--request-timeout` fixo, para a tela não pendurar". **Não basta.** Medido
contra um endereço não roteável:

| Como | Tempo |
|---|---|
| sem teto | travou **além de 70s** |
| `--request-timeout=5s` | falhou em **25s** |

`--request-timeout` limita cada requisição, não o comando — o `kubectl` repete a descoberta
de grupos da API e os tempos somam. São dois tetos: o do `kubectl` e um `subprocess` com
`timeout` do lado da aplicação, que no estouro mata o **grupo** de processos
(`start_new_session` + `killpg`), porque matar o PID sozinho deixa filho órfão.

### A classificação por texto é mais frágil do que eu admiti

Medi nove modos de falha. Dois achados que o ADR original não previa:

1. **todos devolvem `exit 1`.** O código de saída não carrega informação nenhuma.
2. **token inválido, token expirado e certificado de cliente expirado produzem a mesma
   linha**: `error: You must be logged in to the server (Unauthorized)`. O apiserver
   responde 401 nos três. A aplicação **não pode** dizer "credencial expirada" — ela diz
   "rejeitada: expirada, inválida ou revogada". A única exceção é o `exec` plugin, em que o
   provedor informa a expiração.

Por isso existe o rótulo `nao_classificada`, que mostra o `stderr` cru em vez de arriscar um
rótulo errado. Medido com `kubectl` v1.33.13; outra versão pode cair nesse rótulo.

### A quarta camada continua ausente, e agora tem nome e lugar

O RBAC somente-leitura segue não implementado como camada de garantia. O que **foi** feito é
usar um contexto restrito como **cenário de teste** (CA-07), não como mecanismo de proteção
da aplicação. É a mesma dívida que o Ticket 02 registrou, e ela não foi paga aqui.
