# Current vs Target

This document compares the current backend implementation with the target agentic-RAG architecture and highlights the main gaps, mapped to the current files.

## Executive Summary

The current system is already more than plain RAG. It has:

- FastAPI chat entry points
- Rule-based query classification
- Rule-based execution planning
- Tool access for user-specific credit data
- Retrieval for educational knowledge
- Evidence aggregation
- Structured response composition
- Optional SSE streaming

The main gap is control. Today, deterministic code decides most of the flow. In the target architecture, the model should decide what evidence to gather next, while deterministic code should enforce grounding, safety, and output structure.

## High-Level Comparison

| Area | Current | Target | Gap |
|---|---|---|---|
| Routing | Rule-based | Policy-driven with model-guided next steps | Medium |
| Planning | Fixed per category | Dynamic action-by-action | High |
| Tool use | Predetermined tool list | Model chooses next tool | High |
| Retrieval | Fixed by plan | Model issues and refines retrieval queries | High |
| Reasoning | Mostly deterministic local fallback | Real LLM reasoning over evidence | High |
| Streaming | Final text only | Full agent event streaming | Medium |
| Validation | Limited output normalization | Strict grounding and evidence validation | High |
| Traceability | Basic trace | Full action/evidence/validation trace | Medium |
| Testing | Routing and behavior tests | Grounding and reasoning quality tests | High |

## Capability-by-Capability Gap Analysis

### 1. Request and API Layer
Current:
- `/chat` is implemented in [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)
- Supports normal responses and SSE streaming

Target:
- Keep the route
- Extend SSE to include plan, tool, retrieval, and reasoning events

Gap:
- Current streaming only wraps model text chunks into `start`, `data`, `end`, `error`
- There is no streaming of intermediate agent activity

Files involved:
- [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

### 2. Query Analysis
Current:
- [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py) classifies using keyword heuristics

Target:
- Keep lightweight deterministic classification or coarse intent routing
- Use it only for policy and support checks

Gap:
- Current classification is acceptable as a first gate
- But it is too brittle to be the main driver of orchestration

Files involved:
- [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py)

### 3. Planning
Current:
- [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py) builds a largely fixed execution plan per category

Target:
- Planner should set:
  - support policy
  - allowed tools
  - safety rules
  - max steps
- Model should choose the next actual action

Gap:
- Current planner encodes too much of the execution sequence
- Retrieval and tool order are mostly predetermined

Files involved:
- [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)

### 4. Orchestration
Current:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py) executes the plan, runs tools, runs retrieval, and composes the answer
- It has a bounded loop, but it is still mostly deterministic

Target:
- Turn this into a true bounded action loop
- The model chooses between:
  - tool call
  - retrieval
  - answer
  - insufficient evidence

Gap:
- No explicit action schema yet
- No model-driven next-step decision
- The current loop does not meaningfully re-plan

Files involved:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)

### 5. Tool Layer
Current:
- [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py) is clean and usable
- Tools already expose grounded user-specific data

Target:
- Keep this layer
- Add tool metadata:
  - schema
  - purpose
  - provenance
  - timestamps
  - compact summaries

Gap:
- Current tools are close to target structurally
- Main missing piece is richer standardized output for model consumption and validation

Files involved:
- [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py)
- [backend/app/tools/get_credit_profile.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/tools/get_credit_profile.py)
- [backend/app/tools/get_credit_metrics.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/tools/get_credit_metrics.py)
- [backend/app/tools/get_recommendations.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/tools/get_recommendations.py)
- [backend/app/tools/get_inquiries.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/tools/get_inquiries.py)
- [backend/app/tools/get_payment_history.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/tools/get_payment_history.py)

### 6. Retrieval Layer
Current:
- [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py) supports local hybrid retrieval with persistence
- Retrieval is invoked based on planner rules

Target:
- Retrieval becomes an explicit model-selectable action
- The model can refine queries iteratively

Gap:
- Retrieval quality infrastructure is present
- Adaptive retrieval behavior is missing

Files involved:
- [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py)
- [backend/app/retrieval](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/retrieval)

### 7. Reasoning Layer
Current:
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py) supports local, remote, and OpenAI gateways
- `LocalModelGateway` is mostly deterministic composition logic

Target:
- Real model-driven reasoning over tool and retrieval evidence
- Structured action outputs during orchestration
- Structured final answer outputs

Gap:
- This is the largest gap
- Current local path is not true reasoning
- OpenAI path exists, but it is only used as a final generation path, not as an action planner

Files involved:
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

### 8. Response Composition and Grounding
Current:
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py) composes final responses
- Simple paths are template-driven
- Complex and knowledge paths can call the model gateway

Target:
- Composer becomes more of:
  - validator
  - formatter
  - fallback layer
- Final claims should be checked against evidence

Gap:
- Current composer both thinks and formats
- In the target design, reasoning should move to the model, while composition should enforce structure and grounding

