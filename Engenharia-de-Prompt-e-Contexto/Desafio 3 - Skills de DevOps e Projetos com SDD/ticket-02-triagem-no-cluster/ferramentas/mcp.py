#!/usr/bin/env python3
"""
Cliente MCP mínimo para o mcp-server-kubernetes, por stdio/JSON-RPC.

POR QUE ISTO EXISTE
-------------------
A execução da skill de triagem precisa passar pelo transporte real — o servidor MCP em
modo não destrutivo — e não por `kubectl` chamado direto. São coisas diferentes: o
servidor é quem decide quais ferramentas existem, e é essa decisão que o ticket pede para
medir. Rodar `kubectl` e chamar de "execução da skill" mediria outra coisa.

Este cliente faz o mínimo: `initialize`, `tools/list` e `tools/call`.

Uso:
    ./mcp.py tools                                    # lista as ferramentas disponíveis
    ./mcp.py call kubectl_get '{"resourceType":"pods","namespace":"nyx-prod"}'
    ./mcp.py call kubectl_delete '{"resourceType":"pod","name":"x"}'   # deve ser RECUSADA

Variável de ambiente:
    ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS=true   liga o modo não destrutivo (default aqui)

Código de saída:
    0  a chamada retornou resultado
    1  a chamada retornou erro do servidor (ferramenta inexistente, por exemplo)
    2  erro de uso ou o servidor não respondeu
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

COMANDO = ["npx", "-y", "mcp-server-kubernetes"]
TEMPO_LIMITE = 180


def conversar(mensagens: list[dict], nao_destrutivo: bool = True) -> list[dict]:
    """Abre o servidor, despeja as mensagens no stdin e devolve as respostas."""
    ambiente = dict(os.environ)
    if nao_destrutivo:
        ambiente["ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS"] = "true"
    else:
        ambiente.pop("ALLOW_ONLY_NON_DESTRUCTIVE_TOOLS", None)

    entrada = "".join(json.dumps(m) + "\n" for m in mensagens)
    try:
        p = subprocess.run(
            COMANDO, input=entrada, capture_output=True, text=True,
            timeout=TEMPO_LIMITE, env=ambiente,
        )
    except subprocess.TimeoutExpired:
        print("erro: o servidor MCP excedeu o tempo limite", file=sys.stderr)
        sys.exit(2)

    respostas = []
    for linha in p.stdout.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        try:
            respostas.append(json.loads(linha))
        except json.JSONDecodeError:
            continue   # o servidor escreve log em stdout junto com o JSON-RPC
    if not respostas:
        print(f"erro: nenhuma resposta JSON-RPC. stderr:\n{p.stderr[:500]}", file=sys.stderr)
        sys.exit(2)
    return respostas


def abertura() -> list[dict]:
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                    "clientInfo": {"name": "triagem-metacortex", "version": "1.0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]


def listar(nao_destrutivo: bool = True) -> int:
    msgs = abertura() + [{"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}]
    for r in conversar(msgs, nao_destrutivo):
        if r.get("id") == 2 and "result" in r:
            nomes = sorted(t["name"] for t in r["result"]["tools"])
            modo = "nao-destrutivo" if nao_destrutivo else "default"
            print(f"{len(nomes)} ferramentas (modo {modo}):")
            for n in nomes:
                print(f"  {n}")
            return 0
    print("erro: o servidor nao devolveu tools/list", file=sys.stderr)
    return 2


def chamar(ferramenta: str, argumentos: dict, nao_destrutivo: bool = True) -> int:
    msgs = abertura() + [{
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": ferramenta, "arguments": argumentos},
    }]
    for r in conversar(msgs, nao_destrutivo):
        if r.get("id") != 3:
            continue
        if "error" in r:
            print(f"RECUSADA pelo servidor: {r['error'].get('message')}", file=sys.stderr)
            return 1
        res = r.get("result") or {}
        if res.get("isError"):
            for c in res.get("content") or []:
                print(f"ERRO DA FERRAMENTA: {c.get('text')}", file=sys.stderr)
            return 1
        for c in res.get("content") or []:
            print(c.get("text", ""))
        return 0
    print("erro: o servidor nao devolveu resposta para tools/call", file=sys.stderr)
    return 2


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    destrutivo_liberado = "--com-destrutivas" in sys.argv
    argv = [a for a in sys.argv if a != "--com-destrutivas"]
    acao = argv[1]

    if acao == "tools":
        return listar(nao_destrutivo=not destrutivo_liberado)
    if acao == "call":
        if len(argv) < 3:
            print("uso: mcp.py call <ferramenta> '<json de argumentos>'", file=sys.stderr)
            return 2
        try:
            args = json.loads(argv[3]) if len(argv) > 3 else {}
        except json.JSONDecodeError as e:
            print(f"erro: argumentos nao sao JSON valido: {e}", file=sys.stderr)
            return 2
        return chamar(argv[2], args, nao_destrutivo=not destrutivo_liberado)

    print(f"acao desconhecida: {acao}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
