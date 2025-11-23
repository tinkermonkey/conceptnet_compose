# ConceptNet 5.7 Local Deployment Design

## Overview

This document outlines the design for a Docker Compose-based deployment of ConceptNet 5.7, including:
- PostgreSQL database for storing assertions
- Data loader service for importing pre-built ConceptNet data
- API service for hosting the ConceptNet REST API

The design prioritizes using pre-built data to avoid the 18+ hour build process and 30GB RAM requirements.

## Architecture

```
+-------------------------------------------------------+
|                  Docker Compose                       |
|                                                       |
|  +--------------+  +--------------+  +----------+     |
|  |  PostgreSQL  |  | Data Loader  |  |   API    |     |
|  |              |  |  (one-time)  |  |  Service |     |
|  |  Port: 5432  |  |              |  | Port:8084|     |
|  +------+-------+  +------+-------+  +----+-----+     |
|         |                 |                |          |
|         +-----------------+----------------+          |
|                    Network: conceptnet                |
|                                                       |
|  Volumes:                                             |
|  - postgres-data/    (database files)                 |
|  - data/             (CSV downloads)                  |
+-------------------------------------------------------+
```

## Data Sources for ConceptNet 5.7

### Primary Data Files

ConceptNet 5.7.0 is the latest version with publicly available pre-built CSV files. While ConceptNet 5.8 exists, it was released primarily as an API service and AWS AMI without corresponding CSV downloads.

