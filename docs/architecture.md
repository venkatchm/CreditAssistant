# Credit Assistant — Agentic RAG Architecture

## Data Ingestion (Offline)

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────┐
│ CFPB Website     │     │ Chunking      │     │ Embedding    │     │ Supabase │
│ 676 articles     │────>│ Paragraph-    │────>│ OpenAI       │────>│ Postgres │
│ Public domain    │     │ aware split   │     │ text-emb-    │     │          │
│ credit education │     │ max 800 chars │     │ 3-small      │     │ 4 tables │
│                  │     │ 1 sentence    │     │ 1536 dims    │     │          │
│ + knowledge.json │     │ overlap       │     │ batch=100    │     │          │
│ (local docs)     │     │              │     │              │     │          │
└─────────────────┘     │ 2,458 chunks  │     │ 2,458 vectors│     │          │
                         └──────────────┘     └─────────────┘     └──────────┘

Script: backend/scripts/ingest_cfpb.py
API:    POST /ingestion/cfpb
```

### Storage in Supabase

**Retrieval tables:**

| Table | Rows | Contents |
|-------|------|----------|
| `retrieval_documents` | 676 | doc_id, title, topic, raw content |
| `retrieval_chunks` | 2,458 | chunk_text, doc_id, chunk_index |
| `retrieval_chunk_embeddings` | 2,458 | vector(1536), HNSW index |
| `retrieval_chunk_lexical` | 2,458 | tsvector, GIN index |

**User/Credit data tables (seeded from JSON):**

| Table | Rows | Contents |
|-------|------|----------|
| `users` | 5 | user_id, name, age, occupation |
| `credit_reports` | 5 | score, band, bureau, factors |
| `credit_accounts` | 12 | issuer, limit, balance, status |
| `loan_accounts` | 6 | lender, original_balance, rate |
| `inquiries` | 8 | creditor, type, date, impact |
| `payment_history` | 108 | account_id, month, status |
| `credit_metrics` | 5 | utilization, trends JSONB |
| `recommendations` | 18 | title, priority, category |

---

## Runtime (Per Chat Request)

### Stage 1: Query Classification (0ms)

**File:** `query_analyzer.py` — Rule-based classifier, no LLM call.

Priority order:

| Priority | Pattern | Category | What happens |
|----------|---------|----------|-------------|
| 1 | Educational + credit topic ("what is", "how does", "how long" + credit term) | `GENERAL_KNOWLEDGE` | RAG only, no user data |
| 2 | Why/cause patterns ("why did", "score drop", "what caused") | `COMPLEX_EXPLANATION` | User data + RAG |
| 3 | Recommendation + credit topic ("how can I improve", "tips for" + credit term) | `COMPLEX_EXPLANATION` | User data + RAG |
| 4 | Personal data request ("show my", "list my", "what is my score") | `SIMPLE_FACT` | User data only, no RAG |
| 5 | Mentions credit topic | `GENERAL_KNOWLEDGE` | RAG only |
| 6 | None of the above | `UNSUPPORTED` | "not supported yet" |

### Stage 2: Execution Planning (0ms)

**File:** `execution_planner.py` — Maps category to execution plan.

| Category | Tools | Retrieval | Response Strategy |
|----------|-------|-----------|------------------|
| `GENERAL_KNOWLEDGE` | none | YES | RAG only |
| `COMPLEX_EXPLANATION` | 3-5 tools | YES | tools + RAG |
| `SIMPLE_RECOMMENDATION` | 2 tools | YES | tools + RAG |
| `SIMPLE_FACT` | 1-2 tools | NO | tools only |
| `UNSUPPORTED` | none | NO | fallback message |

### Stage 3: Agent Action Loop

**File:** `agent_orchestrator.py`

#### 3a. Tool Execution (if plan has tools)

First tool call triggers **parallel prefetch** of all user data:

```
ThreadPoolExecutor(4 workers)
ConnectionPool(min=1, max=5)

