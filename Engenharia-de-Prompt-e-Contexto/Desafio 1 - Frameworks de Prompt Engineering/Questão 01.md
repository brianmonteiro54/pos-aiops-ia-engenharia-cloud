# Questão 01 — Dockerfile para o Lift

**Framework:** R-T-F (Role, Task, Format)

---

## Prompt

````text
[ROLE]
Você é um engenheiro de plataforma sênior especializado em containerização de aplicações Python para Kubernetes, com experiência em hardening de imagens, redução de superfície de ataque e otimização de tempo de build.

[TASK]
Escreva o Dockerfile de produção que está faltando no projeto "Lift", produto em beta da Hill Valley Tech que vai sair de VMs e passar a rodar no cluster Kubernetes da empresa.

Contexto técnico do projeto:

- Aplicação: API em Python/Flask
- Estrutura do repositório:

```
lift/
├── app.py
├── requirements.txt
├── lib/
└── tests/
```

- Conteúdo do requirements.txt (versões fixadas):

```
Flask==3.0.0
gunicorn==21.2.0
requests==2.31.0
python-dotenv==1.0.0
psycopg2-binary==2.9.9
```

- Porta da aplicação: 8080
- Comando de start em produção: `gunicorn --bind 0.0.0.0:8080 --workers 4 app:app`
- Variáveis de ambiente obrigatórias em runtime: DATABASE_URL e API_KEY (injetadas pelo Kubernetes, nunca com valor embutido na imagem)

Requisitos obrigatórios de boas práticas que o Dockerfile deve cumprir:

1. Multi-stage build: um estágio para instalar/compilar dependências e um estágio final contendo apenas o necessário para rodar.
2. Imagem base enxuta e com tag fixa (ex.: python:3.12-slim). Nunca usar :latest.
3. Cache eficiente de camadas: copiar requirements.txt e instalar as dependências antes de copiar o código da aplicação.
4. Usuário não-root dedicado, com UID e GID explícitos, executando o processo final.
5. EXPOSE 8080 e CMD em formato exec (array), reproduzindo exatamente o comando de start de produção.
6. Não levar para a imagem final: pasta tests/, arquivos .env, .git, caches e artefatos de build. Se for necessário um .dockerignore, entregue também.
7. DATABASE_URL e API_KEY tratadas como obrigatórias em runtime, sem valor default e sem segredo hardcoded.
8. Variáveis de ambiente adequadas para container: PYTHONDONTWRITEBYTECODE e PYTHONUNBUFFERED.
9. psycopg2-binary e gunicorn devem funcionar na imagem slim: resolva as dependências de sistema necessárias no estágio correto, sem inflar a imagem final.
10. HEALTHCHECK apenas se não conflitar com as probes do Kubernetes. Se optar por não incluir, justifique em comentário.

[FORMAT]
Responda somente com o Dockerfile, dentro de um único bloco de código.

