PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS retrieval_documents (
    id TEXT PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_uri TEXT,
    effective_date TEXT,
    version TEXT,
    doc_type TEXT NOT NULL DEFAULT 'knowledge_article',
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    raw_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    source_name TEXT NOT NULL,
    effective_date TEXT,
    version TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_document_id ON retrieval_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_topic ON retrieval_chunks(topic);

CREATE TABLE IF NOT EXISTS retrieval_chunk_embeddings (
    chunk_id TEXT NOT NULL REFERENCES retrieval_chunks(id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (chunk_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunk_embeddings_model
ON retrieval_chunk_embeddings(embedding_model);

CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_chunk_lexical
USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    topic,
    title,
    search_text,
    source_name UNINDEXED,
    content='',
    tokenize='unicode61'
);
