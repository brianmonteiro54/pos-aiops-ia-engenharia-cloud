#!/usr/bin/env bash
# Prepara os cenários de falha de ambiente do RF-04 (CA-05, CA-06, CA-07).
#
# Gera kubeconfigs quebrados de propósito FORA do repositório, em ~/desafio03-lab/t04,
# porque eles contêm token e chave privada de verdade — descartáveis, mas de verdade.
# Nada aqui entra no git.
set -euo pipefail

LAB="${LAB:-$HOME/desafio03-lab/t04}"
CLUSTER="${CLUSTER:-k3d-metacortex}"
mkdir -p "$LAB"
cd "$LAB"

echo "==> laboratório em $LAB"

# ---------------------------------------------------------------- base
kubectl config view --raw > kubeconfig-base.yaml
chmod 600 kubeconfig-base.yaml

# ------------------------------------------- CA-07: leitura restrita
# ClusterRole que concede os cinco tipos do RF-02 e NEGA eventos.
# É o formato de um contexto de leitura restrita de cliente.
echo "==> CA-07: ServiceAccount com eventos negados"
kubectl apply -f - <<'YAML' >/dev/null
apiVersion: v1
kind: ServiceAccount
metadata:
  name: retrato-restrito
  namespace: default
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: retrato-restrito
rules:
  - apiGroups: [""]
    resources: ["namespaces", "pods", "services", "endpoints"]
    verbs: ["get", "list"]
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list"]
  - apiGroups: ["discovery.k8s.io"]
    resources: ["endpointslices"]
    verbs: ["get", "list"]
  # eventos NÃO estão aqui. É o tipo negado do CA-07.
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: retrato-restrito
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: retrato-restrito
subjects:
  - kind: ServiceAccount
    name: retrato-restrito
    namespace: default
YAML

TOKEN_RESTRITO="$(kubectl create token retrato-restrito -n default --duration=24h)"

# -------------------------------------------------- os kubeconfigs
echo "==> montando kubeconfigs dos cenários"
TOKEN_RESTRITO="$TOKEN_RESTRITO" CLUSTER="$CLUSTER" python3 - <<'PY'
import os, yaml, base64, subprocess, json
from datetime import datetime, timedelta, timezone

base    = yaml.safe_load(open("kubeconfig-base.yaml"))
cluster = os.environ["CLUSTER"]
srv     = next(c for c in base["clusters"] if c["name"] == cluster)["cluster"]
usuario = base["users"][0]["user"]

def monta(saida, user, cluster_cfg=None, ns=None):
    ctx = {"cluster": "metacortex", "user": "u"}
    if ns:
        ctx["namespace"] = ns
    d = {"apiVersion": "v1", "kind": "Config",
         "clusters": [{"name": "metacortex", "cluster": cluster_cfg or dict(srv)}],
         "users":    [{"name": "u", "user": user}],
         "contexts": [{"name": "c", "context": ctx}],
         "current-context": "c"}
    yaml.safe_dump(d, open(saida, "w"))
    os.chmod(saida, 0o600)

# CA-05a — porta fechada: o pacote volta com RST, falha rápido
fora = {k: v for k, v in srv.items()}
fora["server"] = "https://127.0.0.1:59999"
monta("kubeconfig-fora.yaml", usuario, fora)

# CA-05b — IP não roteável: o pacote cai no vazio, kubectl TRAVA.
# É o cenário que prova que --request-timeout sozinho não basta.
buraco = {k: v for k, v in srv.items()}
buraco["server"] = "https://10.255.255.1:6443"
monta("kubeconfig-blackhole.yaml", usuario, buraco)

# CA-06a — token inválido
monta("kubeconfig-token-invalido.yaml", {"token": "token-de-mentira-que-nao-existe"})

# CA-06b — JWT com exp no passado
b64j = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).decode().rstrip("=")
agora = int(datetime.now(timezone.utc).timestamp())
jwt_velho = ".".join([
    b64j({"alg": "RS256", "kid": "x"}),
    b64j({"iss": "https://kubernetes.default.svc", "exp": agora - 3600,
          "sub": "system:serviceaccount:default:retrato-restrito"}),
    "assinatura-invalida"])
