## Chat Latency Optimizations

This document summarizes the latency and streaming improvements applied to the backend `/chat` path.

### Scope

Execution path reviewed:

- `POST /chat`
- route
- chat orchestrator
- agent orchestrator
- execution planner
- tool registry and tools
- retrieval
- model gateway

Primary files changed:

- `backend/app/core/dependencies.py`
- `backend/app/repositories/json_credit_repository.py`
- `backend/app/services/execution_planner.py`
- `backend/app/services/agent_orchestrator.py`
- `backend/app/services/chat_orchestrator.py`
- `backend/app/services/grounded_response_composer.py`
- `backend/app/services/rag_service.py`
- `backend/app/retrieval/sqlite_store.py`
- `backend/app/gateway/model_gateway.py`

## What Changed

### 1. Expensive dependencies are now cached

The backend was rebuilding core objects on every request. Dependency factories now use process-level caching for:

- credit repository
- user, credit, metrics, recommendation, inquiry, and payment history services
- query analyzer
- RAG service
- execution planner
- evidence builder
- grounded response composer
- model gateway
- tool registry
- agent orchestrator
- chat orchestrator

This removes repeated construction, repeated file loads, repeated retrieval initialization, and repeated gateway setup from the hot path.

### 2. `JsonCreditRepository` now stays warm in memory

The JSON repository already loaded data in `__init__`, but it was being recreated on each request. The repository now:

- remains cached for reuse
- exposes a `reload()` path for explicit refresh
- builds per-user indexes in memory
- uses a lock for typical FastAPI multi-threaded access

This reduces request work from repeated list scans and repeated filesystem reads to in-memory lookups.

### 3. Retrieval initialization and vector row reads were reduced

`RagService` now guards index creation so concurrent requests do not race to build the same index.

SQLite retrieval now caches embedding rows in memory. This does not change the retrieval algorithm, but it removes repeated database reads for every vector search.

### 4. Orchestration is now deterministic where safe

The previous orchestration loop was structured like an iterative agent action planner. The backend now:

- runs a deterministic tool pass from the execution plan
- performs bounded retrieval retries only when needed
- appends explicit trace steps for each decision
- limits complex explanation planning to a small bounded retry window

For complex explanations, `max_iterations` was reduced from `6` to `3`.

This keeps behavior grounded but cuts loop overhead and avoids unnecessary decision churn.

### 5. Extra LLM action-planning calls were removed

OpenAI and remote gateways no longer spend model calls on `decide_action()`. Action planning now falls back to the local deterministic rule-based gateway.

The configured model backend is still used for final answer generation where appropriate.

This removes one of the most expensive avoidable latency sources for a single user message.

### 6. Timing instrumentation was added

The `/chat` path now records and logs timing for major stages, including:

- total request time
- query analysis time
- planner time
- orchestrator time
- tool execution time
- retrieval time
- evidence build time
- final generation time
- compose time
- streaming first-byte latency

Streaming responses now also include timing fields in the terminal SSE `end` event.

### 7. Streaming responsiveness was improved

The streaming path now emits:

- classification progress
- planning progress
- tool progress
- retrieval progress
- incremental model chunks

The remote model gateway was also updated to consume incremental upstream responses when the provider supports:

- SSE
- NDJSON
- plain-text chunked responses

If the upstream does not truly stream, the backend cannot create real token streaming artificially, but the code path now reflects the true capability more accurately.

## Before / After Reasoning

### Before

- Core services were rebuilt on every request.
- JSON-backed repository data was reloaded repeatedly through repeated dependency creation.
- RAG service and retrieval persistence were rebuilt per request.
- Complex requests spent extra orchestration work in a loop.
- Some model backends could make an avoidable LLM call for action planning before final answer generation.
- Remote streaming could be effectively full-buffered depending on the upstream behavior.
- Retrieval did repeated SQLite reads for vector rows.

### After

- Expensive dependencies are reused across requests.
- Repository data stays in memory and is indexed by user.
- Retrieval initialization is warmed and guarded.
- The orchestration path is deterministic and bounded.
- Final generation remains model-backed, but action planning does not burn extra LLM calls.
- Streaming emits progress and first content as early as the backend can produce it.
- Retrieval avoids repeated DB reads for cached embeddings.

## Remaining Bottlenecks

These areas were improved but not fully eliminated:

- Vector search still ranks embeddings in Python rather than using a dedicated ANN/vector index.
- Retrieval remains acceptable for the bundled small corpus, but it is still the main scalability bottleneck.
- Very fast local operations can log `0 ms` due to integer millisecond rounding.
- True token streaming still depends on the upstream model provider actually supporting incremental streaming.

## Tradeoffs

- Process-level singleton caching improves latency, but any future live-reload requirement should call explicit reload hooks rather than assuming automatic file refresh.
- Deterministic orchestration improves predictability and latency, but it intentionally reduces open-ended agent behavior.
- Retrieval caching improves hot-path performance, but it keeps more data resident in memory.

## Verification

Validated locally with:

```bash
python3 -m compileall backend/app
python3 -m unittest backend/tests/test_chat.py backend/tests/test_agent_orchestrator.py backend/tests/test_model_gateway.py
```

Both completed successfully after the refactor.
