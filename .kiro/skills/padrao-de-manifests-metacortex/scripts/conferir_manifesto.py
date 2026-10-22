#!/usr/bin/env python3
"""
Confere manifesto de Kubernetes contra o Padrão de Manifests da Metacortex.

O QUE ESTE SCRIPT FAZ, E O QUE ELE DELIBERADAMENTE NÃO FAZ
-----------------------------------------------------------
Ele cobre as regras que se verificam olhando SÓ o YAML, sem saber nada da aplicação:
parsing, comparação de strings e igualdade entre dois campos. Essas são as regras em que
leitura humana erra com facilidade e script não erra.

Ele NÃO reimplementa o Trivy. As regras 2.1 (requests e limits), 3.1 (tag :latest) e
3.6 (hostNetwork/hostPID/privileged) são cobertas pelo catálogo do Trivy e ficam com
ele. O que este script faz com o Trivy é outra coisa: invoca, lê o JSON e **traduz** cada
KSV para a regra da casa com a obrigatoriedade da casa. O motivo é concreto — o Trivy
reporta "requests de CPU não especificado" como LOW, e na Metacortex requests e limits
são obrigatórios; quem lê a saída crua do Trivy conclui que é opcional.

A regra 3.2 é a exceção, e por um motivo medido: o Trivy a cobre de um jeito que não
serve de veredito. Ele confere os cinco campos por regras separadas, sem o conceito do
"bloco inteiro" que a casa exige (falso negativo para quem filtra por severidade), e
KSV020/KSV021 olham só o securityContext do container, acusando manifesto correto quando
runAsUser está declarado no pod e é herdado (falso positivo). Como a 3.2 é obrigatória,
ela não pode ficar sem juiz: `regra_3_2_security_context` julga o bloco com a herança, e
os KSVs correspondentes passam a ser corroboração, não violação.

Ele também NÃO decide o que exige ler o projeto: probes (2.2), período de graça (2.6) e
os caminhos de escrita por trás de readOnlyRootFilesystem. Essas são instrução no corpo
da skill, porque a resposta está no código da aplicação e não no manifesto.

Uso:
    conferir_manifesto.py <arquivo-ou-diretorio> [--json] [--sem-trivy]

Código de saída:
    0  nenhuma violação de regra obrigatória ou proibida
    1  ao menos uma violação de regra obrigatória ou proibida
    2  erro de uso ou YAML inválido
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("erro: PyYAML não encontrado. Instale com: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# --------------------------------------------------------------------------------------
# Vocabulário do padrão. A revisão barra sem discussão em OBRIGATORIO e PROIBIDO.
OBRIGATORIO = "obrigatorio"
RECOMENDADO = "recomendado"
PROIBIDO = "proibido"

AMBIENTES_VALIDOS = ("dev", "stg", "prod")
REGISTRY_INTERNO = "registry.metacortex.io"
ROTULOS_EXIGIDOS = (
    "app.kubernetes.io/name",
    "app.kubernetes.io/instance",
    "app.kubernetes.io/part-of",
    "app.kubernetes.io/managed-by",
)
NOMES_DE_CONTAINER_VAGOS = ("app", "main", "container")

# Objetos que carregam rótulo e que o padrão enumera na regra 1.3.
TIPOS_COM_ROTULO = (
    "Deployment", "Service", "ConfigMap", "Secret", "Job", "CronJob",
    "StatefulSet", "DaemonSet", "ServiceAccount", "PodDisruptionBudget",
)
# Objetos que têm template de pod, e de onde se extrai container e seletor.
TIPOS_COM_POD = ("Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "ReplicaSet")

# Mapa KSV do Trivy -> regra da casa. É a tradução de severidade, não uma reimplementação.
TRIVY_PARA_REGRA = {
    "KSV011": ("2.1", OBRIGATORIO, "limite de CPU ausente"),
    "KSV015": ("2.1", OBRIGATORIO, "requests de CPU ausente"),
    "KSV016": ("2.1", OBRIGATORIO, "requests de memória ausente"),
    "KSV018": ("2.1", OBRIGATORIO, "limite de memória ausente"),
    "KSV013": ("3.1", PROIBIDO, "tag :latest"),
    "KSV008": ("3.6", PROIBIDO, "hostIPC"),
    "KSV009": ("3.6", PROIBIDO, "hostNetwork"),
    "KSV010": ("3.6", PROIBIDO, "hostPID"),
    "KSV017": ("3.6", PROIBIDO, "privileged"),
}
# KSVs que o padrão da casa não adota. Reportados como informativo, nunca como violação,
# para a saída não misturar o padrão da Metacortex com o padrão do Trivy.
TRIVY_FORA_DO_PADRAO = {
    "KSV030": "seccompProfile RuntimeDefault",
    "KSV104": "seccompProfile ausente",
    "KSV117": "bind em porta privilegiada",
    # GID. A regra 3.2 exige UID acima de 10000 e NÃO diz nada sobre runAsGroup, então
    # este KSV não corrobora requisito nenhum da casa. Fica como informativo — e, de
    # quebra, tem a mesma cegueira de herança do KSV020.
    "KSV021": "GID <= 10000 — a 3.2 não tem requisito de runAsGroup; "
              "e a regra ignora o nível do pod",
}
# KSVs que têm a mesma INTENÇÃO de uma regra da casa e implementação que não serve de
# veredito. Não cabem em TRIVY_FORA_DO_PADRAO: a casa adota a regra, e dizer "fora do
# padrão" faz quem lê só o cabeçalho concluir o oposto. Formato: id -> (regra, nota).
TRIVY_CORROBORA = {
    # Parece cobrir a 3.3 e NÃO cobre. Verificado por experimento: só olha ConfigMap
    # (ignora Secret.stringData e env.value), casa com palavra de uma lista ('postgres',
    # 'mysql', e até 'CACHE_TTL') e NÃO identifica a senha.
    "AVD-KSV-01010": ("3.3", "conteúdo sensível em ConfigMap — casa por palavra-chave, "
                             "não detecta a senha, e ignora Secret e env.value"),
    "KSV012": ("3.2", "runAsNonRoot"),
    "KSV001": ("3.2", "allowPrivilegeEscalation"),
    "KSV014": ("3.2", "readOnlyRootFilesystem"),
    "KSV003": ("3.2", "capabilities.drop"),
    "KSV106": ("3.2", "capabilities.add"),
    "KSV105": ("3.2", "runAsUser = 0"),
    "KSV020": ("3.2", "UID <= 10000 — cego para o nível do pod"),
}
# Regra 3.2: ONDE cada campo pode ser declarado. É o que nenhuma ferramenta modela.
#   "pod-ou-container" -> vale no securityContext do pod, e o container herda
#   "container"        -> o campo NÃO EXISTE no nível do pod; só vale no container
CAMPO_3_2_NIVEL = {
    "runAsNonRoot": "pod-ou-container",
    "runAsUser": "pod-ou-container",
    "allowPrivilegeEscalation": "container",
    "readOnlyRootFilesystem": "container",
    "capabilities": "container",
}
UID_MINIMO = 10000
CAPABILITY_TOLERADA = "NET_BIND_SERVICE"

# Senha embutida em string de conexão. É a lacuna do Trivy, verificada por experimento:
#   - `trivy fs --scanners secret` reconhece formato de credencial de terceiro
#     (AKIA..., ghp_..., xoxb-..., BEGIN RSA PRIVATE KEY) e NÃO reconhece senha dentro
#     de URI: 0 de 3 ocorrências da mesma senha em ConfigMap, Secret e env.
#   - `trivy config` tem AVD-KSV-01010, que parece cobrir isto e não cobre: só olha
#     ConfigMap, casa com palavra de uma lista ('postgres', 'mysql') e não aponta a senha.
# Ver references/cobertura-do-trivy.md.
URI_COM_SENHA = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|amqps|mssql|oracle"
    r"|clickhouse|cassandra|elasticsearch|https?)(?:\+\w+)?://"
    r"[^\s:/@]+:([^\s@/]+)@",
    re.IGNORECASE,
)
# Nome de variável que denuncia segredo, quando vem com `value` literal.
NOME_SENSIVEL = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|private[_-]?key|credential|senha)",
    re.IGNORECASE,
)
# Valores que não são segredo mesmo com nome sensível.
VALOR_INOCUO = re.compile(r"^(|\s*|false|true|0|none|null|changeme|<.*>|\$\{.*\})$", re.IGNORECASE)


class Achado:
    __slots__ = ("regra", "nivel", "objeto", "campo", "problema", "fonte")

    def __init__(self, regra, nivel, objeto, campo, problema, fonte="script"):
        self.regra = regra
        self.nivel = nivel
        self.objeto = objeto
        self.campo = campo
        self.problema = problema
        self.fonte = fonte

    def como_dict(self):
        return {
            "regra": self.regra, "nivel": self.nivel, "objeto": self.objeto,
            "campo": self.campo, "problema": self.problema, "fonte": self.fonte,
        }


def sugerir_kebab(nome: str) -> str:
    """
    Converte camelCase/PascalCase em kebab-case preservando sigla.

    A primeira versão inseria hífen antes de toda maiúscula, e 'NyxAPI' virava
    'nyx-a-p-i'. As duas regras abaixo tratam sigla: quebra quando a maiúscula vem
    depois de minúscula ou dígito, e quando uma sigla termina e começa outra palavra.
    """
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "-", nome)      # NyxAPI    -> Nyx-API
    s = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "-", s)       # APIServer -> API-Server
    s = re.sub(r"[^A-Za-z0-9-]+", "-", s).lower()
    return re.sub(r"-{2,}", "-", s).strip("-")


def ident(doc) -> str:
    """Identificador legível do objeto, como o relatório precisa citar."""
    meta = doc.get("metadata") or {}
    ns = meta.get("namespace")
    nome = meta.get("name", "<sem nome>")
    kind = doc.get("kind", "<sem kind>")
    return f"{kind}/{nome}" + (f" em {ns}" if ns else "")


def pod_spec(doc):
    """Devolve o podSpec de qualquer controlador, ou None."""
    kind = doc.get("kind")
    if kind == "Pod":
        return doc.get("spec") or {}
    if kind == "CronJob":
        return (((doc.get("spec") or {}).get("jobTemplate") or {}).get("spec") or {}).get("template", {}).get("spec") or {}
    if kind in TIPOS_COM_POD:
        return ((doc.get("spec") or {}).get("template") or {}).get("spec") or {}
    return None


def pod_labels(doc):
    kind = doc.get("kind")
    if kind == "CronJob":
        tmpl = (((doc.get("spec") or {}).get("jobTemplate") or {}).get("spec") or {}).get("template") or {}
    elif kind in TIPOS_COM_POD:
        tmpl = (doc.get("spec") or {}).get("template") or {}
    else:
        return None
    return (tmpl.get("metadata") or {}).get("labels") or {}


def containers_de(ps):
    if not ps:
        return []
    return list(ps.get("containers") or []) + list(ps.get("initContainers") or [])


def ambiente_do_namespace(ns: str | None):
    if not ns:
        return None
    partes = ns.rsplit("-", 1)
    return partes[1] if len(partes) == 2 and partes[1] in AMBIENTES_VALIDOS else None


# --------------------------------------------------------------------------------------
# Regras verificáveis só com o YAML.
# --------------------------------------------------------------------------------------
def regra_1_1_kebab(doc, achados):
    nome = (doc.get("metadata") or {}).get("name")
    if not nome:
        return
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?", nome):
        motivo = []
        if any(c.isupper() for c in nome):
            motivo.append("tem maiúscula")
        if "_" in nome:
            motivo.append("tem underscore")
        if "." in nome:
            motivo.append("tem ponto")
        sugerido = sugerir_kebab(nome)
        achados.append(Achado(
            "1.1", OBRIGATORIO, ident(doc), "metadata.name",
            f"nome '{nome}' não é kebab-case ({', '.join(motivo) or 'formato inválido'}); use '{sugerido}'",
        ))


def regra_1_2_namespace(doc, achados):
    ns = (doc.get("metadata") or {}).get("namespace")
    if doc.get("kind") == "Namespace":
        ns = (doc.get("metadata") or {}).get("name")
    if not ns:
        return
    if not re.fullmatch(r"[a-z0-9-]+-(dev|stg|prod)", ns):
        achados.append(Achado(
            "1.2", OBRIGATORIO, ident(doc), "metadata.namespace",
            f"namespace '{ns}' fora do formato <cliente>-<ambiente> com ambiente em "
            f"{', '.join(AMBIENTES_VALIDOS)}; o Construct não cria e o manifesto não tem onde aterrissar",
        ))


def regra_1_3_rotulos(doc, achados):
    kind = doc.get("kind")
    if kind not in TIPOS_COM_ROTULO:
        return
    labels = (doc.get("metadata") or {}).get("labels") or {}
    faltando = [r for r in ROTULOS_EXIGIDOS if r not in labels]
    if faltando:
        extra = ""
        if "app" in labels and len(faltando) == len(ROTULOS_EXIGIDOS):
            extra = "; o rótulo curto 'app:' existe mas não substitui os quatro"
        achados.append(Achado(
            "1.3", OBRIGATORIO, ident(doc), "metadata.labels",
            f"faltam {len(faltando)} de 4 rótulos: {', '.join(faltando)}{extra}",
        ))
    # O template do pod também carrega os quatro.
    pl = pod_labels(doc)
    if pl is not None:
        faltando_pod = [r for r in ROTULOS_EXIGIDOS if r not in pl]
        if faltando_pod:
            achados.append(Achado(
                "1.3", OBRIGATORIO, ident(doc), "spec.template.metadata.labels",
                f"template do pod sem {len(faltando_pod)} de 4 rótulos: {', '.join(faltando_pod)}",
            ))


def regra_1_4_seletor(doc, achados, indice_pods):
    """O erro mais comum do parque e o mais silencioso."""
    kind = doc.get("kind")

    if kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"):
        sel = ((doc.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
        pl = pod_labels(doc) or {}
        divergentes = {k: (v, pl.get(k)) for k, v in sel.items() if pl.get(k) != v}
        if divergentes:
            det = "; ".join(f"{k}: seletor '{a}' x pod '{b}'" for k, (a, b) in divergentes.items())
            achados.append(Achado(
                "1.4", OBRIGATORIO, ident(doc), "spec.selector.matchLabels",
                f"matchLabels não casa com os rótulos do template do pod ({det}); "
                f"o controlador não governa os próprios pods",
            ))

    if kind == "Service":
        sel = (doc.get("spec") or {}).get("selector") or {}
        if not sel:
            return
        ns = (doc.get("metadata") or {}).get("namespace")
        candidatos = [p for p in indice_pods if p["namespace"] == ns]
        if not candidatos:
            achados.append(Achado(
                "1.4", RECOMENDADO, ident(doc), "spec.selector",
                f"não há workload neste conjunto de arquivos no namespace '{ns}' para conferir "
                f"o seletor contra os rótulos do pod; confirme contra o cluster",
            ))
            return
        casou = [c for c in candidatos if all(c["labels"].get(k) == v for k, v in sel.items())]
        if not casou:
            # Mostra o candidato mais próximo, porque o erro típico é um caractere.
            melhor, score = None, -1
            for c in candidatos:
                s = sum(1 for k, v in sel.items() if c["labels"].get(k) == v)
                if s > score:
                    melhor, score = c, s
            difs = [f"{k}: Service '{v}' x pod '{melhor['labels'].get(k)}'"
                    for k, v in sel.items() if melhor["labels"].get(k) != v]
            achados.append(Achado(
                "1.4", OBRIGATORIO, ident(doc), "spec.selector",
                f"nenhum pod casa com o seletor; o Service sobe e fica SEM ENDPOINT. "
                f"Mais próximo é {melhor['objeto']} ({'; '.join(difs)})",
            ))


def regra_1_6_nome_container(doc, achados):
    ps = pod_spec(doc)
    for c in containers_de(ps):
        nome = c.get("name", "")
        if nome in NOMES_DE_CONTAINER_VAGOS:
            achados.append(Achado(
                "1.6", RECOMENDADO, ident(doc), f"container '{nome}'",
                f"nome '{nome}' não diz o que é; use o nome do componente (api, worker, scheduler)",
            ))


def regra_2_3_replicas(doc, achados):
    if doc.get("kind") not in ("Deployment", "StatefulSet"):
        return
    ns = (doc.get("metadata") or {}).get("namespace")
    if ambiente_do_namespace(ns) != "prod":
        return
    r = (doc.get("spec") or {}).get("replicas")
    if r is None:
        achados.append(Achado("2.3", OBRIGATORIO, ident(doc), "spec.replicas",
                              "replicas não declarado em prod; o default é 1 e prod exige >= 2"))
    elif r < 2:
        achados.append(Achado("2.3", OBRIGATORIO, ident(doc), "spec.replicas",
                              f"replicas: {r} em prod; indisponibilidade a cada deploy, drain e evicção"))


def regra_2_4_estrategia(doc, achados):
    if doc.get("kind") != "Deployment":
        return
    ns = (doc.get("metadata") or {}).get("namespace")
    if ambiente_do_namespace(ns) != "prod":
        return
    st = (doc.get("spec") or {}).get("strategy") or {}
    tipo = st.get("type")
    if tipo == "Recreate":
        achados.append(Achado("2.4", RECOMENDADO, ident(doc), "spec.strategy.type",
                              "Recreate em prod derruba a capacidade inteira; justifique no PR "
                              "(é aceitável para carga que não tolera duas instâncias)"))
        return
    ru = st.get("rollingUpdate") or {}
    if not st:
        achados.append(Achado("2.4", OBRIGATORIO, ident(doc), "spec.strategy",
                              "estratégia não declarada em prod; exigido RollingUpdate com "
                              "maxUnavailable: 0 e maxSurge: 1"))
        return

    # maxUnavailable e maxSurge aceitam inteiro OU percentual em string ('0', '0%', '25%').
    # Comparar só com (0, "0") marcava `maxUnavailable: 0%` como violação, e 0% é zero.
    def e_zero(v):
        if v is None:
            return False
        if isinstance(v, bool):
            return False
        if isinstance(v, int):
            return v == 0
        s = str(v).strip().rstrip("%").strip()
        try:
            return float(s) == 0.0
        except ValueError:
            return False

    mu = ru.get("maxUnavailable")
    if mu is None:
        achados.append(Achado("2.4", OBRIGATORIO, ident(doc), "spec.strategy.rollingUpdate.maxUnavailable",
                              "maxUnavailable não declarado em prod; o default do Kubernetes é 25% "
                              "e a regra exige 0"))
    elif not e_zero(mu):
        achados.append(Achado("2.4", OBRIGATORIO, ident(doc), "spec.strategy.rollingUpdate.maxUnavailable",
                              f"maxUnavailable: {mu!r} em prod; exigido 0 para a capacidade não "
                              f"cair durante o rollout. Trocar a estratégia para Recreate NÃO é o "
                              f"conserto: Recreate derruba a capacidade inteira, que é pior"))

    # maxSurge também é parte da regra, e não era conferido.
    ms = ru.get("maxSurge")
    if ms is None:
        achados.append(Achado("2.4", RECOMENDADO, ident(doc), "spec.strategy.rollingUpdate.maxSurge",
                              "maxSurge não declarado em prod; o default é 25% e a regra pede 1. "
                              "Com maxUnavailable: 0, maxSurge: 0 travaria o rollout para sempre"))
    elif e_zero(ms) and e_zero(mu):
        achados.append(Achado("2.4", OBRIGATORIO, ident(doc), "spec.strategy.rollingUpdate.maxSurge",
                              "maxSurge: 0 junto com maxUnavailable: 0 trava o rollout: o "
                              "controlador não pode criar pod novo nem derrubar o antigo"))
    elif str(ms).strip() not in ("1", "1%"):
        achados.append(Achado("2.4", RECOMENDADO, ident(doc), "spec.strategy.rollingUpdate.maxSurge",
                              f"maxSurge: {ms!r} em prod; a regra pede 1. Valor maior sobe mais "
                              f"pods de uma vez e exige folga de recurso no cluster; justifique no PR"))


def _assinatura_de_probe(p):
    """Identidade do que a probe testa, para comparar duas probes entre si."""
    if not isinstance(p, dict):
        return None
    if "httpGet" in p:
        h = p.get("httpGet") or {}
        return ("httpGet", str(h.get("path", "/")), str(h.get("port", "")))
    if "tcpSocket" in p:
        return ("tcpSocket", str((p.get("tcpSocket") or {}).get("port", "")))
    if "exec" in p:
        return ("exec", " ".join(str(x) for x in ((p.get("exec") or {}).get("command") or [])))
    if "grpc" in p:
        return ("grpc", str((p.get("grpc") or {}).get("port", "")))
    return None


def regra_2_2_probes(doc, achados):
    """
    Parte MECÂNICA da regra 2.2: as duas probes existem, e elas testam a mesma coisa?

    O julgamento de *o que* cada endpoint toca exige ler o projeto e fica no bloco 3.
    Mas presença de campo e comparação de duas assinaturas é parsing — o mesmo motivo
    pelo qual as regras 1.1 e 1.4 estão aqui. Deixar isso para leitura humana era uma
    lacuna: a regra é obrigatória e faltar uma das duas probes barra o deploy.

    Não se aplica a Job e CronJob, que terminam, nem a initContainers.
    """
    kind = doc.get("kind")
    if kind in ("Job", "CronJob"):
        return
    ps = pod_spec(doc)
    if ps is None:
        return

    # Só containers de longa duração. initContainer roda e sai; probe ali não faz sentido.
    for c in (ps.get("containers") or []):
        nome = c.get("name", "<sem nome>")
        readiness = c.get("readinessProbe")
        liveness = c.get("livenessProbe")

        faltando = [n for n, v in (("readinessProbe", readiness), ("livenessProbe", liveness)) if not v]
        if faltando:
            achados.append(Achado(
                "2.2", OBRIGATORIO, ident(doc), f"container '{nome}'",
                f"faltam {' e '.join(faltando)}; as duas são obrigatórias. Sem readiness o "
                f"pod entra no Service antes de estar pronto; sem liveness ele nunca é "
                f"reiniciado quando trava",
            ))
            continue

        a, b = _assinatura_de_probe(readiness), _assinatura_de_probe(liveness)
        if a is not None and a == b:
            achados.append(Achado(
                "2.2", RECOMENDADO, ident(doc), f"container '{nome}'",
                f"readiness e liveness testam exatamente a mesma coisa ({a[0]}: {a[-1]}). "
                f"SE esse teste tocar dependência externa, a regra 2.2 é VIOLADA e barra: "
                f"dependência lenta reinicia o container em vez de só tirá-lo do Service. "
                f"Confirme o que o teste toca e justifique no PR",
            ))


def regra_3_2_security_context(doc, achados):
    """
    Julga o bloco inteiro da regra 3.2, respeitando a herança pod -> container.

    Esta função existe porque o Trivy erra a 3.2 de dois jeitos opostos:

      - FALSO NEGATIVO: ele confere os cinco campos por regras separadas, com
        severidades de LOW a HIGH, e não tem o conceito de "o bloco que a casa exige".
        Quem filtra por `--severity HIGH,CRITICAL` perde quatro dos cinco campos.
      - FALSO POSITIVO: KSV020 e KSV021 olham só `containers[].securityContext` e
        ignoram `runAsUser` declarado no pod, que o Kubernetes herda. Manifesto correto
        é acusado.

    Dois dos cinco campos (`runAsNonRoot`, `runAsUser`) podem morar no pod e são
    herdados. Os outros três NÃO EXISTEM no nível do pod. A mensagem diz em qual nível
    o campo é aceito, porque é a dúvida que de fato aparece na revisão.
    """
    ps = pod_spec(doc)
    if ps is None:
        return
    sc_pod = ps.get("securityContext") or {}

    for c in containers_de(ps):
        sc_c = c.get("securityContext") or {}
        campo = f"container '{c.get('name')}'.securityContext"

        def anotar(problema):
            achados.append(Achado("3.2", OBRIGATORIO, ident(doc), campo, problema))

        def efetivo(nome):
            """Valor que vale em tempo de execução, e de qual nível ele veio."""
            if nome in sc_c:
                return sc_c[nome], "container"
            if CAMPO_3_2_NIVEL[nome] == "pod-ou-container" and nome in sc_pod:
                return sc_pod[nome], "pod"
            return None, None

        # --- os dois campos herdáveis ---
        valor, nivel = efetivo("runAsNonRoot")
        if valor is not True:
            onde = "ausente no pod e no container" if valor is None else f"está {valor!r} (nível {nivel})"
            anotar(f"runAsNonRoot {onde}; exigido true, aceito no pod ou no container")

        valor, nivel = efetivo("runAsUser")
        if valor is None:
            anotar(f"runAsUser ausente no pod e no container; exigido acima de {UID_MINIMO}, "
                   f"aceito em qualquer um dos dois níveis")
        elif valor == 0:
            anotar("runAsUser: 0 é root; exigido acima de %d" % UID_MINIMO)
        elif isinstance(valor, int) and valor <= UID_MINIMO:
            anotar(f"runAsUser: {valor} (nível {nivel}) não está acima de {UID_MINIMO}; "
                   f"se a imagem exige este UID, é desvio e precisa de exceção aprovada no PR")

        # --- os três que só existem no container ---
        if sc_c.get("allowPrivilegeEscalation") is not False:
            atual = sc_c.get("allowPrivilegeEscalation")
            motivo = "ausente" if atual is None else f"está {atual!r}"
            extra = ""
            if "allowPrivilegeEscalation" in sc_pod:
                extra = " (está declarado no pod, onde o campo NÃO EXISTE e é ignorado)"
            anotar(f"allowPrivilegeEscalation {motivo}; exigido false no container{extra}")

        if sc_c.get("readOnlyRootFilesystem") is not True:
            atual = sc_c.get("readOnlyRootFilesystem")
            motivo = "ausente" if atual is None else f"está {atual!r}"
            extra = ""
            if "readOnlyRootFilesystem" in sc_pod:
                extra = " (está declarado no pod, onde o campo NÃO EXISTE e é ignorado)"
            anotar(f"readOnlyRootFilesystem {motivo}; exigido true no container{extra}. "
                   f"Ligar a flag exige emptyDir nos caminhos em que a aplicação escreve")

        caps = sc_c.get("capabilities") or {}
        drop = [str(x).upper() for x in (caps.get("drop") or [])]
        if "ALL" not in drop:
            extra = " (está declarado no pod, onde o campo NÃO EXISTE e é ignorado)" \
                if "capabilities" in sc_pod else ""
            atual = f"drop: {drop}" if drop else "capabilities ausente"
            anotar(f"{atual}; exigido drop: [\"ALL\"] no container{extra}")
        sobrando = [str(x).upper() for x in (caps.get("add") or [])
                    if str(x).upper() != CAPABILITY_TOLERADA]
        if sobrando:
            anotar(f"capabilities.add tem {sobrando} além de {CAPABILITY_TOLERADA}, "
                   f"que é a única tolerada")


def regra_3_3_segredo(doc, achados):
    """A regra que o Trivy não cobre. Varre env.value, ConfigMap e Secret.stringData."""
    alvo = ident(doc)

    def olhar_valor(campo, nome_var, valor):
        if valor is None:
            return
        texto = str(valor)
        m = URI_COM_SENHA.search(texto)
        if m:
            achados.append(Achado(
                "3.3", PROIBIDO, alvo, campo,
                f"string de conexão com senha embutida em '{nome_var}' "
                f"(senha de {len(m.group(1))} caracteres); use valueFrom.secretKeyRef",
            ))
            return
        if NOME_SENSIVEL.search(nome_var or "") and not VALOR_INOCUO.fullmatch(texto):
            achados.append(Achado(
                "3.3", PROIBIDO, alvo, campo,
                f"'{nome_var}' tem valor literal ({len(texto)} caracteres); use valueFrom.secretKeyRef",
            ))

    ps = pod_spec(doc)
    for c in containers_de(ps):
        for e in c.get("env") or []:
            if "value" in e:
                olhar_valor(f"container '{c.get('name')}'.env[{e.get('name')}].value",
                            e.get("name", ""), e.get("value"))

    if doc.get("kind") == "ConfigMap":
        for k, v in (doc.get("data") or {}).items():
            olhar_valor(f"data.{k}", k, v)
    if doc.get("kind") == "Secret":
        for k, v in (doc.get("stringData") or {}).items():
            if v not in (None, ""):
                olhar_valor(f"stringData.{k}", k, v)


def regra_3_4_automount(doc, achados):
    ps = pod_spec(doc)
    if ps is None:
        if doc.get("kind") == "ServiceAccount" and doc.get("automountServiceAccountToken") is not False:
            achados.append(Achado("3.4", OBRIGATORIO, ident(doc), "automountServiceAccountToken",
                                  "ServiceAccount sem automountServiceAccountToken: false"))
        return
    if ps.get("automountServiceAccountToken") is not False:
        achados.append(Achado(
            "3.4", OBRIGATORIO, ident(doc), "spec.template.spec.automountServiceAccountToken",
            "token da ServiceAccount montado; declare false quando a aplicação não fala com o apiserver "
            "(obrigatório desde 2026-07-29)",
        ))


def regra_3_5_serviceaccount(doc, achados):
    ps = pod_spec(doc)
    if ps is None:
        return
    sa = ps.get("serviceAccountName")
    if not sa:
        achados.append(Achado("3.5", RECOMENDADO, ident(doc), "spec.template.spec.serviceAccountName",
                              "sem ServiceAccount dedicada; usa a 'default' do namespace"))
    elif sa == "default":
        achados.append(Achado("3.5", RECOMENDADO, ident(doc), "spec.template.spec.serviceAccountName",
                              "usa a ServiceAccount 'default' do namespace; crie uma por workload"))


def regra_3_7_registry(doc, achados):
    ps = pod_spec(doc)
    for c in containers_de(ps):
        img = c.get("image") or ""
        if not img:
            continue
        if not img.startswith(REGISTRY_INTERNO + "/"):
            achados.append(Achado(
                "3.7", OBRIGATORIO, ident(doc), f"container '{c.get('name')}'.image",
                f"imagem '{img}' não vem de {REGISTRY_INTERNO}; imagem pública entra pelo Loom, "
                f"que espelha, escaneia e republica",
            ))


def regra_1_5_dono(doc, achados):
    if doc.get("kind") not in TIPOS_COM_ROTULO:
        return
    ann = (doc.get("metadata") or {}).get("annotations") or {}
    if "metacortex.io/owner" not in ann:
        achados.append(Achado("1.5", RECOMENDADO, ident(doc), "metadata.annotations",
                              "sem metacortex.io/owner; o plantão não sabe quem é o dono às 3 da manhã"))


def regra_2_5_pdb(docs, achados):
    """PDB é por conjunto de arquivos, não por objeto: precisa olhar o todo."""
    pdbs = [d for d in docs if d.get("kind") == "PodDisruptionBudget"]
    for d in docs:
        if d.get("kind") != "Deployment":
            continue
        ns = (d.get("metadata") or {}).get("namespace")
        if ambiente_do_namespace(ns) != "prod":
            continue
        r = (d.get("spec") or {}).get("replicas") or 1
        if r < 2:
            continue
        pl = pod_labels(d) or {}
        cobre = any(
            all(pl.get(k) == v for k, v in (((p.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}).items())
            and (p.get("metadata") or {}).get("namespace") == ns
            for p in pdbs
        )
        if not cobre:
            achados.append(Achado("2.5", RECOMENDADO, ident(d), "PodDisruptionBudget",
                                  f"prod com {r} réplicas e sem PDB que cubra estes rótulos; "
                                  f"uma manutenção de nó pode derrubar todas as réplicas de uma vez"))


# --------------------------------------------------------------------------------------
def rodar_trivy(caminho: Path):
    """Invoca o Trivy e traduz a saída. Não reimplementa: delega e traduz."""
    if not shutil.which("trivy"):
        return None, "trivy não encontrado no PATH"
    try:
        p = subprocess.run(
            ["trivy", "config", str(caminho), "--format", "json", "--quiet"],
            capture_output=True, text=True, timeout=300,
        )
        if p.returncode not in (0, 1) or not p.stdout.strip():
            return None, f"trivy falhou (rc={p.returncode}): {(p.stderr or '').strip()[:200]}"
        dados = json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        return None, "trivy excedeu o tempo limite"
    except (json.JSONDecodeError, OSError) as e:
        return None, f"não foi possível ler a saída do trivy: {e}"

    traduzidos, informativos, nao_mapeados, corrobora = [], [], [], []
    for r in dados.get("Results") or []:
        alvo = Path(r.get("Target", "")).name
        for m in r.get("Misconfigurations") or []:
            if m.get("Status") != "FAIL":
                continue
            ksv = m.get("ID", "")
            if ksv in TRIVY_PARA_REGRA:
                regra, nivel, descricao = TRIVY_PARA_REGRA[ksv]
                traduzidos.append(Achado(
                    regra, nivel, alvo,
                    (m.get("CauseMetadata") or {}).get("Resource") or "—",
                    f"{descricao} [{ksv}]", fonte="trivy",
                ))
            elif ksv in TRIVY_CORROBORA:
                # Não entra como violação: quem julga estas regras é o script. Fica
                # registrado para o revisor ver que a ferramenta opinou — e, no caso da
                # 3.2, que ela discordou por cegueira de herança.
                regra, nota = TRIVY_CORROBORA[ksv]
                corrobora.append(f"[{regra}] {ksv} em {alvo}: {nota}")
            elif ksv in TRIVY_FORA_DO_PADRAO:
                informativos.append(f"{ksv} em {alvo}: {TRIVY_FORA_DO_PADRAO[ksv]}")
            else:
                # Não engolir achado desconhecido. O mapa de cobertura foi levantado
                # contra o Trivy 0.52.2; versão nova traz regra nova, e regra nova que
                # desaparece em silêncio é pior que regra ruidosa. Quem vê um item aqui
                # precisa decidir se ele entra em TRIVY_PARA_REGRA ou em
                # TRIVY_FORA_DO_PADRAO — e atualizar references/cobertura-do-trivy.md.
                nao_mapeados.append(
                    f"{ksv} em {alvo} ({m.get('Severity', '?')}): {m.get('Title', '—')}"
                )
    return (traduzidos, informativos, nao_mapeados, corrobora), None


def carregar(caminho: Path):
    arquivos = []
    if caminho.is_dir():
        for p in sorted(caminho.rglob("*")):
            if p.suffix in (".yaml", ".yml") and p.is_file():
                arquivos.append(p)
    elif caminho.is_file():
        arquivos.append(caminho)
    else:
        print(f"erro: '{caminho}' não existe", file=sys.stderr)
        sys.exit(2)

    docs = []
    for p in arquivos:
        try:
            for d in yaml.safe_load_all(p.read_text(encoding="utf-8")):
                if isinstance(d, dict) and d.get("kind"):
                    d["__arquivo"] = p.name
                    docs.append(d)
        except yaml.YAMLError as e:
            print(f"erro: YAML inválido em {p}: {str(e).splitlines()[0]}", file=sys.stderr)
            sys.exit(2)
    return docs, arquivos


def main():
    ap = argparse.ArgumentParser(description="Confere manifesto contra o padrão da Metacortex")
    ap.add_argument("caminho", help="arquivo .yaml ou diretório de manifests")
    ap.add_argument("--json", action="store_true", help="saída em JSON")
    ap.add_argument("--sem-trivy", action="store_true", help="não invocar o Trivy")
    args = ap.parse_args()

    caminho = Path(args.caminho)
    docs, arquivos = carregar(caminho)
    if not docs:
        print("erro: nenhum objeto Kubernetes encontrado", file=sys.stderr)
        sys.exit(2)

    # Índice de pods para a regra 1.4 do Service.
    indice_pods = []
    for d in docs:
        pl = pod_labels(d)
        if pl is not None:
            indice_pods.append({"objeto": ident(d),
                                "namespace": (d.get("metadata") or {}).get("namespace"),
                                "labels": pl})

    achados = []
    for d in docs:
        regra_1_1_kebab(d, achados)
        regra_1_2_namespace(d, achados)
        regra_1_3_rotulos(d, achados)
        regra_1_4_seletor(d, achados, indice_pods)
        regra_1_5_dono(d, achados)
        regra_1_6_nome_container(d, achados)
        regra_2_3_replicas(d, achados)
        regra_2_4_estrategia(d, achados)
        regra_2_2_probes(d, achados)
        regra_3_2_security_context(d, achados)
        regra_3_3_segredo(d, achados)
        regra_3_4_automount(d, achados)
        regra_3_5_serviceaccount(d, achados)
        regra_3_7_registry(d, achados)
    regra_2_5_pdb(docs, achados)

    informativos, nao_mapeados, corrobora, erro_trivy = [], [], [], None
    if not args.sem_trivy:
        res, erro_trivy = rodar_trivy(caminho)
        if res:
            traduzidos, informativos, nao_mapeados, corrobora = res
            achados.extend(traduzidos)

    bloqueia = [a for a in achados if a.nivel in (OBRIGATORIO, PROIBIDO)]
    recomenda = [a for a in achados if a.nivel == RECOMENDADO]

    if args.json:
        print(json.dumps({
            "arquivos": [p.name for p in arquivos],
            "objetos": len(docs),
            "trivy": ("desligado por --sem-trivy" if args.sem_trivy
                      else (erro_trivy or "ok")),
            "regras_nao_conferidas": (["2.1", "3.1", "3.6"]
                                      if (args.sem_trivy or erro_trivy) else []),
            "achados": [a.como_dict() for a in achados],
            "informativo_fora_do_padrao": informativos,
            "trivy_nao_mapeado": nao_mapeados,
            "trivy_corrobora": corrobora,
            "resumo": {"barra_revisao": len(bloqueia), "recomendado": len(recomenda)},
        }, ensure_ascii=False, indent=2))
        sys.exit(1 if bloqueia else 0)

    print(f"\nConferência contra o Padrão de Manifests da Metacortex (rev. 2026-07-29)")
    print(f"{len(docs)} objeto(s) em {len(arquivos)} arquivo(s): {', '.join(p.name for p in arquivos)}")
    # Degradar em silêncio é pior que não rodar: quem lê o relatório precisa saber que
    # três regras não foram conferidas, seja por opção (--sem-trivy) ou por falha.
    if args.sem_trivy:
        print("AVISO: --sem-trivy — as regras 2.1 (requests e limits), 3.1 (tag :latest) e")
        print("       3.6 (hostNetwork/hostPID/privileged) NÃO foram conferidas. 15 das 19.")
    elif erro_trivy:
        print(f"AVISO: {erro_trivy}")
        print("       as regras 2.1, 3.1 e 3.6 NÃO foram conferidas. 15 das 19.")

    def bloco(titulo, lista):
        if not lista:
            return
        print(f"\n{titulo}")
        for a in sorted(lista, key=lambda x: x.regra):
            marca = " (via trivy)" if a.fonte == "trivy" else ""
            print(f"  [{a.regra}] {a.objeto}")
            print(f"        campo: {a.campo}{marca}")
            print(f"        {a.problema}")

    bloco(f"BARRA A REVISÃO — {len(bloqueia)} violação(ões) de regra obrigatória ou proibida", bloqueia)
    bloco(f"EXIGE JUSTIFICATIVA NO PR — {len(recomenda)} regra(s) recomendada(s)", recomenda)

    if informativos:
        print(f"\nAPONTADO PELO TRIVY, FORA DO PADRÃO DA CASA — {len(informativos)} item(ns)")
        print("  (não barra a revisão; o padrão da Metacortex não adota estas regras)")
        for i in informativos:
            print(f"  - {i}")

    if nao_mapeados:
        print(f"\nTRIVY APONTOU E O MAPA NÃO CONHECE — {len(nao_mapeados)} item(ns)")
        print("  (o mapa de cobertura foi levantado contra o Trivy 0.52.2; decida se cada")
        print("   item entra no padrão da casa e atualize references/cobertura-do-trivy.md)")
        for i in nao_mapeados:
            print(f"  - {i}")

    if corrobora:
        print(f"\nO TRIVY OPINOU SOBRE REGRAS QUE ESTE SCRIPT JULGA — {len(corrobora)} item(ns)")
        print("  (A CASA ADOTA estas regras. O que não serve de veredito é a implementação")
        print("   do Trivy: KSV020/KSV021 acusam manifesto correto quando runAsUser está no")
        print("   pod, e AVD-KSV-01010 casa por palavra-chave sem achar a senha. O veredito")
        print("   das regras 3.2 e 3.3 é o dos blocos acima, não o desta lista.)")
        for i in corrobora:
            print(f"  - {i}")

    # Bloco 3. Cada item diz o NÍVEL da regra, para o revisor saber o veredito que
    # precisa dar depois de abrir o projeto, em vez de ficar entre "barra" e "pendente".
    print("\nNÃO CONFERIDO POR ESTE SCRIPT — exige abrir o projeto:")
    print("  [2.2] obrigatório — a PRESENÇA das duas probes já foi conferida acima, e")
    print("        também se as duas testam a mesma coisa. Falta o que o YAML não diz: o")
    print("        endpoint existe na aplicação, e a liveness NÃO toca dependência externa?")
    print("  [2.6] recomendado — terminationGracePeriodSeconds foi deliberado? O valor não")
    print("        precisa ser diferente do default de 30s, precisa ser justificado. Sem")
    print("        registro no PR a regra fica PENDENTE, não conforme.")
    print("        Este script não vê o corpo do PR: leve a 2.6 para o bloco 2 do seu")
    print("        relatório, porque o rc acima NÃO reflete pendência de justificativa.")
    print("  [3.2] obrigatório — os cinco campos foram conferidos acima. Falta só o que não")
    print("        está no YAML: se os emptyDir cobrem TODOS os caminhos em que a aplicação")
    print("        escreve. readOnlyRootFilesystem: true com caminho faltando não sobe.")
    print("  [3.3] proibido — o script pega senha em URI e nome de variável sensível. Falta")
    print("        conferir se alguma variável de nome inocente carrega segredo.")
    print("\n  Quando o workload é imagem de terceiro (Postgres, Redis, nginx) não há projeto")
    print("  para abrir: a fonte são a documentação da imagem e o entrypoint dela. Registre")
    print("  isso no DECISOES.md em lugar de arquivo e linha.")

    if not bloqueia and not recomenda:
        print("\nNenhuma violação mecânica. As regras acima ainda precisam de conferência manual.")
    sys.exit(1 if bloqueia else 0)


if __name__ == "__main__":
    main()
