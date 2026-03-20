from __future__ import annotations

import json
from typing import Iterable

from app.schemas.chat import StreamEvent


def format_sse_event(event: StreamEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=True)
    return f"event: {event.event}\ndata: {payload}\n\n"


def build_text_stream_events(chunks: Iterable[str]) -> Iterable[str]:
    chunk_index = 0
    yield format_sse_event(StreamEvent(event="start", data={"status": "started"}))
    for chunk in chunks:
        if not chunk:
            continue
        yield format_sse_event(
            StreamEvent(
                event="data",
                data={
                    "index": chunk_index,
                    "delta": chunk,
                },
            )
        )
        chunk_index += 1
    yield format_sse_event(StreamEvent(event="end", data={"status": "completed"}))


def build_error_event(message: str) -> str:
    return format_sse_event(StreamEvent(event="error", data={"message": message}))
