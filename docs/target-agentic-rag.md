# Target Agentic-RAG Architecture

This document describes the target architecture for evolving the current backend into a stronger agentic-RAG system with real LLM reasoning, dynamic tool use, grounded retrieval, and structured output validation.

## Goal

Build a grounded credit assistant where:

- Personal credit facts come only from tools and trusted user data
- Educational explanations come from retrieval
- The LLM decides what evidence it needs
- The system supports bounded multi-step reasoning
- Final answers remain structured, validated, and auditable

## Target Architecture

### 1. Request Layer
Keep the FastAPI route in [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py), but extend the streaming contract.

Target behavior:
- Accept standard chat requests
- Support richer SSE events, not just final text

Suggested event types:
- `plan`
- `tool_call`
- `tool_result`
- `retrieval`
- `reasoning`
- `data`
- `end`
- `error`

Purpose:
- Make the agent execution visible to the client
- Separate progress events from final answer text

### 2. Agent Controller
Evolve [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py) into a bounded controller loop.

Target responsibilities:
- Maintain execution state
- Ask the model for the next action
- Execute tools or retrieval
- Append observations
- Stop when evidence is sufficient or the step budget is exhausted

Target loop:
1. Build initial context
2. Ask the model for next action
3. If tool action, run tool
4. If retrieval action, run retrieval
5. Append observation to state
6. Ask model whether to continue or answer
7. Stop at `max_steps`

Purpose:
- Move from fixed plan execution to adaptive orchestration

### 3. Planner / Policy Layer
Retain [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py), but narrow its role.

Current role:
- Builds most of the execution sequence directly

Target role:
- Coarse routing only
- Determine if the request is supported
- Determine allowed tool set
- Determine safety and grounding rules
- Set step budget and fallback behavior

Purpose:
- Keep policy and safety deterministic
- Let the model decide the actual next step

### 4. Tool Layer
Keep [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py) as the tool registry abstraction.

Target improvements:
- Each tool declares its purpose
- Each tool returns structured payload plus compact summary
- Each tool returns provenance and timestamps
- Each tool has a schema suitable for model consumption

Current tools that should remain:
- `get_credit_profile`
- `get_credit_metrics`
- `get_recommendations`
- `get_inquiries`
- `get_payment_history`

Purpose:
- Provide grounded user-specific facts
- Keep model reasoning separate from raw data access

### 5. Retrieval Layer
Keep [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py), but expose retrieval as an explicit agent action.

Target behavior:
- The model can issue retrieval queries dynamically
- Retrieval can be repeated with refined queries
- Results are reranked and normalized
- Citations are preserved in the final answer

Purpose:
- Make retrieval adaptive instead of fixed by the planner

### 6. Reasoning Layer
This is the main missing capability today.

Instead of using deterministic local generation logic, the LLM should produce structured agent decisions such as:

- `tool_call`
- `retrieve`
- `answer`
- `insufficient_evidence`

Example action payloads:

```json
{"action":"tool_call","tool_name":"get_credit_metrics"}
```

```json
{"action":"retrieve","query":"impact of recent late payments on credit score"}
```

```json
{
  "action":"answer",
  "message":"...",
  "causes":["..."],
  "evidence":["..."],
  "suggested_actions":["..."]
}
```

Target model instructions:
- Personal facts must come only from tool outputs
- Educational claims must come only from retrieval
- Separate observed facts from inferred explanation
- State when evidence is insufficient
- Return strict JSON matching the schema

Purpose:
- Enable real model-driven reasoning rather than fixed composition

### 7. Grounding and Validation Layer
Evolve [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py) into more of a validator and assembler.

Target responsibilities:
- Validate model JSON
- Ensure referenced evidence exists
- Reject unsupported claims
- Apply safe fallback when model output is malformed
- Build consistent cards, explanation blocks, and citations

Purpose:
- Keep the final answer safe and grounded even with model variability

### 8. Trace and Evaluation Layer
Extend trace capture in [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py).

Target trace fields:
- User message
- Query type
- Chosen actions
- Tool arguments
- Retrieval queries
- Retrieved documents
- Evidence used
- Final answer
- Validation result
- Step count
- Total duration

Purpose:
- Make runs debuggable
- Support offline evaluation of reasoning quality

## Target End-to-End Flow

For a question like `Why did my credit score drop?`, the target flow should be:

1. Request enters `/chat`
2. Request is classified as supported credit explanation
3. Policy layer sets allowed tools and step budget
4. Model chooses `get_credit_profile`
5. Tool result is added to context
6. Model chooses `get_credit_metrics`
7. Tool result is added to context
8. Model chooses `get_payment_history`
9. Tool result is added to context
10. Model decides whether retrieval is needed
11. If needed, model issues a focused retrieval query
12. Retrieval results are added to context
13. Model returns structured grounded answer
14. Validation layer verifies claims and evidence
15. Final `ChatResponse` is returned

This is the key difference from the current system: the model chooses the next action based on intermediate evidence instead of following a largely fixed plan.

## Phased Implementation Plan

### Phase 1. Real LLM-backed final answer
Goal:
- Replace deterministic local composition for final answer generation

Changes:
- Make [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py) use `OpenAIModelGateway` or another real model path for production
- Strengthen prompt instructions for grounded structured JSON output
- Validate returned JSON against the existing answer schema

Outcome:
- Better answer quality quickly
- Low risk because orchestration remains mostly unchanged

### Phase 2. Introduce explicit agent actions
Goal:
- Let the model decide the next step

Changes:
- Add an action schema for `tool_call`, `retrieve`, `answer`, and `insufficient_evidence`
- Convert [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py) into a bounded action loop
- Reduce [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py) to coarse routing and policy

Outcome:
- Adaptive tool use
- Adaptive retrieval
- Real agent control flow

### Phase 3. Normalize evidence and enforce grounding
Goal:
- Improve reliability and auditability

Changes:
- Normalize tool outputs into compact model-facing summaries
- Attach explicit citation IDs to retrieval and tool evidence
- Validate that final claims are supported by evidence
- Add safe fallback when evidence is insufficient

Outcome:
- Better groundedness
- Fewer unsupported claims
- Easier debugging

### Phase 4. Stream agent events
Goal:
- Improve observability and client UX

Changes:
- Extend [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py) to support agent-step events
- Stream planning, tool execution, retrieval, and answer generation separately
- Keep final answer text deltas separate from trace events

Outcome:
- Better frontend visibility
- Better debugging of long or complex runs

### Phase 5. Build evaluation coverage
Goal:
- Measure reasoning quality instead of assuming it

Changes:
- Add test cases for grounded explanations
- Add tests for refusal when evidence is insufficient
- Add tests for correct tool selection and retrieval usage
- Add tests for strict JSON schema compliance
- Extend:
  - [backend/tests/test_agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/tests/test_agent_orchestrator.py)
  - [backend/tests/test_chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/tests/test_chat.py)

Outcome:
- Safer iteration
- Clear regression detection

## Recommended Order

1. Replace deterministic final generation with a real LLM-backed structured answer path
2. Add JSON validation and grounding checks
3. Introduce action-based bounded orchestration
4. Extend streaming for agent-step visibility
5. Add evaluation harness and regression tests

## Summary

The current repo already has the right major building blocks:
- API layer
- query classification
- planning
- tool access
- retrieval
- evidence building
- response composition

What it lacks for true agentic-RAG is:
- model-driven next-step decisions
- iterative tool and retrieval usage
- stronger grounding validation
- richer streaming of agent progress

The target architecture keeps most of the existing modules, but changes who is in control: the model should drive the next action, while deterministic code enforces safety, grounding, and response structure.
