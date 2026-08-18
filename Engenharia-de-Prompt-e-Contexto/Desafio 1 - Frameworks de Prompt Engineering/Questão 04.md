# Questão 04 — Relatório mensal de transações do Ledger

**Framework:** T-A-G (Task, Action, Goal)

---

## Prompt

````text
[TASK]
Gere a query SQL (PostgreSQL) que produz o relatório de crescimento de transações dos últimos 6 meses por categoria, a partir do schema do Ledger fornecido abaixo.

DDL das tabelas envolvidas:

```sql
CREATE TABLE customers (
    id        BIGSERIAL PRIMARY KEY,
    segment   VARCHAR(30) NOT NULL,
    country   CHAR(2)     NOT NULL,
    signup_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE transactions (
    id             BIGSERIAL PRIMARY KEY,
    customer_id    BIGINT      NOT NULL REFERENCES customers(id),
    category       VARCHAR(30) NOT NULL,
    amount_cents   BIGINT      NOT NULL,
    status         VARCHAR(20) NOT NULL,
    payment_method VARCHAR(30) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL,
    completed_at   TIMESTAMPTZ
);

CREATE INDEX idx_transactions_created_at        ON transactions (created_at);
CREATE INDEX idx_transactions_status_category   ON transactions (status, category);
CREATE INDEX idx_transactions_customer_id       ON transactions (customer_id);
```

Categorias válidas: subscription, one_time, refund, credit_adjustment.

[ACTION]
A query deve aplicar exatamente estas regras:

1. Filtrar somente transações com status = 'completed'. Nenhum outro status entra no resultado.
2. Recorte temporal: os últimos 6 meses corridos a partir da data de referência 2026-04-24, usando created_at como data da transação. Defina o início e o fim da janela de forma explícita e determinística no SQL, e registre em comentário a interpretação adotada para "6 meses corridos".
3. Agrupar por mês no formato YYYY-MM e por categoria.
4. Retornar, por linha: o mês (YYYY-MM), a categoria, a contagem de transações e o volume total convertido de centavos para reais com exatamente 2 casas decimais.
5. Usar tipo numérico exato na conversão de amount_cents para reais, sem risco de erro de arredondamento de ponto flutuante.
6. Escrever o filtro de data de modo a permitir o uso do índice idx_transactions_created_at, sem aplicar função sobre a coluna created_at na cláusula WHERE.
7. Não fazer join com customers: nenhuma informação de cliente é necessária neste relatório.
8. Ordenação final: mês crescente e, dentro de cada mês, categoria crescente.
9. Nomes de colunas do resultado legíveis e autoexplicativos, adequados para exportar direto para planilha.
10. Se um mês não tiver transações em alguma categoria, explique em comentário se essa combinação aparece ou não no resultado e como incluí-la com valor zero, caso seja desejado.

[GOAL]
Jennifer (PM) está fechando uma apresentação para a Goldie (CEO) sobre crescimento de transações por categoria nos últimos 6 meses. Ela não escreve SQL e vai apenas executar a query e copiar o resultado. Portanto o objetivo é uma query que rode de primeira, entregue números corretos segundo as regras de negócio acima e produza uma saída pronta para virar tabela e gráfico na apresentação, sem tratamento manual posterior.

Formato da resposta:

1. A query SQL completa em um bloco de código, comentada nos pontos de decisão (filtro de data, conversão de centavos, agrupamento).
2. Depois da query, uma lista curta com as premissas adotadas e um exemplo de 3 a 4 linhas de saída esperada, para a Jennifer conferir que entendeu o formato.
````

---

## Modelo

**GLM-5 (Zhipu AI)**

Escolhido porque a tarefa é geração de SQL preso a um schema conhecido e a regras de negócio verificáveis, cenário em que um modelo forte em código resolve bem sem custo de raciocínio longo, e porque adiciona um terceiro provider ao conjunto das 8 questões.

---

## Output

```sql
/*
 ============================================================================
 RELATÓRIO: Crescimento de Transações por Categoria (Últimos 6 Meses)
 DATA DE REFERÊNCIA: 2026-04-24
 INTERPRETAÇÃO DE "6 MESES CORRIDOS":
   Considera os 6 meses civis completos anteriores ao mês da data de referência.
   Data de referência: abril/2026
   Período: 01/10/2025 00:00:00 até 30/04/2026 23:59:59.999999

   Nota sobre índice: O filtro usa intervalo fechado sobre created_at, sem aplicar
   função sobre a coluna, permitindo o uso eficiente de idx_transactions_created_at.
 ============================================================================
*/

SELECT
    TO_CHAR(t.created_at, 'YYYY-MM') AS mes,
    t.category AS categoria,
    COUNT(*) AS total_transacoes,
    -- Conversão de centavos para reais usando tipo numérico exato (NUMERIC)
    -- Evita erros de arredondamento de ponto flutuante
    -- Divisão por 100.0 (literal numérico) garante resultado NUMERIC com casas decimais
    SUM(t.amount_cents) / 100.0 AS volume_reais
FROM
    transactions t
WHERE
    -- Regra 1: Apenas transações com status 'completed'
    t.status = 'completed'
    -- Regra 2: Filtro de data determinístico (6 meses corridos)
    -- Janela: 2025-10-01 até 2026-04-30 (fechado à direita com timestamp máximo)
    -- Uso de literal de timestamp sem função sobre a coluna → uso do índice
    AND t.created_at >= '2025-10-01 00:00:00'::timestamptz
    AND t.created_at <= '2026-04-30 23:59:59.999999'::timestamptz
GROUP BY
    TO_CHAR(t.created_at, 'YYYY-MM'),
    t.category
ORDER BY
    mes ASC,
    categoria ASC;

/*
 ============================================================================
 NOTA SOBRE COMBINAÇÕES MÊS+CATEGORIA SEM TRANSAÇÕES (Regra 10):

 Com a query acima, combinações mês+categoria sem transações NÃO aparecem
 no resultado. Para incluir todas as combinações com valor zero:

 1. Criar uma CTE com todas as categorias válidas:
    ('subscription', 'one_time', 'refund', 'credit_adjustment')

 2. Criar uma série de meses com generate_series()

 3. Fazer CROSS JOIN dessas duas fontes

 4. Fazer LEFT JOIN com os dados agregados

 5. Usar COALESCE(total_transacoes, 0) e COALESCE(volume_reais, 0.00)
 ============================================================================
*/
```

