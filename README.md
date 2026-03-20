# CreditAssistant

Current status: this backend now implements a bounded AgenticRAG architecture for the credit assistant flow, with model-driven next actions, tool use, retrieval, iterative retrieval retries, insufficient-evidence fallback, and grounded response validation.

## Architecture Docs

- Current backend flow: [docs/current-flow.md](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/current-flow.md)
- Current architecture diagram: [docs/current-architecture-flow.svg](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/current-architecture-flow.svg)
- Implemented agentic flow: [docs/implemented-agentic-flow.md](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/implemented-agentic-flow.md)
- Current vs target gap analysis: [docs/current-vs-target.md](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/current-vs-target.md)
- Target agentic-RAG architecture: [docs/target-agentic-rag.md](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/target-agentic-rag.md)
- Current AgenticRAG flow: [docs/agentic-rag-flow.md](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/docs/agentic-rag-flow.md)

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
