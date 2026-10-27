#!/usr/bin/env python3
"""cluster-retrato: leitura do cluster corrente do kubeconfig.

Encurta os primeiros minutos de um chamado. NÃO substitui o terminal.

Só biblioteca padrão, por decisão do ADR-001. Toda conversa com o cluster passa pela
função `_kubectl`, que é o único ponto do arquivo que cria subprocesso e que carrega a
lista branca de verbos do ADR-002.

A aplicação NÃO TEM AUTENTICAÇÃO. Escuta em loopback por padrão.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# ADR-002: o portão. Lista branca ENUMERADA: prefixo novo é proibido por omissão.
#
# São PREFIXOS, não verbos soltos, por causa de `config`: `kubectl config` tem
# subcomando de escrita (que altera o kubeconfig), então liberar o verbo inteiro
# abriria mais do que o necessário. Só `config view` entra.
# ---------------------------------------------------------------------------
PREFIXOS_PERMITIDOS: frozenset[tuple[str, ...]] = frozenset({
    ("get",),
    ("version",),
    ("api-resources",),
    ("config", "view"),
})
VERBOS_PERMITIDOS = frozenset(p[0] for p in PREFIXOS_PERMITIDOS)

TETO_REQUISICAO_PADRAO = 8     # segundos, por requisição, passado ao kubectl
TETO_EXTERNO_PADRAO = 20       # segundos, pelo comando inteiro, imposto aqui

# Ruído de diagnóstico do kubectl. Detalhe de implementação dele, não vai para a tela.
_RUIDO = re.compile(r'^(E\d{4}\s|.*"Unhandled Error")')


class VerboProibido(RuntimeError):
    """Tentativa de executar comando fora da lista branca de prefixos."""

    def __init__(self, verbo: str) -> None:
        super().__init__(
            f"{verbo!r} não está na lista branca "
            f"{sorted(' '.join(p) for p in PREFIXOS_PERMITIDOS)}: "
            f"esta aplicação é somente leitura"
        )
        self.verbo = verbo


def _permitido(args: list[str]) -> bool:
    """Prefixo de 1 ou 2 palavras tem que estar na lista. Fechado por omissão."""
    return bool(args) and (
        tuple(args[:1]) in PREFIXOS_PERMITIDOS
        or tuple(args[:2]) in PREFIXOS_PERMITIDOS
    )


class Falha:
    """Falha de acesso ao cluster, já classificada."""

    def __init__(self, rotulo: str, detalhe: str, bruto: str = "") -> None:
        self.rotulo = rotulo
        self.detalhe = detalhe
        self.bruto = bruto

    @property
    def global_(self) -> bool:
        """Falha que derruba a coleta inteira, em vez de só uma consulta."""
        return self.rotulo not in {"permissao_negada"}

    def __repr__(self) -> str:  # pragma: no cover
        return f"Falha({self.rotulo!r})"


# ---------------------------------------------------------------------------
# Classificação de falha
# ---------------------------------------------------------------------------
# A ordem importa: ExpiredToken vem ANTES de credencial_rejeitada, porque o plugin
# externo é o único caso que diz o motivo, e perder isso é perder a informação boa.
_PADROES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "credencial_expirada",
        re.compile(r"expiredtoken|token (?:has |is )?expired|credentials?.*expired",
                   re.I),
        "A credencial expirou. O provedor de autenticação informou a expiração.",
    ),
    (
        "plugin_ausente",
        re.compile(r"executable .* not found|credential plugin that is not installed",
                   re.I),
        "O kubeconfig usa um plugin de autenticação que não está instalado nesta "
        "estação.",
    ),
    (
        "plugin_falhou",
        re.compile(r"getting credentials: exec", re.I),
        "O plugin de autenticação do kubeconfig falhou.",
    ),
    (
        "credencial_rejeitada",
        re.compile(r"you must be logged in to the server|\(unauthorized\)", re.I),
        "O cluster rejeitou a credencial (401). Ela pode estar expirada, inválida ou "
        "revogada: o kubectl devolve a mesma mensagem nos três casos, então esta tela "
        "não afirma qual é. Confirme com <code>kubectl auth whoami</code>.",
    ),
    (
        "tls_desconhecido",
        re.compile(r"certificate signed by unknown authority|failed to verify certificate",
                   re.I),
        "O certificado do servidor não foi aceito. A autoridade certificadora do "
        "kubeconfig não confere com a do cluster.",
    ),
    (
        "cluster_inacessivel",
        re.compile(r"connection to the server .* was refused|connection refused"
                   r"|context deadline exceeded|no route to host|i/o timeout"
                   r"|unable to connect to the server|no such host", re.I),
        "O cluster não respondeu.",
    ),
    (
        "permissao_negada",
        re.compile(r"\(forbidden\)|is forbidden:", re.I),
        "O contexto corrente não tem permissão de leitura sobre este tipo de recurso.",
    ),
    (
        "configuracao_invalida",
        re.compile(r"error in configuration|context was not found", re.I),
        "O kubeconfig está inconsistente.",
    ),
)


def limpar_ruido(texto: str) -> str:
    """Remove as linhas de diagnóstico interno do kubectl."""
    uteis = [l for l in texto.splitlines() if l.strip() and not _RUIDO.match(l)]
    return "\n".join(uteis).strip()


def classificar(stderr: str) -> Falha:
    """Transforma a saída de erro do kubectl em falha rotulada.

    Quando nada casa, devolve `nao_classificada` com o texto original. Admitir
    ignorância é melhor que arriscar um rótulo errado: mesma escolha do
    `nao_verificado` do Ticket 03.
    """
    limpo = limpar_ruido(stderr)
    for rotulo, padrao, detalhe in _PADROES:
        if padrao.search(limpo):
            return Falha(rotulo, detalhe, limpo)
    return Falha(
        "nao_classificada",
        "A falha não casou com nenhum padrão conhecido. A saída de erro original está "
        "abaixo, sem interpretação.",
        limpo or "(o kubectl não escreveu nada em stderr)",
    )


def usuario_negado(bruto: str) -> str:
    """Extrai o usuário da mensagem de Forbidden, quando ela o traz."""
    m = re.search(r'User "([^"]+)"', bruto)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# ADR-002: único ponto do arquivo que cria subprocesso
# ---------------------------------------------------------------------------
def _kubectl(
    args: list[str],
    teto_externo: int = TETO_EXTERNO_PADRAO,
    teto_requisicao: int = TETO_REQUISICAO_PADRAO,
    kubeconfig: str | None = None,
) -> tuple[dict | str | None, Falha | None]:
    """Executa kubectl com verbo da lista branca. Devolve (dados, falha).

    Dois tetos de tempo, porque um não basta: medido contra endereço não roteável,
    `--request-timeout=5s` sozinho levou 25s, e sem ele o kubectl passou de 70s.
    O `--request-timeout` limita cada requisição, não o comando.
    """
    if not _permitido(args):
        raise VerboProibido(" ".join(args[:2]) if args else "<vazio>")

    cmd = ["kubectl", *args, f"--request-timeout={teto_requisicao}s"]
    env = dict(os.environ)
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig

    # start_new_session para que o estouro mate o GRUPO: matar só o PID deixa órfão.
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env, start_new_session=True,
    )
    try:
        saida, erro = proc.communicate(timeout=teto_externo)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):  # pragma: no cover
            proc.kill()
        proc.communicate()
        return None, Falha(
            "cluster_inacessivel",
            f"O cluster não respondeu dentro de {teto_externo}s e a consulta foi "
            f"encerrada.",
            f"estourou o teto externo de {teto_externo}s em: kubectl {' '.join(args)}",
        )

    if proc.returncode != 0:
        return None, classificar(erro)

    if "-o" in args or "--output" in args:
        try:
            return json.loads(saida), None
        except json.JSONDecodeError as e:
            return None, Falha(
                "resposta_ilegivel",
                "O kubectl respondeu com sucesso mas a saída não é JSON válido.",
                f"{e}\n{saida[:400]}",
            )
    return saida, None


# ---------------------------------------------------------------------------
# ADR-004: qual fonte de endpoint este cluster oferece
# ---------------------------------------------------------------------------
def detectar_fonte_de_endpoints(**kw) -> tuple[str, Falha | None]:
    """Decide entre EndpointSlice e Endpoints. Roda UMA vez, na subida."""
    saida, falha = _kubectl(["api-resources", "--api-group=discovery.k8s.io",
                             "--no-headers"], **kw)
    if falha is not None:
        return "endpoints", falha
    if isinstance(saida, str) and "endpointslice" in saida.lower():
        return "endpointslices", None
    return "endpoints", None


# ---------------------------------------------------------------------------
# Normalização: funções puras. Aqui vivem os fatos estranhos da API.
# ---------------------------------------------------------------------------
def normalizar_endpoints(itens: list[dict], fonte: str) -> dict[tuple[str, str], dict]:
    """Conta endpoints PRONTOS sobre total, das duas fontes, na mesma estrutura.

    Medido contra o cluster, quatro estados:
      - saudável            -> subsets com addresses        | 1 endpoint ready=true
      - selector não casa   -> chave `subsets` AUSENTE      | chave presente, valor null
      - CrashLoopBackOff    -> subsets PRESENTE, notReady    | endpoints ready=false
      - ImagePullBackOff    -> subsets PRESENTE, notReady    | endpoints ready=false

    Por isso a conta é prontos/total e não um sim/não: contar endpoints acusa só o
    caso do selector, e passa batido nos outros dois.
    """
    fora: dict[tuple[str, str], dict] = {}

    for item in itens:
        meta = item.get("metadata") or {}
        ns = meta.get("namespace", "")

        if fonte == "endpointslices":
            # A ligação com o Service é pelo RÓTULO, nunca pelo nome: o slice se
            # chama <service>-<hash>. E um Service pode ter vários slices.
            svc = (meta.get("labels") or {}).get("kubernetes.io/service-name")
            if not svc:
                continue
            # get(..., []) NÃO salva do null; "or []" sozinho não salva da ausência.
            eps = item.get("endpoints") or []
            prontos = sum(1 for e in eps
                          if ((e.get("conditions") or {}).get("ready") is True))
            total = len(eps)
        else:
            svc = meta.get("name")
            if not svc:
                continue
            prontos = total = 0
            for sub in item.get("subsets") or []:
                p = len(sub.get("addresses") or [])
                n = len(sub.get("notReadyAddresses") or [])
                prontos += p
                total += p + n

        acc = fora.setdefault((ns, svc), {"prontos": 0, "total": 0, "fonte": fonte})
        acc["prontos"] += prontos
        acc["total"] += total

    return fora


def _tem_probe(spec: dict) -> bool:
    """readinessProbe em algum container principal.

    initContainers NÃO contam: probe neles não diz nada sobre o container principal.
    """
    return any(c.get("readinessProbe") for c in (spec.get("containers") or []))


def normalizar_pod(pod: dict) -> dict:
    """Extrai estado, causa, reinícios e prontidão de um pod.

    `status.phase` NÃO é o indicador principal: medido no Ticket 02, pod com
    container em CrashLoopBackOff tem `phase: Running`. Quem lê phase vê tudo verde.
    """
    meta = pod.get("metadata") or {}
    spec = pod.get("spec") or {}
    status = pod.get("status") or {}
    cs = status.get("containerStatuses") or []

    estado = causa = historico = ""
    # 1. por que está esperando: CrashLoopBackOff, ImagePullBackOff, ...
    for c in cs:
        espera = (c.get("state") or {}).get("waiting") or {}
        if espera.get("reason"):
            estado = espera["reason"]
            break
    # 2. por que morreu na última vez: OOMKilled, Error, ...
    #
    # ATENÇÃO: isto só é a CAUSA do chamado se o container NÃO está rodando agora.
    # A skill de triagem do Ticket 02 tem a regra escrita: `state: running` significa
    # que `lastState` é história. A primeira versão desta função ignorava a regra que o
    # próprio projeto cita, e pintava de vermelho a causa de qualquer pod com
    # `lastState`. Medido no cluster de laboratório: 16 células vermelhas em pods
    # saudáveis contra 2 legítimas. Reinício de nó deixa `reason: Unknown` em tudo.
    for c in cs:
        morte = (c.get("lastState") or {}).get("terminated") or {}
        if not morte.get("reason"):
            continue
        # PRESENÇA da chave, não veracidade: `running: {}` sem `startedAt` continua
        # sendo "está rodando", e `bool({})` é False. Mesma armadilha do
        # `endpoints: null` que o ADR-004 documenta, agora do lado de dentro.
        rodando = "running" in (c.get("state") or {})
        if rodando:
            historico = historico or morte["reason"]
        else:
            causa = causa or morte["reason"]
    # 3. nem agendou: a condição carrega a explicação
    if not estado:
        for cond in status.get("conditions") or []:
            if cond.get("status") == "False" and cond.get("message"):
                estado = cond.get("reason") or "NaoPronto"
                causa = cond["message"]
                break
    # 4. último recurso
    if not estado:
        estado = status.get("phase", "?")

    prontos = sum(1 for c in cs if c.get("ready"))
    total = len(spec.get("containers") or [])
    tem_probe = _tem_probe(spec)
    todos_prontos = total > 0 and prontos == total

    if todos_prontos:
        prontidao = "pronto" if tem_probe else "pronto_sem_probe"
    else:
        prontidao = "nao_pronto"

    fase = status.get("phase", "?")
    quebrado = not todos_prontos and fase not in {"Succeeded"}

    return {
        "namespace": meta.get("namespace", ""),
        "nome": meta.get("name", ""),
        "fase": fase,
        "estado": estado,
        "causa": causa,
        "historico": historico,
        "reinicios": sum(c.get("restartCount") or 0 for c in cs),
        "prontos": prontos,
        "total": total,
        "prontidao": prontidao,
        "quebrado": quebrado,
    }


def normalizar_deployment(dep: dict) -> dict:
    """`status.readyReplicas` NÃO vem quando é zero. `spec.replicas` omitido vale 1."""
    meta = dep.get("metadata") or {}
    prontas = (dep.get("status") or {}).get("readyReplicas") or 0
    desejadas = (dep.get("spec") or {}).get("replicas")
    if desejadas is None:
        desejadas = 1
    return {
        "namespace": meta.get("namespace", ""),
        "nome": meta.get("name", ""),
        "prontas": prontas,
        "desejadas": desejadas,
        "quebrado": prontas < desejadas,
    }


def normalizar_servico(svc: dict, endpoints: dict) -> dict:
    meta = svc.get("metadata") or {}
    ns, nome = meta.get("namespace", ""), meta.get("name", "")
    conta = endpoints.get((ns, nome))
    tipo = (svc.get("spec") or {}).get("type", "ClusterIP")
    tem_selector = bool((svc.get("spec") or {}).get("selector"))
    if conta is None:
        prontos = total = 0
        sabido = False
    else:
        prontos, total, sabido = conta["prontos"], conta["total"], True
    # ExternalName não tem endpoint por natureza: não é defeito.
    quebrado = sabido and prontos == 0 and tipo != "ExternalName"
    return {
        "namespace": ns, "nome": nome, "tipo": tipo,
        "prontos": prontos, "total": total,
        "sabido": sabido, "tem_selector": tem_selector,
        "quebrado": quebrado,
        # 0/0 e 0/N contam histórias diferentes: um é selector que não casa,
        # o outro é pod que existe e não está pronto.
        "diagnostico": (
            "" if not quebrado else
            ("nenhum pod casa com o selector" if total == 0 and tem_selector else
             "sem selector e sem endpoint manual" if total == 0 else
             f"{total} endpoint(s) existem, nenhum pronto")
        ),
    }


def normalizar_evento(ev: dict) -> dict:
    return {
        "tipo": ev.get("type", ""),
        "motivo": ev.get("reason", ""),
        "objeto": "/".join(x for x in [(ev.get("involvedObject") or {}).get("kind", ""),
                                       (ev.get("involvedObject") or {}).get("name", "")]
                           if x),
        "mensagem": (ev.get("message") or "").strip(),
        "vezes": ev.get("count") or 1,
        "quando": ev.get("lastTimestamp") or ev.get("eventTime") or "",
    }


def contar_por_namespace(namespaces: list[str], pods: list[dict],
                         deployments: list[dict], servicos: list[dict]) -> dict:
    conta = {ns: {"pods": 0, "deployments": 0, "servicos": 0, "total": 0}
             for ns in namespaces}
    for grupo, chave in ((pods, "pods"), (deployments, "deployments"),
                         (servicos, "servicos")):
        for item in grupo:
            ns = item["namespace"]
            if ns not in conta or not item["quebrado"]:
                continue
            conta[ns][chave] += 1
            conta[ns]["total"] += 1
    return conta


# ---------------------------------------------------------------------------
# Coleta
# ---------------------------------------------------------------------------
def coletar(fonte: str, ns: str = "", **kw) -> dict:
    """As seis consultas do ADR-005. Falha por consulta, não falha global.

    Exceção: se a PRIMEIRA consulta falhar com algo global (cluster fora, credencial),
    as outras cinco são puladas: repetir seis vezes uma falha de conexão custa seis
    estouros de teto.
    """
    estado: dict = {
        "coletado_em": datetime.now().astimezone(),
        "fonte_endpoints": fonte,
        "falha_global": None,
        "falhas": {},
        "namespaces": [], "pods": [], "deployments": [], "servicos": [],
        "eventos": [], "ns_selecionado": ns,
    }

    crus, falha = _kubectl(["get", "namespaces", "-o", "json"], **kw)
    if falha is not None:
        if falha.global_:
            estado["falha_global"] = falha
            return estado
        estado["falhas"]["namespaces"] = falha
    else:
        estado["namespaces"] = sorted(
            (i.get("metadata") or {}).get("name", "") for i in crus.get("items") or []
        )

    consultas = (
        ("pods", ["get", "pods", "-A", "-o", "json"]),
        ("deployments", ["get", "deployments", "-A", "-o", "json"]),
        ("servicos", ["get", "services", "-A", "-o", "json"]),
        ("endpoints", ["get", fonte, "-A", "-o", "json"]),
    )
    brutos: dict[str, list] = {}
    for chave, args in consultas:
        crus, falha = _kubectl(args, **kw)
        if falha is not None:
            if falha.global_ and estado["falha_global"] is None and not brutos:
                estado["falha_global"] = falha
                return estado
            estado["falhas"][chave] = falha
            brutos[chave] = []
        else:
            brutos[chave] = crus.get("items") or []

    mapa_eps = normalizar_endpoints(brutos.get("endpoints", []), fonte)
    estado["pods"] = [normalizar_pod(p) for p in brutos.get("pods", [])]
    estado["deployments"] = [normalizar_deployment(d)
                             for d in brutos.get("deployments", [])]
    estado["servicos"] = [normalizar_servico(s, mapa_eps)
                          for s in brutos.get("servicos", [])]
    estado["contagem"] = contar_por_namespace(
        estado["namespaces"], estado["pods"], estado["deployments"],
        estado["servicos"])

    # 6ª consulta: só com namespace selecionado. `get events -A` é a consulta mais
    # cara da lista e quase sempre inútil.
    if ns:
        crus, falha = _kubectl(["get", "events", "-n", ns, "-o", "json"], **kw)
        if falha is not None:
            estado["falhas"]["eventos"] = falha
        else:
            eventos = [normalizar_evento(e) for e in crus.get("items") or []]
            estado["eventos"] = sorted(eventos, key=lambda e: e["quando"],
                                       reverse=True)[:40]
    return estado


def versao_do_cluster(**kw) -> str:
    """Versão do servidor. Informação de triagem de verdade: k3s não é EKS.

    Falha aqui não impede a aplicação de subir: o CA-05 exige que a tela explique a
    falha, e para isso o servidor HTTP precisa estar no ar.
    """
    dados, falha = _kubectl(["version", "-o", "json"], **kw)
    if falha is not None or not isinstance(dados, dict):
        return "?"
    return ((dados.get("serverVersion") or {}).get("gitVersion") or "?")


def contexto_corrente(**kw) -> tuple[str, str]:
    """Nome do contexto corrente e endereço do servidor DELE.

    Usa `kubectl config view --minify`, e não leitura do arquivo, por dois motivos
    que a primeira versão errou:

    1. a primeira versão pegava o primeiro `server:` do arquivo, que num kubeconfig
       com vários clusters é o servidor ERRADO. Ela anunciou um endpoint de EKS
       enquanto lia um cluster k3d local. Um painel que mente sobre qual cluster
       está lendo é pior que um painel que não diz nada
    2. `KUBECONFIG` aceita vários arquivos separados por `:` e o kubectl os mescla.
       Reimplementar essa mesclagem é trabalho sem motivo

    `--minify` reduz à vista do contexto corrente. Sem `--raw`, o kubectl ainda
    omite certificado e chave da saída, o que é bom: eu não quero esses bytes.
    `config view` não fala com o cluster, então é rápido mesmo com o cluster fora.
    """
    dados, falha = _kubectl(["config", "view", "--minify", "-o", "json"], **kw)
    del falha
    if not isinstance(dados, dict):
        return "?", "?"
    nome = dados.get("current-context") or "?"
    clusters = dados.get("clusters") or []
    servidor = "?"
    if clusters:
        servidor = (clusters[0].get("cluster") or {}).get("server") or "?"
    return nome, servidor


# ---------------------------------------------------------------------------
# Tela: HTML montado no servidor, zero JavaScript (ADR-001)
# ---------------------------------------------------------------------------
E = html.escape

_CSS = """
:root{--fg:#1b1f23;--mu:#6a737d;--bd:#d8dee4;--bg:#fff;--ruim:#b3261e;
       --morno:#8a6116;--bom:#1a7f37;--caixa:#f6f8fa}
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
     color:var(--fg);background:var(--bg);margin:0;padding:1.5rem}
