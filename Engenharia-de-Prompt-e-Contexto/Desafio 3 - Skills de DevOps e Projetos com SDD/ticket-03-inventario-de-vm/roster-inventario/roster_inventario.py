#!/usr/bin/env python3
"""
roster-inventario — audita uma VM por SSH e compara com o baseline do parque.

Primeira peça do substituto do Roster. Roda na máquina de quem opera; o host auditado não
recebe agente nem escrita de nenhum tipo.

    roster_inventario.py --host 127.0.0.1 --porta 2201 --usuario auditor \\
        --chave ~/.ssh/auditor --baseline baseline.yaml [--formato json|markdown|ambos]

Código de saída:
    0  host conforme — nenhum desvio
    1  há desvio
    2  host inalcançável, baseline inválido, ou erro de uso

O desenho está em openspec/changes/inventario-e-drift-de-vm/design.md e as quatro decisões
estruturais em docs/adr/. Em resumo:

    transporte  ->  coleta  ->  julgamento  ->  apresentacao

Coleta e julgamento são separados de propósito: o inventário tem valor sem o baseline, e
trocar o baseline não deve mexer em coletor.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CONFORME = "conforme"
DESVIO = "desvio"
NAO_VERIFICADO = "nao_verificado"

ORDEM_SEVERIDADE = ("critico", "alto", "medio")

# Classificação do endereço de bind. O baseline separa portas públicas de portas que só
# podem escutar na rede interna, então a porta sozinha não decide o veredito:
# 9100 em 127.0.0.1 é conforme, 9100 em 0.0.0.0 é desvio crítico.
BIND_PUBLICO = "publico"
BIND_LOOPBACK = "loopback"
BIND_INTERNO = "interno"


# ======================================================================================
# ETAPA 1 — TRANSPORTE
# ======================================================================================

class FalhaDeConexao(Exception):
    """
    Falha que impede a coleta inteira. É diferente de dado não coletado.

    Dado não coletado vira `nao_verificado` numa regra e a execução segue. Falha de conexão
    significa que não há host para auditar: código 2, sem bloco de conformidade. É o que
    impede confundir host inalcançável com host conforme (CA-04).
    """


# Classificação do stderr do ssh. O stderr NÃO é repassado cru, porque pode conter o
# caminho da chave privada — e a chave é credencial (RE-03).
CATEGORIAS_DE_FALHA = (
    ("REMOTE HOST IDENTIFICATION HAS CHANGED",
     "a chave do host mudou desde a última conexão; o acesso foi recusado por segurança"),
    ("Name or service not known", "o nome do host não resolve"),
    ("No route to host", "host inalcançável: sem rota até o endereço"),
    ("Connection refused", "host alcançável, mas nada escutando na porta de SSH"),
    ("Connection timed out", "host inalcançável: a conexão expirou"),
    ("Operation timed out", "host inalcançável: a conexão expirou"),
    ("timed out", "host inalcançável: a conexão expirou"),
    ("Permission denied", "autenticação recusada pelo host: a chave não foi aceita"),
    ("Too many authentication failures", "autenticação recusada pelo host"),
    ("Host key verification failed", "a chave do host não pôde ser verificada"),
)


def classificar_falha(stderr: str) -> str:
    """Traduz o stderr do ssh numa frase que explica, sem expor caminho de chave."""
    for sinal, explicacao in CATEGORIAS_DE_FALHA:
        if sinal.lower() in stderr.lower():
            return explicacao
    return "não foi possível estabelecer a sessão SSH"


class SessaoSSH:
    """
    Uma sessão, n comandos.

    Usa o `ssh` do sistema como subprocesso (ADR-001) com `ControlMaster`: a primeira
    conexão abre um socket de controle e as seguintes reusam, então há uma autenticação por
    execução em vez de uma por comando.

    O socket vive em diretório temporário próprio e é removido ao fim, inclusive em caminho
    de erro — socket de controle esquecido é conexão aberta para VM de cliente.
    """

    def __init__(self, host: str, usuario: str, chave: str, porta: int = 22,
                 tempo_limite: int = 10):
        self.host = host
        self.usuario = usuario
        self.chave = chave
        self.porta = porta
        self.tempo_limite = tempo_limite
        self._dir_controle: str | None = None
        self._socket: str | None = None

    def __enter__(self) -> "SessaoSSH":
        if not shutil.which("ssh"):
            raise FalhaDeConexao("o binário `ssh` não foi encontrado no PATH")
        if not os.path.isfile(self.chave):
            # Não repete o caminho: a mensagem diz o que fazer sem ecoar o parâmetro.
            raise FalhaDeConexao("o arquivo de chave privada informado não existe")
        self._dir_controle = tempfile.mkdtemp(prefix="roster-ssh-")
        self._socket = os.path.join(self._dir_controle, "ctl")
        return self

    def __exit__(self, *_) -> None:
        if self._socket and os.path.exists(self._socket):
            subprocess.run(
                self._base_ssh() + ["-O", "exit", self.host],
                capture_output=True, text=True, timeout=15,
            )
        if self._dir_controle:
            shutil.rmtree(self._dir_controle, ignore_errors=True)

    def _base_ssh(self) -> list[str]:
        return [
            "ssh",
            "-i", self.chave,
            "-p", str(self.porta),
            "-l", self.usuario,
            # BatchMode: nunca pedir senha. Em pipeline, prompt é travamento silencioso.
            "-o", "BatchMode=yes",
            # accept-new aceita host novo e RECUSA host cuja chave mudou. `no` aceitaria
            # man-in-the-middle; `yes` exigiria known_hosts pré-populado para todo o parque.
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={self.tempo_limite}",
            # IdentitiesOnly: usa só a chave passada. Sem isso o agente SSH da estação pode
            # autenticar com outra chave, e o resultado deixa de ser reproduzível.
            "-o", "IdentitiesOnly=yes",
            "-o", "ControlMaster=auto",
            "-o", f"ControlPath={self._socket}",
            "-o", "ControlPersist=30s",
        ]

    def executar(self, comando: str) -> tuple[int, str, str]:
        """Executa um comando de leitura. Devolve (código, stdout, stderr)."""
        try:
            p = subprocess.run(
                self._base_ssh() + [self.host, comando],
                capture_output=True, text=True, timeout=self.tempo_limite + 50,
            )
        except subprocess.TimeoutExpired:
            raise FalhaDeConexao("o comando remoto excedeu o tempo limite") from None
        # 255 é o código do próprio ssh, não do comando remoto: é falha de transporte.
        if p.returncode == 255:
            raise FalhaDeConexao(classificar_falha(p.stderr))
        return p.returncode, p.stdout, p.stderr


# ======================================================================================
# ETAPA 2 — COLETA
# ======================================================================================

@dataclass
class Coletado:
    """
    Valor OU motivo de falha, nunca exceção para cima (ADR-002).

    `valor is None` com `motivo` preenchido é o único caminho que produz `nao_verificado`
    no julgamento.
    """
    valor: Any = None
    motivo: str | None = None

    @property
    def ok(self) -> bool:
        return self.motivo is None

    @classmethod
    def falhou(cls, motivo: str) -> "Coletado":
        return cls(valor=None, motivo=motivo)


MOTIVO_PRIVILEGIO = "exige privilegio que o usuario da coleta nao tem"


def _primeira_linha(texto: str) -> str:
    return texto.strip().splitlines()[0].strip() if texto.strip() else ""


def coletar_hostname(s: SessaoSSH) -> Coletado:
    rc, out, _ = s.executar("hostname -f 2>/dev/null || hostname")
    nome = _primeira_linha(out)
    if rc != 0 or not nome:
        return Coletado.falhou("o host nao reportou hostname")
    return Coletado(nome)


def coletar_so(s: SessaoSSH) -> Coletado:
    rc, out, _ = s.executar("cat /etc/os-release")
    if rc != 0 or not out.strip():
        return Coletado.falhou("/etc/os-release nao pode ser lido")
    campos = {}
    for linha in out.splitlines():
        if "=" in linha:
            k, _, v = linha.partition("=")
            campos[k.strip()] = v.strip().strip('"').strip("'")
    distro, versao = campos.get("ID"), campos.get("VERSION_ID")
    if not distro or not versao:
        return Coletado.falhou("/etc/os-release sem ID ou VERSION_ID")
    return Coletado({"distribuicao": distro, "versao": versao})


def coletar_kernel(s: SessaoSSH) -> Coletado:
    rc, out, _ = s.executar("uname -r")
    v = _primeira_linha(out)
    if rc != 0 or not v:
        return Coletado.falhou("uname nao respondeu")
    return Coletado({"versao": v})


def coletar_servicos(s: SessaoSSH) -> Coletado:
    """
    `--type=service,socket` não é detalhe: o baseline proíbe `telnet.socket` e
    `rpcbind.socket`. Coletar só `.service` deixaria os dois passarem.
    """
    rc, out, err = s.executar(
        "systemctl list-units --type=service,socket --state=active "
        "--no-legend --no-pager --plain"
    )
    if rc != 0:
        return Coletado.falhou(f"systemctl nao respondeu: {_primeira_linha(err) or 'sem detalhe'}")
    unidades = []
    for linha in out.splitlines():
        partes = linha.split()
        if not partes:
            continue
        nome = partes[0]
        if not (nome.endswith(".service") or nome.endswith(".socket")):
            continue
        unidades.append({
            "nome": nome,
            "tipo": "socket" if nome.endswith(".socket") else "service",
            "estado": "active",
        })
    # Ordenar: a ordem do systemctl varia entre execuções e quebraria o determinismo (RE-02).
    return Coletado(sorted(unidades, key=lambda u: u["nome"]))


def coletar_swap(s: SessaoSSH) -> Coletado:
    rc, out, _ = s.executar("swapon --show=NAME,SIZE --noheadings 2>/dev/null; cat /proc/swaps 2>/dev/null")
    if rc != 0 and not out.strip():
        return Coletado.falhou("nao foi possivel consultar swap")
    linhas = [l for l in out.splitlines() if l.strip() and not l.startswith("Filename")]
    if not linhas:
        # Vazio é informação, não falha: significa swap desabilitado.
        return Coletado({"habilitado": False, "tamanho": None})
    tamanho = None
    for l in linhas:
        partes = l.split()
        if len(partes) >= 2:
            tamanho = partes[1] if not partes[1].isdigit() else _kib_para_humano(partes[1])
            break
    return Coletado({"habilitado": True, "tamanho": tamanho})


def _kib_para_humano(kib: str) -> str:
    try:
        n = int(kib)
    except ValueError:
        return kib
    for unidade, divisor in (("G", 1024 * 1024), ("M", 1024), ("K", 1)):
        if n >= divisor:
            valor = n / divisor
            return f"{valor:.0f}{unidade}" if valor == int(valor) else f"{valor:.1f}{unidade}"
    return f"{n}K"


def classificar_bind(endereco: str) -> str:
    e = endereco.strip().strip("[]")
    if e in ("0.0.0.0", "*", "::", ""):
        return BIND_PUBLICO
    if e in ("127.0.0.1", "::1") or e.startswith("127."):
        return BIND_LOOPBACK
    return BIND_INTERNO


def coletar_portas(s: SessaoSSH) -> Coletado:
    """
    Três campos por porta: número, endereço de bind e processo dono.

    O PID NÃO é coletado de propósito: ele muda a cada reinício e quebraria o determinismo
    (RE-02). O nome do processo basta para o julgamento.
    """
    rc, out, err = s.executar("ss -lntupH 2>/dev/null || ss -lntup 2>/dev/null")
    if rc != 0 or not out.strip():
        return Coletado.falhou(f"ss nao respondeu: {_primeira_linha(err) or 'sem detalhe'}")
    portas = []
    for linha in out.splitlines():
        if linha.lstrip().startswith(("Netid", "State")):
            continue
        partes = linha.split()
        if len(partes) < 5:
            continue
        local = partes[4]
        if ":" not in local:
            continue
        endereco, _, porta_txt = local.rpartition(":")
        if not porta_txt.isdigit():
            continue
        processo = None
        m = re.search(r'users:\(\("([^"]+)"', linha)
        if m:
            processo = m.group(1)
        portas.append({
            "porta": int(porta_txt),
            "bind": endereco.strip("[]") or "0.0.0.0",
            "escopo": classificar_bind(endereco),
            "processo": processo,
        })
    # Desduplicar e ordenar: ss lista IPv4 e IPv6 separados para o mesmo serviço.
    unicas = {(p["porta"], p["bind"], p["processo"]): p for p in portas}
    return Coletado(sorted(unicas.values(), key=lambda p: (p["porta"], p["bind"])))


def coletar_chaves_ssh(s: SessaoSSH) -> Coletado:
    """
    O que identifica a origem de uma chave é o COMENTÁRIO dela — o terceiro campo da linha.
    É por ele que se responde "esta chave foi emitida pela plataforma?".
    """
    rc, out, _ = s.executar("cat ~/.ssh/authorized_keys 2>/dev/null")
    if rc != 0:
        return Coletado.falhou("authorized_keys nao pode ser lido")
    chaves = []
    for linha in out.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        partes = linha.split(None, 2)
        if len(partes) < 2:
            continue
        chaves.append({
            "tipo": partes[0],
            "identificacao": partes[2].strip() if len(partes) > 2 else None,
        })
    return Coletado(sorted(chaves, key=lambda c: (c["identificacao"] or "", c["tipo"])))


def coletar_login_de_root(s: SessaoSSH) -> Coletado:
    """
    A configuração EFETIVA, não a escrita no arquivo.

    `sshd_config.d/*.conf` sobrepõe, `Match` cria bloco condicional, e a primeira diretiva
    é que vence em repetição. Ler o arquivo com grep responde o que alguém escreveu, não o
    que o daemon aplica.

    `sshd -T` imprime a configuração resolvida e EXIGE privilégio — é o caso típico de
    `nao_verificado` que o PRD descreve.
    """
    rc, out, err = s.executar(
        "(sshd -T 2>/dev/null || /usr/sbin/sshd -T 2>/dev/null) | grep -i '^permitrootlogin'"
    )
    linha = _primeira_linha(out)
    if rc != 0 or not linha:
        combinado = (err + out).lower()
        if "permission" in combinado or "denied" in combinado or not linha:
            return Coletado.falhou(MOTIVO_PRIVILEGIO)
        return Coletado.falhou("sshd -T nao respondeu")
    valor = linha.split()[-1].strip().lower()
    return Coletado({"login_de_root": valor not in ("no", "false"), "valor_bruto": valor})


def coletar_ntp(s: SessaoSSH) -> Coletado:
    rc, out, _ = s.executar("timedatectl show 2>/dev/null || timedatectl status 2>/dev/null")
    if rc != 0 or not out.strip():
        return Coletado.falhou("timedatectl nao respondeu")
    texto = out.lower()
    sincronizado = ("ntpsynchronized=yes" in texto.replace(" ", "")
                    or "system clock synchronized: yes" in texto)
    mecanismo = None
    for unidade, nome in (("chrony", "chrony"),
                          ("systemd-timesyncd", "systemd-timesyncd"),
                          ("ntpd", "ntpd")):
        rc2, out2, _ = s.executar(f"systemctl is-active {unidade} 2>/dev/null")
        if _primeira_linha(out2) == "active":
            mecanismo = nome
            break
    return Coletado({"sincronizado": sincronizado, "mecanismo": mecanismo})


COLETORES = {
    "hostname": coletar_hostname,
    "so": coletar_so,
    "kernel": coletar_kernel,
    "servicos": coletar_servicos,
    "swap": coletar_swap,
    "portas_em_escuta": coletar_portas,
    "chaves_ssh": coletar_chaves_ssh,
    "ssh": coletar_login_de_root,
    "ntp": coletar_ntp,
}


def coletar_tudo(s: SessaoSSH) -> dict[str, Coletado]:
    """A falha de um coletor não derruba os outros (ADR-002)."""
    resultado = {}
    for nome, coletor in COLETORES.items():
        try:
            resultado[nome] = coletor(s)
        except FalhaDeConexao:
            raise                       # falha de transporte sobe: não há host para auditar
        except Exception as e:           # noqa: BLE001 — qualquer erro do coletor vira motivo
            resultado[nome] = Coletado.falhou(
                f"erro ao coletar: {type(e).__name__}"
            )
    return resultado


# ======================================================================================
# ETAPA 3 — JULGAMENTO
# ======================================================================================

@dataclass
class Veredito:
    regra: str
    esperado: Any
    encontrado: Any
    veredito: str
    severidade: str | None = None
    motivo: str | None = None

    def como_dict(self) -> dict:
        d = {"regra": self.regra, "esperado": self.esperado,
             "encontrado": self.encontrado, "veredito": self.veredito}
        if self.severidade:
            d["severidade"] = self.severidade
        if self.motivo:
            d["motivo"] = self.motivo
        return d


class Baseline:
    def __init__(self, dados: dict, caminho: str):
        self.caminho = caminho
        self.versao = dados.get("versao")
        self.aplica_a = dados.get("aplica_a")
        self.esperado = dados.get("esperado") or {}
        self._severidade = dados.get("severidade") or {}
        self._mapa = {}
        for nivel, regras in self._severidade.items():
            for r in regras or []:
                self._mapa[r] = nivel

    def severidade_de(self, regra: str) -> str | None:
        """
        A severidade vem do baseline e NUNCA é inferida. Regra sem severidade declarada é
        erro do baseline, e a ferramenta diz em vez de assumir um nível.
        """
        return self._mapa.get(regra)

    def tem(self, caminho: str) -> bool:
        no = self.esperado
        for parte in caminho.split("."):
            if not isinstance(no, dict) or parte not in no:
                return False
            no = no[parte]
        return True

    def valor(self, caminho: str) -> Any:
        no = self.esperado
        for parte in caminho.split("."):
            no = no[parte]
        return no


def versao_em_partes(texto: str) -> tuple[int, ...]:
    """
    Comparação de versão é por componente numérico, não lexicográfica.

    "22.04" < "9.10" é verdade em comparação de string e falso no mundo. E o sufixo do
    fornecedor é descartado: 5.15.0-118-generic vira (5, 15, 0).
    """
    numeros = re.findall(r"\d+", str(texto).split("-")[0])
    return tuple(int(n) for n in numeros) or (0,)


def _ao_menos(encontrado: str, minimo: str) -> bool:
    a, b = versao_em_partes(encontrado), versao_em_partes(minimo)
    tamanho = max(len(a), len(b))
    a += (0,) * (tamanho - len(a))
    b += (0,) * (tamanho - len(b))
    return a >= b


def julgar(coletado: dict[str, Coletado], bl: Baseline) -> list[Veredito]:
    vereditos: list[Veredito] = []

    def emitir(regra: str, esperado: Any, encontrado: Any, ok: bool) -> None:
        if ok:
            vereditos.append(Veredito(regra, esperado, encontrado, CONFORME))
        else:
            sev = bl.severidade_de(regra)
            vereditos.append(Veredito(
                regra, esperado, encontrado, DESVIO,
                severidade=sev or "nao-declarada-no-baseline",
            ))

    def nao_verificado(regra: str, esperado: Any, motivo: str) -> None:
        vereditos.append(Veredito(regra, esperado, None, NAO_VERIFICADO, motivo=motivo))

    # --- so ---
    c = coletado["so"]
    for regra, chave in (("so.distribuicao", "distribuicao"), ("so.versao_minima", "versao")):
        if not bl.tem(regra):
            continue
        esperado = bl.valor(regra)
        if not c.ok:
            nao_verificado(regra, esperado, c.motivo); continue
        achado = c.valor[chave]
        ok = (achado.lower() == str(esperado).lower() if chave == "distribuicao"
              else _ao_menos(achado, esperado))
        emitir(regra, esperado, achado, ok)

    # --- kernel ---
    if bl.tem("kernel.versao_minima"):
        esperado = bl.valor("kernel.versao_minima")
        c = coletado["kernel"]
        if not c.ok:
            nao_verificado("kernel.versao_minima", esperado, c.motivo)
        else:
            achado = c.valor["versao"]
            emitir("kernel.versao_minima", esperado, achado, _ao_menos(achado, esperado))

    # --- servicos ---
    c = coletado["servicos"]
    if bl.tem("servicos.ativos"):
        esperado = bl.valor("servicos.ativos")
        if not c.ok:
            nao_verificado("servicos.ativos", esperado, c.motivo)
        else:
            ativos = {u["nome"] for u in c.valor}
            bases = {u["nome"].rsplit(".", 1)[0] for u in c.valor}
            faltando = sorted(e for e in esperado if e not in ativos and e not in bases)
            emitir("servicos.ativos", esperado,
                   f"ausentes: {', '.join(faltando)}" if faltando else "todos ativos",
                   not faltando)
    if bl.tem("servicos.proibidos"):
        esperado = bl.valor("servicos.proibidos")
        if not c.ok:
            nao_verificado("servicos.proibidos", esperado, c.motivo)
        else:
            ativos = {u["nome"] for u in c.valor}
            presentes = sorted(p for p in esperado if p in ativos)
            emitir("servicos.proibidos", esperado,
                   f"ativos: {', '.join(presentes)}" if presentes else "nenhum ativo",
                   not presentes)

    # --- swap ---
    if bl.tem("swap.habilitado"):
        esperado = bl.valor("swap.habilitado")
        c = coletado["swap"]
        if not c.ok:
            nao_verificado("swap.habilitado", esperado, c.motivo)
        else:
            achado = c.valor["habilitado"]
            texto = f"{achado}" + (f" ({c.valor['tamanho']})" if achado and c.valor.get("tamanho") else "")
            emitir("swap.habilitado", esperado, texto, achado == esperado)

    # --- portas ---
    c = coletado["portas_em_escuta"]
    publicas = []
    if c.ok:
        publicas = [p for p in c.valor if p["escopo"] == BIND_PUBLICO]
    if bl.tem("portas_em_escuta.publicas_permitidas"):
        esperado = bl.valor("portas_em_escuta.publicas_permitidas")
        if not c.ok:
            nao_verificado("portas_em_escuta.publicas_permitidas", esperado, c.motivo)
        else:
            fora = sorted({p["porta"] for p in publicas} - set(esperado))
            emitir("portas_em_escuta.publicas_permitidas", esperado,
                   f"publicas nao permitidas: {fora}" if fora else "nenhuma fora da lista",
                   not fora)
    if bl.tem("portas_em_escuta.somente_rede_interna"):
        esperado = bl.valor("portas_em_escuta.somente_rede_interna")
        if not c.ok:
            nao_verificado("portas_em_escuta.somente_rede_interna", esperado, c.motivo)
        else:
            vazadas = sorted(p["porta"] for p in publicas if p["porta"] in esperado)
            detalhe = ", ".join(
                f"{p['porta']} em {p['bind']}" for p in publicas if p["porta"] in esperado
            )
            emitir("portas_em_escuta.somente_rede_interna", esperado,
                   detalhe if vazadas else "nenhuma exposta publicamente",
                   not vazadas)

    # --- chaves ssh ---
    if bl.tem("chaves_ssh.emitidas_por"):
        esperado = bl.valor("chaves_ssh.emitidas_por")
        c = coletado["chaves_ssh"]
        if not c.ok:
            nao_verificado("chaves_ssh.emitidas_por", esperado, c.motivo)
        else:
            estranhas = [k["identificacao"] or "(sem identificacao)"
                         for k in c.valor
                         if str(esperado) not in (k["identificacao"] or "")]
            emitir("chaves_ssh.emitidas_por", esperado,
                   f"{len(c.valor)} chave(s); fora do emissor: {', '.join(estranhas)}"
                   if estranhas else f"{len(c.valor)} chave(s), todas do emissor esperado",
                   not estranhas)

    # --- login de root ---
    if bl.tem("ssh.login_de_root"):
        esperado = bl.valor("ssh.login_de_root")
        c = coletado["ssh"]
        if not c.ok:
            nao_verificado("ssh.login_de_root", esperado, c.motivo)
        else:
            achado = c.valor["login_de_root"]
            emitir("ssh.login_de_root", esperado, achado, achado == esperado)

    # --- ntp ---
    if bl.tem("ntp.sincronizado"):
        esperado = bl.valor("ntp.sincronizado")
        c = coletado["ntp"]
        if not c.ok:
            nao_verificado("ntp.sincronizado", esperado, c.motivo)
        else:
            achado = c.valor["sincronizado"]
            texto = f"{achado}" + (f" ({c.valor['mecanismo']})" if c.valor.get("mecanismo") else "")
            emitir("ntp.sincronizado", esperado, texto, achado == esperado)

    return vereditos


# ======================================================================================
# ETAPA 4 — APRESENTAÇÃO
# ======================================================================================

def montar_inventario(coletado: dict[str, Coletado]) -> dict:
    def v(nome, padrao=None):
        c = coletado.get(nome)
        return c.valor if (c and c.ok) else padrao

    ssh = v("ssh")
    return {
        "so": v("so"),
        "kernel": v("kernel"),
        "servicos": v("servicos", []),
        "swap": v("swap"),
        "portas_em_escuta": v("portas_em_escuta", []),
        "chaves_ssh": v("chaves_ssh", []),
        "ssh": {"login_de_root": ssh["login_de_root"] if ssh else None},
        "ntp": v("ntp"),
    }


def montar_resumo(vereditos: list[Veredito]) -> dict:
    contagem = {CONFORME: 0, DESVIO: 0, NAO_VERIFICADO: 0}
    por_severidade: dict[str, int] = {}
    for x in vereditos:
        contagem[x.veredito] = contagem.get(x.veredito, 0) + 1
        # Conta os DESVIOS por severidade, não todas as regras.
        if x.veredito == DESVIO and x.severidade:
            por_severidade[x.severidade] = por_severidade.get(x.severidade, 0) + 1
    return {**contagem, "por_severidade": por_severidade}


def saida_json(host: dict, inventario: dict, vereditos: list[Veredito], bl: Baseline) -> str:
    return json.dumps({
        "host": host,
        "baseline": {"versao": bl.versao, "aplica_a": bl.aplica_a},
        "inventario": inventario,
        "conformidade": [x.como_dict() for x in vereditos],
        "resumo": montar_resumo(vereditos),
    }, ensure_ascii=False, indent=2)


def saida_markdown(host: dict, vereditos: list[Veredito], bl: Baseline) -> str:
    def chave(x: Veredito) -> tuple:
        pos = ORDEM_SEVERIDADE.index(x.severidade) if x.severidade in ORDEM_SEVERIDADE else 99
        return (pos, x.regra)

    desvios = sorted([x for x in vereditos if x.veredito == DESVIO], key=chave)
    nao_vers = sorted([x for x in vereditos if x.veredito == NAO_VERIFICADO], key=lambda x: x.regra)
    conformes = sorted([x.regra for x in vereditos if x.veredito == CONFORME])

    rotulo = {"critico": "crítico", "alto": "alto", "medio": "médio"}
    instante = host["coletado_em"].replace("T", " ").replace("Z", " UTC")
    L = [f"# Inventário de {host['hostname']} ({host['endereco']})",
         f"Coletado em {instante} · baseline {bl.versao}", ""]

    if desvios:
        L += ["## Desvios", "", "| Severidade | Regra | Esperado | Encontrado |", "|---|---|---|---|"]
        for x in desvios:
            L.append(f"| {rotulo.get(x.severidade, x.severidade)} | {x.regra} | "
                     f"{x.esperado} | {x.encontrado} |")
        L.append("")
    else:
        L += ["## Desvios", "", "Nenhum.", ""]

    if nao_vers:
        L += ["## Não verificado", "", "| Regra | Motivo |", "|---|---|"]
        for x in nao_vers:
            L.append(f"| {x.regra} | {x.motivo} |")
        L.append("")

    L += ["## Conforme", "", " · ".join(conformes) if conformes else "Nenhuma regra conforme.", ""]
    return "\n".join(L)


# ======================================================================================
# ENTRADA
# ======================================================================================

def carregar_baseline(caminho: str) -> Baseline:
    try:
        import yaml
    except ImportError:
        print("erro: PyYAML nao encontrado. Instale com: pip install pyyaml", file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(caminho):
        print(f"erro: baseline nao encontrado: {caminho}", file=sys.stderr)
        sys.exit(2)
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = yaml.safe_load(f)
    except yaml.YAMLError as e:
        print(f"erro: baseline invalido: {str(e).splitlines()[0]}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(dados, dict) or "esperado" not in dados:
        print("erro: baseline sem a secao 'esperado'", file=sys.stderr)
        sys.exit(2)
    return Baseline(dados, caminho)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Audita uma VM por SSH e compara com o baseline do parque.",
    )
    ap.add_argument("--host", required=True, help="endereco da VM")
    ap.add_argument("--usuario", required=True, help="usuario da coleta")
    ap.add_argument("--chave", required=True, help="caminho da chave privada")
    ap.add_argument("--porta", type=int, default=22)
    ap.add_argument("--baseline", default="baseline.yaml")
    ap.add_argument("--formato", choices=["json", "markdown", "ambos"], default="markdown")
    ap.add_argument("--tempo-limite", type=int, default=10)
    args = ap.parse_args()

    bl = carregar_baseline(args.baseline)

    try:
        with SessaoSSH(args.host, args.usuario, args.chave, args.porta, args.tempo_limite) as s:
            coletado = coletar_tudo(s)
            nome = coletado["hostname"].valor if coletado["hostname"].ok else "(desconhecido)"
    except FalhaDeConexao as e:
        # Sem stack trace, e sem bloco de conformidade: host inalcancavel NAO e host
        # conforme (CA-04).
        print(f"erro: {e}", file=sys.stderr)
        print(f"       host {args.host}:{args.porta} como {args.usuario}", file=sys.stderr)
        return 2

    host = {
        "endereco": args.host,
        "hostname": nome,
        "coletado_em": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    vereditos = julgar(coletado, bl)

    if args.formato in ("json", "ambos"):
        print(saida_json(host, montar_inventario(coletado), vereditos, bl))
    if args.formato in ("markdown", "ambos"):
        if args.formato == "ambos":
            print()
        print(saida_markdown(host, vereditos, bl))

    return 1 if any(x.veredito == DESVIO for x in vereditos) else 0


if __name__ == "__main__":
    sys.exit(main())
