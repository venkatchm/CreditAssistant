from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.dependencies import get_chat_orchestrator
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.streaming import build_error_event
from app.services.chat_orchestrator import ChatOrchestrator


router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(payload: ChatRequest, orchestrator: ChatOrchestrator = Depends(get_chat_orchestrator)):
    if payload.stream:
        def event_stream():
            try:
                yield from orchestrator.stream_response(user_id=payload.user_id, message=payload.message)
            except Exception as exc:  # pragma: no cover
                yield build_error_event(str(exc))

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return orchestrator.respond(user_id=payload.user_id, message=payload.message)
