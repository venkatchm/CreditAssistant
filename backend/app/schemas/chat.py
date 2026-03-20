from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


ChatCategory = Literal[
    "PERSONAL_FINANCE_FACT",
    "PERSONAL_FINANCE_EXPLANATION",
    "GENERAL_FINANCE_KNOWLEDGE",
    "RECOMMENDATION",
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


class ChatResponse(BaseModel):
    message: str
    cards: List[ChatCard] = Field(default_factory=list)
    requires_disclaimer: bool
    category: ChatCategory


class ClassificationResult(BaseModel):
    category: ChatCategory
    normalized_message: str
