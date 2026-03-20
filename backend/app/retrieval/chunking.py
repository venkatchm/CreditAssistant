from __future__ import annotations

from app.retrieval.models import ChunkedDocument, SourceDocument


class SentenceChunker:
    def __init__(self, max_chars: int = 320) -> None:
        self.max_chars = max_chars

    def chunk(self, document: SourceDocument) -> list[ChunkedDocument]:
        sentences = [part.strip() for part in document.content.split(".") if part.strip()]
        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            candidate = f"{current}. {sentence}".strip(". ").strip() if current else sentence
            if len(candidate) <= self.max_chars:
                current = candidate
                continue
            if current:
                chunks.append(f"{current}.")
            current = sentence
        if current:
            chunks.append(f"{current}.")
        if not chunks:
            chunks = [document.content]
        return [
            ChunkedDocument(
                chunk_id=f"{document.doc_id}#chunk_{index}",
                doc_id=document.doc_id,
                topic=document.topic,
                title=document.title,
                content=chunk,
                chunk_index=index,
                tags=document.tags,
                source=document.source,
                effective_date=document.effective_date,
                version=document.version,
            )
            for index, chunk in enumerate(chunks)
        ]
