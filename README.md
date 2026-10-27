# Nutri Vision — Back-end

API REST do Nutri Vision, em **FastAPI + SQLAlchemy + PostgreSQL**.

## Stack

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.12 |
| Framework web | FastAPI |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| Banco | PostgreSQL 16 |
| Testes | pytest (SQLite em memória) |
| Lint/format | ruff |
| CI | GitHub Actions |

## Estrutura

```
app/
├── main.py            # create_app(): CORS, rotas, OpenAPI
├── core/config.py     # Settings (pydantic-settings, lê o .env)
├── db/
│   ├── base.py        # Base declarativa + convenção de nomes
│   └── session.py     # engine, SessionLocal, get_db()
├── api/
│   ├── router.py      # agregador da API v1
│   └── routes/        # um módulo por recurso
├── models/            # modelos ORM (importar todos no __init__)
├── schemas/           # schemas Pydantic (entrada/saída)
└── services/          # regras de negócio
alembic/               # migrations
tests/                 # pytest
```

## Rodando localmente

### Com Docker (recomendado)

```bash
cp .env.example .env
docker compose up --build
```

A API sobe em <http://localhost:8000> e a documentação em <http://localhost:8000/docs>.

### Sem Docker

```bash
cp .env.example .env
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

> Sem Docker você precisa de um PostgreSQL rodando e do `DATABASE_URL` apontando pra ele.

## Variáveis de ambiente

Todas as variáveis estão documentadas em [`.env.example`](.env.example). O arquivo
`.env` é ignorado pelo git — nunca comite credenciais.

## Migrations

```bash
alembic revision --autogenerate -m "descricao"
alembic upgrade head
alembic downgrade -1
```

## Populando a TACO

Depois das migrations (`alembic upgrade head`), importe a Tabela Brasileira de
Composição de Alimentos (TACO, 4ª edição, NEPA/UNICAMP) para a tabela `alimento_taco`:

```bash
python scripts/importar_taco.py            # importa se a tabela estiver vazia
python scripts/importar_taco.py --recriar   # apaga tudo e reimporta
```

Os dados ficam em [`data/taco.csv`](data/taco.csv) (590 alimentos, valores por 100g).
Fonte: planilha oficial da UNICAMP, via [raulfdm/taco-api](https://github.com/raulfdm/taco-api)
(MIT). Sete itens da tabela original ficaram de fora por terem macro nutriente
essencial em branco na própria fonte (ex.: leite integral e desnatado sem
`kcal`/`proteína` preenchidos).

## Testes e qualidade

```bash
pytest                      # testes
pytest --cov=app            # com cobertura
ruff check .                # lint
ruff format .               # formatação
```

## CI/CD (RNF08)

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) roda em todo push e
pull request para `main`/`develop`, com quatro jobs:

1. **lint** — `ruff check` + `ruff format --check`
2. **test** — `pytest` com cobertura
3. **migrations** — `alembic upgrade head` + `alembic check` contra um Postgres real
4. **docker** — build da imagem e validação do `/health` no container

## Modelo de dados

### `refeicoes` — uma refeição registrada por um paciente

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int | PK |
| `paciente_id` | int | indexado; a FK para `usuarios` entra na Task 1.2 |
| `consumida_em` | timestamptz | quando a refeição foi consumida (gravado em UTC) |
| `tipo` | varchar(20) | `cafe_da_manha` \| `almoco` \| `lanche` \| `jantar` (RF19) |
| `observacao` | varchar(500) | opcional |
| `criada_em` / `atualizada_em` | timestamptz | auditoria |

### `itens_refeicao` — os alimentos daquela refeição

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int | PK |
| `refeicao_id` | int | FK → `refeicoes.id`, `ON DELETE CASCADE` |
| `nome_alimento` | varchar(160) | texto livre; o `alimento_id` da TACO entra na Task 2.2 |
| `quantidade_g` | numeric(8,2) | `> 0` (check constraint) |
| `calorias_kcal` | numeric(8,2) | `>= 0` |
| `proteinas_g` | numeric(8,2) | `>= 0` |
| `carboidratos_g` | numeric(8,2) | `>= 0` |
| `gorduras_g` | numeric(8,2) | `>= 0` |

**Os totais não são colunas.** Calorias e macros de uma refeição (e do dia) são
somados a partir dos itens na hora da leitura — uma soma gravada no banco
divergiria dos itens na primeira edição.

Índice `(paciente_id, consumida_em)` sustenta o histórico e o consumo diário.
Índice `(paciente_id, tipo)` sustenta o filtro por tipo (RF19).

**Categorização automática (RF19).** Se `tipo` não vier no `POST`, o service
sugere um valor a partir da hora de `consumida_em`: `cafe_da_manha` (05h–11h),
`almoco` (11h–15h), `jantar` (18h–22h); qualquer outro horário cai em `lanche`,
que funciona como categoria coringa. O cliente pode sempre informar `tipo`
explicitamente para sobrepor a sugestão.

### `pacientes` — triagem e teto calórico diário inicial

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int | PK, **sem autoincrement**: é o id do usuário (a FK para `usuarios` entra na Task 1.2) |
| `peso_kg` | numeric(5,2) | opcional; `> 0` |
| `altura_cm` | numeric(5,2) | opcional; `> 0` |
| `idade` | int | opcional; `> 0` |
| `genero` | varchar(30) | `masculino` \| `feminino` |
| `nivel_atividade` | varchar(30) | `sedentario` \| `leve` \| `moderado` \| `intenso` \| `muito_intenso` |
| `meta_kcal` | numeric(6,2) | teto calórico diário vigente; `>= 0` |
| `origem_meta` | varchar(30) | de onde veio a meta (hoje só `harris_benedict`) |

As colunas são opcionais porque o cadastro (Task 1.2) cria o paciente antes da triagem.

### `alimento_taco` — Banco Nutricional TACO (RF02.2)

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int | PK |
| `nome` | varchar(150) | indexado (usado na busca) |
| `categoria` | varchar(80) | categoria da TACO (ex.: "Cereais e derivados") |
| `kcal_100g` | numeric(6,2) | por 100g |
| `carbs_100g` | numeric(6,2) | por 100g |
| `prot_100g` | numeric(6,2) | por 100g |
| `gord_100g` | numeric(6,2) | por 100g |

Populada a partir da Tabela Brasileira de Composição de Alimentos (TACO, 4ª edição,
NEPA/UNICAMP) — veja [Populando a TACO](#populando-a-taco). O `alimento_id` em
`itens_refeicao` (ligando um item da refeição a um alimento desta tabela) entra
numa task futura, quando o front passar a montar refeições a partir da busca.

### `alimento_personalizado` — alimentos criados pelo paciente (RF22)

| Coluna | Tipo | Observação |
|---|---|---|
| `id` | int | PK |
| `paciente_id` | int | indexado; a FK para `usuarios` entra na Task 1.2 |
| `nome` | varchar(150) | indexado; único por paciente (`uq_alimento_personalizado_paciente_nome`) |
| `kcal_100g` | numeric(6,2) | por 100g; `>= 0` |
| `carbs_100g` | numeric(6,2) | por 100g; `>= 0` |
| `prot_100g` | numeric(6,2) | por 100g; `>= 0` |
| `gord_100g` | numeric(6,2) | por 100g; `>= 0` |
| `criado_em` | timestamptz | auditoria |

Mesmo formato por 100g da `alimento_taco`. Na API, `kcal_100g` vai até 900, cada macro
até 100 e carboidratos + proteínas + gorduras até 100 (g por 100g de alimento).

**Busca unificada.** `GET /api/v1/alimentos?nome=` devolve, numa lista só e em ordem
alfabética, alimentos da TACO e os personalizados do `paciente_id` informado. Sem
`paciente_id` só vem TACO: um alimento personalizado nunca aparece para outro paciente.
Cada item traz `origem` (`taco` \| `personalizado`) e `categoria` (`"Personalizado"` nos
personalizados); como os ids se repetem entre as duas tabelas, o alimento é identificado
por `origem` + `id`. Nome repetido do mesmo paciente (ignorando maiúsculas) → `409`.
`GET /api/v1/alimentos-taco` continua buscando só na TACO.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/health/db` | Readiness (consulta o banco) |
| POST | `/api/v1/refeicoes` | Registra uma refeição com seus itens (RF04); `tipo` opcional, sugerido pelo horário se omitido (RF19) |
| GET | `/api/v1/refeicoes?paciente_id=&data=&tipo=` | Histórico, opcionalmente de um dia e/ou tipo (RF12, RF19) |
| GET | `/api/v1/refeicoes/consumo-diario?paciente_id=&data=&tipo=` | Consumo do dia com os totais, opcionalmente de um tipo (RF12, RF19) |
| GET | `/api/v1/refeicoes/{id}` | Detalhe de uma refeição |
| PUT | `/api/v1/refeicoes/{id}` | Atualiza a refeição (substitui os itens) |
| DELETE | `/api/v1/refeicoes/{id}` | Remove a refeição e seus itens |
| POST | `/api/v1/pacientes/{paciente_id}/triagem` | Recebe a triagem e gera/salva o teto calórico diário inicial (RF14) |
| GET | `/api/v1/alimentos-taco?nome=` | Busca alimentos da TACO por nome (RF02.2) |
| POST | `/api/v1/alimentos-personalizados` | Cadastra um alimento sem correspondência na TACO, com valores por 100g (RF22) |
| POST | `/api/v1/calculo-nutricional` | Mapeia classes da IA para a TACO e calcula kcal/macros por porção (RF03, RF20, RF21) |
| POST | `/api/v1/amizades` | Envia uma solicitação de amizade para outro paciente (RF05) |
| PUT | `/api/v1/amizades/{id}/responder` | Aceita ou recusa convite de amizade recebido (RF05) |
| GET | `/api/v1/amizades?paciente_id=&status=` | Lista amigos e convites de um paciente (RF05) |
| DELETE | `/api/v1/amizades/{id}?paciente_id=` | Desfaz uma amizade ou cancela uma solicitação (RF05) |
| GET | `/api/v1/gamificacao/leaderboard?paciente_id=&limite=` | Leaderboard: Top 10 amigos por ganho de XP na janela semanal (RF05.3, RF29) |
| GET | `/api/v1/privacidade/ranking-publico?paciente_id=&limite=` | Ranking público LGPD: expõe estritamente nome, avatar, pontos e streak (RF29, RNF07) |
| GET | `/api/v1/privacidade/desafios/{id}/publico?participantes=` | Desafio público LGPD: expõe estritamente nome, avatar, pontos e streak (RF05.2, RF29) |
| POST | `/api/v1/gamificacao/xp` | Concede pontos de XP ao paciente e registra histórico (RF05, RF16) |
| GET | `/api/v1/gamificacao/historico-xp?paciente_id=` | Histórico auditável de XP do paciente (RF16) |
| GET | `/docs` | Swagger UI |


