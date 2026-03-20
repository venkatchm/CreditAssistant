from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.dependencies import get_chat_orchestrator
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_orchestrator import ChatOrchestrator


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(payload: ChatRequest, orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator)) -> ChatResponse:
    return orchestrator.respond(user_id=payload.user_id, message=payload.message)
