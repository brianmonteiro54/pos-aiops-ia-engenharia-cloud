#!/usr/bin/env python3
"""Mede o custo em TOKENS e em TEMPO das quatro execucoes da Parte C.

POR QUE ISTO EXISTE
-------------------
A primeira versao da Parte C contou chamadas e declarou que tokens e tempo nao foram
medidos. Chamada e um proxy de custo, nao o custo: duas chamadas podem diferir em uma
ordem de grandeza no que devolvem. `kubectl_get` em modo LISTA devolve um resumo de
cinco campos; no singular com `name` devolve o objeto cru. Contar as duas como "uma
chamada" esconde exatamente a diferenca que decide o custo.

Este script repete a sequencia EXATA que cada executor registrou, pelo mesmo transporte
MCP, e mede o que entra no contexto.

O QUE ELE MEDE, E O QUE NAO MEDE
--------------------------------
Mede:
  - tokens de cada resposta do servidor MCP (tiktoken, o200k_base)
  - bytes de cada resposta
  - tempo de parede de cada chamada, e a parcela que e spawn do `npx`
  - o custo fixo do corpo da skill, que entra no contexto a cada ativacao

NAO mede, e nao tem como:
  - tokens de raciocinio do modelo, nem o total faturado pelo provedor. Nao tenho
    acesso a essa contabilidade. O que esta aqui e o custo de ENTRADA observavel:
    o que as ferramentas devolveram mais o corpo da skill.
  - o tokenizador e o da OpenAI, nao o da Anthropic. Serve como proxy comparavel entre
    os quatro bracos, porque o mesmo tokenizador mede os quatro.

Uso:
    ./medir-custo.py                 # mede tudo e escreve a evidencia
    ./medir-custo.py --so-overhead   # mede so o custo de spawn do transporte
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
TICKET = os.path.dirname(AQUI)
REPO = os.path.abspath(os.path.join(TICKET, "..", "..", ".."))
MCP = os.path.join(AQUI, "mcp.py")
SKILL = os.path.join(REPO, ".kiro", "skills", "triagem-de-cluster-metacortex",
                     "SKILL.md")

# As quatro sequencias, exatamente como cada executor as registrou no bloco
# INSTRUMENTACAO da propria resposta. Nao reconstruidas: transcritas.
SEQUENCIAS: dict[str, list[tuple[str, dict]]] = {
    "chamado-1 COM skill": [
        ("kubectl_get", {"resourceType": "all", "namespace": "nyx-prod"}),
        ("kubectl_get", {"resourceType": "pod", "name": "@api0",
                         "namespace": "nyx-prod", "output": "json"}),
        ("kubectl_get", {"resourceType": "deployment", "name": "nyx-api",
                         "namespace": "nyx-prod", "output": "json"}),
        ("kubectl_get", {"resourceType": "limitranges", "namespace": "nyx-prod"}),
        ("kubectl_get", {"resourceType": "resourcequotas", "namespace": "nyx-prod"}),
        ("kubectl_get", {"resourceType": "pod", "name": "@pg",
                         "namespace": "nyx-prod", "output": "json"}),
        ("kubectl_get", {"resourceType": "pod", "name": "@api1",
                         "namespace": "nyx-prod", "output": "json"}),
        ("kubectl_describe", {"resourceType": "pod", "name": "@api0",
                              "namespace": "nyx-prod"}),
        ("kubectl_logs", {"resourceType": "pod", "name": "@api0",
                          "namespace": "nyx-prod", "previous": True}),
        ("kubectl_get", {"resourceType": "endpoints", "name": "nyx-api",
                         "namespace": "nyx-prod", "output": "json"}),
    ],
    "chamado-1 SEM skill": [
        ("kubectl_get", {"resourceType": "pods", "namespace": "nyx-prod"}),
        ("kubectl_describe", {"resourceType": "pod", "name": "@api1",
                              "namespace": "nyx-prod"}),
        ("kubectl_describe", {"resourceType": "pod", "name": "@api0",
                              "namespace": "nyx-prod"}),
        ("kubectl_get", {"resourceType": "limitranges", "namespace": "nyx-prod",
                         "output": "json"}),
        ("kubectl_get", {"resourceType": "resourcequotas", "namespace": "nyx-prod",
                         "output": "json"}),
        ("kubectl_get", {"resourceType": "deployments", "namespace": "nyx-prod",
                         "output": "json"}),
        ("kubectl_get", {"resourceType": "deployments", "namespace": "nyx-prod",
                         "output": "json"}),
        ("kubectl_describe", {"resourceType": "deployment", "name": "nyx-api",
                              "namespace": "nyx-prod"}),
        ("kubectl_describe", {"resourceType": "deployment", "name": "nyx-postgres",
                              "namespace": "nyx-prod"}),
        ("kubectl_logs", {"resourceType": "pod", "name": "@api0",
                          "namespace": "nyx-prod"}),
        ("kubectl_logs", {"resourceType": "pod", "name": "@api0",
                          "namespace": "nyx-prod", "previous": True}),
        ("kubectl_get", {"resourceType": "events", "namespace": "nyx-prod"}),
        ("kubectl_get", {"resourceType": "endpoints", "namespace": "nyx-prod"}),
        ("kubectl_describe", {"resourceType": "endpoints", "name": "nyx-api",
                              "namespace": "nyx-prod"}),
        ("kubectl_describe", {"resourceType": "node",
                              "name": "k3d-metacortex-agent-0"}),
    ],
    "chamado-3 COM skill": [
        ("kubectl_get", {"resourceType": "all", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "endpoints", "name": "nyx-api",
                         "namespace": "nyx-stg", "output": "json"}),
        ("kubectl_get", {"resourceType": "endpointslices", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "endpointslice", "name": "@slice",
                         "namespace": "nyx-stg", "output": "json"}),
        ("kubectl_get", {"resourceType": "service", "name": "nyx-api",
                         "namespace": "nyx-stg", "output": "json"}),
        ("kubectl_get", {"resourceType": "pod", "name": "@stg0",
                         "namespace": "nyx-stg", "output": "json"}),
        ("kubectl_get", {"resourceType": "pods", "namespace": "nyx-stg",
                         "labelSelector": "app=nyx-api"}),
        ("kubectl_get", {"resourceType": "pods", "namespace": "nyx-stg",
                         "labelSelector": "app=nyxapi"}),
        ("kubectl_get", {"resourceType": "ingress", "allNamespaces": True}),
        ("kubectl_get", {"resourceType": "deployment", "name": "nyx-api",
                         "namespace": "nyx-stg", "output": "json"}),
    ],
    "chamado-3 SEM skill": [
        ("kubectl_get", {"resourceType": "pods", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "services", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "endpoints", "namespace": "nyx-stg"}),
        ("kubectl_describe", {"resourceType": "service", "name": "nyx-api",
                              "namespace": "nyx-stg"}),
        ("kubectl_describe", {"resourceType": "endpoints", "name": "nyx-api",
                              "namespace": "nyx-stg"}),
        ("kubectl_describe", {"resourceType": "pod", "name": "@stg0",
                              "namespace": "nyx-stg"}),
        ("kubectl_describe", {"resourceType": "deployment", "name": "nyx-api",
                              "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "ingress", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "ingresses", "allNamespaces": True}),
        ("list_api_resources", {}),
        ("kubectl_get", {"resourceType": "ingressroutes", "namespace": "nyx-stg"}),
        ("kubectl_get", {"resourceType": "endpointslices", "namespace": "nyx-stg"}),
        ("kubectl_describe", {"resourceType": "endpointslice", "name": "@slice",
                              "namespace": "nyx-stg"}),
    ],
}


def contar(texto: str) -> int:
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(texto))


def nomes_reais() -> dict[str, str]:
    """Resolve os marcadores @api0, @pg, ... para os nomes de hoje no cluster.

    Os nomes de pod mudam a cada recriacao. Fixar o nome registrado pelo executor
    quebraria a reproducao amanha.
    """
    def pods(ns: str, prefixo: str) -> list[str]:
        saida = subprocess.run(
            ["kubectl", "get", "pods", "-n", ns, "-o",
             "jsonpath={range .items[*]}{.metadata.name}{\"\\n\"}{end}"],
            capture_output=True, text=True).stdout
        return sorted(l for l in saida.split() if l.startswith(prefixo))

    api = pods("nyx-prod", "nyx-api-")
    pg = pods("nyx-prod", "nyx-postgres-")
    stg = pods("nyx-stg", "nyx-api-")
    slice_ = subprocess.run(
        ["kubectl", "get", "endpointslices", "-n", "nyx-stg", "-l",
         "kubernetes.io/service-name=nyx-api", "-o",
         "jsonpath={.items[0].metadata.name}"],
        capture_output=True, text=True).stdout.strip()
    return {
        "@api0": api[0] if api else "", "@api1": api[1] if len(api) > 1 else "",
        "@pg": pg[0] if pg else "", "@stg0": stg[0] if stg else "",
        "@slice": slice_,
    }


def chamar(ferramenta: str, args: dict) -> tuple[str, float, bool]:
    inicio = time.monotonic()
    proc = subprocess.run(
        [sys.executable, MCP, "call", ferramenta, json.dumps(args)],
        capture_output=True, text=True, cwd=TICKET)
    return proc.stdout, time.monotonic() - inicio, proc.returncode == 0


def medir_overhead(repeticoes: int = 3) -> dict:
    """Separa spawn do `npx` do tempo de consulta ao apiserver.

    Sem isso o tempo total nao diz nada sobre o metodo: ele e dominado por uma
    escolha de implementacao do cliente MCP.
    """
    por_mcp, por_kubectl = [], []
    for _ in range(repeticoes):
        _, t, _ok = chamar("kubectl_get", {"resourceType": "namespaces"})
        por_mcp.append(t)
        inicio = time.monotonic()
        subprocess.run(["kubectl", "get", "namespaces"],
                       capture_output=True, text=True)
        por_kubectl.append(time.monotonic() - inicio)
    return {
        "mcp_mediana_s": round(statistics.median(por_mcp), 2),
        "kubectl_mediana_s": round(statistics.median(por_kubectl), 2),
        "spawn_npx_s": round(statistics.median(por_mcp)
                             - statistics.median(por_kubectl), 2),
        "repeticoes": repeticoes,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--so-overhead", action="store_true")
    p.add_argument("--saida", default=os.path.join(TICKET, "evidencias",
                                                   "custo-com-e-sem-skill.txt"))
    args = p.parse_args()

    linhas: list[str] = []
    def diz(s: str = "") -> None:
        print(s, flush=True)
        linhas.append(s)

    diz("Custo em tokens e tempo: com e sem skill")
    diz(f"data: {time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    diz("tokenizador: tiktoken o200k_base (proxy; nao e o tokenizador da Anthropic)")
    diz("transporte: mcp-server-kubernetes em modo nao destrutivo, via ferramentas/mcp.py")
    diz()

    diz("== Custo fixo da skill, por ativacao ==")
    with open(SKILL, encoding="utf-8") as fh:
        corpo = fh.read()
    tok_skill = contar(corpo)
    diz(f"  SKILL.md: {len(corpo)} bytes, {tok_skill} tokens")
    diz("  (as references/ estao fora do caminho de execucao e nao entram)")
    diz()

    diz("== Overhead do transporte ==")
    ov = medir_overhead()
    diz(f"  mesma consulta via MCP:     {ov['mcp_mediana_s']}s (mediana de "
        f"{ov['repeticoes']})")
    diz(f"  mesma consulta via kubectl: {ov['kubectl_mediana_s']}s")
    diz(f"  spawn do npx por chamada:   {ov['spawn_npx_s']}s")
    diz()
    if args.so_overhead:
        return 0

    nomes = nomes_reais()
    faltando = [k for k, v in nomes.items() if not v]
    if faltando:
        diz(f"AVISO: nao resolvi {faltando}; o laboratorio pode nao estar no ar")
    resumo: dict[str, dict] = {}

    for rotulo, seq in SEQUENCIAS.items():
        diz(f"== {rotulo} ==")
        diz(f"  {'#':>2}  {'ferramenta':<20} {'tokens':>7} {'bytes':>8} {'s':>6}  alvo")
        tot_tok = tot_bytes = 0
        tot_t = 0.0
        vazias = 0
        for i, (ferramenta, bruto) in enumerate(seq, 1):
            argumentos = {k: nomes.get(v, v) if isinstance(v, str) else v
                          for k, v in bruto.items()}
            saida, segundos, ok = chamar(ferramenta, argumentos)
            tok = contar(saida)
            tot_tok += tok
            tot_bytes += len(saida)
            tot_t += segundos
            if '"items": []' in saida or '"logs": ""' in saida:
                vazias += 1
            alvo = argumentos.get("name") or argumentos.get("resourceType", "")
            modo = "lista" if argumentos.get("resourceType", "").endswith("s") \
                and not argumentos.get("name") else ""
            diz(f"  {i:>2}  {ferramenta:<20} {tok:>7} {len(saida):>8} "
                f"{segundos:>6.1f}  {alvo} {modo}".rstrip())
        diz(f"  {'TOTAL':<24} {tot_tok:>7} {tot_bytes:>8} {tot_t:>6.1f}")
        diz(f"  chamadas: {len(seq)}   respostas vazias: {vazias}")
        diz(f"  tempo sem o spawn do npx: "
            f"{max(0.0, tot_t - len(seq) * ov['spawn_npx_s']):.1f}s")
        if "COM" in rotulo:
            diz(f"  + custo fixo da skill: {tok_skill} tokens  "
                f"=> entrada total {tot_tok + tok_skill} tokens")
        resumo[rotulo] = {
            "chamadas": len(seq), "tokens_resposta": tot_tok,
            "tokens_entrada": tot_tok + (tok_skill if "COM" in rotulo else 0),
            "bytes": tot_bytes, "segundos_replay": round(tot_t, 1),
            "respostas_vazias": vazias,
        }
        diz()

    diz("== Comparacao ==")
    diz(f"  {'braco':<22} {'chamadas':>8} {'tok resposta':>13} {'tok entrada':>12}")
    for rotulo, d in resumo.items():
        diz(f"  {rotulo:<22} {d['chamadas']:>8} {d['tokens_resposta']:>13} "
            f"{d['tokens_entrada']:>12}")
    diz()
    for chamado in ("chamado-1", "chamado-3"):
        com = resumo.get(f"{chamado} COM skill")
        sem = resumo.get(f"{chamado} SEM skill")
        if not (com and sem):
            continue
        razao = com["tokens_entrada"] / sem["tokens_entrada"] if sem["tokens_entrada"] else 0
        diz(f"  {chamado}: entrada com skill / sem skill = {razao:.2f}x")

    os.makedirs(os.path.dirname(args.saida), exist_ok=True)
    with open(args.saida, "w", encoding="utf-8") as fh:
        fh.write("\n".join(linhas) + "\n")
    with open(args.saida.replace(".txt", ".json"), "w", encoding="utf-8") as fh:
        json.dump({"overhead": ov, "skill_tokens": tok_skill, "bracos": resumo},
                  fh, indent=2, ensure_ascii=False)
    print(f"\nevidencia em {args.saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
