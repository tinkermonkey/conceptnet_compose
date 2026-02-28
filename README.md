# ConceptNet 5.7 Local Deployment

## Why this exists

The official ConceptNet API ([api.conceptnet.io](https://api.conceptnet.io/)) is not available for self-hosting — the upstream [`conceptnet-deployment`](https://github.com/commonsense/conceptnet-deployment) repo targets AWS AMIs built with Packer/Puppet, and the [published Docker images](https://github.com/commonsense/conceptnet5/wiki/Docker) track ConceptNet 5.5.x, which is several major versions out of date. This project provides a Docker Compose stack that runs the same official `conceptnet_web` API ([5.7.0 from PyPI](https://pypi.org/project/ConceptNet/) + [GitHub source](https://github.com/commonsense/conceptnet5)) against a local PostgreSQL database loaded from the ConceptNet 5.7 assertions CSV.

## How it works

Three Docker services coordinate via an internal bridge network:

**postgres** — PostgreSQL with the `pgvector` extension, initialized with the official ConceptNet schema (edges, nodes, relations, sources, edges_gin, edge_features, ranked_features) plus an embeddings table with an HNSW index. Data persists in a named volume (~15GB with indexes).

**data-loader** — One-time job (Docker `tools` profile, not started by default). Downloads the ConceptNet 5.7 assertions CSV (~1.5GB compressed, ~9.5GB uncompressed) and loads all 34M+ edges into PostgreSQL at ~1,400 rows/sec. Takes 6–7 hours on typical hardware. A separate script (`load_embeddings.py`) loads Numberbatch vectors into the embeddings table (~4 minutes for 516K English concepts). Neither step needs to be repeated after the volume exists.

**api** — Runs `conceptnet_web.api` (cloned from the [official upstream repo](https://github.com/commonsense/conceptnet5) at build time) via Flask on port 8084. Database credentials are injected via environment variables. The `/relatedness` and `/related` endpoints additionally require `data/vectors/mini.h5` (an HDF5 file generated once from the downloaded Numberbatch text file — see below).

## Setup

### Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- 25GB free disk space (15GB database volume + 10GB raw data)
- 8GB+ RAM (PostgreSQL needs 4–6GB with the full dataset loaded)

### 1. Configure environment

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env
```

### 2. Start the database

```bash
docker-compose up -d postgres
docker-compose ps  # wait until postgres is healthy
```

### 3. Load data (one-time, ~7 hours)

```bash
# Load edges, nodes, and all schema tables
docker-compose run --rm data-loader python /app/loader-improved.py --yes

# Load Numberbatch embeddings into PostgreSQL (separate step, ~4 min)
docker-compose run --rm data-loader python3 /app/load_embeddings.py --yes
```

If the host is memory-constrained during embedding loading, add `--throttle=1.0`.

### 4. Generate vector file for similarity endpoints (optional)

The `/relatedness` and `/related` endpoints require `data/vectors/mini.h5`. Generate it once from the already-downloaded Numberbatch text file:

```bash
pip install pandas tables numpy
python generate_vectors.py
```

The file is mounted into the API container at `/app/data/vectors/mini.h5`. Restart the API after generating it.

### 5. Start the API

```bash
docker-compose up -d api
curl http://localhost:8084/
```

## API endpoints

| Endpoint | Description |
|---|---|
| `GET /` | API info |
| `GET /c/{lang}/{term}` | Edges for a concept (e.g. `/c/en/dog`) |
| `GET /query` | Filter edges by `start`, `end`, `node`, `rel`, `minWeight` |
| `GET /uri` | Standardize a URI |
| `GET /search` | Search concepts |
| `GET /relatedness` | Cosine similarity between two concepts (requires HDF5 file) |
| `GET /related` | Nearest neighbors by vector similarity (requires HDF5 file) |

Parameters accept full URIs (`/c/en/dog`, `/r/IsA`) or bare terms (`dog`, `IsA`) — the API adds prefixes automatically.

## Triage

**API container exits immediately**

```bash
docker-compose logs api --tail 50
```
Most common cause: database not yet healthy when the API started. Restart: `docker-compose restart api`.

**Queries return no results**

The database may not be fully loaded. Check row counts:

```bash
docker exec conceptnet-db psql -U conceptnet conceptnet5 -c "
SELECT
  (SELECT COUNT(*) FROM edges) as edges,
  (SELECT COUNT(*) FROM nodes) as nodes,
  (SELECT COUNT(*) FROM relations) as relations,
  (SELECT COUNT(*) FROM embeddings) as embeddings;"
```

Expected when fully loaded: ~34M edges, ~30M nodes, 50 relations, 516K embeddings.

**`/relatedness` or `/related` returns an error**

These endpoints require `data/vectors/mini.h5`. If the file does not exist, run `generate_vectors.py` as described above, then `docker-compose restart api`.

**Data loader OOM**

Reduce `BATCH_SIZE` in `services/data-loader/config.py` (default: 10000). For embeddings, use `--throttle=1.0`.

**Slow queries**

Verify indexes were created:

```bash
docker exec conceptnet-db psql -U conceptnet conceptnet5 \
  -c "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public';"
```

The most important indexes are on `edges` (start_uri, end_uri, relation_id) and the HNSW index on `embeddings`.

**Rebuild API after code changes**

```bash
docker-compose up -d --build api
```

## Data management

```bash
# Backup
docker exec conceptnet-db pg_dump -U conceptnet conceptnet5 > backup.sql

# Restore
docker exec -i conceptnet-db psql -U conceptnet conceptnet5 < backup.sql

# Full reset (deletes all loaded data)
docker-compose down -v
```

## References

- [ConceptNet 5 data downloads](https://conceptnet.io/)
- [conceptnet5 GitHub](https://github.com/commonsense/conceptnet5)
- [Numberbatch embeddings](https://github.com/commonsense/conceptnet-numberbatch)