- Sem texto introdutório, sem explicação em prosa antes ou depois, sem conclusão.
- Toda explicação deve estar em comentários (#) dentro do próprio Dockerfile, em português, com uma linha de comentário antes de cada instrução ou bloco relevante justificando a decisão técnica.
- No topo do arquivo, um comentário de cabeçalho com: propósito, imagem base escolhida, porta exposta e variáveis de ambiente obrigatórias.
- Se o .dockerignore for necessário, coloque-o em um segundo bloco de código imediatamente após o primeiro, sem nenhum texto entre os dois blocos.
````

---

## Modelo

**Gemini Pro (Google) — modo de raciocínio estendido**

Escolhido porque a tarefa é geração de um único artefato técnico com muitas restrições simultâneas (10 requisitos de boas práticas + formato de saída restritivo), cenário em que o raciocínio estendido ajuda o modelo a resolver os trade-offs entre estágios do build antes de escrever o arquivo.

---

## Output

```dockerfile
# Propósito: Dockerfile de produção (Multi-stage) para a API "Lift" em ambiente Kubernetes
# Imagem Base: python:3.12-slim
# Porta Exposta: 8080
# Variáveis de Ambiente Obrigatórias (Runtime): DATABASE_URL, API_KEY (injetadas via secrets/configmaps K8s)

# -----------------------------------------------------------------------------
# Estágio 1: Builder (Compilação e preparação de dependências)
# -----------------------------------------------------------------------------

# Utilizamos a versão slim como base builder para manter a mesma arquitetura de sistema,
# fixando a tag menor para garantir reproduções determinísticas de build.
FROM python:3.12-slim AS builder

# Ajustes de comportamento do interpretador Python para containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instalamos dependências de sistema para build.
# O psycopg2-binary e o gunicorn podem requerer bibliotecas de C durante a instalação ou extração (gcc, libpq-dev).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Criamos um virtual environment isolado para facilitar a transferência limpa de pacotes Python para a imagem final.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copiamos apenas o arquivo de dependências primeiro.
# Isso garante um cache eficiente da camada do Docker caso o código fonte mude, mas as dependências não.
WORKDIR /build
COPY requirements.txt .

# Instalamos as dependências garantindo que o cache do pip não seja armazenado.
RUN pip install --no-cache-dir -r requirements.txt

# -----------------------------------------------------------------------------
# Estágio 2: Production (Imagem final minimalista)
# -----------------------------------------------------------------------------

# Iniciamos uma nova camada do zero baseada na mesma imagem slim para descartar compiladores e lixo do build.
FROM python:3.12-slim

# Replicamos as variáveis do Python e adicionamos o venv ao PATH para que o Gunicorn/Flask fiquem disponíveis.
# PYTHONDONTWRITEBYTECODE previne a criação de artefatos desnecessários (.pyc).
# PYTHONUNBUFFERED força o envio de logs do stdout/stderr em tempo real, crucial para os logs do K8s.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Instalamos as dependências de sistema dinâmicas vitais para runtime.
# libpq5 é estritamente necessário para o driver PostgreSQL, mas sem o "peso" do libpq-dev ou gcc, reduzindo superfície de ataque.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Criamos um usuário e grupo dedicados sem permissões de root.
# Especificamos UID/GID explícitos (10001) para previsibilidade em SecurityContexts do Kubernetes.
# Removemos o diretório home e setamos o shell como /bin/false para endurecimento (hardening).
RUN groupadd -g 10001 liftgroup && \
    useradd -u 10001 -g liftgroup -s /bin/false --no-create-home liftuser

# Definimos o diretório de trabalho padrão.
WORKDIR /app

# Copiamos apenas o virtual environment do estágio de build. Todo o cache de C e compiladores ficam para trás.
COPY --from=builder /opt/venv /opt/venv

# Copiamos exclusivamente o código necessário para a aplicação rodar.
# A ausência de testes, .env e .git é garantida pela combinação das instruções COPY explícitas com o .dockerignore.
COPY app.py .
COPY lib/ ./lib/

# Ajustamos o dono dos arquivos para o usuário não-root.
RUN chown -R liftuser:liftgroup /app

# Alteramos o contexto de execução para o usuário não-root antes da declaração de processos de runtime.
USER liftuser

# Justificativa técnica: Omitimos a instrução HEALTHCHECK nativa do Docker.
# Em ambientes Kubernetes, delegamos essa responsabilidade exclusivamente para o Kubelet
# usando livenessProbe e readinessProbe no Deployment manifest, evitando ciclos de vida concorrentes/conflitantes.

# Documentamos a porta padrão da aplicação para runtime (serve como metadado).
EXPOSE 8080

# Usamos o formato "exec" (JSON array) no CMD em vez do formato "shell".
# Isso assegura que o Gunicorn seja o PID 1 e receba adequadamente os sinais POSIX (como SIGTERM)
# enviados pelo K8s durante pods terminations e rolling updates (Graceful Shutdown).
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "app:app"]
```

```dockerignore
.git/
.gitignore
.env
tests/
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/
venv/
.venv/
env/
pip-log.txt
Dockerfile
.dockerignore
```

---

## Justificativa

**Role:** o primeiro bloco fixa o modelo como engenheiro de plataforma sênior com experiência em hardening e redução de superfície de ataque, e é isso que aparece no output em decisões que não foram pedidas linha a linha: `libpq5` no runtime em vez de `libpq-dev`, shell `/bin/false` no usuário e UID/GID 10001 explícitos para casar com o `securityContext` do Kubernetes.

**Task:** a tarefa foi delimitada a um artefato único (o Dockerfile faltante) com todos os insumos no próprio prompt (estrutura do repo, requirements.txt com versões fixadas, porta 8080, comando de start e as duas variáveis de runtime) mais 10 requisitos não negociáveis, o que eliminou pergunta de volta e ambiguidade sobre o que gerar.

**Format:** o formato exigia só o Dockerfile em bloco de código, comentários em português antes de cada instrução, cabeçalho no topo e o `.dockerignore` em um segundo bloco sem texto entre eles; o modelo respondeu exatamente nesse formato, sem prosa introdutória nem conclusão, inclusive usando comentário para justificar a ausência do `HEALTHCHECK` conforme o requisito 10.
