#!/usr/bin/env bash
# Validação do Ticket 04: CA-01 a CA-08.
#
# Pré-requisitos:
#   laboratorio/subir-workload.sh            (os quatro estados no cluster)
#   laboratorio/preparar-cenarios-de-falha.sh (os kubeconfigs quebrados)
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$AQUI/cluster-retrato/cluster_retrato.py"
LAB="${LAB:-$HOME/desafio03-lab/t04}"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

OK=0; FALHOU=0

verde()  { printf '  \033[32m[ok]\033[0m     %s\n' "$1"; OK=$((OK+1)); }
vermelho(){ printf '  \033[31m[FALHOU]\033[0m %s\n' "$1"; FALHOU=$((FALHOU+1)); }
titulo() { printf '\n=== %s\n' "$1"; }

# conferir <descricao> <arquivo> <padrao-grep-E>
conferir() {
  if grep -qE "$3" "$2"; then verde "$1"; else vermelho "$1 (não achei: $3)"; fi
}
negar() {
  if grep -qE "$3" "$2"; then vermelho "$1 (achei o que não devia: $3)"; else verde "$1"; fi
}

# texto <html> -> texto legível, para os greps não dependerem de marcação
texto() {
  python3 - "$1" <<'PY'
import html, re, sys
BLOCO = r"tr|table|thead|tbody|h1|h2|h3|div|p|footer|header|form|pre|br|option|li|ul"
t = open(sys.argv[1], encoding="utf-8").read()
t = re.sub(r"<style.*?</style>", "", t, flags=re.S)
# célula vira separador ANTES da remoção geral, para a linha da tabela ficar inteira
t = re.sub(r"(?i)</t[dh]>", " | ", t)
t = re.sub(rf"(?i)</?({BLOCO})\b[^>]*>", "\n", t)
t = re.sub(r"<[^>]+>", "", t)          # o resto sai sem quebrar linha
t = html.unescape(t)
print("\n".join(l.strip() for l in t.splitlines() if l.strip()))
PY
}

# roda a coleta uma vez com um kubeconfig e devolve o texto da tela
tela() {              # tela <kubeconfig|""> <namespace> <saida>
  local kc="$1" ns="$2" saida="$3"
  if [ -n "$kc" ]; then export KUBECONFIG="$kc"; else unset KUBECONFIG; fi
  python3 "$APP" --uma-vez --namespace "$ns" \
      --teto-externo 6 --teto-requisicao 3 > "$TMP/bruto.html" 2>"$TMP/bruto.err"
  local code=$?
  texto "$TMP/bruto.html" > "$saida"
  cat "$TMP/bruto.err" >> "$saida"
  unset KUBECONFIG
  return $code
}

printf 'Validação do Ticket 04: cluster-retrato\n'
printf 'data: %s\n' "$(date --iso-8601=seconds)"
printf 'kubectl: %s\n' "$(kubectl version --client -o json 2>/dev/null \
        | python3 -c 'import sys,json;print(json.load(sys.stdin)["clientVersion"]["gitVersion"])' 2>/dev/null)"
printf 'python: %s\n' "$(python3 --version)"

# ---------------------------------------------------------------- CA-08
titulo "CA-08: nenhum caminho do código executa verbo de escrita"
if python3 "$APP" --auditar > "$TMP/auditoria.txt" 2>&1; then
  verde "varredura do fonte: $(tail -1 "$TMP/auditoria.txt")"
else
  vermelho "varredura do fonte acusou: $(cat "$TMP/auditoria.txt")"
fi

if python3 -m unittest discover -s "$AQUI/cluster-retrato/testes" -p 'teste_*.py' \
     > "$TMP/testes.txt" 2>&1; then
  verde "testes de unidade: $(grep -oE 'Ran [0-9]+ tests' "$TMP/testes.txt") OK"
else
  vermelho "testes de unidade falharam"
  tail -20 "$TMP/testes.txt" | sed 's/^/      /'
fi

# ---------------------------------------------------------------- CA-01
titulo "CA-01: os seis itens do RF-02 contra o cluster real"
tela "" "nyx-prod" "$TMP/ca01.txt"
for secao in Namespaces Pods Deployments Services Eventos; do
  conferir "seção $secao presente" "$TMP/ca01.txt" "^${secao}"