Batch 1 (4 threads, 4 connections from pool):           ~100ms
  Thread 1: SELECT * FROM users WHERE user_id=...
  Thread 2: SELECT * FROM credit_reports WHERE user_id=...
  Thread 3: SELECT * FROM credit_accounts WHERE user_id=...
  Thread 4: SELECT * FROM loan_accounts WHERE user_id=...

Batch 2 (4 threads reuse connections):                   ~100ms
  Thread 1: SELECT * FROM inquiries WHERE user_id=...
  Thread 2: SELECT * FROM payment_history WHERE user_id=...
  Thread 3: SELECT * FROM credit_metrics WHERE user_id=...
  Thread 4: SELECT * FROM recommendations WHERE user_id=...

Results cached in _UserCache (in-memory dict)
All subsequent tool calls -> instant read from cache (0ms)
```

#### 3b. RAG Retrieval Pipeline (~2000ms)

**Step 1: Query Embedding (~200-400ms)**

```
OpenAI API: text-embedding-3-small
"How long do hard inquiries stay on my report?"
        |
        v
[0.023, -0.041, 0.087, ..., 0.012]  (1536 floats)
```

**Step 2: Dual Search (~600-1500ms)**

| | Vector Search (pgvector) | Lexical Search (tsvector) |
|---|---|---|
| **Table** | `retrieval_chunk_embeddings` | `retrieval_chunk_lexical` |
| **SQL** | `1-(embedding <=> query_vec) AS score ORDER BY embedding <=> query_vec LIMIT 15` | `ts_rank_cd(search_vector, websearch_to_tsquery('english', query)) WHERE search_vector @@ websearch_to_tsquery(...)  LIMIT 15` |
| **Index** | HNSW (vector_cosine_ops, m=16, ef_construction=64) | GIN |
| **Finds** | Semantically similar ("boost credit" matches "improve score") | Exact keywords ("FCRA" exact match) |
| **Returns** | 15 chunks with cosine scores | 15 chunks with BM25 scores |

**Step 3: RRF Merge (~1ms)**

Reciprocal Rank Fusion (k=60) — merges rankings by position, not raw score.

```
For each chunk:
  score = 1/(60 + vector_rank) + 1/(60 + lexical_rank)

Example:
  Chunk A: vec#1 + lex#8  = 1/61 + 1/68 = 0.0311  <- wins (found in BOTH)
  Chunk B: vec#3 only     = 1/63        = 0.0159
  Chunk C: lex#1 only     = 1/61        = 0.0164
```

Why RRF over weighted average:
- Vector scores: 0.0-1.0 (cosine)
- Lexical scores: 0.0-infinity (BM25)
- Can't add/average different scales
- RRF uses rank position only — scale-independent
- Industry standard (Elasticsearch, Pinecone, Weaviate)

**Step 4: Title/Topic Boost (~1ms)**

```
Tokenize query -> {"hard", "inquiries", "stay", "credit", "report"}

For each chunk:
  if query_terms intersect title_terms -> +0.005
  if query_terms intersect topic_terms -> +0.003

Re-sort by boosted score
Return top 3
```

**Step 5: Score Filter (~0ms)**

```
Keep chunks where score >= 0.005
Convert to RetrievalDocument { snippet, confidence, source, topic, title }

