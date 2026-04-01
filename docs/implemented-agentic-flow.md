# Implemented Agentic Flow

This document describes the currently implemented flow after introducing the first agentic-RAG slice.

The key change is that the backend now has an explicit next-action contract:

- `tool_call`
- `retrieve`
- `answer`

The local gateway still chooses these actions deterministically, but the control flow now follows an agent-style loop.

## Step-by-Step Flow

### 1. Client sends `POST /chat`
File: [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)

Main function:
- `chat(payload, orchestrator)`

What happens:
- Receives `user_id`, `message`, and optional `stream`
- If `stream=false`, uses the normal response path
- If `stream=true`, returns an SSE stream

### 2. Request enters `ChatOrchestrator`
File: [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)

Main functions:
- `respond(user_id, message)`
- `stream_response(user_id, message)`

What happens:
- `respond()` handles the standard API response path
- `stream_response()` handles the SSE path and emits progress events

### 3. Query is classified
File: [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py)

Main function:
- `analyze(message)`

What happens:
- Normalizes the message
- Classifies it into:
  - `SIMPLE_FACT`
  - `SIMPLE_RECOMMENDATION`
  - `COMPLEX_EXPLANATION`
  - `GENERAL_KNOWLEDGE`
  - `UNSUPPORTED`

Streaming event:
- `classification`

### 4. A coarse execution plan is built
File: [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)

Main function:
- `build_plan(analysis, message)`

What happens:
- The planner still defines:
  - query type
  - execution mode
  - allowed tools
  - whether retrieval is needed
  - response strategy
  - iteration budget

Streaming event:
- `plan`

Important note:
- This is still rule-based
- But it no longer directly controls every execution step

### 5. The orchestrator starts a bounded action loop
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main functions:
- `build_gateway_request(...)`
- `_execute_action_loop(...)`

What happens:
- The orchestrator creates an initial model-gateway payload
- It enters a bounded loop
- On each pass, it asks the model gateway for the next action

This is the newly implemented agent-style control point.

### 6. The model gateway decides the next action
File: [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Main functions:
- `decide_action(...)`
- currently implemented in `LocalModelGateway`

Possible actions:
- `tool_call`
- `retrieve`
- `answer`

What happens now:
- The local gateway chooses actions deterministically
- It checks:
  - which tools are still incomplete
  - whether retrieval is still required
  - whether the system can answer

Current behavior:
- If a tool is still pending, return `tool_call`
- Else if retrieval is needed and not done, return `retrieve`
- Else return `answer`

### 7. If action is `tool_call`, the backend runs the tool
Files:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py)

Main functions:
- `_run_tool(...)`
- `get(tool_name)`

What happens:
- The tool is resolved from the registry
- The tool is executed against the synthetic data services
- Tool output, evidence summary, and trace step are recorded

Streaming events:
- `tool_start`
- `tool_result`

### 8. If action is `retrieve`, the backend runs retrieval
Files:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py)

Main functions:
- `_run_retrieval(...)`
- `search_knowledge(query)`

What happens:
- The orchestrator runs a knowledge search
- Retrieved documents are added to the current context
- Retrieval evidence is recorded in the trace

Streaming events:
- `retrieval_start`
- `retrieval_result`

### 9. After each action, the gateway payload is refreshed
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main function:
- `_refresh_gateway_payload(...)`

What happens:
- The backend rebuilds the model input with the latest:
  - tool evidence
  - retrieval evidence
  - tool context
  - retrieval context

Purpose:
- Let the next action decision depend on what has already been gathered

### 10. When the next action becomes `answer`, evidence gathering stops
Files:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)

Main functions:
- `build(...)`
- `is_sufficient_for_complex_explanation(...)`

What happens:
- The action loop exits
- Evidence is finalized
- The backend prepares for final answer composition

Streaming event:
- `compose`

Meaning:
- Evidence collection is complete
- The backend is preparing the final response generation step

### 11. A model gateway request is built for final answer generation
File: [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

Main function:
- `build_gateway_request(...)`

What happens:
- Packages:
  - plan
  - user message
  - tool context
  - retrieval context
  - evidence
  - grounding rules

Purpose:
- Create the input for final answer generation

### 12. Final answer text is generated
File: [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Main functions:
- `generate(...)`
- `stream(...)`

What happens now:
- `LocalModelGateway` still generates the final answer deterministically
- It formats grounded output using tool and retrieval data
- It does not yet provide real LLM reasoning in the local path

Streaming event:
- `data`

Meaning:
- Final answer text chunks are arriving

### 13. Stream completes
Files:
- [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

Main functions:
- `build_start_event()`
- `build_progress_event(...)`
- `build_text_chunk_event(...)`
- `build_end_event(...)`

Current streaming event order:
- `start`
- `classification`
- `plan`
- zero or more `tool_start`
- zero or more `tool_result`
- optional `retrieval_start`
- optional `retrieval_result`
- `compose`
- one or more `data`
- `end`

## Main Architectural Meaning

Before this change:
- The backend directly iterated the planned tool list

After this change:
- The backend asks the model-gateway contract for the next action
- The local gateway still answers deterministically
- But the control shape is now agent-like:
  - choose next action
  - execute action
  - refresh context
  - choose next action again
  - stop when ready to answer

This is the first implemented step toward true agentic-RAG.

## Important Limitation Right Now

The standard non-streaming `execute(...)` path is still mostly plan-driven.

The new action loop is currently implemented in the streaming preparation path through:
- `build_gateway_request(...)`

So the backend now has:
- explicit agent actions
- a bounded action loop
- refreshed context after each action
- streaming of progress events

But it does not yet have:
- OpenAI-driven action selection
- real LLM-based next-step reasoning
- the same action loop fully shared by both streaming and non-streaming paths

## Short Sequence Summary

`classification -> plan -> decide_action -> tool/retrieve -> refresh_context -> decide_action -> answer -> stream data -> end`
