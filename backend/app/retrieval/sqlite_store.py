from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from math import sqrt
from pathlib import Path
from threading import RLock
from typing import Iterator
from uuid import uuid4

from app.retrieval.models import ChunkedDocument, RetrievedChunk, SourceDocument
from app.retrieval.persistence import RetrievalPersistenceBackend


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RetrievalDatabase:
    def __init__(self, db_path: Path, migration_path: Path) -> None:
        self.db_path = db_path
        self.migration_path = migration_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._apply_migrations()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _apply_migrations(self) -> None:
        sql = self.migration_path.read_text(encoding="utf-8")
        with self.connect() as connection:
            connection.executescript(sql)


class RetrievalPersistence(RetrievalPersistenceBackend):
    def __init__(self, database: RetrievalDatabase, embedding_model: str) -> None:
        self.database = database
        self.embedding_model = embedding_model
        self._embedding_rows_cache: list[sqlite3.Row] | None = None
        self._cache_lock = RLock()

    def replace_documents(self, documents: list[SourceDocument], chunks: list[ChunkedDocument], embeddings: list[list[float]]) -> None:
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        now = utc_now_iso()
        with self.database.connect() as connection:
            connection.execute("DELETE FROM retrieval_chunk_lexical")
            connection.execute("DELETE FROM retrieval_chunk_embeddings")
            connection.execute("DELETE FROM retrieval_chunks")
            connection.execute("DELETE FROM retrieval_documents")

            document_id_map: dict[str, str] = {}
            for document in documents:
                document_id = str(uuid4())
                document_id_map[document.doc_id] = document_id
                connection.execute(
                    """
                    INSERT INTO retrieval_documents (
                        id, external_id, topic, title, source_name, source_uri, effective_date, version,
                        metadata_json, raw_content, content_hash, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        document.doc_id,
                        document.topic,
                        document.title,
                        document.source,
                        None,
                        document.effective_date,
                        document.version,
                        json.dumps({"tags": document.tags}),
                        document.content,
                        sha256(document.content.encode("utf-8")).hexdigest(),
                        now,
                        now,
                    ),
                )

            for chunk in chunks:
                chunk_row_id = str(uuid4())
                metadata_json = json.dumps({"tags": chunk.tags, "chunk_id": chunk.chunk_id})
                connection.execute(
                    """
                    INSERT INTO retrieval_chunks (
                        id, document_id, chunk_index, heading, topic, title, chunk_text,
                        token_count, char_count, source_name, effective_date, version,
                        metadata_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_row_id,
                        document_id_map[chunk.doc_id],
                        chunk.chunk_index,
                        None,
                        chunk.topic,
                        chunk.title,
                        chunk.content,
                        len(chunk.content.split()),
                        len(chunk.content),
                        chunk.source,
                        chunk.effective_date,
                        chunk.version,
                        metadata_json,
                        now,
                    ),
                )
                chunk_by_id[chunk.chunk_id] = chunk.model_copy(update={"chunk_id": chunk_row_id, "doc_id": chunk.doc_id})
                connection.execute(
                    """
                    INSERT INTO retrieval_chunk_lexical (
                        chunk_id, document_id, topic, title, search_text, source_name
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_row_id,
                        document_id_map[chunk.doc_id],
                        chunk.topic,
                        chunk.title,
                        build_search_text(chunk),
                        chunk.source,
                    ),
                )

            for original_chunk, embedding in zip(chunks, embeddings):
                persisted_chunk = chunk_by_id[original_chunk.chunk_id]
                connection.execute(
                    """
                    INSERT INTO retrieval_chunk_embeddings (
                        chunk_id, embedding_model, embedding_dimensions, embedding_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        persisted_chunk.chunk_id,
                        self.embedding_model,
                        len(embedding),
                        json.dumps(embedding),
                        now,
                    ),
                )
        with self._cache_lock:
            self._embedding_rows_cache = None

    def vector_search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        rows = self._get_embedding_rows()
        ranked: list[RetrievedChunk] = []
        for row in rows:
            embedding = json.loads(row["embedding_json"])
            score = cosine_similarity(query_embedding, embedding)
            ranked.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    topic=row["topic"],
                    title=row["title"],
                    content=row["chunk_text"],
                    source=row["source_name"],
                    score=score,
                    strategy="vector",
                    score_breakdown={"vector": round(score, 4)},
                    effective_date=row["effective_date"],
                    version=row["version"],
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[:top_k]

    def _get_embedding_rows(self) -> list[sqlite3.Row]:
        with self._cache_lock:
            if self._embedding_rows_cache is None:
                # This remains an in-Python ranking path, which is fine for the bundled tiny corpus.
                # Caching removes repeated SQLite reads on the /chat retrieval hot path.
                with self.database.connect() as connection:
                    self._embedding_rows_cache = connection.execute(
                        """
                        SELECT
                            c.id AS chunk_id,
                            d.external_id AS doc_id,
                            c.topic,
                            c.title,
                            c.chunk_text,
                            c.source_name,
                            c.effective_date,
                            c.version,
                            e.embedding_json
                        FROM retrieval_chunk_embeddings e
                        JOIN retrieval_chunks c ON c.id = e.chunk_id
                        JOIN retrieval_documents d ON d.id = c.document_id
                        WHERE e.embedding_model = ?
                        """,
                        (self.embedding_model,),
                    ).fetchall()
            return list(self._embedding_rows_cache)

    def lexical_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        match_query = normalize_match_query(query)
        if not match_query:
            return []
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    l.chunk_id,
                    d.external_id AS doc_id,
                    c.topic,
                    c.title,
                    c.chunk_text,
                    c.source_name,
                    c.effective_date,
                    c.version,
                    bm25(retrieval_chunk_lexical) AS lexical_rank
                FROM retrieval_chunk_lexical l
                JOIN retrieval_chunks c ON c.id = l.chunk_id
                JOIN retrieval_documents d ON d.id = c.document_id
                WHERE retrieval_chunk_lexical MATCH ?
                ORDER BY lexical_rank
                LIMIT ?
                """,
                (match_query, top_k),
            ).fetchall()
        results: list[RetrievedChunk] = []
        for row in rows:
            rank = float(row["lexical_rank"])
            score = 1.0 / (1.0 + max(rank, 0.0))
            results.append(
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    doc_id=row["doc_id"],
                    topic=row["topic"],
                    title=row["title"],
                    content=row["chunk_text"],
                    source=row["source_name"],
                    score=score,
                    strategy="lexical",
                    score_breakdown={"lexical": round(score, 4)},
                    effective_date=row["effective_date"],
                    version=row["version"],
                )
            )
        return results

    def has_indexed_chunks(self) -> bool:
        with self.database.connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM retrieval_chunks").fetchone()
        return bool(row and row["count"] > 0)


def build_search_text(chunk: ChunkedDocument) -> str:
    return " ".join([chunk.topic, chunk.title, chunk.content, " ".join(chunk.tags)])


def normalize_match_query(query: str) -> str:
    tokens = [
        token
        for token in "".join(character.lower() if character.isalnum() or character.isspace() else " " for character in query).split()
        if token
    ]
    return " OR ".join(tokens)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(lhs * rhs for lhs, rhs in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left)) or 1.0
    right_norm = sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)
