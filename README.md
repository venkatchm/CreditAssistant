# CreditAssistant

## Local Retrieval DB Demo

To see retrieval storage working against local Postgres with `pgvector`, install Docker Desktop and run:

```bash
docker compose up -d retrieval-db
```

Then copy `backend/.env.example` to your shell environment and switch to Postgres:

```bash
export RETRIEVAL_BACKEND=postgres
export RETRIEVAL_POSTGRES_DSN=postgresql://credit_user:credit_pass@localhost:5432/credit_assistant
export MODEL_BACKEND=local
```

Bootstrap the retrieval index:

```bash
PYTHONPATH=backend python3 backend/scripts/bootstrap_postgres_retrieval.py
```

Run tests:

```bash
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
```

GUI options for inspecting the stored data:
- TablePlus
- DBeaver
- pgAdmin
- Postico

Connection values:
- host: `localhost`
- port: `5432`
- database: `credit_assistant`
- user: `credit_user`
- password: `credit_pass`
