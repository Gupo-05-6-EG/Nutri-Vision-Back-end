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

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/v1/health` | Liveness |
| GET | `/api/v1/health/db` | Readiness (consulta o banco) |
| GET | `/docs` | Swagger UI |

## Repositórios do projeto

- [Nutri-Vision-Back-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Back-end) — esta API
- [Nutri-Vision-Front-end](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end) — app Flutter (paciente)
- [Nutri-Vision-Front-end-Web](https://github.com/Gupo-05-6-EG/Nutri-Vision-Front-end-Web) — painel React (nutricionista)
- [Nutri-Vision-IA](https://github.com/Gupo-05-6-EG/Nutri-Vision-IA) — reconhecimento de alimentos