header{border-bottom:2px solid var(--bd);padding-bottom:.75rem;margin-bottom:1.25rem}
h1{font-size:1.25rem;margin:0 0 .35rem}
h2{font-size:1rem;margin:1.75rem 0 .5rem;padding-bottom:.25rem;
   border-bottom:1px solid var(--bd)}
.mu{color:var(--mu);font-size:.85rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0;font-size:.88rem}
th,td{text-align:left;padding:.3rem .5rem;border-bottom:1px solid var(--bd);
      vertical-align:top}
th{font-weight:600;background:var(--caixa);white-space:nowrap}
.ruim{color:var(--ruim);font-weight:600}
.bom{color:var(--bom)}
.morno{color:var(--morno)}
.nota{background:var(--caixa);border-left:3px solid var(--bd);
      padding:.6rem .8rem;margin:.6rem 0;border-radius:3px}
.nota.erro{border-left-color:var(--ruim)}
.nota.aviso{border-left-color:var(--morno)}
form{margin:.5rem 0}
input,select,button{font:inherit;padding:.25rem .4rem;border:1px solid var(--bd);
                    border-radius:3px}
button{background:var(--caixa);cursor:pointer}
code{background:var(--caixa);padding:.05rem .3rem;border-radius:3px;font-size:.85em}
pre{background:var(--caixa);padding:.6rem;border-radius:3px;overflow-x:auto;
    font-size:.8rem;white-space:pre-wrap;word-break:break-word}
