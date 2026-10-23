# Curadoria — Ticket 04

## O que foi entregue

`cluster-retrato`: 1007 linhas de Python sem dependência, 41 testes de unidade, 66
verificações de ponta a ponta, 5 ADRs, PRD, TRD e um ciclo OpenSpec arquivado. Lê seis
tipos de recurso do cluster corrente e degrada de forma legível nos três cenários de falha
de ambiente.

## O que o ticket pedia e o que mudou de ideia pelo caminho

As cinco decisões em aberto foram todas para ADR, e **duas delas mudaram depois de
escritas**, porque a medição discordou:

| ADR | Decisão | Mudou? |
|---|---|---|
| 001 | Python 3 + `http.server` + HTML no servidor | não |
| 002 | `kubectl` como subprocesso + lista branca | **sim**, em três pontos |
| 003 | consulta sob demanda | não |
| 004 | `EndpointSlice` primário, `Endpoints` como alternativa | **sim**, a pergunta mudou |
| 005 | o mínimo do RF-02 + os três cenários de falha | não |

## As cinco coisas que a medição desmentiu

Esta é a parte que vale guardar. Em todos os cinco casos eu tinha escrito uma coisa e o
cluster disse outra.

**1. `--request-timeout` não limita o comando.** Eu havia escrito no ADR-002
"`--request-timeout` fixo, para a tela não pendurar". Medido contra um IP não roteável: sem
teto, travou **além de 70s**; com `--request-timeout=5s`, levou **25s**. O `kubectl` repete
a descoberta de grupos da API e os tempos somam. Precisou de um segundo teto, do lado da
aplicação, matando o **grupo** de processos — matar o PID deixa órfão.

**2. Credencial expirada é indistinguível de credencial inválida.** Construí três
kubeconfigs: token inválido, JWT com `exp` no passado, e certificado de cliente expirado
assinado pela **CA real do cluster**. Os três devolvem
`error: You must be logged in to the server (Unauthorized)`, `exit 1`. O CA-06 pede
"credencial expirada ... distinguível de cluster fora": é distinguível de cluster fora, e
**não** é distinguível de inválida. A tela diz "expirada, inválida ou revogada". A única
exceção é o `exec` plugin, em que o provedor informa.

**3. Contar endpoints responde a pergunta errada.** O PRD dizia que "ausência de endpoint
explica 'subiu mas não responde'". Medido: nos namespaces com `CrashLoopBackOff` e
`ImagePullBackOff`, o objeto `Endpoints` **tem** `subsets`, populado com
`notReadyAddresses`. Contar endpoints acusa só o caso do selector e passa batido nos outros
dois. Virou `prontos/total`, e `0/0` contra `0/3` conta histórias diferentes. **Corrigiu o
PRD, o RF-02, o CA-03 e a skill do Ticket 02.**

**4. O cabeçalho mentia sobre qual cluster estava lendo.** A primeira versão lia o
kubeconfig como texto e pegava o primeiro `server:` do arquivo. Num kubeconfig com vários
clusters, isso é o servidor errado: a tela anunciou um endpoint de EKS enquanto lia um k3d
local. **Nenhum critério de aceite olhava o cabeçalho** — apareceu ao ler a saída.

**5. Minha própria varredura de segurança me pegou.** Na primeira execução, o teste do CA-08
falhou acusando o literal `"run"` — dentro do próprio auditor, no conjunto de nomes de
método de `subprocess` que ele procura. Verdadeiro positivo da regra aplicado ao vocabulário
de quem a aplica. Isentei o auditor e declarei a isenção, em vez de encurtar a lista de
verbos.

## O erro de método que repeti

No registro das skills eu escrevi que a reference de triagem do Ticket 02 estava incompleta
sobre endpoints. **Fui conferir e ela não estava** — tinha os dois modos de quebra, a
comparação e o idioma correto. Afirmei sobre um documento meu sem reler o documento.

É o **mesmo erro do Ticket 01**, onde eu inventei três regras do Padrão de Manifests e só
descobri quando o anexo chegou. Duas ocorrências do mesmo padrão em quatro tickets: eu
confio na minha memória de um documento mais do que no documento. A correção que funciona é
mecânica, não de disciplina: reler antes de afirmar, sempre que a afirmação for sobre
conteúdo de arquivo.

## O que ficou de fora, e por quê

| Fora | Motivo |
|---|---|
| **logs** | fura a lista branca do ADR-002 e exige `pods/log`. Primeiro da próxima fatia, e vai reabrir o ADR-002 |
| **RBAC somente-leitura como camada de garantia** | a dívida que o Ticket 02 registrou e que este ticket **não pagou**. Em produção seria a primeira camada. Aqui o contexto restrito foi usado como **cenário de teste**, não como proteção |
| **`exec`, métricas, multicluster, YAML view, histórico** | escopo, pelo ADR-005 |
| **paralelizar os seis `LIST`** | ganho imperceptível em cluster de 2 nós |

## O que a validação não prova

Registrado porque 66 verificações verdes dão uma sensação de cobertura que não corresponde:

- **o caminho de `Endpoints` só roda por injeção no teste.** Este cluster tem
  `discovery.k8s.io/v1`, então a alternativa nunca é exercitada de verdade. Valida a
  normalização, não a detecção
- **a soma de N `EndpointSlice` por Service não é exercitada com N > 1.** Medido: 14 pares
  `(namespace, service)`, máximo 1 slice cada. O código soma; o teste não prova
- **a classificação depende do texto do `kubectl` v1.33.13.** Outra versão cai em
  `nao_classificada` — degrada para feio, não para errado, que é o motivo de esse rótulo
  existir
- **nada foi medido em cluster grande.** `get pods -A` carrega um JSON único na memória, e
  os seis `LIST` são sequenciais
- **a varredura do CA-08 prova que não há verbo de escrita no fonte.** Não prova que a
  credencial em uso não poderia escrever
- **a aplicação não tem autenticação.** Mitigado por bind em loopback e aviso na exposição;
  não resolvido

## O custo

| Etapa | Observação |
|---|---|
| medir os nove modos de falha | a parte mais cara, e a que mais mudou o projeto. Construir o certificado expirado assinado pela CA real do k3d foi o passo que deu o achado nº 2 |
| escrever os 5 ADRs | dois foram reescritos depois do código |
| o ciclo OpenSpec | rápido, porque `openspec templates` resolveu a dúvida de formato que o Ticket 03 errou: os cabeçalhos do `proposal.md` são **em inglês** |
| a implementação | a camada de normalização é curta; a classificação de falha e o HTML são a maior parte |
| a validação | 66 verificações. 7 falharam na primeira rodada, todas por defeito do **extrator de texto do `validar.sh`**, que quebrava linha em cada célula de tabela |

## Se eu fizesse de novo

- **mediria os modos de falha antes de escrever o ADR-002.** Os três pontos que mudaram no
  ADR teriam entrado na primeira versão
- **colocaria um critério de aceite sobre o cabeçalho.** O defeito nº 4 passou porque
  nenhum critério olhava para lá, e era o campo mais visível da tela
- **não escreveria "credencial expirada" em nenhum requisito** antes de confirmar que o
  `kubectl` distingue. O RF-04 e o CA-06 usam uma palavra que o ambiente não suporta, e o
  ticket teve que explicar isso em vez de cumprir
