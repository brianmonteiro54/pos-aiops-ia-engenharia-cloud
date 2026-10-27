# Decisões: ServiceAccount de leitura restrita em `nyx-dev`

Objeto do PR: fixture de RBAC para exercitar **permissão negada** em um tipo de recurso.
Arquivo: `nyx-dev-leitor.yaml`. Padrão aplicado: revisão 2026-07-29.

## Não há projeto para abrir

As quatro regras do passo 3 (2.2 probes, 2.6 período de graça, 3.2 caminhos de escrita,
3.3 variáveis) pressupõem um workload. Este PR não cria container nenhum: são
ServiceAccount, Role e RoleBinding. O bloco "NÃO CONFERIDO" do script é texto fixo e
**não se aplica aqui**: não é pendência, é ausência de sujeito.

Se alguém depois pendurar um pod nesta SA, as quatro voltam a valer para esse pod, e o
`automountServiceAccountToken: true` terá de estar no manifesto do pod (ver abaixo).

## O tipo negado é `secrets`, e a negação é por omissão

O RBAC do Kubernetes **só permite**. Não existe `deny`, não existe verbo negativo, não
existe precedência entre regras. O efeito "negado" vem de `secrets` não estar em nenhuma
`rule` da Role. Quem procurar no YAML uma linha que proíbe não vai encontrar, e isso é o
desenho correto, não omissão acidental, e daí o comentário explícito no arquivo.

Consequência prática: a Role é a lista do que **passa**. Toda vez que alguém adicionar um
recurso ali, o conjunto de negados encolhe sem ninguém editar nada chamado "negado".

## `pods/exec`, `pods/attach` e `pods/portforward` ficam fora

Esta é a decisão que sustenta o teste. Com `get pods` a SA lê o spec do pod, mas com
`pods/exec` ela entra no container e lê o Secret **já montado** ali, por variável de
ambiente ou volume. O apiserver continuaria respondendo `Forbidden` para
`get secrets`, e o segredo sairia pela porta do lado: o teste mediria a resposta da API,
não a confidencialidade.

`pods/log` ficou **dentro**, porque é o que torna a SA útil para diagnóstico. O risco
residual é aplicação que loga segredo, o que é problema da regra 3.3 na aplicação, não
deste RBAC.

## `Role`, não `ClusterRole`

O alcance para em `nyx-dev`. Isso dá dois casos de negação pelo preço de um:

| Comando | Resultado esperado | Motivo |
|---|---|---|
| `get pods -n nyx-dev` | permitido | está na Role |
| `get secrets -n nyx-dev` | **negado** | o tipo negado |
| `get pods -n orion-prod` | **negado** | RoleBinding não alcança outro namespace |
| `get pods -A` | **negado** | listar em todos os namespaces é decisão cluster-scoped |
| `get nodes` | **negado** | recurso cluster-scoped, Role não alcança |
| `delete pod` | **negado** | só `get`/`list`/`watch` |

## `automountServiceAccountToken: false` na SA, apesar da regra 3.4

A regra 3.4 obriga `false` **quando a aplicação não fala com a API**. Aqui a SA existe
para falar com a API, então a condição da regra não é o que decide. Mantive `false` por
outro motivo: o teste planejado é por **impersonação** (`--as`), que não usa token, e
deixar o default da SA em `true` entregaria credencial a qualquer pod que a referencie
depois. Pod que precise do token pede `automountServiceAccountToken: true` no próprio
spec, e aí a decisão aparece no manifesto do workload em vez de ficar implícita aqui.

Não é desvio da 3.4: é a leitura restritiva dela.

## Namespace não redeclarado

`nyx-dev` é declarado em `../kube-news/nyx-dev.yaml`. Não repeti o objeto aqui para não
existirem dois arquivos donos do mesmo Namespace, com rótulos que podem divergir no
futuro. Custo: este arquivo não sobe sozinho em cluster novo sem o namespace existir.

## Verificação executada

```
python3 scripts/conferir_manifesto.py manifests/rbac-leitura-restrita   # rc=0
kubectl apply --dry-run=server -f nyx-dev-leitor.yaml                   # 3 objetos ok
```

Nenhuma violação mecânica. Regras 1.1, 1.2, 1.3, 1.5 conferidas nos três objetos; 1.4,
1.6 e o bloco 2 inteiro não têm sujeito neste PR.

## Verificação que ficou com o operador

O fixture só mede o que se propõe se **nenhum outro binding** somar permissão a esta SA.
Antes de concluir que a negação é do desenho, confira o que mais alcança o sujeito e os
grupos automáticos (`system:authenticated`, `system:serviceaccounts`,
`system:serviceaccounts:nyx-dev`):

```bash
kubectl get clusterrolebindings -o json \
  | jq -r '.items[] | select(.subjects[]? |
      (.name=="nyx-leitor" and .namespace=="nyx-dev")
      or .name=="system:authenticated"
      or (.name|startswith("system:serviceaccounts"))) | .metadata.name'
```

`system:discovery` e `system:basic-user` costumam aparecer e são esperados: dão descoberta
de API e `SelfSubjectAccessReview`, não leitura de recurso. Qualquer coisa além disso
precisa ser olhada antes de interpretar o resultado do teste.

Este comando não foi executado na geração do manifesto: ler estado de cluster está fora do
escopo da conferência de manifesto.