monta("kubeconfig-token-expirado.yaml", {"token": jwt_velho})

# CA-06c — certificado de cliente expirado, assinado pela CA DE VERDADE do cluster.
# Sem isso o erro seria "unknown authority", que é outro problema.
try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    nome_srv = subprocess.run(
        ["docker", "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, check=True).stdout
    nome_srv = next(l for l in nome_srv.splitlines() if l.endswith("-server-0"))
    for arq in ("client-ca.crt", "client-ca.key"):
        subprocess.run(["docker", "cp",
                        f"{nome_srv}:/var/lib/rancher/k3s/server/tls/{arq}", f"./{arq}"],
                       check=True, capture_output=True)
    os.chmod("client-ca.key", 0o600)

    ca_crt = x509.load_pem_x509_certificate(open("client-ca.crt", "rb").read())
    ca_key = serialization.load_pem_private_key(open("client-ca.key", "rb").read(),
                                                password=None)
    chave = ec.generate_private_key(ec.SECP256R1())
    agora_dt = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, "auditor-expirado"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "system:masters")]))
            .issuer_name(ca_crt.subject)
            .public_key(chave.public_key())
            .serial_number(x509.random_serial_number() or 1)
            .not_valid_before(agora_dt - timedelta(days=30))
            .not_valid_after(agora_dt - timedelta(days=1))      # expirou ontem
            .sign(ca_key, hashes.SHA256()))
    open("cliente-expirado.crt", "wb").write(cert.public_bytes(serialization.Encoding.PEM))
    open("cliente-expirado.key", "wb").write(chave.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    os.chmod("cliente-expirado.key", 0o600)
    b64f = lambda p: base64.b64encode(open(p, "rb").read()).decode()
    monta("kubeconfig-cert-expirado.yaml",
          {"client-certificate-data": b64f("cliente-expirado.crt"),
           "client-key-data":         b64f("cliente-expirado.key")})
    print("   cert de cliente expirado: ok")
except Exception as e:                                    # noqa: BLE001
    print(f"   cert de cliente expirado: PULADO ({type(e).__name__}: {e})")

# CA-06d — exec plugin que falha dizendo que o token venceu.
# É a forma que "credencial expirada" tem em EKS/GKE, e a ÚNICA que diz o motivo.
with open("plugin-falha.sh", "w") as f:
    f.write("#!/bin/bash\n"
            "echo 'could not get token: ExpiredTokenException: the security token "
            "included in the request is expired' >&2\n"
            "exit 1\n")
os.chmod("plugin-falha.sh", 0o755)
monta("kubeconfig-exec-falha.yaml",
      {"exec": {"apiVersion": "client.authentication.k8s.io/v1beta1",
                "command": os.path.abspath("plugin-falha.sh")}})

# CA-06e — exec plugin que nem existe
monta("kubeconfig-exec-ausente.yaml",
      {"exec": {"apiVersion": "client.authentication.k8s.io/v1beta1",
                "command": "aws-iam-authenticator-que-nao-existe",
                "args": ["token", "-i", "cluster"]}})

# CA-07 — leitura restrita, eventos negados
monta("kubeconfig-restrito.yaml", {"token": os.environ["TOKEN_RESTRITO"]}, ns="default")
print("   kubeconfigs escritos")
PY

echo
echo "==> prontos em $LAB:"
ls -1 kubeconfig-*.yaml | sed 's/^/   /'
echo
echo "   CA-05  kubeconfig-fora.yaml           porta fechada"
echo "   CA-05  kubeconfig-blackhole.yaml      IP não roteável (trava)"
echo "   CA-06  kubeconfig-token-invalido.yaml"
echo "   CA-06  kubeconfig-token-expirado.yaml"
echo "   CA-06  kubeconfig-cert-expirado.yaml"
echo "   CA-06  kubeconfig-exec-falha.yaml     diz 'ExpiredToken'"
echo "   CA-06  kubeconfig-exec-ausente.yaml"
echo "   CA-07  kubeconfig-restrito.yaml       eventos negados"