> **`paciente_id` por parâmetro é temporário.** Ainda não existe autenticação: a
> Task 1.2 passa a tirar o paciente do token JWT e a Task 1.6 aplica o controle
> de acesso por perfil e vínculo.

### Exemplo

```bash
curl -X POST http://localhost:8000/api/v1/refeicoes   -H 'Content-Type: application/json'   -d '{
    "paciente_id": 1,
    "consumida_em": "2026-09-20T12:30:00Z",
    "observacao": "Almoço em casa",
    "itens": [
      {"nome_alimento": "Arroz branco cozido", "quantidade_g": 150,
       "calorias_kcal": 193.5, "proteinas_g": 3.75,
       "carboidratos_g": 42.45, "gorduras_g": 0.3}
    ]
  }'

curl 'http://localhost:8000/api/v1/refeicoes/consumo-diario?paciente_id=1&data=2026-09-20'
```

### Cálculo nutricional por porção (RF03, RF20, RF21)

`POST /api/v1/calculo-nutricional` recebe as classes reconhecidas pelo modelo de IA,
o método de preparo e as gramas, e devolve a tabela nutricional da refeição (kcal,
proteínas, carboidratos e gorduras por item e total). Não grava nada.

```json
{"itens": [{"classe": "arroz", "metodo_preparo": "cozido", "gramas": 150}]}
```