done
conferir "filtro por namespace e busca por nome" "$TMP/ca01.txt" "buscar por nome|filtrar"
conferir "hora da coleta no cabeçalho"           "$TMP/ca01.txt" "coletado em"
conferir "contexto corrente no cabeçalho"        "$TMP/ca01.txt" "contexto"
conferir "fonte dos endpoints declarada"         "$TMP/ca01.txt" "contagem de endpoints via"
conferir "contagem de quebrados por namespace"   "$TMP/ca01.txt" "quebrados"

titulo "CA-01b: a tela responde por HTTP, em loopback por padrão"
PORTA=8787
python3 "$APP" --porta "$PORTA" > "$TMP/srv.out" 2>"$TMP/srv.err" &
SRV=$!
for _ in $(seq 1 40); do
  ss -ltn 2>/dev/null | grep -q ":$PORTA " && break
  sleep 0.25
done
if ss -ltn 2>/dev/null | grep -q "127.0.0.1:$PORTA "; then
  verde "escutando em 127.0.0.1 (loopback) por padrão"
else
  vermelho "não escutou em loopback: $(ss -ltn 2>/dev/null | grep ":$PORTA " || echo nada)"
fi
if python3 - "$PORTA" > "$TMP/http.html" 2>"$TMP/http.err" <<'PY'
import sys, urllib.request
with urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/?ns=nyx-prod&q=api",
                            timeout=40) as r:
    assert r.status == 200, r.status
    sys.stdout.write(r.read().decode())
PY
then
  texto "$TMP/http.html" > "$TMP/http.txt"
  verde "GET / respondeu 200"
  conferir "filtro da query string aplicado (só pod com 'api')" "$TMP/http.txt" "nyx-api"
  negar  "filtro excluiu o que não casa (postgres fora)" "$TMP/http.txt" "nyx-postgres-"
else
  vermelho "GET / falhou: $(head -3 "$TMP/http.err")"
fi
kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null

# ---------------------------------------------------------------- CA-02
titulo "CA-02: readyReplicas ausente aparece como 0/N, não como erro"
conferir "deployment nyx-api em 0/2"    "$TMP/ca01.txt" "nyx-api \| 0/2"
conferir "deployment saudável em 1/1"   "$TMP/ca01.txt" "nyx-postgres \| 1/1"
negar    "nenhum rastro de exceção"     "$TMP/ca01.txt" "Traceback|KeyError|TypeError"

# ---------------------------------------------------------------- CA-03
titulo "CA-03: Service por endpoints prontos/total, nos dois modos de vazio"
conferir "nyx-prod/nyx-api: 0/2, endpoints existem e não servem" \
         "$TMP/ca01.txt" "0/2 \| 2 endpoint\(s\) existem, nenhum pronto"
tela "" "nyx-stg" "$TMP/ca03.txt"
conferir "nyx-stg/nyx-api: 0/0, selector não casa" \
         "$TMP/ca03.txt" "0/0 \| nenhum pod casa com o selector"
negar    "chave ausente e chave nula não quebraram" \
         "$TMP/ca03.txt" "Traceback|KeyError|TypeError"

# ---------------------------------------------------------------- CA-04
titulo "CA-04: CrashLoopBackOff com OOMKilled, apesar de phase: Running"
conferir "estado e causa juntos na mesma linha" \
         "$TMP/ca01.txt" "CrashLoopBackOff \| OOMKilled"
tela "" "orion-stg" "$TMP/ca04b.txt"
conferir "ImagePullBackOff em orion-stg" "$TMP/ca04b.txt" "ImagePullBackOff"
conferir "a tag errada aparece no evento" "$TMP/ca04b.txt" "v1\.14\.2"

titulo "RF-03: prontidão presumida é marcada como presumida"
conferir "pod pronto sem probe é marcado" "$TMP/ca01.txt" "pronto \(sem probe\)"
conferir "a ressalva é explicada"         "$TMP/ca01.txt" "não está verificando"

# ---------------------------------------------------------------- CA-05
titulo "CA-05: cluster que não responde"
for caso in fora blackhole; do
  if [ -f "$LAB/kubeconfig-$caso.yaml" ]; then
    tela "$LAB/kubeconfig-$caso.yaml" "" "$TMP/ca05-$caso.txt"
    conferir "[$caso] rótulo cluster_inacessivel" "$TMP/ca05-$caso.txt" \
             "cluster_inacessivel"
    conferir "[$caso] mensagem explica"           "$TMP/ca05-$caso.txt" \
             "não respondeu"
    negar    "[$caso] sem rastro de exceção"      "$TMP/ca05-$caso.txt" "Traceback"
    conferir "[$caso] cabeçalho ainda presente"   "$TMP/ca05-$caso.txt" "coletado em"
    negar    "[$caso] sem ruído de diagnóstico do kubectl" \
             "$TMP/ca05-$caso.txt" "Unhandled Error"
  else
    vermelho "[$caso] kubeconfig ausente: rode preparar-cenarios-de-falha.sh"
  fi
