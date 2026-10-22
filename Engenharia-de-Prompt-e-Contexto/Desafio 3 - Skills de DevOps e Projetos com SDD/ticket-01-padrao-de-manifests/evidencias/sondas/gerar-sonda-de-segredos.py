#!/usr/bin/env python3
"""
Gera `trivy-segredos-seis-formatos.yaml`, a sonda do experimento da regra 3.3.

O QUE O EXPERIMENTO MEDE
------------------------
Se o `trivy fs --scanners secret` detecta seis tipos de segredo num manifesto. Cinco têm
formato conhecido de credencial de terceiro; o sexto é uma senha dentro de string de
conexão. O resultado é **5 de 6** — e o que passa é justamente a senha na URI, que é a
forma mais comum de vazamento em manifesto. É por isso que a regra 3.3 ficou com o script
da skill em vez de ficar com a ferramenta.

POR QUE OS VALORES SÃO SORTEADOS A CADA EXECUÇÃO
------------------------------------------------
O experimento mede se o scanner reconhece a **forma**, não um valor específico. Qualquer
`AKIA` seguido de 16 caracteres dispara a regra; o valor em si é irrelevante para a
medição. Então este gerador sorteia.

A alternativa — guardar os valores no arquivo — foi tentada e abandonada por um motivo
que vale registrar como achado do ticket:

  1. Versionar a sonda com os valores: o **push protection do GitHub recusou o push**,
     com três violações (AWS Access Key ID, AWS Secret Access Key, Slack API Token).
  2. Guardar os valores em base64 dentro deste gerador: **o GitHub decodificou o base64
     e recusou de novo**, apontando as linhas exatas.

A segunda tentativa foi um erro de julgamento meu. Codificar valor para escapar de um
controle de segurança é o padrão que o controle existe para impedir, e não melhora por o
valor ser falso. Sortear resolve o problema de verdade: não existe credencial, nem em
texto nem codificada, em lugar nenhum do repositório.

Efeito colateral aceito: a sonda não é mais reprodutível byte a byte. O resultado da
medição é, e está registrado em `../relatorios/06-trivy-saida-crua.txt`.

Uso:
    python3 gerar-sonda-de-segredos.py            # escreve ao lado deste script
    python3 gerar-sonda-de-segredos.py --stdout   # imprime, sem escrever

Depois:
    trivy fs --scanners secret trivy-segredos-seis-formatos.yaml   # 5 de 6
    rm trivy-segredos-seis-formatos.yaml                            # nao commitar

O `.gitignore` da raiz do repositorio ja impede o commit por engano.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ARQUIVO = "trivy-segredos-seis-formatos.yaml"

MAIUSCULAS_DIGITOS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
BASE62 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
BASE64_CHARS = BASE62 + "+/"


def sortear(alfabeto: str, n: int) -> str:
    return "".join(secrets.choice(alfabeto) for _ in range(n))


def valores_sorteados() -> dict[str, str]:
    """
    Cada valor respeita a FORMA que o detector reconhece. Nada aqui é credencial.

    A senha da `DATABASE_URL` é fixa e legível de propósito: ela é o objeto do
    experimento, precisa ser identificável no relatório, e nenhum scanner a detecta —
    que é exatamente o achado.
    """
    return {
        # AKIA + 16 maiusculas/digitos
        "AWS_ACCESS_KEY_ID": "AKIA" + sortear(MAIUSCULAS_DIGITOS, 16),
        # 40 caracteres base64
        "AWS_SECRET_ACCESS_KEY": sortear(BASE64_CHARS, 40),
        # ghp_ + 36 base62
        "GITHUB_TOKEN": "ghp_" + sortear(BASE62, 36),
        # xoxb- + dois blocos numericos + bloco alfanumerico
        "SLACK_TOKEN": (
            "xoxb-" + sortear("0123456789", 12)
            + "-" + sortear("0123456789", 13)
            + "-" + sortear(BASE62, 24)
        ),
        # O unico valor fixo, e o unico que o Trivy NAO detecta.
        "DATABASE_URL": "postgres://nyx:s3nh4-do-banco@pg.nyx-prod.svc:5432/nyx",
    }


def bloco_de_chave_privada() -> str:
    """Bloco PEM com corpo sorteado, no formato que o detector de chave reconhece."""
    corpo = sortear(BASE64_CHARS, 64)
    marcador = "-" * 5
    cabeca = f"{marcador}BEGIN RSA PRIVATE KEY{marcador}"
    rodape = f"{marcador}END RSA PRIVATE KEY{marcador}"
    return "\n".join(f"    {linha}" for linha in (cabeca, corpo, rodape))


# A ordem coloca DATABASE_URL primeiro porque e o foco do experimento.
ORDEM = (
    "DATABASE_URL",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
    "SLACK_TOKEN",
)

CABECALHO = """\
# ============================================================================
# ARQUIVO GERADO por gerar-sonda-de-segredos.py — NAO COMMITAR.
#
# Os cinco valores de formato conhecido sao SORTEADOS a cada execucao. Nenhum e
# credencial real, e nenhum existe em lugar nenhum do repositorio: o gerador
# produz a forma, nao o valor.
#
# A senha da DATABASE_URL e fixa de proposito — ela e o objeto do experimento.
#
# Resultado esperado (Trivy 0.52.2): 5 dos 6 detectados. O que passa e a senha
# dentro da string de conexao, que e a forma mais comum de vazamento em
# manifesto e a razao de a regra 3.3 ficar com o script da skill.
#
# Saida registrada em ../relatorios/06-trivy-saida-crua.txt
# ============================================================================
"""


def montar() -> str:
    valores = valores_sorteados()
    linhas = [
        CABECALHO,
        "apiVersion: v1",
        "kind: ConfigMap",
        "metadata:",
        "  name: sonda-segredos",
        "  namespace: nyx-prod",
        "data:",
    ]
    for chave in ORDEM:
        linhas.append(f'  {chave}: "{valores[chave]}"')
    linhas.append("  PRIVATE_KEY: |")
    linhas.append(bloco_de_chave_privada())
    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Gera a sonda de segredos do experimento da regra 3.3"
    )
    ap.add_argument("--stdout", action="store_true", help="imprime em vez de escrever")
    args = ap.parse_args()

    conteudo = montar()
    if args.stdout:
        sys.stdout.write(conteudo)
        return 0

    destino = Path(__file__).resolve().parent / ARQUIVO
    destino.write_text(conteudo, encoding="utf-8")
    print(f"escrito: {destino}")
    print("  6 valores, 5 deles sorteados. Agora rode:")
    print(f"    trivy fs --scanners secret {ARQUIVO}")
    print("  esperado: 5 de 6 detectados (DATABASE_URL passa)")
    print(f"  ao terminar: rm {ARQUIVO}   # nao commitar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
