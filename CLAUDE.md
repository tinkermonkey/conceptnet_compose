# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Docker Compose deployment of ConceptNet 5.7 — a local REST API for querying the ConceptNet knowledge graph. It consists of three services:

- **postgres**: Custom PostgreSQL image with pgvector extension, seeded with the official ConceptNet schema
- **data-loader**: One-time job that downloads and loads ~34M edges + Numberbatch embeddings into PostgreSQL
- **api**: Flask/Gunicorn REST API serving ConceptNet graph queries and semantic similarity

## Common Commands

### Service management
```bash
# Start database
docker-compose up -d postgres

# Start API (after DB is healthy)
docker-compose up -d api

# Rebuild and restart API after code changes
docker-compose up -d --build api

# View live logs
docker-compose logs -f api
docker-compose logs -f postgres

# Check service health
docker-compose ps
curl http://localhost:8084/health
```

### Data loading (one-time, takes 6-7 hours)
```bash
# Load full dataset (edges + nodes + embeddings)
docker-compose run --rm data-loader python /app/loader-improved.py --yes

# Load embeddings only (with throttling for resource-constrained systems)
docker-compose run --rm data-loader python3 /app/load_embeddings.py --yes --throttle=1.0

# Test mode (limited rows, for validation)
docker-compose run --rm data-loader python /app/loader-improved.py --test
```

### Database access
```bash
# Connect to database
docker exec -it conceptnet-db psql -U conceptnet conceptnet5

# Check row counts
docker exec conceptnet-db psql -U conceptnet conceptnet5 -c "
SELECT
  (SELECT COUNT(*) FROM edges) as edges,
  (SELECT COUNT(*) FROM nodes) as nodes,
  (SELECT COUNT(*) FROM relations) as relations,
  (SELECT COUNT(*) FROM embeddings) as embeddings;"

# Backup
docker exec conceptnet-db pg_dump -U conceptnet conceptnet5 > backup.sql
```

### Environment setup
```bash
cp .env.example .env
# Edit .env to set POSTGRES_PASSWORD
```

## Architecture

### Docker services (docker-compose.yml)
- `data-loader` is in the `tools` profile — it only runs when explicitly invoked with `docker-compose run`
- All services communicate over the internal `conceptnet` Docker bridge network
- PostgreSQL data persists in the `postgres-data` named volume (~15GB)
- Raw CSV data is mounted from `./data/raw` into the loader container

### API implementation
The API service (`Dockerfile.official`) clones `conceptnet_web` from the official upstream ConceptNet5 GitHub repo and starts it via `start-official-fixed.sh`. That script sets the required DB env vars and runs `conceptnet_web.api` directly with `python`.

For the data-loader, `loader-improved.py` is the production loader (populates all official schema tables). `load_embeddings.py` is a separate standalone script for loading Numberbatch vectors and is run independently when needed.

### Database schema (two layers)
- **Official ConceptNet schema** (`01-create-schema-official.sql`): `edges`, `nodes`, `sources`, `relations`, `edges_gin`, `edge_features`, `ranked_features` materialized view — uses integer IDs with normalized relations/nodes tables
- **Embeddings extension** (`02-create-embeddings.sql`): `embeddings` table with 300-dimensional pgvector columns and an HNSW index for fast cosine similarity search

### API configuration
Config is read from environment variables (see `services/api/config.py`):
- `CONCEPTNET_DB_HOSTNAME`, `CONCEPTNET_DB_PORT`, `CONCEPTNET_DB_NAME`, `CONCEPTNET_DB_USER`, `CONCEPTNET_DB_PASSWORD`
- API runs on port `8084` (configurable via `API_PORT`)
- Connection pool: min=2, max=10 threads

### ConceptNet URI format
- Concepts: `/c/{language}/{term}` — e.g., `/c/en/dog`
- Relations: `/r/{relation}` — e.g., `/r/IsA`
- The API auto-prefixes bare terms (e.g., `dog` → `/c/en/dog`, `IsA` → `/r/IsA`)

### Semantic similarity
The `/relatedness` and `/related` endpoints use pgvector's `<=>` operator (cosine distance) against the `embeddings` table. These only work for English concepts that appear in the Numberbatch dataset (~516K concepts). The official ConceptNet API's vector endpoints require HDF5 files which are not set up here.

### Performance notes
- PostgreSQL needs 4-6GB RAM with full dataset; 8GB+ total system RAM recommended
- Reduce `BATCH_SIZE` in `services/data-loader/config.py` (default: 10000) if OOM during loading
- Increase gunicorn workers in `services/api/start.sh` (default: 4) for higher throughput