### Premissas Adotadas

- **Período de 6 meses corridos:** Interpretado como os 6 meses civis completos anteriores ao mês da data de referência (outubro/2025 a abril/2026), pois a data de referência 2026-04-24 está dentro de abril.
- **Conversão monetária:** `amount_cents / 100.0` com literal numérico garante tipo NUMERIC exato, evitando arredundamento de ponto flutuante.
- **Filtro de status:** Apenas `status = 'completed'` entra no relatório.
- **Uso de índice:** Filtro com literais de timestamp (`>=` e `<=`) sobre `created_at` permite o uso de `idx_transactions_created_at`.
- **Sem join com customers:** O relatório não requer informações do cliente.
- **Meses vazios:** Não aparecem no resultado. Para incluí-los, seria necessário gerar uma grade completa com CROSS JOIN de categorias e meses.

### Exemplo de Saída Esperada

| mes | categoria | total_transacoes | volume_reais |
|---|---|---:|---:|
| 2025-10 | one_time | 1523 | 45892.30 |
| 2025-10 | subscription | 892 | 127340.00 |
| 2025-11 | credit_adjustment | 45 | 2340.50 |
| 2026-04 | refund | 67 | 8920.15 |

---

## Justificativa

**Task:** a Task delimitou um artefato único (a query PostgreSQL) e entregou o DDL completo das duas tabelas, os índices e as categorias válidas dentro do prompt. Com o schema em mão o modelo não inventou coluna nem tabela: usou `status`, `category`, `amount_cents` e `created_at` exatamente como declarados, e respeitou o item 7 não fazendo join com `customers`.

**Action:** as 10 regras numeradas foram o que transformou "gere um relatório" em especificação executável: filtro de status, janela determinística com a interpretação registrada em comentário, agrupamento por `YYYY-MM` e categoria, conversão de centavos com tipo exato, filtro de data sem função sobre a coluna para permitir o índice `idx_transactions_created_at`, ordenação e nomes de coluna legíveis. Cada regra aparece rastreável no output, inclusive comentada pelo número ("Regra 1", "Regra 2", "Regra 10").

**Goal:** o Goal (Jennifer não escreve SQL, executa e cola na apresentação da Goldie) puxou o que a query sozinha não daria: a lista de premissas em linguagem de negócio e o exemplo de 3 a 4 linhas de saída, para ela conferir o formato antes de montar tabela e gráfico. Sem o Goal, o modelo provavelmente teria entregado só o SQL.

**O que eu faria diferente — três defeitos no output**

Os três pontos abaixo foram verificados executando a query exata do modelo em um PostgreSQL 16 com o DDL do enunciado e uma transação `completed` por mês entre set/2025 e mai/2026.

1. **A janela está errada e contradiz o próprio comentário.** O cabeçalho diz "6 meses civis completos anteriores ao mês da data de referência", o que seria outubro/2025 a março/2026. Mas o `WHERE` vai de `2025-10-01` a `2026-04-30` e a execução devolveu **7 linhas de mês** (2025-10 a 2026-04), sendo abril parcial porque a referência é dia 24. A Jennifer receberia 7 meses num relatório anunciado como de 6, com o último mês incompleto distorcendo a leitura de crescimento. Correção: fechar em `< '2026-04-01'` para a leitura de 6 meses civis completos, ou começar em `2025-11-01` se a intenção fosse incluir abril.
2. **As 2 casas decimais não estão garantidas.** A regra 4 pedia volume "com exatamente 2 casas decimais", mas `SUM(amount_cents) / 100.0` devolve `numeric` de escala alta: o valor saiu como `45892.300000000000`, não `45892.30`, exatamente o tratamento manual que o Goal queria evitar. Correção: `ROUND(SUM(t.amount_cents) / 100.0, 2)` ou cast para `numeric(14,2)`.
3. **Determinismo de timezone.** `created_at` é `TIMESTAMPTZ` e os literais da janela foram escritos sem offset, então tanto os limites quanto o `TO_CHAR(..., 'YYYY-MM')` dependem do `TimeZone` da sessão. No teste, a transação de `2026-04-01 00:30+00` foi rotulada como `2026-04` em UTC e como `2026-03` em `America/Sao_Paulo`: o mesmo dado cai em meses diferentes conforme quem executa. Para um número que vai para apresentação de CEO, o fuso deveria estar fixado no SQL.
