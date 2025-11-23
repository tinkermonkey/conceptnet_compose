-- ConceptNet 5.7 Database Indexes
-- This script creates indexes for optimized query performance

-- Print start message
DO $$
BEGIN
    RAISE NOTICE 'Creating indexes for ConceptNet tables...';
END $$;

-- Indexes for edges table (most important for query performance)

-- Index on relation for filtering by relationship type
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);

-- Index on start_node for finding outgoing edges from a concept
CREATE INDEX IF NOT EXISTS idx_edges_start_node ON edges(start_node);

-- Index on end_node for finding incoming edges to a concept
CREATE INDEX IF NOT EXISTS idx_edges_end_node ON edges(end_node);

-- Index on weight for sorting by edge strength
CREATE INDEX IF NOT EXISTS idx_edges_weight ON edges(weight DESC);

-- Index on dataset for filtering by data source
CREATE INDEX IF NOT EXISTS idx_edges_dataset ON edges(dataset);

-- Composite index for common query pattern: start_node + relation
CREATE INDEX IF NOT EXISTS idx_edges_start_relation ON edges(start_node, relation);

-- Composite index for common query pattern: end_node + relation
CREATE INDEX IF NOT EXISTS idx_edges_end_relation ON edges(end_node, relation);

-- Composite index for bidirectional queries
CREATE INDEX IF NOT EXISTS idx_edges_nodes ON edges(start_node, end_node);

-- GIN index on metadata JSONB for flexible JSON queries
CREATE INDEX IF NOT EXISTS idx_edges_metadata ON edges USING GIN(metadata);

-- Full-text search index on surface_text (if present)
CREATE INDEX IF NOT EXISTS idx_edges_surfacetext_gin
ON edges USING GIN(to_tsvector('english', COALESCE(surface_text, '')));

-- Indexes for nodes table

-- Index on concept for text search
CREATE INDEX IF NOT EXISTS idx_nodes_concept ON nodes(concept);

-- Index on language for filtering by language
CREATE INDEX IF NOT EXISTS idx_nodes_language ON nodes(language);

-- Index on label for text search
CREATE INDEX IF NOT EXISTS idx_nodes_label ON nodes(label);

-- Composite index for concept + language
CREATE INDEX IF NOT EXISTS idx_nodes_concept_lang ON nodes(concept, language);

-- Full-text search on label
CREATE INDEX IF NOT EXISTS idx_nodes_label_gin
ON nodes USING GIN(to_tsvector('english', COALESCE(label, '')));

-- Indexes for relations table (small table, but useful for joins)

-- Index on label
CREATE INDEX IF NOT EXISTS idx_relations_label ON relations(label);

-- Analyze tables to update statistics
ANALYZE edges;
ANALYZE nodes;
ANALYZE relations;

-- Print completion message with index count
DO $$
DECLARE
    index_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'public'
    AND tablename IN ('edges', 'nodes', 'relations');

    RAISE NOTICE 'Index creation complete. Total indexes created: %', index_count;
END $$;
