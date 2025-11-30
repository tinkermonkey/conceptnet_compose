#!/usr/bin/env python3
"""
Improved ConceptNet Data Loader
- Populates all required tables for official API compatibility
- Includes progress reporting with ETA
- Supports test mode with limited rows
- Properly handles edges_gin and edge_features tables
"""
import os
import sys
import csv
import json
import time
import psycopg2
from pathlib import Path
from collections import OrderedDict
from datetime import timedelta

from config import DB_CONFIG
from download_data import download_assertions, download_embeddings

RAW_DATA_DIR = Path("/data/raw")
BATCH_SIZE = 10000


def get_connection():
    """Get a new database connection"""
    return psycopg2.connect(
        host=DB_CONFIG['host'],
        port=DB_CONFIG['port'],
        database=DB_CONFIG['database'],
        user=DB_CONFIG['user'],
        password=DB_CONFIG['password']
    )


def uri_prefixes(uri, min_pieces=2):
    """
    Get URIs that are prefixes of a given URI
    Simplified version compatible with ConceptNet official API
    """
    if uri.startswith('http://') or uri.startswith('https://'):
        return [uri]

    pieces = uri.split('/')
    prefixes = []

    for i in range(min_pieces, len(pieces) + 1):
        prefix = '/'.join(pieces[:i])
        if prefix:
            prefixes.append(prefix)

    return prefixes


def gin_indexable_edge(edge_data):
    """
    Convert edge data to GIN-indexable format with URI prefixes
    This matches the format expected by conceptnet5.db.query
    """
    gin_edge = {}

    # Add URI prefixes for start, end, rel, dataset
    gin_edge['start'] = uri_prefixes(edge_data['start'])
    gin_edge['end'] = uri_prefixes(edge_data['end'])
    gin_edge['rel'] = uri_prefixes(edge_data['rel'])

    if 'dataset' in edge_data:
        gin_edge['dataset'] = uri_prefixes(edge_data['dataset'])

    # Flatten sources into a list of URI prefixes
    if 'sources' in edge_data:
        flat_sources = set()
        for source in edge_data['sources']:
            for value in source.values():
                flat_sources.update(uri_prefixes(value, min_pieces=3))
        gin_edge['sources'] = sorted(flat_sources)

    return gin_edge


def is_symmetric_relation(rel):
    """Check if a relation is symmetric"""
    SYMMETRIC_RELATIONS = {
        '/r/Antonym', '/r/DistinctFrom', '/r/EtymologicallyRelatedTo',
        '/r/LocatedNear', '/r/RelatedTo', '/r/SimilarTo', '/r/Synonym'
    }
    return rel in SYMMETRIC_RELATIONS


