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

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/health/db` | Readiness (consulta o banco) |
| POST | `/api/v1/refeicoes` | Registra uma refeição com seus itens (RF04) |
| GET | `/api/v1/refeicoes?paciente_id=&data=` | Histórico, opcionalmente de um dia (RF12) |
| GET | `/api/v1/refeicoes/consumo-diario?paciente_id=&data=` | Consumo do dia com os totais (RF12) |
| GET | `/api/v1/refeicoes/{id}` | Detalhe de uma refeição |
| PUT | `/api/v1/refeicoes/{id}` | Atualiza a refeição (substitui os itens) |
| DELETE | `/api/v1/refeicoes/{id}` | Remove a refeição e seus itens |
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

### Valores nutricionais

No banco são `numeric(8,2)` e no código `Decimal` — as somas são exatas, sem erro
de ponto flutuante. **No JSON saem como número** (`193.5`, não `"193.50"`), para
o app e o painel não precisarem fazer parse de texto em campo numérico.

### Fusos horários

Todos os instantes são gravados e devolvidos em **UTC**, sempre com offset no
JSON. O agrupamento por dia usa o dia em UTC — a conversão para o fuso do
paciente fica no app e no painel.

## Repositórios do projeto

- [Nutri-Vision-Back-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Back-end) — esta API
- [Nutri-Vision-Front-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end) — app Flutter (paciente)
- [Nutri-Vision-Front-end-Web](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end-Web) — painel React (nutricionista)
- [Nutri-Vision-IA](https://github.com/Gupo-05-6-EG/Nutri-Vision-IA) — reconhecimento de alimentos
