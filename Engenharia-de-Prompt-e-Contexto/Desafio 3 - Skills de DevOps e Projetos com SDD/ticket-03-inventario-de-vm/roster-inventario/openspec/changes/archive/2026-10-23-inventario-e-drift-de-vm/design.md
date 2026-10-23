# Design — inventário e drift de VM

As quatro decisões estruturais estão em ADRs, em `../../../docs/adr/`. Este documento é o
desenho que decorre delas.

| ADR | Decisão |
|---|---|
| **001** | transporte: `ssh` do sistema como subprocesso, com `ControlMaster` |
| **002** | dado não coletado: terceiro veredito `nao_verificado`, com motivo |
| **003** | linguagem: Python 3, biblioteca padrão, mais `PyYAML` para o baseline |
| **004** | laboratório: containers com systemd, e duas regras que eles não podem satisfazer |

## Quatro etapas, nesta ordem

```
transporte  -->  coleta  -->  julgamento  -->  apresentacao
   ssh           9 coletores   11 regras       JSON | Markdown
```

A separação entre **coleta** e **julgamento** é a decisão de desenho que organiza o resto.
O inventário tem valor sem o baseline — o Roster quer saber o que existe, não só o que está
errado — e trocar o baseline não deve mexer em coletor.

O custo: duas estruturas em vez de uma. O ganho: os dois formatos saem do mesmo dado, sem
segunda coleta.

## Estruturas

```python
@dataclass
class Coletado:          # o resultado de um coletor
    valor: Any | None    # None quando falhou
    motivo: str | None   # preenchido quando falhou

@dataclass
class Veredito:
    regra: str
    esperado: Any
    encontrado: Any
    veredito: str              # conforme | desvio | nao_verificado
    severidade: str | None     # so quando desvio
    motivo: str | None         # so quando nao_verificado
```

`Coletado` com `valor=None` e `motivo` preenchido é o que vira `nao_verificado` no
julgamento. É o único caminho — nenhum coletor levanta exceção para cima.

## Transporte

Uma sessão, n comandos. `ControlMaster` abre um socket de controle na primeira conexão e as
seguintes reusam: uma autenticação por execução.

Opções fixadas, com o motivo em `docs/02-trd.md`: `BatchMode=yes`,
`StrictHostKeyChecking=accept-new`, `ConnectTimeout=10`, `IdentitiesOnly=yes`.

O socket de controle vive em diretório temporário próprio e é removido ao fim — socket
esquecido é conexão aberta para VM de cliente.

### Classificação de falha de conexão

O `stderr` do `ssh` não é repassado cru, porque pode conter o caminho da chave. É
classificado em três categorias:

| Sinal no `stderr` | Categoria |
|---|---|
| `No route to host`, `Connection refused`, `timed out`, `Name or service not known` | host inalcançável |
| `Permission denied`, `publickey` | autenticação recusada |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | chave do host mudou |

As três saem com código `2` e **nenhuma produz bloco de conformidade**. É o que impede
confundir host inalcançável com host conforme.

## Coleta

Nove coletores, cada um com um comando de leitura. A tabela comando a comando está em
`docs/02-trd.md`.

Dois pontos de desenho que vêm da spec:

**`systemctl list-units --type=service,socket`.** Sem o `socket` os dois proibidos pelo
baseline — `telnet.socket` e `rpcbind.socket` — passariam sem ser vistos.

**`ss -lntupH` e a normalização do bind.** O baseline separa `publicas_permitidas` de
`somente_rede_interna`, então a porta sozinha não decide. `0.0.0.0`, `*`, `::` viram
**público**; `127.0.0.1`, `::1` viram **loopback**; qualquer outro IP vira **rede interna**.

## Julgamento

Onze regras. Cada uma é uma função que recebe o esperado e o `Coletado`, e devolve
`Veredito`.

Duas invariantes:

1. **`Coletado.valor is None` produz `nao_verificado`**, sempre, antes de qualquer
   comparação. Nenhuma regra julga dado que não veio.
2. **a severidade vem do mapa `severidade` do baseline.** Regra que não apareça em nenhum
   dos três níveis é erro do baseline, e a ferramenta diz em vez de assumir.

Comparação de versão é por componente numérico. `"22.04" < "9.10"` é verdade em string.

## Apresentação

O JSON segue o formato do ticket. `resumo.por_severidade` conta **os desvios**, não todas as
regras.

O Markdown põe desvios primeiro, ordenados `critico` → `alto` → `medio`, depois não
verificados com motivo, depois conformes em uma linha. O plantão lê de cima e para quando
quiser.

## Determinismo

Três fontes de variação e o tratamento de cada:

| Fonte | Tratamento |
|---|---|
| ordem de `systemctl` e `ss` | ordenar toda lista antes de comparar e de imprimir |
| instante da coleta | único campo que muda, declarado assim |
| `uptime`, PID, uso de memória | **não coletados** — não estão no baseline e tornariam a saída instável |

Não coletar PID foi decisão: identificaria o processo dono da porta com mais precisão e
muda a cada reinício. O nome do processo basta para o julgamento.

## O que o laboratório não prova

Por **ADR-004**, `kernel.versao_minima` e `swap.habilitado` são de nível de host e o
container compartilha os dois. A validação do CA-01 é feita em duas partes, com o motivo
escrito, em vez de afrouxar o baseline do parque.
