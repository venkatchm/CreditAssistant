-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add native vector column for fast similarity search
ALTER TABLE retrieval_chunk_embeddings
    ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Backfill existing JSON embeddings into the native vector column
UPDATE retrieval_chunk_embeddings
SET embedding = embedding_json::text::vector
WHERE embedding IS NOT NULL AND embedding_json IS NOT NULL;

-- Create HNSW index for cosine similarity (sub-linear search)
CREATE INDEX IF NOT EXISTS idx_chunk_embeddings_vector
ON retrieval_chunk_embeddings USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
