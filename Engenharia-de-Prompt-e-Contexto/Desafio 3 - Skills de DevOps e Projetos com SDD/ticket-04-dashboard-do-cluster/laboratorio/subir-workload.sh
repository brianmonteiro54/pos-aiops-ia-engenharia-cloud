#!/usr/bin/env bash
# Sobe no cluster os dois projetos cujos manifests a skill do Ticket 01 gerou.
#
#   kube-news  (cliente nyx)   -> namespace nyx-dev
#   fake-shop  (cliente orion) -> namespace orion-prod
#
# POR QUE A IMAGEM É SUBSTITUÍDA
# ------------------------------
# Os manifests do Ticket 01 apontam para `registry.metacortex.io`, porque a regra 3.7 do
# padrão da casa exige registry interno. Esse registry é da ficção do desafio e não existe —
# aplicar os manifests sem tocar nada dá ImagePullBackOff nos dois projetos.
#
# Então a substituição é SÓ da imagem, feita com `kubectl set image` DEPOIS do apply, e o
# manifesto versionado continua sendo o que passa nas 19 regras. Duas consequências que
# importam para o Ticket 04:
#
#   1. a regra 3.7 fica satisfeita no ARTEFATO e insatisfeita no CLUSTER. É a diferença
#      entre o que a skill do Ticket 01 julga (arquivo) e o que a skill do Ticket 02 vê
#      (estado). As duas estão certas, sobre coisas diferentes.
#   2. o dashboard vai mostrar a imagem real, `fabricioveronez/...`, e não a do manifesto.
#      Isso é correto: ele lê o cluster.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T01="$AQUI/../../ticket-01-padrao-de-manifests/manifests"

echo "=== 1. aplicando os manifests gerados no Ticket 01 ==="
kubectl apply -f "$T01/kube-news/nyx-dev.yaml"           >/dev/null
kubectl apply -f "$T01/kube-news/nyx-dev-postgres.yaml"  >/dev/null
kubectl apply -f "$T01/fake-shop/orion-prod.yaml"        >/dev/null
kubectl apply -f "$T01/fake-shop/orion-prod-postgres.yaml" >/dev/null
echo "  aplicados"

echo "=== 2. o Secret: o manifesto traz placeholder vazio de proposito ==="
# Regra 3.3: a senha nao entra em manifesto. O valor real e injetado no apply.
kubectl -n nyx-dev    create secret generic nyx-db   --from-literal=password='Pg#123' \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl -n orion-prod create secret generic orion-db --from-literal=password='Pg1234' \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
echo "  senhas injetadas (laboratorio)"

echo "=== 3. substituindo a imagem: registry.metacortex.io nao existe ==="
kubectl -n nyx-dev    set image deploy/nyx-api       api=fabricioveronez/kube-news:v1   >/dev/null
kubectl -n nyx-dev    set image deploy/nyx-postgres  postgres=postgres:16-alpine        >/dev/null
kubectl -n orion-prod set image deploy/orion-web     web=fabricioveronez/fake-shop:v26  >/dev/null
kubectl -n orion-prod set image deploy/orion-postgres postgres=postgres:16-alpine       >/dev/null
kubectl -n orion-prod set image job/orion-web-migracao migracao=fabricioveronez/fake-shop:v26 2>/dev/null \
  || echo "  (o Job nao aceita troca de imagem depois de criado; sera recriado abaixo)"

# O Job tem template imutavel: recriar com a imagem do laboratorio.
kubectl -n orion-prod delete job orion-web-migracao --ignore-not-found >/dev/null
kubectl -n orion-prod get deploy orion-web -o json 2>/dev/null >/dev/null

echo "=== 4. o UID do Postgres: a imagem alpine precisa do 70 ==="
# Os manifests ja declaram runAsUser 70 e fsGroup 70 — nada a fazer, so registrando.
echo "  ja declarado nos manifests do Ticket 01"

echo "=== 5. esperando ==="
sleep 45
for ns in nyx-dev orion-prod; do
  printf '\n  --- %s ---\n' "$ns"
  kubectl -n "$ns" get deploy,pod,svc 2>&1 | sed 's/  */ /g' | sed 's/^/  /'
done
echo
echo "Workload no ar. O dashboard le o CONTEXTO CORRENTE do kubeconfig: $(kubectl config current-context)"