class ProgressTracker:
    """Track loading progress with ETA"""

    def __init__(self, total_rows, description="Loading"):
        self.total_rows = total_rows
        self.description = description
        self.start_time = time.time()
        self.last_update = self.start_time
        self.rows_processed = 0

    def update(self, rows_processed):
        """Update progress and print status"""
        self.rows_processed = rows_processed
        current_time = time.time()

        # Update every 2 seconds
        if current_time - self.last_update < 2:
            return

        self.last_update = current_time
        elapsed = current_time - self.start_time

        if rows_processed > 0:
            rate = rows_processed / elapsed
            remaining = self.total_rows - rows_processed
            eta_seconds = remaining / rate if rate > 0 else 0
            eta = timedelta(seconds=int(eta_seconds))

            percent = (rows_processed / self.total_rows) * 100

            print(f"{self.description}: {rows_processed:,}/{self.total_rows:,} "
                  f"({percent:.1f}%) | {rate:.0f} rows/sec | ETA: {eta}",
                  end='\r', flush=True)

    def finish(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        rate = self.rows_processed / elapsed if elapsed > 0 else 0
        print(f"\n✓ {self.description} complete: {self.rows_processed:,} rows "
              f"in {timedelta(seconds=int(elapsed))} ({rate:.0f} rows/sec)")


def count_csv_lines(filepath):
    """Count lines in a CSV file"""
    filepath = Path(filepath) if isinstance(filepath, str) else filepath
    print(f"Counting rows in {filepath.name}...")
    with open(filepath, 'r', encoding='utf-8') as f:
        count = sum(1 for _ in f)
    print(f"  Total rows: {count:,}")
    return count


def check_if_data_loaded():
    """Check if data is already loaded"""
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM edges")
            count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    except:
        return False


def load_assertions(test_mode=False, test_rows=1000):
    """
    Load ConceptNet assertions into database

    Args:
        test_mode: If True, only load test_rows for testing
        test_rows: Number of rows to load in test mode
    """
    print("\n" + "="*70)
    if test_mode:
        print(f"LOADING CONCEPTNET ASSERTIONS (TEST MODE - {test_rows:,} rows)")
    else:
        print("LOADING CONCEPTNET ASSERTIONS (FULL DATASET)")
    print("="*70)

    # Download assertions file
    assertions_file = download_assertions()
    print(f"Assertions file: {assertions_file}")

    # Count total rows if not in test mode
    if not test_mode:
        total_rows = count_csv_lines(assertions_file)
    else:
        total_rows = test_rows

    # Get database connection
    conn = get_connection()
    cursor = conn.cursor()

    # Track unique items with OrderedDict (maintains insertion order like OrderedSet)
    nodes = OrderedDict()
    relations = OrderedDict()
    sources = OrderedDict()

    # Batch accumulators
    edges_batch = []
    edges_gin_batch = []
    edge_features_batch = []

    # Counters
    next_node_id = 1
    next_relation_id = 1
    next_source_id = 1
    next_edge_id = 1
    rows_processed = 0

    # Progress tracker
    progress = ProgressTracker(total_rows, "Assertions")

    print("\nReading and processing assertions...")

    try:
        with open(assertions_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')

            for row in reader:
                if len(row) < 4:
                    continue

                # Parse row
                edge_uri = row[0]
                relation_uri = row[1]
                start_uri = row[2]
                end_uri = row[3]

                # Parse metadata JSON
                metadata = {}
                weight = 1.0
                if len(row) > 4 and row[4]:
                    try:
                        metadata = json.loads(row[4])
                        weight = metadata.get('weight', 1.0)
                    except json.JSONDecodeError:
                        pass

                # Build full edge data structure for API
                edge_data = {
                    'uri': edge_uri,
                    'rel': relation_uri,
                    'start': start_uri,
                    'end': end_uri,
                    'weight': weight
                }

                # Add optional metadata fields
                if 'dataset' in metadata:
                    edge_data['dataset'] = metadata['dataset']
                if 'license' in metadata:
                    edge_data['license'] = metadata['license']
                if 'sources' in metadata:
                    edge_data['sources'] = metadata['sources']
                if 'surfaceText' in metadata:
                    edge_data['surfaceText'] = metadata['surfaceText']

                # Add surfaceStart and surfaceEnd (required by transform_for_linked_data)
                # These are often the same as start/end if not specified
                edge_data['surfaceStart'] = metadata.get('surfaceStart')
                edge_data['surfaceEnd'] = metadata.get('surfaceEnd')

                # Get or create node IDs
                if start_uri not in nodes:
                    nodes[start_uri] = next_node_id
                    next_node_id += 1

                if end_uri not in nodes:
                    nodes[end_uri] = next_node_id
                    next_node_id += 1

                # Get or create relation ID
                if relation_uri not in relations:
                    is_symmetric = is_symmetric_relation(relation_uri)
                    relations[relation_uri] = (next_relation_id, is_symmetric)
                    next_relation_id += 1

                # Track sources
                if 'sources' in metadata:
                    for source in metadata['sources']:
                        for source_val in source.values():
                            if source_val not in sources:
                                sources[source_val] = next_source_id
                                next_source_id += 1

                # Get IDs
                start_id = nodes[start_uri]
                end_id = nodes[end_uri]
                relation_id, is_symmetric = relations[relation_uri]

                # Prepare edge data for database
                edge_json = json.dumps(edge_data, ensure_ascii=False, sort_keys=True)

                edges_batch.append((
                    next_edge_id,
                    edge_uri,
                    relation_id,
                    start_id,
                    end_id,
                    weight,
                    edge_json
                ))

                # Prepare edges_gin data
                gin_data = gin_indexable_edge(edge_data)
                gin_json = json.dumps(gin_data, ensure_ascii=False, sort_keys=True)
                edges_gin_batch.append((next_edge_id, weight, gin_json))

                # Prepare edge_features data
                # Get node prefixes for feature matching
                start_prefixes = uri_prefixes(start_uri, min_pieces=3)
                end_prefixes = uri_prefixes(end_uri, min_pieces=3)

                # Add node prefix IDs
                for prefix in start_prefixes:
                    if prefix not in nodes:
                        nodes[prefix] = next_node_id
                        next_node_id += 1

                for prefix in end_prefixes:
                    if prefix not in nodes:
                        nodes[prefix] = next_node_id
                        next_node_id += 1

                # Create features based on relation directionality
                if is_symmetric:
                    # Symmetric: direction = 0
                    for prefix in start_prefixes:
                        edge_features_batch.append((
                            relation_id, 0, nodes[prefix], next_edge_id
                        ))
                    for prefix in end_prefixes:
                        edge_features_batch.append((
                            relation_id, 0, nodes[prefix], next_edge_id
                        ))
                else:
                    # Directed: direction = 1 (forward), -1 (backward)
                    for prefix in start_prefixes:
                        edge_features_batch.append((
                            relation_id, 1, nodes[prefix], next_edge_id
                        ))
                    for prefix in end_prefixes:
                        edge_features_batch.append((
                            relation_id, -1, nodes[prefix], next_edge_id
                        ))

                next_edge_id += 1
                rows_processed += 1

                # Batch insert
                if len(edges_batch) >= BATCH_SIZE:
                    insert_batches(conn, cursor, nodes, relations, sources,
                                 edges_batch, edges_gin_batch, edge_features_batch)
                    edges_batch = []
                    edges_gin_batch = []
                    edge_features_batch = []
                    progress.update(rows_processed)

                # Stop if test mode and reached limit
                if test_mode and rows_processed >= test_rows:
                    break

        # Insert remaining batches
        if edges_batch:
            insert_batches(conn, cursor, nodes, relations, sources,
                         edges_batch, edges_gin_batch, edge_features_batch)
            progress.update(rows_processed)

        progress.finish()

        # Print statistics
        print("\nDatabase statistics:")
        print(f"  Nodes: {len(nodes):,}")
        print(f"  Relations: {len(relations):,}")
        print(f"  Sources: {len(sources):,}")
        print(f"  Edges: {rows_processed:,}")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error loading assertions: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        cursor.close()
        conn.close()


def insert_batches(conn, cursor, nodes, relations, sources,
                  edges_batch, edges_gin_batch, edge_features_batch):
    """Insert accumulated batches into database"""

    # Insert nodes (only new ones since last batch)
    # This is inefficient but works for now
    cursor.execute("SELECT MAX(id) FROM nodes")
    result = cursor.fetchone()
    last_node_id = result[0] if result[0] else 0

    new_nodes = [(nid, uri) for uri, nid in nodes.items() if nid > last_node_id]
    if new_nodes:
        cursor.executemany(
            "INSERT INTO nodes (id, uri) VALUES (%s, %s) ON CONFLICT (uri) DO NOTHING",
            new_nodes
        )

    # Insert relations
    cursor.execute("SELECT MAX(id) FROM relations")
    result = cursor.fetchone()
    last_rel_id = result[0] if result[0] else 0

    new_relations = [
        (rid, uri, directed)
        for uri, (rid, directed) in relations.items()
        if rid > last_rel_id
    ]
    if new_relations:
        cursor.executemany(
            "INSERT INTO relations (id, uri, directed) VALUES (%s, %s, %s) ON CONFLICT (uri) DO NOTHING",
            new_relations
        )

    # Insert sources
    cursor.execute("SELECT MAX(id) FROM sources")
    result = cursor.fetchone()
    last_source_id = result[0] if result[0] else 0

    new_sources = [(sid, uri) for uri, sid in sources.items() if sid > last_source_id]
    if new_sources:
        cursor.executemany(
            "INSERT INTO sources (id, uri) VALUES (%s, %s) ON CONFLICT (uri) DO NOTHING",
            new_sources
        )

    # Insert edges
    if edges_batch:
        cursor.executemany(
            "INSERT INTO edges (id, uri, relation_id, start_id, end_id, weight, data) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            edges_batch
        )

    # Insert edges_gin
    if edges_gin_batch:
        cursor.executemany(
            "INSERT INTO edges_gin (edge_id, weight, data) VALUES (%s, %s, %s)",
            edges_gin_batch
        )

    # Insert edge_features
    if edge_features_batch:
        cursor.executemany(
            "INSERT INTO edge_features (rel_id, direction, node_id, edge_id) "
            "VALUES (%s, %s, %s, %s)",
            edge_features_batch
        )

    conn.commit()


def create_ranked_features_view(conn):
    """Create the ranked_features materialized view"""
    print("\nCreating ranked_features materialized view...")
    cursor = conn.cursor()
    try:
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS ranked_features")
        cursor.execute("""
            CREATE MATERIALIZED VIEW ranked_features AS (
                SELECT ef.rel_id, ef.direction, ef.node_id, ef.edge_id, e.weight,
                    row_number() OVER (
                        PARTITION BY (ef.node_id, ef.rel_id, ef.direction)
                        ORDER BY e.weight DESC, e.id
                    ) AS rank
                FROM edge_features ef, edges e WHERE e.id=ef.edge_id
            ) WITH DATA
        """)
        cursor.execute("CREATE INDEX rf_node ON ranked_features (node_id)")
        conn.commit()
        print("✓ Ranked features view created")
    except Exception as e:
        conn.rollback()
        print(f"✗ Error creating ranked features view: {e}")
        raise
    finally:
        cursor.close()


def load_embeddings(test_mode=False):
    """Load Numberbatch embeddings"""
    print("\n" + "="*70)
    print("LOADING NUMBERBATCH EMBEDDINGS")
    print("="*70)

    embeddings_file = download_embeddings()
    print(f"Embeddings file: {embeddings_file}")

    conn = get_connection()
    cursor = conn.cursor()

    try:
        # Check if embeddings table exists
        cursor.execute(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'embeddings')"
        )
        if not cursor.fetchone()[0]:
            print("✗ Embeddings table does not exist. Skipping.")
            return

        cursor.execute("SELECT COUNT(*) FROM embeddings")
        existing_count = cursor.fetchone()[0]

        if existing_count > 0 and not test_mode:
            print(f"Embeddings already loaded ({existing_count:,} vectors)")
            return

        # Count lines
        total_lines = count_csv_lines(embeddings_file) - 1  # Subtract header

        batch = []
        batch_size = 5000
        total_loaded = 0

        progress = ProgressTracker(total_lines, "Embeddings")

        with open(embeddings_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num == 1:  # Skip header
                    continue

                parts = line.strip().split(' ')
                if len(parts) < 301:
                    continue

                concept = parts[0]
                if not concept.startswith('/c/'):
                    concept = f'/c/en/{concept}'

                vector = [float(x) for x in parts[1:301]]
                batch.append((concept, vector))

                if len(batch) >= batch_size:
                    cursor.executemany(
                        "INSERT INTO embeddings (concept, vector) "
                        "VALUES (%s, %s::vector) ON CONFLICT (concept) DO NOTHING",
                        batch
                    )
                    conn.commit()
                    total_loaded += len(batch)
                    batch = []
                    progress.update(line_num - 1)

                if test_mode and total_loaded >= 10000:
                    break

            # Insert remaining
            if batch:
                cursor.executemany(
                    "INSERT INTO embeddings (concept, vector) "
                    "VALUES (%s, %s::vector) ON CONFLICT (concept) DO NOTHING",
                    batch
                )
                conn.commit()
                total_loaded += len(batch)

        progress.finish()

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error loading embeddings: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def main():
    """Main loading process"""
    print("="*70)
    print("ConceptNet Improved Data Loader")
    print("="*70)

    # Parse arguments
    test_mode = '--test' in sys.argv
    non_interactive = '--yes' in sys.argv or '-y' in sys.argv
    test_rows = 1000

    if test_mode:
        print("\n⚠️  TEST MODE: Loading only", test_rows, "rows for validation")
        if not non_interactive:
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                sys.exit(0)

    # Check if data already loaded
    if check_if_data_loaded() and not test_mode:
        print("\n⚠️  Data already exists in database")
        if not non_interactive:
            response = input("Do you want to reload? This will ADD to existing data. (y/N): ")
            if response.lower() != 'y':
                sys.exit(0)

    try:
        # Load assertions
        load_assertions(test_mode=test_mode, test_rows=test_rows)

        # Create materialized view
        conn = get_connection()
        create_ranked_features_view(conn)
        conn.close()

        # Load embeddings
        if not test_mode:
            load_embeddings(test_mode=test_mode)

        print("\n" + "="*70)
        print("✓ DATA LOADING COMPLETE!")
        print("="*70)

    except Exception as e:
        print(f"\n✗ Data loading failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
