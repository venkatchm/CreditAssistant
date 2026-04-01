# AgenticRAG Flow

This document describes the current end-to-end AgenticRAG flow implemented in the backend.

The system is now a bounded agentic-RAG architecture with:

- model-driven next actions
- shared action loop for streaming and non-streaming paths
- iterative retrieval
- explicit insufficient-evidence handling
- grounded response validation
- action reasoning traces

## Step-by-Step Flow

### 1. Client sends `POST /chat`
File: [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)

Main function:
- `chat(payload, orchestrator)`

What happens:
- Receives `user_id`, `message`, and optional `stream`
- If `stream=false`, returns a normal `ChatResponse`
- If `stream=true`, returns an SSE stream

### 2. Request enters `ChatOrchestrator`
File: [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)

Main functions:
- `respond(user_id, message)`
- `stream_response(user_id, message)`

What happens:
- Both paths classify the request first
- Both paths ultimately use the same bounded action loop

### 3. Query is classified
File: [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py)

Main function:
- `analyze(message)`

What happens:
- Normalizes the message
- Maps it to:
  - `SIMPLE_FACT`
  - `SIMPLE_RECOMMENDATION`
  - `COMPLEX_EXPLANATION`
  - `GENERAL_KNOWLEDGE`
  - `UNSUPPORTED`

Streaming event:
- `classification`

### 4. Planner creates a policy boundary, not a fixed execution script
File: [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)

Main function:
- `build_plan(analysis, message)`

What happens now:
- Defines:
  - query type
  - execution mode
  - allowed tools
  - whether retrieval is needed
  - retrieval seed query
  - response strategy
  - bounded step budget

Important:
- The planner no longer hardcodes the actual next-step sequence
- The action loop decides the sequence

Streaming event:
- `plan`

### 5. The bounded agent action loop starts
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main functions:
- `execute(...)`
- `build_gateway_request(...)`
- `_execute_action_loop(...)`

What happens:
- Creates initial `ModelGatewayRequest`
- Starts a bounded loop
- On each pass, asks the model gateway for the next action

This loop is shared by:
- normal response path
- streaming path

### 6. Model chooses the next action
File: [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Main function:
- `decide_action(...)`

Current action types:
- `tool_call`
- `retrieve`
- `answer`
- `insufficient_evidence`

What happens:
- `OpenAIModelGateway` can decide the next action via the Responses API
- `LocalModelGateway` provides deterministic fallback logic

Inputs considered:
- allowed tools
- completed tools
- retrieval state
- retrieval attempts
- last retrieval confidence
- current evidence/tool context/retrieval context

### 7. If action is `tool_call`, run the selected tool
Files:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py)

Main functions:
- `_run_tool(...)`
- `get(tool_name)`

What happens:
- Tool is selected dynamically by the action loop
- Tool output is stored
- Evidence is produced
- Trace records both the decision step and the tool execution step

Streaming events:
- `tool_start`
- `tool_result`

### 8. If action is `retrieve`, run retrieval
Files:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py)

Main functions:
- `_run_retrieval(...)`
- `search_knowledge(query)`

What happens:
- Retrieval runs using the current query
- Retrieved docs are added to context
- Retrieval confidence and document titles are recorded

Streaming events:
- `retrieval_start`
- `retrieval_result`

### 9. Iterative retrieval can happen
Files:
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

What happens:
- If the first retrieval is weak or empty, the agent can choose `retrieve` again
- A refined retrieval query is generated
- The loop retries within the bounded budget

If repeated retrieval still fails:
- the agent can return `insufficient_evidence`

### 10. Context is refreshed after each action
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main function:
- `_refresh_gateway_payload(...)`

What happens:
- Rebuilds the model input with the latest:
  - evidence
  - tool context
  - retrieval context

Purpose:
- Let the next action depend on newly gathered evidence

### 11. Action reasoning is recorded in the trace
File: [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

Main behavior:
- Every chosen action is logged as a trace step:
  - `decide_tool_call`
  - `decide_retrieve`
  - `decide_answer`
  - `decide_insufficient_evidence`

Trace detail includes:
- selected action
- target tool or retrieval query
- reasoning text
- completed tools at that point
- retrieval state

### 12. If action is `insufficient_evidence`, the loop stops safely
Files:
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

What happens:
- The loop stops without forcing an answer from weak evidence
- The composer returns a safe grounded fallback message

Examples:
- no usable retrieval documents for a knowledge question
- missing retrieval grounding for a complex explanation after bounded retries

### 13. Final answer is composed
File: [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

Main functions:
- `compose(...)`
- `as_chat_response(...)`
- `build_gateway_request(...)`

What happens:
- Builds the final grounded response
- Applies fallback behavior when evidence is insufficient
- Converts the result to `ChatResponse`

### 14. Claim verification is applied during composition
Files:
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

What happens:
- Generated evidence lines are filtered against grounded evidence
- Generated causes are filtered against grounded evidence
- If a generated message is not grounded enough, the backend falls back to deterministic grounded text

This is basic claim verification, not full per-claim proof, but it is stronger than simple prompt-only grounding.

### 15. Final model generation happens when needed
File: [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Main functions:
- `generate(...)`
- `stream(...)`

What happens:
- `OpenAIModelGateway` can generate final structured answer content
- `LocalModelGateway` provides deterministic fallback generation

### 16. Streaming path emits progress and answer events
Files:
- [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

Current event types:
- `start`
- `classification`
- `plan`
- `tool_start`
- `tool_result`
- `retrieval_start`
- `retrieval_result`
- `compose`
- `data`
- `end`
- `error`

Purpose:
- Let the frontend visualize flow progress

## Short Sequence Summary

`classification -> plan -> decide_action -> tool/retrieve -> refresh_context -> decide_action -> retrieve again or answer or insufficient_evidence -> compose -> data/end`

## What Makes This AgenticRAG

The system is now AgenticRAG because:

- the model chooses the next action
- retrieval and tools are inside the action loop
- retrieval can be iterative
- the system can stop with insufficient evidence
- the final answer is grounded and partially claim-verified
- both streaming and non-streaming paths share the same agent loop

## Current Boundaries

This is a bounded AgenticRAG system, not an open-ended autonomous agent.

Boundaries:
- fixed domain
- fixed tool registry
- bounded number of steps
- planner still defines allowed tools and broad policy

That is the right shape for a credit assistant.
