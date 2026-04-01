from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SourceDocument(BaseModel):
    doc_id: str
    topic: str
    title: str
    content: str
    tags: List[str] = Field(default_factory=list)
    source: str
    effective_date: Optional[str] = None
    version: Optional[str] = None


class ChunkedDocument(BaseModel):
    chunk_id: str
    doc_id: str
    topic: str
    title: str
    content: str
    chunk_index: int
    tags: List[str] = Field(default_factory=list)
    source: str
    effective_date: Optional[str] = None
    version: Optional[str] = None


class RetrievalCandidate(BaseModel):
    chunk: ChunkedDocument
    score: float
    strategy: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    topic: str
    title: str
    content: str
    source: str
    score: float
    strategy: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    effective_date: Optional[str] = None
    version: Optional[str] = None