1. **Assertions CSV** (Required)
   - URL: `https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz`
   - Size: ~1.5 GB compressed, ~5 GB uncompressed
   - Format: Tab-separated values with 5 columns: URI, relation, start, end, metadata (JSON)
   - Contains: All edges (assertions) in ConceptNet 5.7
   - Official source: [ConceptNet Downloads Wiki](https://github.com/commonsense/conceptnet5/wiki/Downloads)

2. **Numberbatch Embeddings** (Optional, for semantic similarity features)
   - URL: `https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz`
   - **Purpose**: Powers the `/relatedness` and `/related` API endpoints
   - **What it does**:
     - Computes semantic similarity between concepts using 600-dimensional word vectors
     - Finds related terms even without direct graph connections
     - Supports multilingual similarity (concepts across different languages)
   - **Format**: Text file with one concept per line followed by 600 space-separated floats
   - **Size**: ~500 MB compressed
   - **Built from**: Ensemble of ConceptNet graph + word2vec + GloVe + OpenSubtitles data
   - **Note**: Not required for basic graph querying (`/c/{concept}`, `/query` endpoints work without it)
   - **Storage**: Can be loaded into PostgreSQL using pgvector extension or kept in-memory

### Graph Data vs. Embeddings: Two Types of Queries

ConceptNet provides two complementary ways to explore concepts:

| Feature | Graph Data (Required) | Embeddings (Optional) |
|---------|----------------------|----------------------|
| **Data Type** | Explicit relationships | Semantic vectors |
| **Example** | "dog IsA mammal" | dog = [0.23, -0.11, ...] (600 numbers) |
| **Query Method** | Graph traversal | Vector similarity (cosine distance) |
| **API Endpoints** | `/c/{concept}`, `/query` | `/relatedness`, `/related` |
| **Finds** | Stated facts and connections | Semantic similarity (implicit) |
| **Use Case** | "What properties does a dog have?" | "How similar are 'dog' and 'puppy'?" |
| **Multilingual** | Via explicit translations | Native multilingual space |

**Example Comparison**:
- **Graph query**: `/c/en/dog` → Returns edges like "dog IsA animal", "dog HasA tail"
- **Embedding query**: `/relatedness?node1=/c/en/dog&node2=/c/en/puppy` → Returns similarity score (e.g., 0.85)

### Data Format Details

**Assertions CSV** (tab-separated):
```
/a/[id]    /r/[relation]    /c/[lang]/[concept]    /c/[lang]/[concept]    {"weight": X.X, "dataset": "...", ...}
```

Example:
```
/a/[id]    /r/RelatedTo    /c/en/example    /c/en/sample    {"weight": 2.0, "dataset": "/d/wiktionary/en"}
```

**Numberbatch Embeddings** (space-separated):
```
/c/en/example 0.1234 -0.5678 0.9012 ... (600 dimensions total)
```

## Database Schema Design

### Tables

#### 1. `edges` (Primary assertions table)
```sql
CREATE TABLE edges (
    id SERIAL PRIMARY KEY,
    uri VARCHAR(255) UNIQUE NOT NULL,
    relation VARCHAR(100) NOT NULL,
    start VARCHAR(255) NOT NULL,
    "end" VARCHAR(255) NOT NULL,
    weight NUMERIC(10, 4) DEFAULT 1.0,
    sources TEXT,
    dataset VARCHAR(100),
    surfaceText TEXT,
    license VARCHAR(100),
    CONSTRAINT edges_uri_unique UNIQUE (uri)
);
```

#### 2. `nodes` (Concepts/entities)
```sql
CREATE TABLE nodes (
    id SERIAL PRIMARY KEY,
    uri VARCHAR(255) UNIQUE NOT NULL,
    concept TEXT NOT NULL,
    language VARCHAR(10),
    label TEXT,
    sense_label TEXT,
    CONSTRAINT nodes_uri_unique UNIQUE (uri)
);
```

#### 3. `relations` (Relationship types)
```sql
CREATE TABLE relations (
    id SERIAL PRIMARY KEY,
    uri VARCHAR(100) UNIQUE NOT NULL,
    label VARCHAR(100) NOT NULL,
    description TEXT
);
```

### Indexes

```sql
-- Performance indexes for common queries
CREATE INDEX idx_edges_relation ON edges(relation);
CREATE INDEX idx_edges_start ON edges(start);
CREATE INDEX idx_edges_end ON edges("end");
CREATE INDEX idx_edges_weight ON edges(weight);
CREATE INDEX idx_nodes_concept ON nodes(concept);
CREATE INDEX idx_nodes_language ON nodes(language);

-- Full-text search indexes (optional)
CREATE INDEX idx_edges_surfacetext_gin ON edges USING gin(to_tsvector('english', surfaceText));
```

## Service Definitions

### 1. PostgreSQL Service

**Purpose**: Store ConceptNet graph data

**Configuration**:
- Image: `postgres:15-alpine` (lightweight, modern)
- Memory: 8-12 GB allocation
- Storage: 20 GB minimum for full dataset
- Health check: Connection validation every 10s

**Environment Variables**:
- `POSTGRES_USER`: conceptnet
- `POSTGRES_PASSWORD`: (from .env file)
- `POSTGRES_DB`: conceptnet5
- `POSTGRES_INITDB_ARGS`: "--encoding=UTF8 --locale=en_US.UTF-8"

**Volumes**:
- `postgres-data:/var/lib/postgresql/data` (persistent storage)
- `./init-scripts:/docker-entrypoint-initdb.d` (schema initialization)

### 2. Data Loader Service

**Purpose**: One-time service to download and import ConceptNet data

**Base Image**: `python:3.11-slim`

**Lifecycle**:
1. Starts after PostgreSQL is healthy
2. Downloads ConceptNet CSV files if not present
3. Imports data into PostgreSQL
4. Creates indexes
5. Exits with success status
6. Can be rerun with `docker-compose run data-loader`

**Dependencies**:
```
pandas
psycopg2-binary
requests
tqdm (for progress bars)
```

**Process Flow**:
```
1. Check if data already loaded (count edges table)
2. If not loaded:
   a. Download CSV files to /data volume
   b. Decompress files
   c. Parse and validate data
   d. Bulk insert into PostgreSQL
   e. Create indexes
   f. Run vacuum analyze
3. Exit
```

### 3. ConceptNet API Service

**Purpose**: Host the ConceptNet REST API

**Base Image**: `python:3.11-slim` or custom built from ConceptNet repo

**Dependencies**:
```
conceptnet5 (from git repository)
Flask
psycopg2-binary
hug (ConceptNet's API framework)
ftfy (text normalization)
wordfreq
```

**API Endpoints** (standard ConceptNet API):
- `GET /c/{concept}` - Get information about a concept
- `GET /d/{relation}/{concept}` - Get related concepts
- `GET /query?start=/c/en/{concept}` - Query edges
- `GET /relatedness` - Semantic similarity

**Environment Variables**:
- `CONCEPTNET_DB_HOSTNAME`: postgres
- `CONCEPTNET_DB_PORT`: 5432
- `CONCEPTNET_DB_NAME`: conceptnet5
- `CONCEPTNET_DB_USER`: conceptnet
- `CONCEPTNET_DB_PASSWORD`: (from .env)

## File Structure

```
conceptnet/
 docker-compose.yml
 .env
 .env.example
 .dockerignore
 .gitignore
 README.md

 services/
    postgres/
       init-scripts/
           01-create-schema.sql
           02-create-indexes.sql
   
    data-loader/
       Dockerfile
       requirements.txt
       loader.py
       download_data.py
       config.py
   
    api/
        Dockerfile
        requirements.txt
        start.sh
        config.py

 data/
    raw/                    (downloaded CSVs)
    processed/              (temporary processing)

 documentation/
     00_research.md
     01_design.md            (this file)
     02_api_guide.md         (future)
```

## Docker Compose Configuration

### Networks
```yaml
networks:
  conceptnet:
    driver: bridge
```

### Volumes
```yaml
volumes:
  postgres-data:
    driver: local
  data-downloads:
    driver: local
```

### Service Dependencies
```
postgres (no dependencies)
  �
data-loader (depends_on: postgres with health check)
  �
api (depends_on: postgres with health check)
```

## Data Loading Strategy

### Phase 1: Download
```python
# download_data.py
SOURCES = {
    'assertions': {
        'url': 'https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz',
        'local': '/data/raw/conceptnet-assertions-5.7.0.csv.gz',
        'uncompressed': '/data/raw/conceptnet-assertions-5.7.0.csv'
    }
}
```

### Phase 2: Parse and Transform
```python
# loader.py
def parse_assertion_line(line):
    """
    Parse ConceptNet assertion CSV line
    Format: /a/[id], /r/[relation], /c/[lang]/[concept], /c/[lang]/[concept], {...}
    """
    parts = line.strip().split('\t')
    return {
        'uri': parts[0],
        'relation': parts[1],
        'start': parts[2],
        'end': parts[3],
        'metadata': json.loads(parts[4]) if len(parts) > 4 else {}
    }
```

### Phase 3: Bulk Insert
```python
# Use COPY for maximum performance
def bulk_insert_edges(conn, edges_file):
    cursor = conn.cursor()
    with open(edges_file, 'r') as f:
        cursor.copy_expert(
            """
            COPY edges (uri, relation, start, "end", weight, sources, dataset)
            FROM STDIN WITH CSV DELIMITER E'\t'
            """,
            f
        )
    conn.commit()
```

### Phase 4: Post-Processing
- Extract unique nodes from edges
- Populate relations table
- Create indexes (may take 30-60 minutes)
- Run `VACUUM ANALYZE`

## API Implementation Strategy

### Option A: Use Official ConceptNet Repository

**Pros**:
- Official implementation
- Matches public API behavior
- Well-tested

**Cons**:
- May have outdated dependencies
- Complex setup
- Tied to specific Python version

**Implementation**:
```dockerfile
FROM python:3.8-slim

RUN git clone https://github.com/commonsense/conceptnet5.git /app/conceptnet5
WORKDIR /app/conceptnet5

RUN pip install -e .
```

### Option B: Custom Lightweight API

**Pros**:
- Minimal dependencies
- Modern Python (3.11+)
- Easy to customize
- Smaller container

**Cons**:
- Need to implement API endpoints
- May miss some features

**Implementation**:
```python
# Flask-based API
from flask import Flask, jsonify, request
import psycopg2

app = Flask(__name__)

@app.route('/c/<path:concept>')
def get_concept(concept):
    # Query edges where start or end = concept
    pass

@app.route('/query')
def query_edges():
    # Flexible query with filters
    pass
```

**Recommendation**: Start with Option B (custom API) for simplicity, can migrate to Option A later if needed.

## Performance Considerations

### Database Tuning

**PostgreSQL Configuration** (`postgresql.conf` overrides):
```ini
# Memory
shared_buffers = 4GB              # 25% of available RAM
effective_cache_size = 12GB       # 75% of available RAM
work_mem = 128MB
maintenance_work_mem = 1GB

# Connections
max_connections = 100

# Query Planning
random_page_cost = 1.1           # SSD optimization
effective_io_concurrency = 200   # SSD optimization

# Write Performance
wal_buffers = 16MB
checkpoint_completion_target = 0.9
```

### API Caching

- Use Redis for frequently accessed concepts
- Cache query results for 1 hour
- Implement ETag headers for client-side caching

### Connection Pooling

```python
# Use connection pooling in API service
from psycopg2 import pool
db_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,
    host='postgres',
    database='conceptnet5',
    user='conceptnet',
    password=os.getenv('POSTGRES_PASSWORD')
)
```

## Security Considerations

1. **Environment Variables**:
   - Store passwords in `.env` (not committed)
   - Use strong passwords (16+ characters)

2. **Network Isolation**:
   - PostgreSQL not exposed to host (internal only)
   - API only exposed on localhost or with authentication

3. **Database Access**:
   - Read-only user for API service
   - Admin user only for data loader

4. **Container Security**:
   - Run as non-root user
   - Minimal base images
   - Regular security updates

## Deployment Steps

### Initial Setup

1. Clone repository and enter directory
2. Copy `.env.example` to `.env` and configure passwords
3. Run `docker-compose up -d postgres` (start database)
4. Run `docker-compose run data-loader` (load data, one-time)
5. Run `docker-compose up -d api` (start API)
6. Verify API: `curl http://localhost:8084/c/en/example`

### Maintenance

- **Backup**: `docker exec conceptnet-db pg_dump -U conceptnet conceptnet5 > backup.sql`
- **Restore**: `docker exec -i conceptnet-db psql -U conceptnet conceptnet5 < backup.sql`
- **Update data**: Re-run data-loader service
- **View logs**: `docker-compose logs -f api`

## Monitoring and Health Checks

### Database Health
```sql
-- Check row counts
SELECT COUNT(*) FROM edges;
SELECT COUNT(*) FROM nodes;

-- Check index usage
SELECT schemaname, tablename, indexname, idx_scan
FROM pg_stat_user_indexes
ORDER BY idx_scan ASC;
```

### API Health
```bash
# Health endpoint
curl http://localhost:8084/health

# Sample query
curl http://localhost:8084/c/en/knowledge
```

### Container Monitoring
```bash
# Resource usage
docker stats conceptnet-db conceptnet-api

# Health status
docker-compose ps
```

## Future Enhancements

1. **Numberbatch Embeddings Integration**:
   - Download and load Numberbatch word vectors
   - Implement `/relatedness` and `/related` endpoints
   - Options: pgvector extension in PostgreSQL or in-memory vector store
2. **Caching Layer**: Add Redis for performance
3. **API Gateway**: Add nginx for load balancing
4. **Monitoring**: Add Prometheus + Grafana
5. **GraphQL API**: Alternative to REST API
6. **Multi-language Support**: Full multilingual concept support
7. **Data Updates**: Automated pipeline for new ConceptNet releases

## Open Questions

1. **~~ConceptNet 5.8 Data Availability~~** ✓ RESOLVED:
   - Pre-built CSV for 5.8 is NOT publicly available
   - **Decision**: Use ConceptNet 5.7.0 CSV (confirmed available and well-documented)
   - Rationale: Version 5.8 changes were primarily infrastructure improvements; data content differences are minimal

2. **API Feature Set**:
   - **Essential endpoints** (graph-based, no embeddings needed):
     - `/c/{concept}` - Get concept information
     - `/query` - Query edges with filters
   - **Optional endpoints** (require Numberbatch embeddings):
     - `/relatedness` - Semantic similarity between two concepts
     - `/related` - Find semantically similar concepts
   - **Recommendation**: Start with graph-based endpoints only, add embeddings later if needed

3. **Data Volume**:
   - Full dataset or subset (e.g., English only)?
   - Trade-off: completeness vs. resource usage

4. **Update Frequency**:
   - Static dataset or periodic updates?
   - How to handle schema migrations?

## Next Steps

1. **Implement PostgreSQL Service**: Create docker-compose.yml and init scripts
2. **Develop Data Loader**: Python script to download and import data
3. **Build API Service**: Minimal Flask API with core endpoints
4. **Test End-to-End**: Verify complete workflow
5. **Document API**: Create usage guide (02_api_guide.md)
6. **Performance Tuning**: Optimize queries and indexes
