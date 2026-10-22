# Ticket 01 — Skill do padrão de manifests

Empacotar o Padrão de Manifests da Metacortex (revisão 2026-07-29) numa skill, com o que é
mecânico virando script e o que exige ler o projeto virando instrução — sem reimplementar o
que o Trivy já cobre.

## Onde está cada item do `Entregue.`

| Item pedido | Onde está |
|---|---|
| **A skill completa: corpo, script e arquivos de apoio** | `../../../.kiro/skills/padrao-de-manifests-metacortex/` — `SKILL.md`, `scripts/conferir_manifesto.py`, `references/padrao-completo.md`, `references/cobertura-do-trivy.md` |
| **A origem da skill: de qual fluxo nasceu, como foi produzida e com qual ferramenta** | `curadoria.md` seção 0, e os dois fluxos em `fluxos/` |
| **Saída real — os manifests gerados** | `manifests/fake-shop/` e `manifests/kube-news/`, com `DECISOES.md` em cada um |
| **Saída real — a conferência do manifesto barrado** | `evidencias/relatorios/01-manifesto-barrado.txt` |
| **Curadoria — a linha entre script e instrução, regra por regra** | `curadoria.md` seção 1 |
| **Curadoria — o que o Trivy já cobria** | `curadoria.md` seções 2 e 3, e `references/cobertura-do-trivy.md` |
| **Curadoria — corpo da skill x arquivo consultado sob demanda** | `curadoria.md` seção 4 |
| **Curadoria — o que decidi não empacotar e por quê** | `curadoria.md` seção 7 |
| **Curadoria — quais permissões a skill pede** | `curadoria.md` seção 8 |

Extra, não pedido: `validacao/testes-cegos.md` — três sub-agentes executaram a skill sem
acesso aos fluxos nem às sondas e acharam 15 defeitos nela, todos corrigidos. O que eles
**não** pegaram foram as três regras que eu havia inventado: teste cego valida consistência
interna, não fidelidade à fonte. Essas saíram do confronto com o anexo.

## A skill

```
.kiro/skills/padrao-de-manifests-metacortex/
├── SKILL.md                            procedimento dos dois modos
├── references/padrao-completo.md       os 4 blocos do padrão, com minhas interpretações marcadas
├── references/cobertura-do-trivy.md    o mapa medido por experimento
└── scripts/conferir_manifesto.py       15 das 19 regras
```

Quem julga cada regra:

| Juiz | Regras | Quantas |
|---|---|---|
| **script** | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 2.3, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5, 3.7 | 15 |
| **Trivy**, invocado e traduzido pelo script | 2.1, 3.1, 3.6 | 3 |
| **só leitura do projeto** | 2.6 | 1 |

O Trivy é juiz de **3 das 19**. Chegar a esse número exigiu dois experimentos, porque rodar
`trivy config` num manifesto não diz o que a ferramenta tem — diz o que aquele manifesto
violou.

## Os três achados que mais mudaram a skill

**1. O Trivy não vê a senha.** A regra 3.3 é `proibido` e é a que vaza credencial de banco.
`trivy fs --scanners secret` acha `AKIA…`, `ghp_…` e bloco de chave privada, e **não acha**
`postgres://nyx:s3nh4-do-banco@pg…`. Pior: existe o `AVD-KSV-01010`, chamado "ConfigMap
with sensitive content", que parece cobrir. Testado com a mesma senha em três lugares, ele
alcança um, casa com a palavra `postgres` em vez da senha, e aponta a linha do `---`.

**2. A regra 3.2 não pode ter o Trivy como juiz.** Ele confere os cinco requisitos por
regras separadas, com severidades de LOW a HIGH, sem o conceito do bloco que a casa exige.
Quem filtra por `--severity HIGH,CRITICAL` vê um e perde quatro.

**3. A severidade do Trivy não é a obrigatoriedade da casa.** As quatro regras de
`requests`/`limits` são **LOW** no Trivy e **barram o deploy** na Metacortex.

## Resultado das duas execuções

| Alvo | rc | Barra | Recomendado |
|---|---|---|---|
| manifesto barrado (`nyx-prod`) | 1 | **20** | 3 |
| fake-shop gerado (`orion-prod`) | 1 | 2 | 1 |
| kube-news gerado (`nyx-dev`) | **0** | 0 | 1 |

As duas violações do fake-shop são do Postgres e saem do mesmo fato — volume único em prod:
`replicas: 1` fere a 2.3 e `strategy.type: Recreate` fere a 2.4. Os dois casos são
legítimos e **continuam barrando**, porque desvio documentado não é exceção aprovada. É o
princípio que a skill protege.

## Onde eu errei

Três exigências da skill **não existiam no padrão** e saíram quando confrontei a skill com
o anexo: piso de UID na 3.2, `Recreate` como alternativa na 2.4, e `hostIPC` na 3.6. As
três nasceram de completar de cabeça uma regra que parecia incompleta. Detalhe em
`curadoria.md` seção 7.

Um quarto erro: eu afirmei que campo de container declarado no nível do pod é
"silenciosamente ignorado". Testei contra o apiserver e está errado — `kubectl apply`
strict **recusa** com `strict decoding error`; só `--validate=false` aceita e descarta.

## Reproduzir

```bash
S=../../../.kiro/skills/padrao-de-manifests-metacortex/scripts/conferir_manifesto.py

python3 "$S" manifests/nyx-api-barrado.yaml   # rc=1 — 20 barram, 3 recomendadas
python3 "$S" manifests/fake-shop/             # rc=1 — 2 barram (desvios do Postgres)
python3 "$S" manifests/kube-news/             # rc=0 — nada barra
python3 "$S" validacao/teste-cego-01-vega-stg.yaml     # rc=1 — 4 barram
python3 "$S" validacao/teste-cego-02-atlas-prod.yaml   # rc=1 — 4 barram
```

Requer `python3` com PyYAML. Sem `trivy` o script confere 15 das 19 e avisa na saída quais
ficaram de fora — rode com `--sem-trivy` para ver.

### A sonda de segredos é gerada, não versionada

```bash
cd evidencias/sondas
python3 gerar-sonda-de-segredos.py
trivy fs --scanners secret trivy-segredos-seis-formatos.yaml   # 5 de 6 detectados
rm trivy-segredos-seis-formatos.yaml                            # nao commitar
```

O motivo vale como achado. A sonda precisa de valores com a **forma exata** de credencial
real, senão o scanner não dispara. Essa mesma forma fez o push protection do GitHub
**bloquear** o push deste ticket, com três violações. A segunda tentativa guardou os
valores em base64 — o GitHub decodificou e recusou de novo. Por isso o gerador **sorteia**
os valores: o experimento mede a forma, não um valor específico.

O resultado está em `evidencias/relatorios/06-trivy-saida-crua.txt`, auditável sem rodar
nada.