Confidence threshold: >= 0.01 to accept retrieval
(below -> retry with refined query, max 2 attempts)
```

### Stage 4: Evidence Building

**File:** `evidence_builder.py`

Combines tool results + retrieval results into evidence list:

```python
evidence = [
    # From tools (if any):
    EvidenceItem(source="tool", title="Credit Score", detail="611, Fair band"),
    EvidenceItem(source="tool", title="Utilization", detail="30.5% overall"),

    # From RAG retrieval:
    EvidenceItem(source="retrieval",
                 title="Understanding Hard Inquiries",
                 detail="Hard inquiries stay on report for 2 years...",
                 citation="CFPB"),
]
```

### Stage 5: Grounded Response

**File:** `grounded_response_composer.py`

Builds LLM prompt with all gathered context:

```
ModelGatewayRequest {
  system: "You are a credit education assistant..."
  user_message: original question
  tool_context: { score, utilization, recs... }
  retrieval_context: [
    "Hard inquiries stay on report for 2 years...",
    "Inquiries affect score for ~12 months...",
    "Multiple inquiries for same loan type..."
  ]
  evidence: [EvidenceItem, EvidenceItem, ...]
  grounding_rules: "Only cite provided evidence. Do not make up information."
}
```

LLM: OpenAI GPT-4o
- Prompt caching: 96% hit rate on repeated prefixes
- TTFT: 520ms (cached) / 1200ms (cold)
- Output: ~100 tokens @ 47-67 tok/sec
- Total: ~1.6-2.0s

Post-generation: Grounding validation checks LLM response is supported by evidence. Falls back to first retrieval snippet if not grounded.

### Stage 6: Streaming Response

Server-Sent Events (SSE):

```
event: start            -> { trace_id, query_type }
event: classification   -> { category, execution_mode }
event: plan             -> { tools, retrieval_needed }
event: tool_start       -> { tool_name }
event: tool_result      -> { tool_name, data }
event: retrieval_start  -> { query }
event: retrieval_result -> { docs, confidence }
event: data             -> "Hard inquiries remain on your..."  (chunk)
event: data             -> "credit report for two years..."    (chunk)
event: end              -> { trace_id, timing_ms }
```

---

## Infrastructure

```
┌────────────────┐    ┌────────────────┐    ┌───────────────────────────────┐
│ React Frontend  │    │ Fly.io (sin)   │    │ Supabase Postgres             │
│                 │    │                │    │ ap-southeast-1 (Singapore)    │
│ User selection  │    │ FastAPI        │    │                               │
│ Chat interface  │    │ Uvicorn        │    │ pgvector extension            │
│ Score display   │--->│ Port 8080      │--->│ HNSW index (cosine)           │
│ Recommendations │    │ shared-cpu-1x  │    │ tsvector + GIN index          │
│ Evidence panel  │<---│ 512MB RAM      │<---│                               │
│                 │    │                │    │ Connection pools:             │
└────────────────┘    │ scale-to-zero  │    │   credit_repo: max 5         │
                       │ (auto stop/    │    │   retrieval:  max 5          │
                       │  start)        │    │                               │
                       └───────┬────────┘    └───────────────────────────────┘
                               │
                       ┌───────┴────────┐
                       │ OpenAI API      │
                       │                 │
                       │ GPT-4o          │
                       │ (chat LLM)      │
                       │                 │
                       │ text-embedding- │
                       │ 3-small         │
                       │ (query embed)   │
                       └─────────────────┘
```

---

## Performance Profile

### First Request (cold cache)

| Stage | Duration |
|-------|----------|
| Analysis | 0ms (rule-based) |
| Parallel prefetch | 200ms (8 queries, 4 threads) |
| Embed query | 400ms (OpenAI API) |
| Vector search | 800ms (pgvector HNSW) |
| Lexical search | 200ms (tsvector) |
| RRF + boost | 1ms |
| LLM generation | 2000ms (GPT-4o) |
| **Total** | **~3600-5600ms** |

### Warm Request (user cached + prompt cached)

| Stage | Duration |
|-------|----------|
| Analysis | 0ms |
| Tools (from cache) | 0ms |
| Embed query | 400ms |
| Vector search | 800ms |
| Lexical search | 200ms |
| RRF + boost | 1ms |
| LLM generation | 1600ms (96% cache hit) |
| **Total** | **~3000-4000ms** |

### No-Retrieval Request (simple fact)

| Stage | Duration |
|-------|----------|
| Analysis | 0ms |
| LLM generation | 1600ms |
| **Total** | **~1600ms** |

### Optimization Journey

| Version | Total |
|---------|-------|
| Original (15 sequential connections) | 17s |
| + Connection pooling | 7s |
| + Prefetch cache | 5.6s |
| + Parallel queries | 4.9s |
| + Fly.io to Singapore | 3.5-5s |
| Warm cache + prompt cache | 1.6-4s |

---

## Evaluation (Ragas)

20 test cases covering credit education topics.

```
test_cases.json --> run_eval.py --HTTP--> /chat API
(20 questions        (local)              (Fly.io)
 + ground truth)          |                   |
                          |<---answers--------+
                          |
                          v
                    Ragas evaluate()
                    |-- faithfulness       (answer matches chunks?)
                    |-- answer_relevancy   (answer addresses query?)
                    |-- context_precision  (chunks relevant?)
                    +-- context_recall     (chunks complete?)
                          |
                          v
                    results.json + summary report
