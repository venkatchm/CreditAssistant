from __future__ import annotations

import re

from app.retrieval.models import ChunkedDocument, SourceDocument

# Regex that splits on sentence boundaries (period, question mark, exclamation)
# followed by whitespace, while preserving the delimiter.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class SentenceChunker:
    """Split documents into chunks of roughly max_chars, with optional sentence overlap."""

    def __init__(self, max_chars: int = 800, overlap_sentences: int = 1) -> None:
        self.max_chars = max_chars
        self.overlap_sentences = overlap_sentences

    def chunk(self, document: SourceDocument) -> list[ChunkedDocument]:
        raw_chunks = self._split_text(document.content)
        if not raw_chunks:
            raw_chunks = [document.content]
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
            for index, chunk in enumerate(raw_chunks)
        ]

    def _split_text(self, text: str) -> list[str]:
        # First split on paragraph breaks, then on sentences within paragraphs
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        sentences: list[str] = []
        for para in paragraphs:
            parts = [s.strip() for s in _SENTENCE_SPLIT.split(para) if s.strip()]
            sentences.extend(parts)

        if not sentences:
            return [text] if text.strip() else []

        chunks: list[str] = []
        current_sentences: list[str] = []
        current_len = 0

        for sentence in sentences:
            candidate_len = current_len + len(sentence) + (1 if current_sentences else 0)
            if candidate_len <= self.max_chars or not current_sentences:
                current_sentences.append(sentence)
                current_len = candidate_len
                continue

            # Flush current chunk
            chunks.append(" ".join(current_sentences))

            # Carry overlap sentences into next chunk
            if self.overlap_sentences > 0:
                overlap = current_sentences[-self.overlap_sentences :]
                current_sentences = overlap + [sentence]
            else:
                current_sentences = [sentence]
            current_len = sum(len(s) for s in current_sentences) + len(current_sentences) - 1

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        return chunks
