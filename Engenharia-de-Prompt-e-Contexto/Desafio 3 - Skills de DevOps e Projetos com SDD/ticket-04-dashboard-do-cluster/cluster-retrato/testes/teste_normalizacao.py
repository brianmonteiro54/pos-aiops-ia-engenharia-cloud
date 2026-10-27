#!/usr/bin/env python3
"""Testes da camada de normalização e do portão de acesso.

`normalizar()` é função pura: recebe dicionário, devolve dicionário. Então estes testes
não precisam de cluster, e é aqui que os fatos estranhos da API ficam presos.

O JSON de entrada não é inventado: foi recortado da saída real de `kubectl -o json`
contra o cluster de laboratório nos quatro estados que o Ticket 02 construiu.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cluster_retrato import (  # noqa: E402
    PREFIXOS_PERMITIDOS, VerboProibido, _kubectl, _permitido, _tabela_pods,
    auditar_fonte, classificar, contar_por_namespace, limpar_ruido,
    normalizar_deployment, normalizar_endpoints, normalizar_pod,
    normalizar_servico, usuario_negado,
)

AQUI = os.path.dirname(os.path.abspath(__file__))
FONTE = os.path.join(os.path.dirname(AQUI), "cluster_retrato.py")


# ---------------------------------------------------------------- CA-03
class TesteEndpoints(unittest.TestCase):
    """As duas fontes, os quatro estados. Medido contra o cluster."""

    def test_slice_com_chave_nula_nao_quebra(self):
        """nyx-stg: selector não casa. A chave EXISTE com valor null -> TypeError."""
        itens = [{"metadata": {"namespace": "nyx-stg", "name": "nyx-api-wszq8",
                               "labels": {"kubernetes.io/service-name": "nyx-api"}},
                  "endpoints": None}]
        fora = normalizar_endpoints(itens, "endpointslices")
        self.assertEqual(fora[("nyx-stg", "nyx-api")]["prontos"], 0)
        self.assertEqual(fora[("nyx-stg", "nyx-api")]["total"], 0)

    def test_endpoints_com_chave_ausente_nao_quebra(self):
        """nyx-stg: na outra fonte a chave `subsets` NEM VEM -> KeyError."""
        itens = [{"metadata": {"namespace": "nyx-stg", "name": "nyx-api"}}]
        fora = normalizar_endpoints(itens, "endpoints")
        self.assertEqual(fora[("nyx-stg", "nyx-api")], {
            "prontos": 0, "total": 0, "fonte": "endpoints"})

    def test_slice_com_endpoints_nao_prontos(self):
        """nyx-prod: CrashLoopBackOff. Os endpoints EXISTEM e não servem.

        É o caso que contar endpoints erra: a lista tem 2, e a resposta é 0 pronto.
        """
        itens = [{"metadata": {"namespace": "nyx-prod", "name": "nyx-api-xbpqm",
                               "labels": {"kubernetes.io/service-name": "nyx-api"}},
                  "endpoints": [
                      {"addresses": ["10.42.1.8"],
                       "conditions": {"ready": False, "serving": False,
                                      "terminating": False}},
                      {"addresses": ["10.42.0.8"],
                       "conditions": {"ready": False, "serving": False,
                                      "terminating": False}}]}]
        fora = normalizar_endpoints(itens, "endpointslices")
        self.assertEqual(fora[("nyx-prod", "nyx-api")]["prontos"], 0)
        self.assertEqual(fora[("nyx-prod", "nyx-api")]["total"], 2)

    def test_endpoints_separa_prontos_de_nao_prontos(self):
        """Na fonte antiga o não-pronto vive em `notReadyAddresses`."""
        itens = [{"metadata": {"namespace": "nyx-prod", "name": "nyx-api"},
                  "subsets": [{"addresses": [{"ip": "10.42.0.1"}],
                               "notReadyAddresses": [{"ip": "10.42.0.8"},
                                                     {"ip": "10.42.1.8"}]}]}]
        fora = normalizar_endpoints(itens, "endpoints")
        self.assertEqual(fora[("nyx-prod", "nyx-api")]["prontos"], 1)
        self.assertEqual(fora[("nyx-prod", "nyx-api")]["total"], 3)

    def test_slice_pronto(self):
        itens = [{"metadata": {"namespace": "nyx-dev", "name": "nyx-api-w4tht",
                               "labels": {"kubernetes.io/service-name": "nyx-api"}},
                  "endpoints": [{"addresses": ["10.42.0.15"],
                                 "conditions": {"ready": True, "serving": True,
                                                "terminating": False}}]}]
        fora = normalizar_endpoints(itens, "endpointslices")
        self.assertEqual(fora[("nyx-dev", "nyx-api")]["prontos"], 1)

    def test_varios_slices_somam(self):
        """Caminho NÃO exercitado pelo cluster: ele tem 1 slice por service."""
        rotulo = {"kubernetes.io/service-name": "web"}
        itens = [
            {"metadata": {"namespace": "p", "name": "web-aaa", "labels": rotulo},
             "endpoints": [{"conditions": {"ready": True}},
                           {"conditions": {"ready": False}}]},
            {"metadata": {"namespace": "p", "name": "web-bbb", "labels": rotulo},
             "endpoints": [{"conditions": {"ready": True}}]},
        ]
        fora = normalizar_endpoints(itens, "endpointslices")
        self.assertEqual(fora[("p", "web")]["prontos"], 2)
        self.assertEqual(fora[("p", "web")]["total"], 3)

    def test_slice_sem_rotulo_de_service_e_ignorado(self):
        itens = [{"metadata": {"namespace": "p", "name": "orfao"},
                  "endpoints": [{"conditions": {"ready": True}}]}]
        self.assertEqual(normalizar_endpoints(itens, "endpointslices"), {})

    def test_servico_distingue_zero_de_zero_e_zero_de_n(self):
        """0/0 e 0/N contam histórias diferentes. É o que separa o chamado 3 do 1."""
        eps = {("a", "sem-pod"): {"prontos": 0, "total": 0, "fonte": "x"},
               ("a", "pod-quebrado"): {"prontos": 0, "total": 3, "fonte": "x"}}
        sem_pod = normalizar_servico(
            {"metadata": {"namespace": "a", "name": "sem-pod"},
             "spec": {"type": "ClusterIP", "selector": {"app": "x"}}}, eps)
        quebrado = normalizar_servico(
            {"metadata": {"namespace": "a", "name": "pod-quebrado"},
             "spec": {"type": "ClusterIP", "selector": {"app": "y"}}}, eps)
        self.assertTrue(sem_pod["quebrado"])
        self.assertIn("selector", sem_pod["diagnostico"])
        self.assertTrue(quebrado["quebrado"])
        self.assertIn("nenhum pronto", quebrado["diagnostico"])
        self.assertNotEqual(sem_pod["diagnostico"], quebrado["diagnostico"])

    def test_externalname_sem_endpoint_nao_e_defeito(self):
        svc = {"metadata": {"namespace": "a", "name": "externo"},
               "spec": {"type": "ExternalName"}}
        fora = normalizar_servico(svc, {("a", "externo"): {"prontos": 0, "total": 0,
                                                           "fonte": "x"}})
        self.assertFalse(fora["quebrado"])

    def test_servico_sem_dado_de_endpoint_e_desconhecido_nao_zero(self):
        """Se a consulta de endpoints falhou, a tela mostra `?`, não `0`."""
        fora = normalizar_servico(
            {"metadata": {"namespace": "a", "name": "x"},
             "spec": {"type": "ClusterIP", "selector": {"app": "x"}}}, {})
        self.assertFalse(fora["sabido"])
        self.assertFalse(fora["quebrado"])


# ---------------------------------------------------------------- CA-04
class TestePod(unittest.TestCase):

    def test_crashloop_com_phase_running_mostra_estado_e_causa(self):
        """O fato que derruba quem lê `status.phase`: a fase diz Running."""
        pod = {"metadata": {"namespace": "nyx-prod", "name": "nyx-api-x"},
               "spec": {"containers": [{"name": "api"}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "api", "ready": False, "restartCount": 38,
                    "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                    "lastState": {"terminated": {"reason": "OOMKilled"}}}]}}
        fora = normalizar_pod(pod)
        self.assertEqual(fora["fase"], "Running")
        self.assertEqual(fora["estado"], "CrashLoopBackOff")
        self.assertEqual(fora["causa"], "OOMKilled")
        self.assertEqual(fora["historico"], "")
        self.assertTrue(fora["quebrado"])
        self.assertEqual(fora["reinicios"], 38)

    def test_terminacao_antiga_em_container_rodando_e_historico(self):
        """A regra que a skill do Ticket 02 escreve e que eu havia ignorado aqui.

        `state: running` significa que `lastState` é historia, nao a causa de um
        chamado aberto. Medido no laboratorio: reinicio de no deixou
        `reason: Unknown` em 16 pods saudaveis, e a tela pintava os 16 de vermelho.
        """
        pod = {"metadata": {"namespace": "kube-system", "name": "coredns-x"},
               "spec": {"containers": [{"name": "coredns",
                                        "readinessProbe": {"httpGet": {}}}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "coredns", "ready": True, "restartCount": 1,
                    "state": {"running": {"startedAt": "2026-10-26T11:23:44Z"}},
                    "lastState": {"terminated": {"reason": "Unknown",
                                                 "exitCode": 255}}}]}}
        fora = normalizar_pod(pod)
        self.assertEqual(fora["causa"], "", "causa deve ficar vazia: nao e o chamado")
        self.assertEqual(fora["historico"], "Unknown")
        self.assertFalse(fora["quebrado"])
        self.assertEqual(fora["prontidao"], "pronto")

    def test_historico_nao_vira_vermelho_na_tela(self):
        """Fecha o circuito: a tela nao pode pintar historico como causa."""
        pod = {"metadata": {"namespace": "nyx-stg", "name": "nyx-api-y"},
               "spec": {"containers": [{"name": "api"}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "api", "ready": True, "restartCount": 6,
                    "state": {"running": {}},
                    "lastState": {"terminated": {"reason": "Error",
                                                 "exitCode": 1}}}]}}
        html = _tabela_pods([normalizar_pod(pod)])
        self.assertIn("(histórico)", html)
        self.assertNotIn("<span class=ruim>Error</span>", html)
        self.assertIn("voltou a rodar", html)

    def test_imagepullbackoff(self):
        pod = {"metadata": {"namespace": "orion-stg", "name": "orion-web-x"},
               "spec": {"containers": [{"name": "web"}]},
               "status": {"phase": "Pending", "containerStatuses": [
                   {"name": "web", "ready": False, "restartCount": 0,
                    "state": {"waiting": {"reason": "ImagePullBackOff"}}}]}}
        fora = normalizar_pod(pod)
        self.assertEqual(fora["estado"], "ImagePullBackOff")
        self.assertEqual(fora["causa"], "")
        self.assertTrue(fora["quebrado"])

    def test_reinicios_somam_entre_containers(self):
        pod = {"metadata": {}, "spec": {"containers": [{"name": "a"}, {"name": "b"}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "a", "ready": True, "restartCount": 3},
                   {"name": "b", "ready": True, "restartCount": 5}]}}
        self.assertEqual(normalizar_pod(pod)["reinicios"], 8)

    def test_pod_nao_agendado_cai_para_a_condicao(self):
        pod = {"metadata": {}, "spec": {"containers": [{"name": "a"}]},
               "status": {"phase": "Pending", "conditions": [
                   {"type": "PodScheduled", "status": "False",
                    "reason": "Unschedulable",
                    "message": "0/2 nodes are available: insufficient cpu."}]}}
        fora = normalizar_pod(pod)
        self.assertEqual(fora["estado"], "Unschedulable")
        self.assertIn("insufficient cpu", fora["causa"])

    def test_pod_concluido_nao_e_quebrado(self):
        pod = {"metadata": {}, "spec": {"containers": [{"name": "a"}]},
               "status": {"phase": "Succeeded", "containerStatuses": [
                   {"name": "a", "ready": False, "restartCount": 0,
                    "state": {"terminated": {"reason": "Completed",
                                             "exitCode": 0}}}]}}
        self.assertFalse(normalizar_pod(pod)["quebrado"])


# ---------------------------------------------------------------- RF-03
class TesteProntidaoPresumida(unittest.TestCase):

    def test_pronto_com_probe(self):
        pod = {"metadata": {}, "spec": {"containers": [
                   {"name": "a", "readinessProbe": {"httpGet": {"path": "/"}}}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "a", "ready": True, "restartCount": 0}]}}
        self.assertEqual(normalizar_pod(pod)["prontidao"], "pronto")

    def test_pronto_sem_probe_e_marcado(self):
        """fake-shop: sem endpoint de saúde. Pronto só quer dizer que subiu."""
        pod = {"metadata": {}, "spec": {"containers": [{"name": "a"}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "a", "ready": True, "restartCount": 0}]}}
        self.assertEqual(normalizar_pod(pod)["prontidao"], "pronto_sem_probe")

    def test_probe_em_initcontainer_nao_conta(self):
        pod = {"metadata": {},
               "spec": {"containers": [{"name": "a"}],
                        "initContainers": [
                            {"name": "i", "readinessProbe": {"exec": {}}}]},
               "status": {"phase": "Running", "containerStatuses": [
                   {"name": "a", "ready": True, "restartCount": 0}]}}
        self.assertEqual(normalizar_pod(pod)["prontidao"], "pronto_sem_probe")


# ---------------------------------------------------------------- CA-02
class TesteDeployment(unittest.TestCase):

    def test_readyreplicas_ausente_e_zero(self):
        """A API NÃO manda `readyReplicas` quando é zero."""
        dep = {"metadata": {"namespace": "nyx-prod", "name": "nyx-api"},
               "spec": {"replicas": 2}, "status": {"replicas": 2,
                                                   "unavailableReplicas": 2}}
        fora = normalizar_deployment(dep)
        self.assertEqual((fora["prontas"], fora["desejadas"]), (0, 2))
        self.assertTrue(fora["quebrado"])

    def test_replicas_omitido_vale_um(self):
        dep = {"metadata": {"namespace": "a", "name": "b"}, "spec": {},
               "status": {"readyReplicas": 1}}
        self.assertEqual(normalizar_deployment(dep)["desejadas"], 1)

    def test_escalado_para_zero_nao_e_quebrado(self):
        dep = {"metadata": {"namespace": "a", "name": "b"},
               "spec": {"replicas": 0}, "status": {}}
        self.assertFalse(normalizar_deployment(dep)["quebrado"])


class TesteContagem(unittest.TestCase):

    def test_conta_quebrados_por_namespace(self):
        pods = [{"namespace": "p", "nome": "a", "quebrado": True},
                {"namespace": "p", "nome": "b", "quebrado": False},
                {"namespace": "d", "nome": "c", "quebrado": True}]
        deps = [{"namespace": "p", "nome": "x", "quebrado": True}]
        svcs = [{"namespace": "p", "nome": "s", "quebrado": True}]
        fora = contar_por_namespace(["p", "d", "vazio"], pods, deps, svcs)
        self.assertEqual(fora["p"], {"pods": 1, "deployments": 1, "servicos": 1,
                                     "total": 3})
        self.assertEqual(fora["d"]["total"], 1)
        self.assertEqual(fora["vazio"]["total"], 0)


# ---------------------------------------------------------- CA-05 / CA-06
class TesteClassificacao(unittest.TestCase):
    """Os nove modos de falha medidos contra kubectl v1.33.13."""

    def test_porta_fechada(self):
        f = classificar("The connection to the server 127.0.0.1:59999 was refused"
                        " - did you specify the right host or port?")
        self.assertEqual(f.rotulo, "cluster_inacessivel")

    def test_endereco_nao_roteavel(self):
        f = classificar("Unable to connect to the server: context deadline exceeded")
        self.assertEqual(f.rotulo, "cluster_inacessivel")

    def test_token_invalido_e_expirado_caem_no_mesmo_rotulo(self):
        """Medido: o kubectl NÃO distingue. A tela não pode afirmar expiração."""
        msg = "error: You must be logged in to the server (Unauthorized)"
        self.assertEqual(classificar(msg).rotulo, "credencial_rejeitada")

    def test_cert_de_cliente_expirado_tambem(self):
        """Mesmo assinado pela CA real do cluster, a mensagem é a mesma."""
        msg = "error: You must be logged in to the server (Unauthorized)"
        f = classificar(msg)
        self.assertEqual(f.rotulo, "credencial_rejeitada")
        self.assertIn("expirada, inválida ou revogada", f.detalhe)

    def test_plugin_externo_informa_expiracao(self):
        """O único caso em que a expiração PODE ser afirmada."""
        f = classificar(
            "could not get token: ExpiredTokenException: the security token included"
            " in the request is expired\n"
            "Unable to connect to the server: getting credentials: exec: executable"
            " /x/plugin.sh failed with exit code 1")
        self.assertEqual(f.rotulo, "credencial_expirada")

    def test_plugin_ausente(self):
        f = classificar("Unable to connect to the server: getting credentials: exec:"
                        " executable aws-iam-authenticator not found")
        self.assertEqual(f.rotulo, "plugin_ausente")

    def test_ca_desconhecida(self):
        f = classificar("Unable to connect to the server: tls: failed to verify"
                        " certificate: x509: certificate signed by unknown authority")
        self.assertEqual(f.rotulo, "tls_desconhecido")

    def test_permissao_negada_e_local(self):
        f = classificar('Error from server (Forbidden): events is forbidden: User'
                        ' "system:serviceaccount:default:retrato-restrito" cannot'
                        ' list resource "events" in API group "" at the cluster scope')
        self.assertEqual(f.rotulo, "permissao_negada")
        self.assertFalse(f.global_, "permissão negada NÃO pode derrubar a tela")
        self.assertEqual(usuario_negado(f.bruto),
                         "system:serviceaccount:default:retrato-restrito")

    def test_configuracao_invalida(self):
        f = classificar("Error in configuration: context was not found for specified"
                        " context: nao-existe")
        self.assertEqual(f.rotulo, "configuracao_invalida")

    def test_falha_desconhecida_admite_ignorancia(self):
        f = classificar("algo totalmente novo que o kubectl inventou")
        self.assertEqual(f.rotulo, "nao_classificada")
        self.assertIn("algo totalmente novo", f.bruto)

    def test_ruido_de_diagnostico_e_descartado(self):
        bruto = (
            'E1023 09:33:19.056298  295376 memcache.go:265] "Unhandled Error"'
            ' err="couldn\'t get current server API group list: ..."\n'
            'E1023 09:33:19.057897  295376 memcache.go:265] "Unhandled Error"'
            ' err="couldn\'t get current server API group list: ..."\n'
            'The connection to the server 127.0.0.1:59999 was refused'
            ' - did you specify the right host or port?')
        limpo = limpar_ruido(bruto)
        self.assertNotIn("Unhandled Error", limpo)
        self.assertEqual(len(limpo.splitlines()), 1)
        self.assertEqual(classificar(bruto).rotulo, "cluster_inacessivel")

    def test_falhas_de_conexao_e_credencial_sao_globais(self):
        for msg in ("The connection to the server x was refused",
                    "error: You must be logged in to the server (Unauthorized)"):
            self.assertTrue(classificar(msg).global_)


# ---------------------------------------------------------------- CA-08
class TesteSomenteLeitura(unittest.TestCase):

    def test_portao_recusa_verbo_de_escrita(self):
        for verbo in ("delete", "apply", "scale", "patch", "edit", "exec",
                      "create", "replace", "drain", "cordon", "annotate", "run"):
            with self.subTest(verbo=verbo):
                self.assertFalse(_permitido([verbo, "pods"]))
                with self.assertRaises(VerboProibido):
                    _kubectl([verbo, "pods"])

    def test_portao_recusa_lista_vazia(self):
        with self.assertRaises(VerboProibido):
            _kubectl([])

    def test_portao_aceita_so_o_que_esta_na_lista(self):
        self.assertTrue(_permitido(["get", "pods"]))
        self.assertTrue(_permitido(["version", "-o", "json"]))
        self.assertTrue(_permitido(["api-resources"]))
        self.assertTrue(_permitido(["config", "view", "--minify"]))

    def test_config_so_aceita_view(self):
        """`config` NÃO está liberado por inteiro: tem subcomando de escrita."""
        for sub in ("set-context", "use-context", "set", "unset", "rename-context"):
            with self.subTest(sub=sub):
                self.assertFalse(_permitido(["config", sub, "x"]))

    def test_varredura_do_fonte_nao_encontra_verbo_de_escrita(self):
        self.assertEqual(auditar_fonte(FONTE), [])

    def test_a_varredura_realmente_pega_algo(self):
        """Teste do teste: um auditor que nunca acusa nada não vale nada."""
        import tempfile
        ruim = ('import subprocess\n'
                'def f():\n'
                '    subprocess.run(["kubectl", "delete", "pod", "x"])\n')
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as fh:
            fh.write(ruim)
            caminho = fh.name
        try:
            problemas = auditar_fonte(caminho)
            self.assertTrue(any("delete" in p for p in problemas), problemas)
            self.assertTrue(any("subprocess.run" in p for p in problemas), problemas)
        finally:
            os.unlink(caminho)

    def test_lista_branca_e_pequena_e_enumerada(self):
        self.assertEqual(
            sorted(" ".join(p) for p in PREFIXOS_PERMITIDOS),
            ["api-resources", "config view", "get", "version"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