a{color:#0969da}
footer{margin-top:2rem;padding-top:.75rem;border-top:1px solid var(--bd)}
.vazio{color:var(--mu);font-style:italic;padding:.4rem 0}
"""


def _pagina(corpo: str, titulo: str = "cluster-retrato") -> bytes:
    return (f"<!DOCTYPE html><html lang=pt-BR><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{E(titulo)}</title><style>{_CSS}</style></head>"
            f"<body>{corpo}</body></html>").encode("utf-8")


def _cabecalho(estado: dict, ctx: str, servidor: str, versao: str = "?") -> str:
    """Contexto, servidor e HORA DA COLETA. Presente inclusive na tela de falha."""
    quando = estado["coletado_em"].strftime("%d/%m/%Y %H:%M:%S %Z")
    return (
        f"<header><h1>cluster-retrato</h1>"
        f"<div class=mu>contexto <code>{E(ctx)}</code> &middot; "
        f"servidor <code>{E(servidor)}</code> &middot; "
        f"versão <code>{E(versao)}</code></div>"
        f"<div class=mu>coletado em <strong>{E(quando)}</strong> &middot; "
        f"consulta sob demanda: recarregue para atualizar</div></header>"
    )


def _bloco_falha(falha: Falha, titulo: str) -> str:
    bruto = (f"<pre>{E(falha.bruto)}</pre>" if falha.bruto else "")
    return (f"<div class='nota erro'><strong>{E(titulo)}</strong><br>"
            f"{falha.detalhe}<br><span class=mu>rótulo: "
            f"<code>{E(falha.rotulo)}</code></span>{bruto}</div>")


def _formulario(estado: dict, q: str) -> str:
    opcoes = "<option value=''>(todos os namespaces)</option>" + "".join(
        f"<option value='{E(ns)}'"
        f"{' selected' if ns == estado['ns_selecionado'] else ''}>{E(ns)}</option>"
        for ns in estado["namespaces"])
    return (f"<form method=get><select name=ns>{opcoes}</select> "
            f"<input name=q placeholder='buscar por nome' value='{E(q)}'> "
            f"<button type=submit>filtrar</button> "
            f"<a href='/' class=mu>limpar</a></form>")


def _filtrar(itens: list[dict], ns: str, q: str) -> list[dict]:
    fora = itens
    if ns:
        fora = [i for i in fora if i["namespace"] == ns]
    if q:
        alvo = q.lower()
        fora = [i for i in fora if alvo in i["nome"].lower()]
    return fora


def _tabela_namespaces(estado: dict) -> str:
    conta = estado.get("contagem") or {}
    if not estado["namespaces"]:
        return "<p class=vazio>nenhum namespace legível</p>"
    linhas = []
    for ns in estado["namespaces"]:
        c = conta.get(ns, {"pods": 0, "deployments": 0, "servicos": 0, "total": 0})
        classe = "ruim" if c["total"] else "bom"
        marca = f"<span class={classe}>{c['total']}</span>"
        linhas.append(
            f"<tr><td><a href='?ns={urllib.parse.quote(ns)}'>{E(ns)}</a></td>"
            f"<td>{marca}</td><td>{c['pods']}</td><td>{c['deployments']}</td>"
            f"<td>{c['servicos']}</td></tr>")
    return ("<table><tr><th>namespace</th><th>quebrados</th><th>pods</th>"
            "<th>deployments</th><th>services</th></tr>"
            + "".join(linhas) + "</table>")


def _tabela_pods(pods: list[dict]) -> str:
    if not pods:
        return "<p class=vazio>nenhum pod no recorte atual</p>"
    linhas = []
    sem_probe = tem_historico = False
    for p in sorted(pods, key=lambda x: (not x["quebrado"], x["namespace"], x["nome"])):
        if p["prontidao"] == "pronto_sem_probe":
            sem_probe = True
            pronto = (f"<span class=morno>{p['prontos']}/{p['total']} "
                      f"pronto (sem probe)</span>")
        elif p["prontidao"] == "pronto":
            pronto = f"<span class=bom>{p['prontos']}/{p['total']}</span>"
        else:
            pronto = f"<span class=ruim>{p['prontos']}/{p['total']}</span>"
        estado_txt = (f"<span class=ruim>{E(p['estado'])}</span>"
                      if p["quebrado"] else E(p["estado"]))
        # Causa do chamado em vermelho; terminação antiga de container que voltou a
        # rodar em cinza, marcada como histórico. São coisas diferentes.
        if p["causa"]:
            causa = f"<span class=ruim>{E(p['causa'])}</span>"
        elif p.get("historico"):
            causa = (f"<span class=mu>{E(p['historico'])} (histórico)</span>")
            tem_historico = True
        else:
            causa = ""
        rein = (f"<span class=morno>{p['reinicios']}</span>"
                if p["reinicios"] else "0")
        linhas.append(
            f"<tr><td>{E(p['namespace'])}</td><td>{E(p['nome'])}</td>"
            f"<td>{pronto}</td><td>{estado_txt}</td><td>{causa}</td>"
            f"<td>{rein}</td></tr>")
    nota = ("<div class='nota aviso'><strong>pronto (sem probe)</strong> significa que o "
            "container subiu e que <em>nenhuma readinessProbe está declarada</em>: "
            "o Kubernetes não está verificando se a aplicação responde. "
            "É prontidão presumida, não verificada.</div>") if sem_probe else ""
    nota_hist = ("<div class=nota><strong>(histórico)</strong> é terminação anterior de um "
                 "container que <em>voltou a rodar</em>. Não é a causa de um chamado "
                 "aberto agora: reinício de nó deixa esse campo preenchido em tudo. "
                 "Vermelho só quando o container não está rodando.</div>"
                 ) if tem_historico else ""
    return ("<table><tr><th>namespace</th><th>pod</th><th>prontos</th><th>estado</th>"
            "<th>causa</th><th>reinícios</th></tr>" + "".join(linhas) + "</table>"
            + nota + nota_hist)


def _tabela_deployments(deps: list[dict]) -> str:
    if not deps:
        return "<p class=vazio>nenhum deployment no recorte atual</p>"
    linhas = []
    for d in sorted(deps, key=lambda x: (not x["quebrado"], x["namespace"], x["nome"])):
        classe = "ruim" if d["quebrado"] else "bom"
        linhas.append(
            f"<tr><td>{E(d['namespace'])}</td><td>{E(d['nome'])}</td>"
            f"<td class={classe}>{d['prontas']}/{d['desejadas']}</td></tr>")
    return ("<table><tr><th>namespace</th><th>deployment</th><th>prontas/desejadas</th>"
            "</tr>" + "".join(linhas) + "</table>")


def _tabela_servicos(svcs: list[dict], fonte: str) -> str:
    if not svcs:
        return "<p class=vazio>nenhum service no recorte atual</p>"
    linhas = []
    for s in sorted(svcs, key=lambda x: (not x["quebrado"], x["namespace"], x["nome"])):
        if not s["sabido"]:
            conta = "<span class=mu>?</span>"
        else:
            classe = "ruim" if s["quebrado"] else "bom"
            conta = f"<span class={classe}>{s['prontos']}/{s['total']}</span>"
        linhas.append(
            f"<tr><td>{E(s['namespace'])}</td><td>{E(s['nome'])}</td>"
            f"<td>{E(s['tipo'])}</td><td>{conta}</td>"
            f"<td>{E(s['diagnostico'])}</td></tr>")
    return ("<table><tr><th>namespace</th><th>service</th><th>tipo</th>"
            "<th>endpoints prontos/total</th><th>diagnóstico</th></tr>"
            + "".join(linhas) + "</table>"
            + f"<div class=mu>contagem de endpoints via <code>{E(fonte)}</code>"
            + ("" if fonte == "endpointslices" else
               ": nesta fonte <code>terminating</code> não é distinguido")
            + "</div>")


def _tabela_eventos(estado: dict) -> str:
    if "eventos" in estado["falhas"]:
        falha = estado["falhas"]["eventos"]
        extra = ""
        if falha.rotulo == "permissao_negada":
            quem = usuario_negado(falha.bruto)
            extra = (f" Usuário identificado pelo cluster: <code>{E(quem)}</code>."
                     if quem else "")
            return (f"<div class='nota erro'><strong>Permissão negada para eventos."
                    f"</strong> {falha.detalhe}{extra} O restante desta tela continua "
                    f"válido.<pre>{E(falha.bruto)}</pre></div>")
        return _bloco_falha(falha, "Falha ao ler eventos")
    if not estado["ns_selecionado"]:
        return ("<p class=vazio>selecione um namespace para ver os eventos: "
                "<code>get events -A</code> é a consulta mais cara e quase sempre "
                "inútil</p>")
    if not estado["eventos"]:
        return "<p class=vazio>nenhum evento recente neste namespace</p>"
    linhas = []
    for e in estado["eventos"]:
        classe = "ruim" if e["tipo"] == "Warning" else ""
        linhas.append(
            f"<tr><td class={classe}>{E(e['tipo'])}</td><td>{E(e['motivo'])}</td>"
            f"<td>{E(e['objeto'])}</td><td>{E(e['mensagem'])}</td>"
            f"<td>{e['vezes']}</td><td class=mu>{E(e['quando'])}</td></tr>")
    return ("<table><tr><th>tipo</th><th>motivo</th><th>objeto</th><th>mensagem</th>"
            "<th>vezes</th><th>quando</th></tr>" + "".join(linhas) + "</table>")


def renderizar(estado: dict, ctx: str, servidor: str, q: str = "",
               versao: str = "?") -> bytes:
    """Estrutura interna vira HTML. Não fala com o cluster."""
    cab = _cabecalho(estado, ctx, servidor, versao)

    if estado["falha_global"] is not None:
        return _pagina(
            cab
            + _bloco_falha(estado["falha_global"], "Não foi possível ler o cluster")
            + "<div class=nota>A aplicação está no ar. O problema está no acesso ao "
              "cluster, não na aplicação. Corrija o contexto ou a credencial e "
              "recarregue.</div>",
            "cluster-retrato: falha de acesso")

    ns = estado["ns_selecionado"]
    partes = [cab, _formulario(estado, q)]

    for chave, titulo in (("namespaces", "Falha ao ler namespaces"),
                          ("pods", "Falha ao ler pods"),
                          ("deployments", "Falha ao ler deployments"),
                          ("servicos", "Falha ao ler services"),
                          ("endpoints", "Falha ao ler endpoints")):
        if chave in estado["falhas"]:
            falha = estado["falhas"][chave]
            if falha.rotulo == "permissao_negada":
                quem = usuario_negado(falha.bruto)
                partes.append(
                    f"<div class='nota erro'><strong>Permissão negada: {E(chave)}."
                    f"</strong> {falha.detalhe}"
                    + (f" Usuário: <code>{E(quem)}</code>." if quem else "")
                    + f" As outras seções continuam válidas."
                      f"<pre>{E(falha.bruto)}</pre></div>")
            else:
                partes.append(_bloco_falha(falha, titulo))

    partes += [
        "<h2>Namespaces</h2>", _tabela_namespaces(estado),
        "<h2>Pods</h2>", _tabela_pods(_filtrar(estado["pods"], ns, q)),
        "<h2>Deployments</h2>",
        _tabela_deployments(_filtrar(estado["deployments"], ns, q)),
        "<h2>Services</h2>",
        _tabela_servicos(_filtrar(estado["servicos"], ns, q),
                         estado["fonte_endpoints"]),
        f"<h2>Eventos{': ' + E(ns) if ns else ''}</h2>", _tabela_eventos(estado),
        "<footer><div class=mu>somente leitura: comandos permitidos "
        f"<code>kubectl "
        f"{E(' | '.join(sorted(' '.join(p) for p in PREFIXOS_PERMITIDOS)))}</code>. "
        "Isto encurta os primeiros minutos de um chamado e não substitui o "
        "terminal.</div></footer>",
    ]
    return _pagina("".join(partes))


# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "cluster-retrato"
    opcoes: dict = {}

    def do_GET(self) -> None:  # noqa: N802
        caminho = urllib.parse.urlparse(self.path)
        if caminho.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        if caminho.path not in ("/", "/index.html"):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"nao encontrado\n")
            return

        params = urllib.parse.parse_qs(caminho.query)
        ns = (params.get("ns") or [""])[0].strip()
        q = (params.get("q") or [""])[0].strip()
        o = self.opcoes
        kw = {"teto_externo": o["teto_externo"],
              "teto_requisicao": o["teto_requisicao"]}

        try:
            estado = coletar(o["fonte"], ns, **kw)
            corpo = renderizar(estado, o["contexto"], o["servidor"], q,
                               o.get("versao", "?"))
        except VerboProibido as e:
            # Não deveria acontecer nunca. Se acontecer, é defeito, e aparece como tal.
            corpo = _pagina(
                f"<div class='nota erro'><strong>Defeito na aplicação.</strong> "
                f"{E(str(e))}</div>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def _loopback(endereco: str) -> bool:
    return endereco in {"127.0.0.1", "::1", "localhost"} \
        or endereco.startswith("127.")


# ---------------------------------------------------------------------------
# CA-08: a varredura do próprio fonte
# ---------------------------------------------------------------------------
VERBOS_DE_ESCRITA = frozenset({
    "annotate", "attach", "auth", "autoscale", "certificate", "cordon", "cp",
    "debug", "delete", "drain", "edit", "evict", "expose", "label", "patch",
    "proxy", "replace", "rollout", "run", "scale", "set", "taint", "uncordon",
    "apply", "create", "exec", "port-forward",
})


def auditar_fonte(caminho: str) -> list[str]:
    """Varre o fonte: nenhum literal igual a verbo de escrita, e subprocesso só em
    `_kubectl`.

    Um verbo só chega ao kubectl como string. Então a checagem é sobre os literais,
    via AST: mais preciso que grep, que acusaria `frozenset` por conter "set".
    """
    with open(caminho, encoding="utf-8") as fh:
        arvore = ast.parse(fh.read(), filename=caminho)
    problemas: list[str] = []

    # Duas isenções, as duas declaradas. Na primeira vez que esta varredura rodou ela
    # acusou o literal 'run' do conjunto `perigosos`, aqui dentro: verdadeiro
    # positivo da regra aplicado ao vocabulário do próprio auditor. A saída não é
    # encurtar a lista de verbos; é isentar o auditor, que não chama kubectl e que
    # continua coberto pela checagem 2.
    isento: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "VERBOS_DE_ESCRITA"
                for t in no.targets):
            isento.update(id(f) for f in ast.walk(no.value))
        if (isinstance(no, ast.FunctionDef) and no.name == "auditar_fonte"):
            isento.update(id(f) for f in ast.walk(no))

    # 1. nenhum literal de string igual a um verbo de escrita.
    # Um verbo só chega ao kubectl como string, então a checagem é sobre literais.
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                and no.value.lower() in VERBOS_DE_ESCRITA
                and id(no) not in isento):
            problemas.append(
                f"linha {no.lineno}: literal {no.value!r} é verbo de escrita")

    # 2. subprocesso só dentro de _kubectl
    perigosos = {"Popen", "run", "call", "check_output", "check_call",
                 "system", "spawnl", "spawnv", "popen"}
    for fn in [n for n in ast.walk(arvore)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        if fn.name == "_kubectl":
            continue
        for no in ast.walk(fn):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func
            if isinstance(alvo, ast.Attribute) and alvo.attr in perigosos:
                base = alvo.value
                if isinstance(base, ast.Name) and base.id in {"subprocess", "os"}:
                    problemas.append(
                        f"linha {no.lineno}: {fn.name} chama "
                        f"{base.id}.{alvo.attr}, só _kubectl pode")
    return problemas


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="cluster-retrato: leitura do cluster corrente. Somente leitura.")
    p.add_argument("--endereco", default="127.0.0.1",
                   help="endereço de escuta (padrão: 127.0.0.1, loopback)")
    p.add_argument("--porta", type=int, default=8777)
    p.add_argument("--teto-externo", type=int, default=TETO_EXTERNO_PADRAO,
                   help="segundos para o comando kubectl inteiro")
    p.add_argument("--teto-requisicao", type=int, default=TETO_REQUISICAO_PADRAO,
                   help="segundos por requisição, passado ao kubectl")
    p.add_argument("--auditar", action="store_true",
                   help="roda a varredura do CA-08 no próprio fonte e sai")
    p.add_argument("--uma-vez", action="store_true",
                   help="coleta, imprime o HTML em stdout e sai (para validação)")
    p.add_argument("--namespace", default="",
                   help="namespace selecionado quando usado com --uma-vez")
    args = p.parse_args(argv)

    if args.auditar:
        problemas = auditar_fonte(os.path.abspath(__file__))
        if problemas:
            print("CA-08 FALHOU:")
            for x in problemas:
                print(f"  {x}")
            return 1
        print("CA-08 ok: nenhum verbo de escrita no fonte, "
              "subprocesso confinado a _kubectl")
        return 0

    if shutil.which("kubectl") is None:
        print("kubectl não está no PATH. Esta aplicação depende dele (ADR-002).",
              file=sys.stderr)
        return 2

    kw = {"teto_externo": args.teto_externo,
          "teto_requisicao": args.teto_requisicao}

    # RF-01: sem contexto corrente a aplicação NÃO sobe e NÃO abre porta.
    ctx, servidor = contexto_corrente(**kw)
    if ctx == "?":
        print("não foi possível determinar o contexto corrente do kubeconfig. "
              "Verifique com `kubectl config current-context`.", file=sys.stderr)
        return 2
    # As duas chamadas de subida. Falha aqui NÃO impede o servidor de subir: o CA-05
    # exige que a tela explique a falha, e para isso a porta precisa estar aberta.
    fonte, falha_fonte = detectar_fonte_de_endpoints(**kw)
    versao = versao_do_cluster(**kw)

    if args.uma_vez:
        estado = coletar(fonte, args.namespace, **kw)
        if falha_fonte is not None and estado["falha_global"] is None:
            estado["falhas"].setdefault("endpoints", falha_fonte)
        sys.stdout.write(
            renderizar(estado, ctx, servidor, "", versao).decode("utf-8"))
        return 0

    Handler.opcoes = {"fonte": fonte, "contexto": ctx, "servidor": servidor,
                      "versao": versao, **kw}
    if not _loopback(args.endereco):
        print("=" * 72, file=sys.stderr)
        print("AVISO: escutando em endereço que não é loopback "
              f"({args.endereco}).", file=sys.stderr)
        print("Esta aplicação NÃO TEM AUTENTICAÇÃO: quem alcançar a porta lê o",
              file=sys.stderr)
        print("cluster inteiro com a credencial deste processo.", file=sys.stderr)
        print("=" * 72, file=sys.stderr)

    httpd = ThreadingHTTPServer((args.endereco, args.porta), Handler)
    print(f"cluster-retrato em http://{args.endereco}:{args.porta}  "
          f"contexto={ctx}  endpoints via {fonte}", file=sys.stderr)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando", file=sys.stderr)
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
