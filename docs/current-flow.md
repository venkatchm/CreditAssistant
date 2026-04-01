# Current Chat Flow

This document describes the current `/chat` flow in the repo and lists the main functions by file.

## Flow

### 1. API receives the request
File: [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)

Main function:
- `chat(payload, orchestrator)`

Role:
- Entry point for `POST /chat`
- Decides normal response vs SSE streaming

### 2. Chat orchestration begins
File: [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)

Main functions:
- `respond(user_id, message)`
- `stream_response(user_id, message)`

Role:
- Central entry into the assistant flow

### 3. Query is classified
File: [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py)

Main function:
- `analyze(message)`

Role:
- Classifies the request into `SIMPLE_FACT`, `SIMPLE_RECOMMENDATION`, `COMPLEX_EXPLANATION`, `GENERAL_KNOWLEDGE`, or `UNSUPPORTED`

### 4. Execution plan is built
File: [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)

Main function:
- `build_plan(analysis, message)`

Role:
- Decides tool list, retrieval need, response strategy, and max iterations

### 5. Main orchestration loop runs
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main functions:
- `execute(user_id, message, analysis)`
- `build_gateway_request(user_id, message, analysis)`

Role:
- Runs the plan
- Executes tools
- Runs retrieval
- Builds evidence
- Composes the response

### 6. Tools are resolved and executed
File: [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py)

Main function:
- `get(tool_name)`

Supporting internal function:
- `_run_tool(...)` in [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Role:
- Maps tool names to runnable functions and evidence summaries

### 7. Credit data is fetched from services and repository
Files:
- [backend/app/services/credit_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/credit_service.py)
- [backend/app/services/metrics_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/metrics_service.py)
- [backend/app/services/recommendation_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/recommendation_service.py)
- [backend/app/services/inquiry_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/inquiry_service.py)
- [backend/app/services/payment_history_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/payment_history_service.py)
- [backend/app/repositories/json_credit_repository.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/repositories/json_credit_repository.py)

Role:
- Loads synthetic user credit data from JSON

### 8. Retrieval runs when needed
File: [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py)

Main functions:
- `search_knowledge(query)`
- `rebuild_index()`

Role:
- Retrieves educational credit knowledge from the local retrieval store

### 9. Evidence is assembled
File: [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)

Main functions:
- `build(tool_results, retrieval_result)`
- `is_sufficient_for_complex_explanation(evidence)`

Role:
- Combines tool outputs and retrieval results into normalized evidence

### 10. Response is composed
File: [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

Main functions:
- `compose(...)`
- `as_chat_response(...)`
- `build_gateway_request(...)`

Main internal composition functions:
- `_compose_simple_fact(...)`
- `_compose_recommendation(...)`
- `_compose_general_knowledge(...)`
- `_compose_complex_explanation(...)`

Role:
- Creates the grounded answer and maps it to `ChatResponse`

### 11. Model generation happens if needed
File: [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Main classes and functions:
- `LocalModelGateway.generate()`
- `LocalModelGateway.stream()`
- `RemoteModelGateway.generate()`
- `OpenAIModelGateway.generate()`
- `OpenAIModelGateway.stream()`

Role:
- Generates the final answer text
- Local is mostly deterministic
- OpenAI and remote are real model-backed paths

### 12. Final API response is returned
File: [backend/app/schemas/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/schemas/chat.py)

Main schema:
- `ChatResponse`

Role:
- Defines the response contract returned to the client

### 13. Streaming wrapper is applied for SSE mode
Files:
- [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

Main functions:
- `event_stream()` inside route
- `build_text_stream_events(chunks)`
- `format_sse_event(event)`
- `build_error_event(message)`

Role:
- Wraps model output into SSE `start`, `data`, `end`, and `error` events

## Main Functions By File

- [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py): `chat(...)`
- [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py): `respond(...)`, `stream_response(...)`
- [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py): `analyze(...)`
- [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py): `build_plan(...)`
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py): `execute(...)`, `build_gateway_request(...)`, `_run_tool(...)`, `_run_retrieval(...)`
- [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py): `get(...)`, `has_tool(...)`
- [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py): `search_knowledge(...)`, `rebuild_index(...)`
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py): `build(...)`, `is_sufficient_for_complex_explanation(...)`
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py): `compose(...)`, `as_chat_response(...)`, `build_gateway_request(...)`
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py): `generate(...)`, `stream(...)`
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py): `format_sse_event(...)`, `build_text_stream_events(...)`, `build_error_event(...)`
- [backend/app/core/dependencies.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/core/dependencies.py): `get_chat_orchestrator(...)`, `get_agent_orchestrator(...)`, `get_model_gateway(...)`, `get_rag_service(...)`
