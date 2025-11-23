# ConceptNet 5.7 Local Deployment

A Docker Compose-based deployment of ConceptNet 5.7, providing a local REST API for querying the ConceptNet knowledge graph.

## Overview

This project provides:
- PostgreSQL database with ConceptNet 5.7 assertions (edges) and Numberbatch embeddings
- Data loader service to download and import ConceptNet data
- REST API service for querying concepts and relationships
- Complete graph-based querying with semantic similarity features

## Prerequisites

- Docker (20.10+)
- Docker Compose (2.0+)
- At least 20GB free disk space (for database and downloaded data)
- 8-16GB RAM recommended

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd conceptnet

# Copy environment template
cp .env.example .env

# Edit .env and set a secure password
nano .env  # or use your preferred editor
```

### 2. Start PostgreSQL

```bash
# Start the database
docker-compose up -d postgres

# Wait for it to be healthy (about 10-15 seconds)
docker-compose ps
```

### 3. Load ConceptNet Data

This step downloads ~1.7GB of data and loads it into PostgreSQL. It takes 45-75 minutes depending on your system.

```bash
# Run the data loader (one-time operation)
docker-compose run --rm data-loader

# The loader will:
# 1. Download conceptnet-assertions-5.7.0.csv.gz (~1.5GB)
# 2. Download numberbatch-en-19.08.txt.gz (~150MB)
# 3. Decompress the files
# 4. Load ~34 million edges into PostgreSQL
# 5. Extract ~19 million unique nodes
# 6. Load ~1.5 million English concept embeddings (600-dimensional vectors)
# 7. Create indexes (including HNSW vector index)
```

**Note**: The loader checks if data is already loaded and will prompt before reloading.

### 4. Start the API

```bash
# Start the API service
docker-compose up -d api

# Check that it's running
curl http://localhost:8084/health
```

### 5. Test the API

```bash
# Get API information
curl http://localhost:8084/

# Get database statistics
curl http://localhost:8084/stats

# Query a concept
curl http://localhost:8084/c/en/dog

# Query with filters
curl "http://localhost:8084/query?start=/c/en/dog&rel=/r/IsA&limit=10"

# Test semantic similarity
curl "http://localhost:8084/relatedness?node1=/c/en/dog&node2=/c/en/puppy"

# Find related concepts
curl "http://localhost:8084/related?node=/c/en/dog&limit=10"
```

## API Endpoints

### GET /

Returns API information and available endpoints.

### GET /health

Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### GET /stats

Database statistics.

**Response**:
```json
{
  "edges": 34074917,
  "nodes": 19102359,
  "relations": 34,
  "languages": 304,
  "embeddings": 1500000
}
```

### GET /c/{concept}

Get edges for a specific concept.

**Parameters**:
- `limit` (optional): Number of results (default 50, max 1000)
- `offset` (optional): Pagination offset (default 0)
- `rel` (optional): Filter by relation (e.g., `/r/IsA` or just `IsA`)

**Example**:
```bash
curl "http://localhost:8084/c/en/dog?limit=10&rel=IsA"
```

**Response**:
```json
{
  "concept": "/c/en/dog",
  "edges": [
    {
      "uri": "/a/[id]",
      "rel": "/r/IsA",
      "rel_label": "is a",
      "start": "/c/en/dog",
      "end": "/c/en/mammal",
      "weight": 3.46,
      "dataset": "/d/wiktionary/en",
      "surfaceText": "A dog is a mammal"
    }
  ],
  "count": 10,
  "limit": 10,
  "offset": 0
}
```

### GET /query

Query edges with flexible filters.

**Parameters**:
- `start` (optional): Filter by start node
- `end` (optional): Filter by end node
- `node` (optional): Filter by either start or end node
- `rel` (optional): Filter by relation
- `minWeight` (optional): Minimum edge weight
- `limit` (optional): Number of results (default 50, max 1000)
- `offset` (optional): Pagination offset (default 0)

**Examples**:
```bash
# Find what dogs are
curl "http://localhost:8084/query?start=/c/en/dog&rel=IsA"

# Find things that are animals
curl "http://localhost:8084/query?end=/c/en/animal&rel=IsA&limit=20"

# Find all relationships involving "coffee"
curl "http://localhost:8084/query?node=/c/en/coffee"

