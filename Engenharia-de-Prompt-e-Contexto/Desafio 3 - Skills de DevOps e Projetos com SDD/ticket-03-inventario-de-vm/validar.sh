#!/usr/bin/env bash
# Valida roster-inventario contra os cinco critérios de pronto do ticket.
#
# Pré-requisitos: os dois hosts do laboratório no ar (ver laboratorio/subir.sh) e o par de
# chaves gerado em ~/desafio03-lab/t03/chaves/.
#
# Uso:  ./validar.sh [diretorio-de-saida]
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FERRAMENTA="$AQUI/roster-inventario/roster_inventario.py"
CHAVES="$HOME/desafio03-lab/t03/chaves"
SAIDA="${1:-$AQUI/evidencias}"
mkdir -p "$SAIDA"
cd "$AQUI/roster-inventario"

CONFORME_PORTA=2201
DESVIOS_PORTA=2202
USUARIO=auditor

auditar() {   # auditar <porta> <baseline> <formato>
  python3 "$FERRAMENTA" \
    --host 127.0.0.1 --porta "$1" --usuario "$USUARIO" \
    --chave "$CHAVES/auditor" --baseline "$2" --formato "$3"
}

titulo() { printf '\n########## %s ##########\n' "$1"; }

{
printf '# Validacao de roster-inventario contra os critérios de pronto\n'
printf '# %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# ---------------------------------------------------------------- CA-01
titulo "CA-01: host conforme sai sem nenhum desvio (baseline do laboratorio)"
auditar $CONFORME_PORTA baseline-laboratorio.yaml markdown
auditar $CONFORME_PORTA baseline-laboratorio.yaml json > /dev/null
printf '\ncodigo de saida: %s   (esperado 0)\n' "$?"

# ---------------------------------------------------------------- CA-01b
titulo "CA-01b: o MESMO host contra o baseline do parque (ADR-004)"
printf 'Esperado: exatamente DOIS desvios, kernel e swap, e nada mais.\n'
printf 'Os dois sao de nivel de HOST e o container compartilha os dois.\n\n'
auditar $CONFORME_PORTA baseline.yaml markdown
auditar $CONFORME_PORTA baseline.yaml json > /dev/null
printf '\ncodigo de saida: %s   (esperado 1, ha desvio, e e verdade)\n' "$?"

# ---------------------------------------------------------------- CA-02
titulo "CA-02: host com desvios, cada um com a severidade do baseline"
auditar $DESVIOS_PORTA baseline.yaml markdown
auditar $DESVIOS_PORTA baseline.yaml json > /dev/null
printf '\ncodigo de saida: %s   (esperado 1)\n' "$?"

titulo "CA-02: a classificacao por severidade, do JSON"
auditar $DESVIOS_PORTA baseline.yaml json 2>/dev/null > /tmp/rst-ca02.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/rst-ca02.json"))
for x in d["conformidade"]:
    if x["veredito"] == "desvio":
        print("  {:8} {}".format(x["severidade"], x["regra"]))
print("  resumo por severidade:", d["resumo"]["por_severidade"])
PY
rm -f /tmp/rst-ca02.json

# ---------------------------------------------------------------- CA-03
titulo "CA-03: regra nao verificavel aparece separada de conforme"
printf 'O usuario da coleta e sem privilegio, e `sshd -T` exige root.\n\n'
auditar $DESVIOS_PORTA baseline.yaml json 2>/dev/null > /tmp/rst-ca03.json
python3 - <<'PY'
import json
d=json.load(open("/tmp/rst-ca03.json"))
for x in d["conformidade"]:
    if x["veredito"] == "nao_verificado":
        print("  regra     :", x["regra"])
        print("  esperado  :", x["esperado"])
        print("  encontrado:", x["encontrado"])
        print("  veredito  :", x["veredito"])
        print("  motivo    :", x["motivo"])
        print()
r = d["resumo"]
print("  conforme       :", r["conforme"])
print("  desvio         :", r["desvio"])
print("  nao_verificado :", r["nao_verificado"])
print("  -> nao_verificado NAO esta somado em conforme")
print("  -> no inventario, ssh.login_de_root =", d["inventario"]["ssh"]["login_de_root"])
PY
rm -f /tmp/rst-ca03.json

# ---------------------------------------------------------------- CA-04
titulo "CA-04: host inalcancavel: tres falhas, sem stack trace"
for caso in "porta sem SSH:19999:$CHAVES/auditor" \
            "chave recusada:$CONFORME_PORTA:$CHAVES/intruso" \
            "nome que nao resolve:22:$CHAVES/auditor"; do
  nome="${caso%%:*}"; resto="${caso#*:}"; porta="${resto%%:*}"; chave="${resto#*:}"
  destino=127.0.0.1
  [ "$nome" = "nome que nao resolve" ] && destino="host-que-nao-existe.invalid"
  printf '\n--- %s ---\n' "$nome"
  python3 "$FERRAMENTA" --host "$destino" --porta "$porta" --usuario "$USUARIO" \
      --chave "$chave" --baseline baseline.yaml --formato json 2>&1
  rc=$?
  printf 'codigo de saida: %s   (esperado 2)\n' "$rc"
done

printf '\n--- chave privada inexistente ---\n'
python3 "$FERRAMENTA" --host 127.0.0.1 --porta $CONFORME_PORTA --usuario "$USUARIO" \
    --chave /caminho/que/nao/existe --baseline baseline.yaml 2>&1
printf 'codigo de saida: %s   (esperado 2)\n' "$?"

# ---------------------------------------------------------------- CA-05
titulo "CA-05: a segunda execucao devolve o mesmo resultado"
auditar $DESVIOS_PORTA baseline.yaml json 2>/dev/null > /tmp/rst-1.json
sleep 2
auditar $DESVIOS_PORTA baseline.yaml json 2>/dev/null > /tmp/rst-2.json
python3 - <<'PY'
import json
a=json.load(open("/tmp/rst-1.json")); b=json.load(open("/tmp/rst-2.json"))
ia, ib = a["host"].pop("coletado_em"), b["host"].pop("coletado_em")
print(f"  instante da 1a coleta: {ia}")
print(f"  instante da 2a coleta: {ib}")
print(f"  os instantes diferem : {ia != ib}")
print()
va={x["regra"]:(x["veredito"],x.get("severidade")) for x in a["conformidade"]}
vb={x["regra"]:(x["veredito"],x.get("severidade")) for x in b["conformidade"]}
print(f"  mesmo veredito em todas as {len(va)} regras: {va == vb}")
print(f"  resto do documento identico             : {a == b}")
if a != b:
    for k in a:
        if a[k] != b[k]: print(f"    DIVERGE em: {k}")
PY
rm -f /tmp/rst-1.json /tmp/rst-2.json

# ---------------------------------------------------------------- RE-03
titulo "RE-03: a chave privada nao aparece em saida nenhuma"
PRIV="$(head -2 "$CHAVES/auditor" | tail -1 | cut -c1-40)"
TUDO="$( { auditar $DESVIOS_PORTA baseline.yaml ambos; \
           python3 "$FERRAMENTA" --host 127.0.0.1 --porta 19999 --usuario "$USUARIO" \
             --chave "$CHAVES/auditor" --baseline baseline.yaml; } 2>&1 )"
printf '  conteudo da chave na saida : %s\n' \
  "$(grep -qF "$PRIV" <<<"$TUDO" && echo 'ENCONTRADO: FALHA' || echo 'ausente')"
printf '  caminho da chave na saida  : %s\n' \
  "$(grep -qF "$CHAVES/auditor" <<<"$TUDO" && echo 'ENCONTRADO: FALHA' || echo 'ausente')"
printf '  "BEGIN OPENSSH PRIVATE KEY": %s\n' \
  "$(grep -qF 'BEGIN OPENSSH PRIVATE KEY' <<<"$TUDO" && echo 'ENCONTRADO: FALHA' || echo 'ausente')"
printf '  traceback na saida         : %s\n' \
  "$(grep -qF 'Traceback' <<<"$TUDO" && echo 'ENCONTRADO: FALHA' || echo 'ausente')"

printf '\n########## fim ##########\n'
} 2>&1 | tee "$SAIDA/validacao.txt"
