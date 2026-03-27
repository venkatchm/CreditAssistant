from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from math import sqrt
from uuid import uuid4

from app.retrieval.models import ChunkedDocument, RetrievedChunk, SourceDocument
from app.retrieval.persistence import RetrievalPersistenceBackend
from app.retrieval.sqlite_store import build_search_text, normalize_match_query

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresRetrievalPersistence(RetrievalPersistenceBackend):
    def __init__(self, dsn: str, embedding_model: str, migration_sql: str | None = None) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is required for the postgres retrieval backend.")
        self.dsn = dsn
        self.embedding_model = embedding_model
        if migration_sql:
            self._apply_migration(migration_sql)

    @contextmanager
    def connect(self):
        connection = psycopg.connect(self.dsn, row_factory=dict_row)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def replace_documents(self, documents: list[SourceDocument], chunks: list[ChunkedDocument], embeddings: list[list[float]]) -> None:
        now = utc_now_iso()
        document_id_map: dict[str, str] = {}
        chunk_row_id_map: dict[str, str] = {}
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM retrieval_chunk_lexical")
                cursor.execute("DELETE FROM retrieval_chunk_embeddings")
                cursor.execute("DELETE FROM retrieval_chunks")
                cursor.execute("DELETE FROM retrieval_documents")

                for document in documents:
                    document_row_id = str(uuid4())
                    document_id_map[document.doc_id] = document_row_id
                    cursor.execute(
                        """
                        INSERT INTO retrieval_documents (
                            id, external_id, topic, title, source_name, source_uri, effective_date, version,
                            metadata_json, raw_content, content_hash, created_at, updated_at
                        ) VALUES (
                            %(id)s, %(external_id)s, %(topic)s, %(title)s, %(source_name)s, %(source_uri)s,
                            %(effective_date)s, %(version)s, %(metadata_json)s, %(raw_content)s,
                            %(content_hash)s, %(created_at)s, %(updated_at)s
                        )
                        """,
                        {
                            "id": document_row_id,
                            "external_id": document.doc_id,
                            "topic": document.topic,
                            "title": document.title,
                            "source_name": document.source,
                            "source_uri": None,
                            "effective_date": document.effective_date,
                            "version": document.version,
                            "metadata_json": json.dumps({"tags": document.tags}),
                            "raw_content": document.content,
                            "content_hash": sha256(document.content.encode("utf-8")).hexdigest(),
                            "created_at": now,
                            "updated_at": now,
                        },
                    )

                for chunk in chunks:
                    chunk_row_id = str(uuid4())
                    chunk_row_id_map[chunk.chunk_id] = chunk_row_id
                    cursor.execute(
                        """
                        INSERT INTO retrieval_chunks (
                            id, document_id, chunk_index, heading, topic, title, chunk_text,
                            token_count, char_count, source_name, effective_date, version,
                            metadata_json, created_at
                        ) VALUES (
                            %(id)s, %(document_id)s, %(chunk_index)s, %(heading)s, %(topic)s, %(title)s,
                            %(chunk_text)s, %(token_count)s, %(char_count)s, %(source_name)s,
                            %(effective_date)s, %(version)s, %(metadata_json)s, %(created_at)s
                        )
                        """,
                        {
                            "id": chunk_row_id,
                            "document_id": document_id_map[chunk.doc_id],
                            "chunk_index": chunk.chunk_index,
                            "heading": None,
                            "topic": chunk.topic,
                            "title": chunk.title,
                            "chunk_text": chunk.content,
                            "token_count": len(chunk.content.split()),
                            "char_count": len(chunk.content),
                            "source_name": chunk.source,
                            "effective_date": chunk.effective_date,
                            "version": chunk.version,
                            "metadata_json": json.dumps({"tags": chunk.tags, "chunk_id": chunk.chunk_id}),
                            "created_at": now,
                        },
                    )
                    cursor.execute(
                        """
                        INSERT INTO retrieval_chunk_lexical (
                            chunk_id, document_id, topic, title, search_text, source_name
                        ) VALUES (
                            %(chunk_id)s, %(document_id)s, %(topic)s, %(title)s, %(search_text)s, %(source_name)s
                        )
                        """,
                        {
                            "chunk_id": chunk_row_id,
                            "document_id": document_id_map[chunk.doc_id],
                            "topic": chunk.topic,
                            "title": chunk.title,
                            "search_text": build_search_text(chunk),
                            "source_name": chunk.source,
                        },
                    )

                for chunk, embedding in zip(chunks, embeddings):
                    embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                    cursor.execute(
                        """
                        INSERT INTO retrieval_chunk_embeddings (
                            chunk_id, embedding_model, embedding_dimensions, embedding_json, embedding, created_at
                        ) VALUES (
                            %(chunk_id)s, %(embedding_model)s, %(embedding_dimensions)s, %(embedding_json)s,
                            %(embedding)s::vector, %(created_at)s
                        )
                        """,
                        {
                            "chunk_id": chunk_row_id_map[chunk.chunk_id],
                            "embedding_model": self.embedding_model,
                            "embedding_dimensions": len(embedding),
                            "embedding_json": json.dumps(embedding),
                            "embedding": embedding_str,
                            "created_at": now,
                        },
                    )

    def vector_search(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        query_vec = "[" + ",".join(str(v) for v in query_embedding) + "]"
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                        1 - (e.embedding <=> %(query_vec)s::vector) AS score
                    FROM retrieval_chunk_embeddings e
                    JOIN retrieval_chunks c ON c.id = e.chunk_id
                    JOIN retrieval_documents d ON d.id = c.document_id
                    WHERE e.embedding_model = %(embedding_model)s
                      AND e.embedding IS NOT NULL
                    ORDER BY e.embedding <=> %(query_vec)s::vector
                    LIMIT %(limit)s
                    """,
                    {"query_vec": query_vec, "embedding_model": self.embedding_model, "limit": top_k},
                )
                rows = cursor.fetchall()
        return [
            RetrievedChunk(
                chunk_id=str(row["chunk_id"]),
                doc_id=str(row["doc_id"]),
                topic=row["topic"],
                title=row["title"],
                content=row["chunk_text"],
                source=row["source_name"],
                score=float(row["score"]),
                strategy="vector",
                score_breakdown={"vector": round(float(row["score"]), 4)},
                effective_date=str(row["effective_date"]) if row["effective_date"] else None,
                version=row["version"],
            )
            for row in rows
        ]

    def lexical_search(self, query: str, top_k: int) -> list[RetrievedChunk]:
        ts_query = normalize_match_query(query).replace(" OR ", " | ")
        if not ts_query:
            return []
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
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
                        ts_rank_cd(l.search_vector, websearch_to_tsquery('english', %(query)s)) AS lexical_rank
                    FROM retrieval_chunk_lexical l
                    JOIN retrieval_chunks c ON c.id = l.chunk_id
                    JOIN retrieval_documents d ON d.id = c.document_id
                    WHERE l.search_vector @@ websearch_to_tsquery('english', %(query)s)
                    ORDER BY lexical_rank DESC
                    LIMIT %(limit)s
                    """,
                    {"query": query, "limit": top_k},
                )
                rows = cursor.fetchall()
        return [
            RetrievedChunk(
                chunk_id=str(row["chunk_id"]),
                doc_id=str(row["doc_id"]),
                topic=row["topic"],
                title=row["title"],
                content=row["chunk_text"],
                source=row["source_name"],
                score=float(row["lexical_rank"]),
                strategy="lexical",
                score_breakdown={"lexical": round(float(row["lexical_rank"]), 4)},
                effective_date=str(row["effective_date"]) if row["effective_date"] else None,
                version=row["version"],
            )
            for row in rows
        ]

    def has_indexed_chunks(self) -> bool:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM retrieval_chunks")
                row = cursor.fetchone()
        return bool(row and row["count"] > 0)

    def _apply_migration(self, migration_sql: str) -> None:
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(migration_sql)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    numerator = sum(lhs * rhs for lhs, rhs in zip(left, right))
    left_norm = sqrt(sum(value * value for value in left)) or 1.0
    right_norm = sqrt(sum(value * value for value in right)) or 1.0
    return numerator / (left_norm * right_norm)
