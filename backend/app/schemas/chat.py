from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


ChatCategory = Literal[
    "SIMPLE_FACT",
    "SIMPLE_RECOMMENDATION",
    "COMPLEX_EXPLANATION",
    "GENERAL_KNOWLEDGE",
    "UNSUPPORTED",
]


class ChatRequest(BaseModel):
    user_id: str
    message: str
    stream: bool = False


class ChatCard(BaseModel):
    type: str
    title: Optional[str] = None
    description: Optional[str] = None
    score: Optional[int] = None
    updated_at: Optional[str] = None
    priority: Optional[str] = None
    value: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)


class ChatExplanation(BaseModel):
    causes: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    cards: List[ChatCard] = Field(default_factory=list)
    requires_disclaimer: bool
    category: ChatCategory
    explanation: Optional[ChatExplanation] = None


class ClassificationResult(BaseModel):
    category: ChatCategory
    normalized_message: str


ExecutionMode = Literal[
    "FAST_FACT",
    "FAST_RECOMMENDATION",
    "KNOWLEDGE_ONLY",
    "COMPLEX_EXPLANATION",
    "UNSUPPORTED",
]

ExecutionStepKind = Literal["tool", "retrieval", "compose", "classify"]


class RetrievalDocument(BaseModel):
    doc_id: str
    topic: str
    title: str
    snippet: str
    source: str
    confidence: float
    effective_date: Optional[str] = None
    version: Optional[str] = None


class RetrievalResult(BaseModel):
    query: str
    documents: List[RetrievalDocument] = Field(default_factory=list)
    used: bool
    top_confidence: float = 0.0


class ToolResult(BaseModel):
    tool_name: str
    source: str
    payload: Any
    payload_summary: str
    evidence: List[str] = Field(default_factory=list)


class ExecutionStep(BaseModel):
    name: str
    kind: ExecutionStepKind
    status: Literal["completed", "skipped"]
    detail: str
    duration_ms: int = 0
    evidence: List[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    query_type: ChatCategory
    execution_mode: ExecutionMode
    steps: List[str] = Field(default_factory=list)
    tool_names: List[str] = Field(default_factory=list)
    retrieval_needed: bool
    retrieval_query: Optional[str] = None
    response_strategy: str
    max_iterations: int = 1


class TraceContext(BaseModel):
    trace_id: str
    user_id: str
    query_type: ChatCategory
    execution_mode: ExecutionMode
    tool_calls: List[str] = Field(default_factory=list)
    retrieval_used: bool = False
    retrieval_docs: List[str] = Field(default_factory=list)
    response_strategy: str
    steps: List[ExecutionStep] = Field(default_factory=list)
    total_duration_ms: int = 0


class AgentExecutionResult(BaseModel):
    response: ChatResponse
    plan: ExecutionPlan
    trace: TraceContext


EvidenceSourceKind = Literal["tool", "retrieval"]


class EvidenceItem(BaseModel):
    source_kind: EvidenceSourceKind
    source_name: str
    title: str
    detail: str
    citation: Optional[str] = None
    confidence: Optional[float] = None


class GroundedAnswer(BaseModel):
    message: str
    cards: List[ChatCard] = Field(default_factory=list)
    explanation: Optional[ChatExplanation] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)


AgentActionKind = Literal["tool_call", "retrieve", "answer", "insufficient_evidence"]


class AgentAction(BaseModel):
    action: AgentActionKind
    tool_name: Optional[str] = None
    query: Optional[str] = None
    reasoning: str = ""


StreamEventName = Literal[
    "start",
    "classification",
    "plan",
    "tool_start",
    "tool_result",
    "retrieval_start",
    "retrieval_result",
    "compose",
    "data",
    "end",
    "error",
]


class StreamEvent(BaseModel):
    event: StreamEventName
    data: dict[str, Any] = Field(default_factory=dict)