done
if pgrep -af 'kubectl.*10\.255\.255\.1|kubectl.*59999' >/dev/null 2>&1; then
  vermelho "sobrou processo kubectl órfão após o estouro"
else
  verde "nenhum processo kubectl órfão após os estouros"
fi

# ---------------------------------------------------------------- CA-06
titulo "CA-06: credencial rejeitada, distinguível de cluster fora"
declare -A ESPERADO=(
  [token-invalido]=credencial_rejeitada
  [token-expirado]=credencial_rejeitada
  [cert-expirado]=credencial_rejeitada
  [exec-falha]=credencial_expirada
  [exec-ausente]=plugin_ausente
)
for caso in token-invalido token-expirado cert-expirado exec-falha exec-ausente; do
  arq="$LAB/kubeconfig-$caso.yaml"
  if [ ! -f "$arq" ]; then vermelho "[$caso] kubeconfig ausente"; continue; fi
  tela "$arq" "" "$TMP/ca06-$caso.txt"
  conferir "[$caso] rótulo ${ESPERADO[$caso]}" "$TMP/ca06-$caso.txt" \
           "${ESPERADO[$caso]}"
  negar    "[$caso] não foi confundido com cluster fora" "$TMP/ca06-$caso.txt" \
           "cluster_inacessivel"
  negar    "[$caso] sem rastro de exceção" "$TMP/ca06-$caso.txt" "Traceback"
done
conferir "401 NÃO é afirmado como expiração" "$TMP/ca06-token-expirado.txt" \
         "expirada, inválida ou revogada"
conferir "expiração É afirmada quando o provedor informa" "$TMP/ca06-exec-falha.txt" \
         "provedor de autenticação informou"

# ---------------------------------------------------------------- CA-07
titulo "CA-07: permissão negada em um tipo, os outros seguem na tela"
arq="$LAB/kubeconfig-restrito.yaml"
if [ -f "$arq" ]; then
  tela "$arq" "nyx-prod" "$TMP/ca07.txt"
  conferir "eventos aparecem como negados"   "$TMP/ca07.txt" "Permissão negada para eventos"
  conferir "o usuário negado é identificado" "$TMP/ca07.txt" "serviceaccount:default:retrato-restrito"
  conferir "a tela diz que o resto vale"     "$TMP/ca07.txt" "restante desta tela continua"
  conferir "pods continuam preenchidos"      "$TMP/ca07.txt" "CrashLoopBackOff"
  conferir "deployments continuam"           "$TMP/ca07.txt" "nyx-api \| 0/2"
  conferir "services continuam"              "$TMP/ca07.txt" "0/2 \| 2 endpoint"
  conferir "namespaces continuam"            "$TMP/ca07.txt" "nyx-prod"
  negar    "a falha NÃO derrubou a tela"     "$TMP/ca07.txt" "Não foi possível ler o cluster"
  negar    "sem rastro de exceção"           "$TMP/ca07.txt" "Traceback"
else
  vermelho "kubeconfig restrito ausente: rode preparar-cenarios-de-falha.sh"
fi

# ---------------------------------------------------------------- RE-01
titulo "RE-01: exposição na rede avisa que não há autenticação"
if python3 - "$APP" > "$TMP/aviso.txt" 2>&1 <<'PY'
import subprocess, sys, time
p = subprocess.Popen([sys.executable, sys.argv[1], "--endereco", "0.0.0.0",
                      "--porta", "8788"], stderr=subprocess.PIPE, text=True)
time.sleep(3)
p.terminate()
sys.stdout.write(p.communicate()[1] or "")
PY
then
  conferir "aviso de ausência de autenticação" "$TMP/aviso.txt" "NÃO TEM AUTENTICAÇÃO"
  conferir "aviso nomeia o endereço"           "$TMP/aviso.txt" "não é loopback"
else
  vermelho "não foi possível testar a exposição"
fi

# ----------------------------------------------------------------
printf '\n=========================================\n'
printf 'ok: %d   falhou: %d\n' "$OK" "$FALHOU"
printf '=========================================\n'
[ "$FALHOU" -eq 0 ] || exit 1
