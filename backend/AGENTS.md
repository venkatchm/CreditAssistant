# AGENTS.md

## Project intent
This repository powers a credit assistant backend. Build toward a real Agentic RAG architecture, not a toy chatbot.

## Non-negotiables
- Personal credit facts must come from tools or structured repositories.
- Retrieval is for domain knowledge, not user truth.
- Complex answers should combine tools + retrieval.
- Prefer modular, testable Python.
- Keep FastAPI integration clean.
- Use Pydantic models for contracts.
- Avoid keyword-only fake RAG.
- Preserve backward compatibility where reasonable.

## Coding style
- Small focused modules
- Strong typing
- Minimal but useful comments
- Keep orchestration readable
- Add tests for behavior changes

## Delivery expectations
- Always inspect existing code before changing architecture
- Propose a migration path
- Implement real wiring, not empty abstractions
- Summarize changed files and remaining gaps