#!/usr/bin/env bash
# Sobe o laboratório de hosts auditados do Ticket 03.
#
# Dois containers com systemd como PID 1: um ajustado para conformidade (porta 2201) e um
# com desvios deliberados (porta 2202). O motivo de ser container, e as duas regras do
# baseline que ele não pode satisfazer, estão em docs/adr/ADR-004-laboratorio.md.
#
# O `--privileged` é do LABORATÓRIO, não da ferramenta. A ferramenta entra por SSH com
# usuário comum, e é justamente a falta de privilégio dela que exercita o CA-03.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHAVES="$HOME/desafio03-lab/t03/chaves"

echo "=== 1. par de chaves (a PRIVADA fica fora do repositorio) ==="
mkdir -p "$CHAVES"
cd "$CHAVES"
[ -f auditor ] || ssh-keygen -t ed25519 -N "" -f auditor -C "platform@metacortex-platform" -q
[ -f intruso ] || ssh-keygen -t ed25519 -N "" -f intruso -C "jdoe@laptop-pessoal" -q
chmod 600 auditor intruso
mkdir -p "$AQUI/chaves"
cp auditor.pub intruso.pub "$AQUI/chaves/"
echo "  auditor.pub : $(awk '{print $3}' auditor.pub)"
echo "  intruso.pub : $(awk '{print $3}' intruso.pub)   <- origem desconhecida, de proposito"

echo "=== 2. construindo as imagens ==="
cd "$AQUI"
docker build -q -f Dockerfile.base      -t roster-lab-base:1     . >/dev/null
docker build -q -f Dockerfile.conforme  -t roster-lab-conforme:1  . >/dev/null
docker build -q -f Dockerfile.desvios   -t roster-lab-desvios:1   . >/dev/null
echo "  roster-lab-base:1 roster-lab-conforme:1 roster-lab-desvios:1"

echo "=== 3. subindo os dois hosts ==="
docker rm -f roster-conforme roster-desvios >/dev/null 2>&1 || true

# Container recriado gera host key NOVA no mesmo endereco e porta. Com a entrada antiga em
# known_hosts, a ferramenta recusa a conexao: e esta CERTA: ela usa
# StrictHostKeyChecking=accept-new, que aceita host novo e barra host cuja chave mudou.
# Isso apareceu na primeira validacao depois de um rebuild, e o veredito foi
# "a chave do host mudou desde a ultima conexao".
# Limpar e higiene do LABORATORIO, nao concessao da ferramenta. Num parque de verdade,
# chave de host que muda sem reinstalacao e incidente de seguranca.
for p in 2201 2202; do
  ssh-keygen -R "[127.0.0.1]:$p" >/dev/null 2>&1 || true
done
docker run -d --name roster-conforme --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw -p 2201:22 roster-lab-conforme:1 >/dev/null
docker run -d --name roster-desvios  --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw -p 2202:22 roster-lab-desvios:1  >/dev/null

echo "=== 4. esperando o systemd ==="
for c in roster-conforme roster-desvios; do
  for _ in $(seq 1 30); do
    estado="$(docker exec "$c" systemctl is-system-running 2>/dev/null || true)"
    case "$estado" in running|degraded) break;; esac
    sleep 2
  done
  printf '  %-16s %s\n' "$c" "${estado:-sem resposta}"
done

echo "=== 5. estado das unidades que o baseline cobra ==="
for c in roster-conforme roster-desvios; do
  printf '  %s:\n' "$c"
  for u in ssh dbus chrony node_exporter containerd rpcbind.socket; do
    printf '    %-16s %s\n' "$u" "$(docker exec "$c" systemctl is-active "$u" 2>/dev/null || echo inactive)"
  done
done

echo "=== 6. SSH de fora, com a chave da plataforma ==="
for p in 2201 2202; do
  ssh -i "$CHAVES/auditor" -p "$p" -o StrictHostKeyChecking=no \
      -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o BatchMode=yes \
      auditor@127.0.0.1 'printf "  porta '"$p"': %s@%s, systemctl=%s\n" "$(whoami)" "$(hostname)" "$(systemctl is-system-running 2>&1)"' 2>/dev/null
done

echo
echo "Laboratorio no ar. Agora: ../validar.sh"