- `metodo_preparo`: `cru` \| `cozido` \| `frito`.
- O de-para (classe + preparo → alimento da TACO) fica em
  [`data/mapeamento_ia_taco.csv`](data/mapeamento_ia_taco.csv); para suportar uma
  classe nova do modelo basta adicionar linhas lá (o nome precisa existir em `data/taco.csv`).
- Fórmula: `nutriente = valor_por_100g × gramas / 100`, 2 casas (meio para cima); o total
  soma os itens já arredondados.
- Combinação sem mapeamento → `422`; alimento do de-para ausente em `alimento_taco`
  (importação não rodada) → `404`.

### Cálculo basal (RF14)

`POST /api/v1/pacientes/{paciente_id}/triagem` recebe os dados da triagem, calcula o
**Teto Calórico Diário Inicial** e o salva em `pacientes.meta_kcal`
(`origem_meta = "harris_benedict"`). Se o paciente ainda não existe ele é criado; se já
existe, a triagem e o teto são sobrescritos (refazer a triagem gera um novo teto).

**Corpo da requisição** — todos os campos são obrigatórios:

| Campo | Tipo | Regra |
|---|---|---|
| `peso_kg` | número | 20 a 250, até 2 casas decimais |
| `altura_cm` | número | 100 a 250, até 2 casas decimais (**centímetros**, não metros) |
| `idade` | inteiro | 10 a 120 |
| `genero` | texto | `masculino` \| `feminino` |
| `nivel_atividade` | texto | `sedentario` \| `leve` \| `moderado` \| `intenso` \| `muito_intenso` |

