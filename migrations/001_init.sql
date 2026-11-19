CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policies (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    pages jsonb NOT NULL,
    terms jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
    policy_id uuid NOT NULL REFERENCES policies ON DELETE CASCADE,
    page int NOT NULL,
    ord int NOT NULL,
    text text NOT NULL,
    embedding vector(768) NOT NULL,
    PRIMARY KEY (policy_id, ord)
);

CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
    ON chunks USING hnsw (embedding vector_cosine_ops);