# Find strong relationships (weight >= 2.0)
curl "http://localhost:8084/query?node=/c/en/knowledge&minWeight=2.0"
```

### GET /relations

Get all available relations.

**Response**:
```json
{
  "relations": [
    {
      "uri": "/r/IsA",
      "label": "is a",
      "description": "X is a subtype or a specific instance of Y"
    }
  ],
  "count": 34
}
```

### GET /relatedness

Compute semantic similarity between two concepts using Numberbatch embeddings.

**Parameters**:
- `node1` (required): First concept URI (e.g., `/c/en/dog` or just `dog`)
- `node2` (required): Second concept URI (e.g., `/c/en/puppy` or just `puppy`)

**Example**:
```bash
curl "http://localhost:8084/relatedness?node1=/c/en/dog&node2=/c/en/puppy"
```

**Response**:
```json
{
  "node1": "/c/en/dog",
  "node2": "/c/en/puppy",
  "similarity": 0.8542
}
```

The similarity score ranges from 0 to 1, where:
- 1.0 = identical concepts
- 0.8+ = highly related concepts
- 0.5-0.8 = moderately related
- < 0.5 = weakly related

**Use cases**:
- Compare semantic similarity of words
- Find conceptual distance between ideas
- Identify synonyms or related terms

### GET /related

Find semantically related concepts using vector similarity search.

**Parameters**:
- `node` (required): Concept URI (e.g., `/c/en/dog` or just `dog`)
- `limit` (optional): Number of results (default 10, max 100)

**Example**:
```bash
curl "http://localhost:8084/related?node=/c/en/dog&limit=15"
```

**Response**:
```json
{
  "node": "/c/en/dog",
  "related": [
    {
      "concept": "/c/en/puppy",
      "similarity": 0.8542
    },
    {
      "concept": "/c/en/dogs",
      "similarity": 0.8213
    },
    {
      "concept": "/c/en/pet",
      "similarity": 0.7891
    },
    {
      "concept": "/c/en/canine",
      "similarity": 0.7654
    }
  ],
  "count": 15,
  "limit": 15
}
```

Results are ordered by similarity (highest first) and use the HNSW vector index for fast approximate nearest neighbor search.

**Use cases**:
- Find synonyms and related terms
- Expand search queries with related concepts
- Build semantic recommendation systems
- Explore conceptual neighborhoods

## Common ConceptNet Relations

- `/r/RelatedTo` - General relation
- `/r/IsA` - Type/instance relationship
- `/r/PartOf` - Part-whole relationship
- `/r/HasA` - Has property or part
- `/r/UsedFor` - Purpose or function
- `/r/CapableOf` - Ability or capability
- `/r/AtLocation` - Typical location
- `/r/Causes` - Causation
- `/r/Synonym` - Similar meaning
- `/r/Antonym` - Opposite meaning
- `/r/DerivedFrom` - Linguistic derivation

See `/relations` endpoint for complete list.

## URI Format

ConceptNet uses a hierarchical URI format:

- Concepts: `/c/{language}/{term}` (e.g., `/c/en/dog`, `/c/es/perro`)
- Relations: `/r/{relation}` (e.g., `/r/IsA`, `/r/PartOf`)
- Assertions: `/a/{id}` (unique edge identifier)

You can omit the `/c/` or `/r/` prefix in API queries - the API will add them automatically.

## Docker Commands

### View Logs

```bash
# API logs
docker-compose logs -f api

# Database logs
docker-compose logs -f postgres

# Data loader logs (when running)
docker-compose logs data-loader
```

### Stop Services

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v
```

### Restart Services

```bash
# Restart API
docker-compose restart api

# Restart all services
docker-compose restart
```

### Rebuild After Code Changes

```bash
# Rebuild API service
docker-compose build api

# Rebuild and restart
docker-compose up -d --build api
```

## Data Management

### Backup Database

```bash
docker exec conceptnet-db pg_dump -U conceptnet conceptnet5 > backup.sql
```

### Restore Database

```bash
docker exec -i conceptnet-db psql -U conceptnet conceptnet5 < backup.sql
```

### Reload Data

```bash
# Delete existing data
docker-compose down -v

# Start fresh
docker-compose up -d postgres
docker-compose run --rm data-loader
docker-compose up -d api
```

