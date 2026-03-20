from __future__ import annotations

from typing import List, Literal, Optional

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