**Como o teto é calculado**

1. **TMB** pela equação de Harris-Benedict original (1919), em kcal/dia:
   - homem: `66,47 + 13,75 × peso + 5,003 × altura − 6,755 × idade`
   - mulher: `655,1 + 9,563 × peso + 1,850 × altura − 4,676 × idade`
2. **Teto calórico** = TMB × fator do nível de atividade:

| `nivel_atividade` | Fator |
|---|---|
| `sedentario` | 1,2 |
| `leve` | 1,375 |
| `moderado` | 1,55 |
| `intenso` | 1,725 |
| `muito_intenso` | 1,9 |

Os resultados são arredondados para 2 casas (meio para cima). Os valores devolvidos
batem entre si: `tmb_kcal × fator_atividade = teto_calorico_kcal`.

```bash
curl -X POST http://localhost:8000/api/v1/pacientes/1/triagem   -H 'Content-Type: application/json'   -d '{"peso_kg": 80, "altura_cm": 180, "idade": 30, "genero": "masculino", "nivel_atividade": "moderado"}'
```

```json
{
  "paciente_id": 1,
  "tmb_kcal": 1864.36,
  "fator_atividade": 1.55,
  "teto_calorico_kcal": 2889.76,
  "origem_meta": "harris_benedict"
}
```

Dados inválidos devolvem `422`.

### Valores nutricionais

No banco são `numeric(8,2)` e no código `Decimal` — as somas são exatas, sem erro
de ponto flutuante. **No JSON saem como número** (`193.5`, não `"193.50"`), para
o app e o painel não precisarem fazer parse de texto em campo numérico.

### Fusos horários

Todos os instantes são gravados e devolvidos em **UTC**, sempre com offset no
JSON. O agrupamento por dia usa o dia em UTC — a conversão para o fuso do
paciente fica no app e no painel.

## Documentação Técnica do Sistema

Para entender a arquitetura completa, integrações e modelagem de dados:
- [Documento de Arquitetura](../Documentação/ARQUITETURA.md) — Visão C4, fluxos de integração e motor de regras.
- [Modelagem de Banco de Dados](../Documentação/BANCO_DE_DADOS.md) — DER completo e dicionário de dados.

## Repositórios do projeto

- [Nutri-Vision-Back-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Back-end) — esta API
- [Nutri-Vision-Front-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end) — app Flutter (paciente)
- [Nutri-Vision-Front-end-Web](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end-Web) — painel React (nutricionista)
- [Nutri-Vision-IA](https://github.com/Gupo-05-6-EG/Nutri-Vision-IA) — reconhecimento de alimentos
