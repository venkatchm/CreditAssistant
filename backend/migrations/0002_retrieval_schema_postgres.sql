CREATE TABLE IF NOT EXISTS retrieval_documents (
    id UUID PRIMARY KEY,
    external_id TEXT NOT NULL UNIQUE,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_uri TEXT,
    effective_date DATE,
    version TEXT,
    doc_type TEXT NOT NULL DEFAULT 'knowledge_article',
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_chunks (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    heading TEXT,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    char_count INTEGER NOT NULL DEFAULT 0,
    source_name TEXT NOT NULL,
    effective_date DATE,
    version TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_document_id ON retrieval_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_chunks_topic ON retrieval_chunks(topic);

CREATE TABLE IF NOT EXISTS retrieval_chunk_embeddings (
    chunk_id UUID NOT NULL REFERENCES retrieval_chunks(id) ON DELETE CASCADE,
    embedding_model TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    embedding_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (chunk_id, embedding_model)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunk_embeddings_model
ON retrieval_chunk_embeddings(embedding_model);

CREATE TABLE IF NOT EXISTS retrieval_chunk_lexical (
    chunk_id UUID PRIMARY KEY REFERENCES retrieval_chunks(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES retrieval_documents(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    search_text TEXT NOT NULL,
    source_name TEXT NOT NULL,
    search_vector tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(topic, '') || ' ' || coalesce(title, '') || ' ' || coalesce(search_text, ''))
    ) STORED
);

CREATE INDEX IF NOT EXISTS idx_retrieval_chunk_lexical_search_vector
ON retrieval_chunk_lexical USING GIN(search_vector);
