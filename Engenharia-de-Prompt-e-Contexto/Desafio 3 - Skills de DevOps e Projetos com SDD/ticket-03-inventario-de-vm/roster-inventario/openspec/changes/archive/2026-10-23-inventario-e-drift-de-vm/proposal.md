# Proposta — inventário e drift de VM

## Why

O Roster, inventário do parque, é uma página de wiki mantida à mão e está desatualizada.
Hosts mudaram de papel, há agentes instalados e nunca registrados, e chaves SSH que ficaram
para trás.

A consequência que dói: **ninguém consegue dizer quantas VMs estão fora do padrão.** Existe
um baseline escrito do parque e não existe nada que compare o estado real de um host com ele.

## What Changes

Uma ferramenta de linha de comando que audita **uma** VM por SSH, sem agente, e compara o
que encontra com o baseline versionado do parque.

Ela roda na máquina de quem opera. Recebe endereço, usuário e chave privada; coleta nove
grupos de dados; e devolve inventário e conformidade em **JSON** — para o Roster consumir —
e em **Markdown** — para o plantão ler no terminal.

Cada regra do baseline recebe um de três vereditos: `conforme`, `desvio` com a severidade
que o baseline atribui, ou `nao_verificado` com o motivo.

## Fora de escopo

- **varredura de frota e paralelismo.** Esta é a primeira peça: uma VM. Paralelizar antes
  de a coleta de uma estar correta multiplica o erro
- **correção de desvio.** Auditoria que conserta não é auditoria, e conserto exige contexto
  que o baseline não tem
- **histórico e tendência de drift**, que exige armazenamento entre execuções
- **descoberta de hosts na rede.** O endereço vem de quem chama
- **baseline por papel de host.** O campo `aplica_a` existe no baseline e hoje tem um valor
- **agente no host auditado.** As VMs não têm agente e nenhum será instalado

## Por que agora, e nesta ordem

O inventário e o julgamento são separados de propósito: o Roster quer saber o que existe,
não só o que está errado. Essa separação é o que permite a segunda peça — varredura de
frota — reusar coleta e julgamento sem reescrever nada.

## Como se sabe que funcionou

Cinco critérios, todos verificáveis por execução contra host real:

1. host conforme sai **sem nenhum desvio**
2. host com desvios sai com **cada desvio classificado pela severidade do baseline**
3. regra que não pôde ser verificada aparece como `nao_verificado`, **separada de conforme**
4. host inalcançável falha com mensagem que explica, **sem stack trace**, e não é confundido
   com host conforme
5. a segunda execução devolve **o mesmo resultado**

## Riscos aceitos

| Risco | Mitigação |
|---|---|
| a chave privada vazar em log ou mensagem de erro | ela é passada por caminho, nunca por conteúdo, e o `stderr` do SSH é classificado em vez de repassado |
| parsing de saída de comando quebrar em outra distro | cada coletor falha para `nao_verificado` em vez de derrubar a execução |
| confundir "não coletei" com "está conforme" | é o terceiro veredito, e ele não conta como conforme em lugar nenhum |
| o laboratório não ser uma VM | duas regras do baseline são de nível de host; está registrado e a validação trata |
