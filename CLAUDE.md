# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run backend (from repo root)
cd backend && PYTHONPATH=. uvicorn main:app --reload

# Run all tests
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v

# Run a single test file
PYTHONPATH=backend python3 -m unittest backend/tests/test_agent_orchestrator.py -v

# Run a single test method
PYTHONPATH=backend python3 -m unittest backend.tests.test_agent_orchestrator.TestAgentOrchestrator.test_method_name -v

# Start Postgres (optional, default is SQLite)
docker compose up -d retrieval-db

# Bootstrap Postgres retrieval index
PYTHONPATH=backend python3 backend/scripts/bootstrap_postgres_retrieval.py

# Frontend is served at http://localhost:8000/app/ when backend runs
```

## Architecture

This is a **bounded Agentic RAG** credit assistant. The backend is FastAPI (Python); the frontend is vanilla JS served as static files.

### Request Flow (POST /chat)

1. **ChatOrchestrator** receives the request and runs QueryAnalyzer + AgentOrchestrator
2. **QueryAnalyzer** classifies the message into one of 5 categories: `SIMPLE_FACT`, `SIMPLE_REC`, `COMPLEX_EXPL`, `GENERAL_KNOW`, `UNSUPPORTED`
3. **ExecutionPlanner** builds a deterministic plan: which tools to call, whether retrieval is needed, max iterations
4. **AgentOrchestrator** executes the bounded loop:
   - Run planned **tools** (credit profile, metrics, payment history, inquiries, recommendations)
   - Run **RAG retrieval** if needed (hybrid BM25 + vector search)
   - **EvidenceBuilder** aggregates tool + retrieval results
   - **GroundedResponseComposer** generates the final answer via ModelGateway
5. Streaming responses use SSE with typed progress events

### Key Design Rules

- **Personal credit facts** come only from tools/repositories (JSON data files), never from retrieval or LLM
- **Retrieval** (RAG) is for educational/domain knowledge only
- **Complex answers** must combine both tool results and retrieval evidence
- The agentic loop is **bounded** — fixed tool passes + capped retrieval attempts, no open-ended looping

### LLM Gateway

`ModelGateway` is an abstract interface with four implementations selected by `MODEL_BACKEND` env var:
- `local` — rule-based, no external API (default for dev/tests)
- `openai` — GPT via OpenAI SDK
- `anthropic` — Claude via Anthropic SDK
- `remote` — custom HTTP endpoint

### Data Layer

- **Repository**: `JsonCreditRepository` loads synthetic data from `backend/data/*.json`
- **Retrieval**: Factory pattern creates SQLite (default) or Postgres+pgvector persistence
- **Embeddings**: `LocalHashEmbeddingProvider` — deterministic hash-based, no ML model needed
- Data is auto-seeded on startup if JSON files are missing

### Configuration

Environment variables via `backend/.env.example`. Key ones:
- `MODEL_BACKEND` — LLM provider (local/openai/anthropic/remote)
- `RETRIEVAL_BACKEND` — storage backend (sqlite/postgres)
- `RETRIEVAL_POSTGRES_DSN` — Postgres connection string

## Coding Guidelines (from AGENTS.md)

- Small focused modules with strong typing
- Pydantic models for API contracts (see `backend/app/schemas/`)
- Inspect existing code before changing architecture
- Implement real wiring, not empty abstractions
- Add tests for behavior changes
- Preserve backward compatibility where reasonable

## Compaction Rules
When compacting, always preserve:
- List of all modified files in this session
- Current task and progress status
- Test commands and their last results
- Any error messages or stack traces being debugged
- Which MODEL_BACKEND and RETRIEVAL_BACKEND are in use

## Testing Requirements
- Always run tests after making changes: PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
- If a test fails, fix it before moving on
- Add tests for any new behavior or bug fixes

## Common Pitfalls
- Personal credit data must NEVER come from RAG or LLM — only from JsonCreditRepository
- Always set PYTHONPATH=backend when running anything
- Don't modify files in backend/data/*.json unless explicitly asked
- The agentic loop must stay bounded — never introduce open-ended looping

## Git Workflow
- Always create a new branch before making changes: git checkout -b fix/description-of-change
- Commit after each logical unit of work, not at the end
- Write descriptive commit messages explaining WHY, not just WHAT
- Run tests before committing — never commit broken code
- Show git diff before pushing to let me review changes
- If something goes wrong: git reset --hard HEAD to undo last commit
- Never force push to main or shared branches