## Performance Tuning

### Database Configuration

For better performance with large datasets, you can customize PostgreSQL settings by creating `services/postgres/postgresql.conf`:

```conf
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 128MB
maintenance_work_mem = 1GB
```

Then mount it in docker-compose.yml:
```yaml
volumes:
  - ./services/postgres/postgresql.conf:/etc/postgresql/postgresql.conf
command: postgres -c config_file=/etc/postgresql/postgresql.conf
```

### API Scaling

Increase API workers in `services/api/start.sh`:
```bash
--workers 8  # Increase from 4
```

## Troubleshooting

### Data loader fails with "out of memory"

Reduce `BATCH_SIZE` in `services/data-loader/config.py`:
```python
BATCH_SIZE = 5000  # Default is 10000
```

### API returns "database connection error"

Check that PostgreSQL is healthy:
```bash
docker-compose ps
docker-compose logs postgres
```

### Slow queries

Check that indexes were created:
```bash
docker exec -it conceptnet-db psql -U conceptnet conceptnet5 \
  -c "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public';"
```

## Project Structure

```
conceptnet/
├── docker-compose.yml          # Docker services configuration
├── .env                        # Environment variables (create from .env.example)
├── .env.example               # Environment template
├── README.md                  # This file
│
├── services/
│   ├── postgres/
│   │   ├── Dockerfile          # Custom PostgreSQL with pgvector
│   │   └── init-scripts/
│   │       ├── 01-create-schema.sql    # Database schema
│   │       ├── 02-create-indexes.sql   # Database indexes
│   │       └── 03-create-embeddings.sql # Embeddings table + vector index
│   │
│   ├── data-loader/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── config.py           # Loader configuration
│   │   ├── download_data.py    # Download ConceptNet data + embeddings
│   │   └── loader.py           # Load data into PostgreSQL
│   │
│   └── api/
│       ├── Dockerfile
│       ├── requirements.txt
│       ├── config.py           # API configuration
│       ├── app.py              # Flask API application
│       └── start.sh            # Startup script
│
├── data/
│   ├── raw/                    # Downloaded CSV files + embeddings
│   └── processed/              # Temporary processing files
│
└── documentation/
    ├── 00_research.md          # Research notes
    └── 01_design.md            # Design document
```

## Development

### Adding New Endpoints

1. Edit `services/api/app.py`
2. Add your new endpoint function
3. Rebuild and restart:
   ```bash
   docker-compose up -d --build api
   ```

### Database Schema Changes

1. Edit SQL files in `services/postgres/init-scripts/`
2. Recreate database:
   ```bash
   docker-compose down -v
   docker-compose up -d postgres
   ```

## Completed Features

Phase 1:
- [x] PostgreSQL database with ConceptNet 5.7 assertions
- [x] Data loader for edges and nodes
- [x] REST API for graph-based queries
- [x] Comprehensive query endpoints

Phase 2:
- [x] Numberbatch embeddings integration
- [x] pgvector extension with HNSW indexing
- [x] `/relatedness` endpoint for semantic similarity
- [x] `/related` endpoint for finding similar concepts

## Future Enhancements (Phase 3+)

- [ ] Redis caching layer for frequently accessed queries
- [ ] GraphQL API alternative interface
- [ ] Full-text search across concept surface text
- [ ] Multi-language embeddings support (beyond English)
- [ ] Batch query endpoints for efficiency
- [ ] WebSocket support for real-time updates

## License

ConceptNet 5 is available under the Creative Commons Attribution-ShareAlike license (CC BY SA 4.0).

This deployment code is provided as-is for educational and research purposes.

## References

- [ConceptNet Official Site](https://conceptnet.io/)
- [ConceptNet GitHub](https://github.com/commonsense/conceptnet5)
- [ConceptNet API Documentation](https://github.com/commonsense/conceptnet5/wiki/API)
- [Design Document](documentation/01_design.md)

## Support

For issues with this deployment, please check:
1. Docker and Docker Compose are up to date
2. Sufficient disk space (20GB+)
3. PostgreSQL is healthy (`docker-compose ps`)
4. Logs for error messages (`docker-compose logs`)

For ConceptNet data questions, see the [official documentation](https://github.com/commonsense/conceptnet5/wiki).