Files involved:
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

### 9. Evidence Layer
Current:
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py) builds evidence items and checks sufficiency

Target:
- Evidence should carry:
  - stable IDs
  - citation references
  - source type
  - claim mapping support

Gap:
- The concept is already present
- The missing piece is stronger claim-to-evidence mapping and final answer verification

Files involved:
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)
- [backend/app/schemas/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/schemas/chat.py)

### 10. Streaming
Current:
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py) only emits text SSE frames

Target:
- Stream:
  - plan
  - tool start
  - tool result
  - retrieval result
  - reasoning events
  - answer text

Gap:
- No agent-step visibility in the current stream

Files involved:
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

### 11. Dependency Wiring
Current:
- [backend/app/core/dependencies.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/core/dependencies.py) wires repository, services, retrieval, model gateway, and orchestrators

Target:
- Keep the dependency structure
- Change the orchestration composition:
  - planner becomes policy layer
  - orchestrator becomes action loop
  - model gateway becomes decision-maker

Gap:
- Wiring is structurally fine
- Composition logic needs to be reorganized around an action loop

Files involved:
- [backend/app/core/dependencies.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/core/dependencies.py)

## File-by-File Gap Map

### [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)
Current:
- Normal and streaming chat endpoint

Needed:
- Support richer SSE event types
- Potentially expose trace metadata in streaming mode

### [backend/app/services/chat_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/chat_orchestrator.py)
Current:
- Thin wrapper over classification and orchestration

Needed:
- Minimal change
- May need new streaming behavior to surface agent events instead of only model text

### [backend/app/services/query_analyzer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/query_analyzer.py)
Current:
- Keyword classification

Needed:
- Keep as coarse routing or replace with stronger intent analysis later
- Do not rely on it to fully determine tool flow

### [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)
Current:
- Fixed sequence planner

Needed:
- Reduce to policy and constraints
- Remove hardcoded tool sequences from the core flow

### [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
Current:
- Deterministic plan executor

Needed:
- Add explicit action loop
- Track model decisions and observations
- Let the model request tools and retrieval dynamically

### [backend/app/services/tool_registry.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/tool_registry.py)
Current:
- Functional tool registry

Needed:
- Add richer tool metadata and standardized model-facing outputs

### [backend/app/services/rag_service.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/rag_service.py)
Current:
- Good local retrieval layer

Needed:
- Expose retrieval as an agent action
- Support iterative query refinement

### [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)
Current:
- Aggregates evidence

Needed:
- Add stronger citation IDs and claim-to-evidence support

### [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)
Current:
- Performs a lot of answer generation logic

Needed:
- Shift toward validation, assembly, and fallback behavior
- Reduce business reasoning inside the composer

### [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)
Current:
- Supports local, remote, and OpenAI gateways

Needed:
- Introduce structured action outputs
- Make the model choose the next action in the loop
- Keep strict JSON output handling

### [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)
Current:
- Text SSE helper

Needed:
- Support event types beyond text deltas

### [backend/app/core/dependencies.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/core/dependencies.py)
Current:
- Wires current architecture cleanly

Needed:
- Rewire to new agent controller and policy composition

## Recommended Work Sequence

### Step 1. Improve final answer generation first
Focus:
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)

Why:
- Fastest route to better answer quality

### Step 2. Add structured validation and grounding checks
Focus:
- [backend/app/services/evidence_builder.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/evidence_builder.py)
- [backend/app/services/grounded_response_composer.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/grounded_response_composer.py)
- [backend/app/schemas/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/schemas/chat.py)

Why:
- Prevent unsupported claims before introducing more dynamic behavior

### Step 3. Introduce action-based orchestration
Focus:
- [backend/app/services/agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/agent_orchestrator.py)
- [backend/app/services/execution_planner.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/execution_planner.py)
- [backend/app/gateway/model_gateway.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/gateway/model_gateway.py)

Why:
- This is the actual shift to agentic behavior

### Step 4. Upgrade streaming
Focus:
- [backend/app/api/routes/chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/api/routes/chat.py)
- [backend/app/services/streaming.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/app/services/streaming.py)

Why:
- Better observability during development and frontend integration

### Step 5. Expand tests and evaluation
Focus:
- [backend/tests/test_agent_orchestrator.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/tests/test_agent_orchestrator.py)
- [backend/tests/test_chat.py](/Users/venkatachalamperumal/Documents/CreditAssistant/CreditAssistant/backend/tests/test_chat.py)

Why:
- Prevent regressions as orchestration becomes more dynamic

## Bottom Line

The current architecture already has the right major modules. The biggest missing pieces are:

- model-driven next-step decisions
- dynamic tool and retrieval usage
- strict claim-to-evidence validation
- richer agent-event streaming

So this is not a rewrite problem. It is a control-shift problem:

- today, deterministic code controls most of the flow
- target state, the model controls next actions within deterministic safety and grounding boundaries