```

**Requirements:** Python 3.10+, `pip install ragas datasets`

**Scripts:**
- `backend/evals/test_cases.json` — 20 ground truth Q&A pairs
- `backend/evals/run_eval.py` — Ragas evaluation runner
- `backend/evals/results.json` — Latest eval results

---

## File Map

```
backend/
├── main.py                          -> FastAPI app, routers, /health
├── requirements.txt                 -> fastapi, openai, anthropic, psycopg
├── app/
│   ├── core/
│   │   ├── settings.py              -> env vars, config
│   │   └── dependencies.py          -> DI: repos, services, orchestrators
│   ├── api/routes/
│   │   ├── chat.py                  -> POST /chat (SSE streaming)
│   │   ├── users.py                 -> GET /users, /users/{id}
│   │   ├── credit.py                -> GET /credit/profile, /recommendations
│   │   └── ingestion.py             -> POST /ingestion/cfpb, /rebuild
│   ├── services/
│   │   ├── query_analyzer.py        -> Rule-based query classification
│   │   ├── execution_planner.py     -> Category to execution plan mapping
│   │   ├── agent_orchestrator.py    -> Tool loop + retrieval loop
│   │   ├── chat_orchestrator.py     -> Top-level: analyze, execute, respond
│   │   ├── rag_service.py           -> Wraps hybrid retriever
│   │   ├── evidence_builder.py      -> Combines tool + retrieval evidence
│   │   ├── grounded_response_composer.py -> Builds LLM prompt, validates
│   │   └── streaming.py             -> SSE event formatting
│   ├── gateway/
│   │   └── model_gateway.py         -> OpenAI/Anthropic API calls
│   ├── repositories/
│   │   ├── base.py                  -> CreditRepository ABC
│   │   ├── json_credit_repository.py -> Local JSON file backend
│   │   └── postgres_credit_repository.py -> Supabase + prefetch cache
│   └── retrieval/
│       ├── embeddings.py            -> OpenAI embedding provider
│       ├── chunking.py              -> Paragraph-aware sentence splitter
│       ├── persistent_hybrid.py     -> Vector + lexical + RRF merge
│       ├── postgres_store.py        -> pgvector + tsvector queries
│       ├── sqlite_store.py          -> SQLite fallback (local dev)
│       ├── ingestion.py             -> Chunk + embed + store pipeline
│       ├── cfpb_client.py           -> CFPB article scraper
│       └── factory.py               -> Backend selection + migrations
├── migrations/
│   ├── 0002_retrieval_schema.sql    -> Retrieval tables
│   ├── 0003_pgvector_native.sql     -> pgvector extension + HNSW index
│   └── 0004_credit_data_schema.sql  -> User/credit data tables
├── scripts/
│   ├── ingest_cfpb.py               -> Fetch CFPB + embed + store
│   └── seed_postgres_credit_data.py -> Migrate JSON to Postgres
├── evals/
│   ├── test_cases.json              -> 20 ground truth Q&A pairs
│   ├── run_eval.py                  -> Ragas evaluation runner
│   └── results.json                 -> Latest eval results
└── synthetic/
    └── models.py                    -> Pydantic models (User, CreditReport...)

Dockerfile                           -> Python 3.12-slim, uvicorn
fly.toml                             -> Fly.io config, sin region
docker-compose.yml                   -> Local dev with Postgres
.dockerignore                        -> Excludes .venv, .git, .env
```
