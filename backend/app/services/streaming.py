from __future__ import annotations

import json
from typing import Any

from app.schemas.chat import StreamEvent


def format_sse_event(event: StreamEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=True)
    return f"event: {event.event}\ndata: {payload}\n\n"


def build_start_event() -> str:
    return format_sse_event(StreamEvent(event="start", data={"status": "started"}))


def build_progress_event(event_name: str, **data: Any) -> str:
    return format_sse_event(StreamEvent(event=event_name, data=data))


def build_text_chunk_event(index: int, delta: str) -> str:
    return format_sse_event(StreamEvent(event="data", data={"index": index, "delta": delta}))


def build_end_event(**data: Any) -> str:
    payload = {"status": "completed", **data}
    return format_sse_event(StreamEvent(event="end", data=payload))


def build_error_event(message: str) -> str:
    return format_sse_event(StreamEvent(event="error", data={"message": message}))
