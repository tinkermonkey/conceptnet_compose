-- ConceptNet Numberbatch Embeddings Schema
-- This script creates the embeddings table for semantic similarity features

-- Print start message
DO $$
BEGIN
    RAISE NOTICE 'Creating pgvector extension and embeddings table...';
END $$;

-- Enable pgvector extension for vector operations
CREATE EXTENSION IF NOT EXISTS vector;

-- Table: embeddings (Concept word vectors for semantic similarity)
-- Stores 300-dimensional vectors for concepts
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    concept TEXT UNIQUE NOT NULL,
    vector vector(300) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT embeddings_concept_unique UNIQUE (concept)
);

-- Create vector similarity index using HNSW (Hierarchical Navigable Small World)
-- This enables fast approximate nearest neighbor search
-- Using cosine distance as the similarity metric
CREATE INDEX IF NOT EXISTS idx_embeddings_vector_hnsw
ON embeddings USING hnsw (vector vector_cosine_ops);

-- Also create a regular index on concept for lookups
CREATE INDEX IF NOT EXISTS idx_embeddings_concept ON embeddings(concept);

-- Grant permissions
GRANT SELECT ON embeddings TO PUBLIC;

-- Print completion message
DO $$
BEGIN
    RAISE NOTICE 'Embeddings table and pgvector extension created successfully';
END $$;
