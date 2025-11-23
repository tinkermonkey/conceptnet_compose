-- ConceptNet 5.7 Database Schema
-- This script creates the initial database schema for ConceptNet

-- Enable UUID extension for potential future use
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Table: edges (Primary assertions/relationships table)
-- Stores all the edges (assertions) from ConceptNet
CREATE TABLE IF NOT EXISTS edges (
    id SERIAL PRIMARY KEY,
    uri TEXT UNIQUE NOT NULL,
    relation VARCHAR(100) NOT NULL,
    start_node TEXT NOT NULL,
    end_node TEXT NOT NULL,
    weight NUMERIC(10, 4) DEFAULT 1.0,
    sources TEXT,
    dataset VARCHAR(100),
    surface_text TEXT,
    license VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT edges_uri_unique UNIQUE (uri)
);

-- Table: nodes (Concepts/entities)
-- Stores unique concepts extracted from edges
CREATE TABLE IF NOT EXISTS nodes (
    id SERIAL PRIMARY KEY,
    uri TEXT UNIQUE NOT NULL,
    concept TEXT NOT NULL,
    language VARCHAR(10),
    label TEXT,
    sense_label TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT nodes_uri_unique UNIQUE (uri)
);

-- Table: relations (Relationship types)
-- Stores the types of relationships used in ConceptNet
CREATE TABLE IF NOT EXISTS relations (
    id SERIAL PRIMARY KEY,
    uri VARCHAR(100) UNIQUE NOT NULL,
    label VARCHAR(100) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT relations_uri_unique UNIQUE (uri)
);

-- Table: data_loading_log (Track data loading operations)
-- Useful for tracking when data was loaded and monitoring progress
CREATE TABLE IF NOT EXISTS data_loading_log (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,
    rows_affected INTEGER,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Insert common ConceptNet relations
INSERT INTO relations (uri, label, description) VALUES
    ('/r/RelatedTo', 'related to', 'The most general relation. X is related to Y'),
    ('/r/FormOf', 'form of', 'X is a form of the word Y'),
    ('/r/IsA', 'is a', 'X is a subtype or a specific instance of Y'),
    ('/r/PartOf', 'part of', 'X is a part of Y'),
    ('/r/HasA', 'has a', 'X has Y as a part or attribute'),
    ('/r/UsedFor', 'used for', 'X is used for Y'),
    ('/r/CapableOf', 'capable of', 'X can do Y'),
    ('/r/AtLocation', 'at location', 'X is typically found at Y'),
    ('/r/Causes', 'causes', 'X causes Y to happen'),
    ('/r/HasSubevent', 'has subevent', 'Event X has subevent Y'),
    ('/r/HasFirstSubevent', 'has first subevent', 'The first thing that happens during X is Y'),
    ('/r/HasLastSubevent', 'has last subevent', 'The last thing that happens during X is Y'),
    ('/r/HasPrerequisite', 'has prerequisite', 'In order to do X, you need to do Y'),
    ('/r/HasProperty', 'has property', 'X has property Y'),
    ('/r/MotivatedByGoal', 'motivated by goal', 'You would do X because you want result Y'),
    ('/r/ObstructedBy', 'obstructed by', 'X is prevented or obstructed by Y'),
    ('/r/Desires', 'desires', 'X wants Y'),
    ('/r/CreatedBy', 'created by', 'X was created by Y'),
    ('/r/Synonym', 'synonym', 'X and Y have very similar meanings'),
    ('/r/Antonym', 'antonym', 'X and Y are opposites in some relevant way'),
    ('/r/DistinctFrom', 'distinct from', 'X and Y are distinct members of a set'),
    ('/r/DerivedFrom', 'derived from', 'X is derived from Y in a linguistic sense'),
    ('/r/SymbolOf', 'symbol of', 'X symbolically represents Y'),
    ('/r/DefinedAs', 'defined as', 'X is defined as Y'),
    ('/r/MannerOf', 'manner of', 'X is a specific way to do Y'),
    ('/r/LocatedNear', 'located near', 'X is typically found near Y'),
    ('/r/HasContext', 'has context', 'X is used in the context of Y'),
    ('/r/SimilarTo', 'similar to', 'X is similar to Y'),
    ('/r/EtymologicallyRelatedTo', 'etymologically related to', 'X and Y have a common origin'),
    ('/r/EtymologicallyDerivedFrom', 'etymologically derived from', 'X is derived from Y'),
    ('/r/CausesDesire', 'causes desire', 'X makes people want Y'),
    ('/r/MadeOf', 'made of', 'X is made of Y'),
    ('/r/ReceivesAction', 'receives action', 'X can be Yed'),
    ('/r/ExternalURL', 'external URL', 'X can be found at URL Y')
ON CONFLICT (uri) DO NOTHING;

-- Create a view for easy querying of edge information with relation labels
CREATE OR REPLACE VIEW edges_with_labels AS
SELECT
    e.id,
    e.uri,
    e.relation,
    r.label as relation_label,
    e.start_node,
    e.end_node,
    e.weight,
    e.sources,
    e.dataset,
    e.surface_text,
    e.metadata
FROM edges e
LEFT JOIN relations r ON e.relation = r.uri;

-- Grant appropriate permissions
GRANT SELECT ON edges TO PUBLIC;
GRANT SELECT ON nodes TO PUBLIC;
GRANT SELECT ON relations TO PUBLIC;
GRANT SELECT ON edges_with_labels TO PUBLIC;

-- Print completion message
DO $$
BEGIN
    RAISE NOTICE 'ConceptNet schema created successfully';
END $$;
