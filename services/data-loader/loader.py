"""
Load ConceptNet assertions into PostgreSQL database
"""
import json
import sys
import psycopg2
from psycopg2.extras import execute_batch
from datetime import datetime
from tqdm import tqdm
from config import DB_CONFIG, RAW_DATA_DIR, BATCH_SIZE
from download_data import download_assertions, download_embeddings
import os


def connect_db():
    """Connect to PostgreSQL database"""
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        print(f"Connected to {DB_CONFIG['database']} at {DB_CONFIG['host']}")
        return conn
    except Exception as e:
        print(f"Error connecting to database: {e}")
        sys.exit(1)


def check_if_loaded(conn):
    """Check if data is already loaded"""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM edges")
    count = cursor.fetchone()[0]
    cursor.close()
    return count > 0


def log_operation(conn, operation, status, rows_affected=None, error_message=None):
    """Log data loading operation"""
    cursor = conn.cursor()
    if status == 'started':
        cursor.execute(
            """
            INSERT INTO data_loading_log (operation, status, rows_affected)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (operation, status, rows_affected)
        )
        log_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        return log_id
    else:
        cursor.execute(
            """
            UPDATE data_loading_log
            SET status = %s, rows_affected = %s, completed_at = %s, error_message = %s
            WHERE id = %s
            """,
            (status, rows_affected, datetime.now(), error_message, operation)
        )
        conn.commit()
        cursor.close()


def parse_assertion_line(line):
    """
    Parse a line from the ConceptNet assertions CSV
    Format: URI, relation, start, end, metadata (JSON)
    """
    parts = line.strip().split('\t')
    if len(parts) < 4:
        return None

    uri = parts[0]
    relation = parts[1]
    start = parts[2]
    end = parts[3]
    metadata = {}

    # Parse metadata JSON if present
    if len(parts) >= 5:
        try:
            metadata = json.loads(parts[4])
        except json.JSONDecodeError:
            pass

    # Extract fields from metadata
    weight = metadata.get('weight', 1.0)
    sources = json.dumps(metadata.get('sources', []))
    dataset = metadata.get('dataset', '')
    surface_text = metadata.get('surfaceText', '')
    license_info = metadata.get('license', '')

    return {
        'uri': uri,
        'relation': relation,
        'start_node': start,
        'end_node': end,
        'weight': weight,
        'sources': sources,
        'dataset': dataset,
        'surface_text': surface_text,
        'license': license_info,
        'metadata': json.dumps(metadata)
    }


def count_file_lines(file_path):
    """Count number of lines in file for progress bar"""
    print("Counting lines in file...")
    count = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        for _ in f:
            count += 1
    return count


def load_assertions(conn, assertions_file):
    """
    Load assertions from CSV file into database
    """
    log_id = log_operation(conn, 'load_assertions', 'started')

    cursor = conn.cursor()
    batch = []
    total_loaded = 0
    total_errors = 0

    try:
        # Count total lines for progress bar
        total_lines = count_file_lines(assertions_file)
        print(f"Total lines to process: {total_lines:,}")

        with open(assertions_file, 'r', encoding='utf-8') as f:
            with tqdm(total=total_lines, desc="Loading assertions", unit=" rows") as pbar:
                for line_num, line in enumerate(f, 1):
                    try:
                        parsed = parse_assertion_line(line)
                        if parsed:
                            batch.append((
                                parsed['uri'],
                                parsed['relation'],
                                parsed['start_node'],
                                parsed['end_node'],
                                parsed['weight'],
                                parsed['sources'],
                                parsed['dataset'],
                                parsed['surface_text'],
                                parsed['license'],
                                parsed['metadata']
                            ))

                            if len(batch) >= BATCH_SIZE:
                                try:
                                    execute_batch(
                                        cursor,
                                        """
                                        INSERT INTO edges (uri, relation, start_node, end_node, weight,
                                                          sources, dataset, surface_text, license, metadata)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                        ON CONFLICT (uri) DO NOTHING
                                        """,
                                        batch
                                    )
                                    conn.commit()
                                    total_loaded += len(batch)
                                except Exception as batch_error:
                                    conn.rollback()
                                    total_errors += len(batch)
                                    if total_errors <= 100:
                                        print(f"\nBatch error at line ~{line_num}: {batch_error}")
                                batch = []

                    except Exception as e:
                        total_errors += 1
                        if total_errors <= 10:  # Only print first 10 errors
                            print(f"\nError on line {line_num}: {e}")

                    pbar.update(1)

                # Insert remaining batch
                if batch:
                    try:
                        execute_batch(
                            cursor,
                            """
                            INSERT INTO edges (uri, relation, start_node, end_node, weight,
                                              sources, dataset, surface_text, license, metadata)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (uri) DO NOTHING
                            """,
                            batch
                        )
                        conn.commit()
                        total_loaded += len(batch)
                    except Exception as batch_error:
                        conn.rollback()
                        total_errors += len(batch)
                        print(f"\nFinal batch error: {batch_error}")

        cursor.close()
        print(f"\nAssertions loaded: {total_loaded:,}")
        print(f"Errors encountered: {total_errors:,}")

        log_operation(conn, log_id, 'completed', total_loaded)
        return total_loaded

    except Exception as e:
        print(f"Error loading assertions: {e}")
        log_operation(conn, log_id, 'failed', total_loaded, str(e))
        raise


def extract_nodes(conn):
    """
    Extract unique nodes from edges table using batched approach with progress
    """
    print("\nExtracting nodes from edges...")
    log_id = log_operation(conn, 'extract_nodes', 'started')

    cursor = conn.cursor()
    total_inserted = 0

    try:
        # Step 1: Create temporary table with distinct node URIs
        print("Finding distinct node URIs...")
        cursor.execute("""
            CREATE TEMP TABLE temp_distinct_nodes AS
            SELECT DISTINCT start_node as uri FROM edges WHERE start_node LIKE '/c/%'
            UNION
            SELECT DISTINCT end_node as uri FROM edges WHERE end_node LIKE '/c/%';
        """)
        conn.commit()

        # Get count for progress bar
        cursor.execute("SELECT COUNT(*) FROM temp_distinct_nodes")
        total_distinct = cursor.fetchone()[0]
        print(f"Found {total_distinct:,} distinct nodes")

        # Step 2: Process in batches with progress bar
        print("Processing and inserting nodes in batches...")
        batch_size = 50000
        offset = 0

        with tqdm(total=total_distinct, desc="Inserting nodes", unit=" nodes") as pbar:
            while offset < total_distinct:
                # Process batch
                cursor.execute("""
                    INSERT INTO nodes (uri, concept, language)
                    SELECT
                        uri,
                        regexp_replace(uri, '^/c/([^/]+)/(.+)$', '\\2'),
                        regexp_replace(uri, '^/c/([^/]+)/.+$', '\\1')
                    FROM temp_distinct_nodes
                    ORDER BY uri
                    LIMIT %s OFFSET %s
                    ON CONFLICT (uri) DO NOTHING
                """, (batch_size, offset))

                rows_inserted = cursor.rowcount
                conn.commit()
                total_inserted += rows_inserted

                offset += batch_size
                pbar.update(min(batch_size, total_distinct - offset + batch_size))

        # Clean up temp table
        cursor.execute("DROP TABLE temp_distinct_nodes")
        conn.commit()

        cursor.close()

        log_operation(conn, log_id, 'completed', total_inserted)
        print(f"\nTotal unique nodes inserted: {total_inserted:,}")

        return total_inserted

    except Exception as e:
        print(f"Error extracting nodes: {e}")
        log_operation(conn, log_id, 'failed', 0, str(e))
        # Clean up temp table if it exists
        try:
            cursor.execute("DROP TABLE IF EXISTS temp_distinct_nodes")
            conn.commit()
        except:
            pass
        raise


def load_embeddings(conn, embeddings_file):
    """
    Load Numberbatch embeddings into PostgreSQL database
    Format: word 0.123 -0.456 0.789 ... (300 floats)
    First line is header with format: num_words dimensions
    """
    print("\nLoading embeddings...")
    log_id = log_operation(conn, 'load_embeddings', 'started')

    cursor = conn.cursor()
    batch = []
    total_loaded = 0
    total_errors = 0
    batch_size = 5000  # Smaller batches for vector data

    try:
        # Count total lines for progress bar
        total_lines = count_file_lines(embeddings_file)
        print(f"Total embeddings to process: {total_lines:,}")

        with open(embeddings_file, 'r', encoding='utf-8') as f:
            with tqdm(total=total_lines, desc="Loading embeddings", unit=" vectors") as pbar:
                for line_num, line in enumerate(f, 1):
                    try:
                        # Skip header line
                        if line_num == 1:
                            pbar.update(1)
                            continue

                        parts = line.strip().split(' ')
                        if len(parts) < 301:  # concept + 300 dimensions
                            total_errors += 1
                            pbar.update(1)
                            continue

                        concept = parts[0]
                        # Prefix with /c/en/ to match ConceptNet URI format
                        if not concept.startswith('/c/'):
                            concept = f'/c/en/{concept}'

                        # Convert string floats to a list
                        vector = [float(x) for x in parts[1:301]]

                        batch.append((concept, vector))

                        if len(batch) >= batch_size:
                            try:
                                execute_batch(
                                    cursor,
                                    """
                                    INSERT INTO embeddings (concept, vector)
                                    VALUES (%s, %s::vector)
                                    ON CONFLICT (concept) DO NOTHING
                                    """,
                                    batch
                                )
                                conn.commit()
                                total_loaded += len(batch)
                            except Exception as batch_error:
                                conn.rollback()
                                total_errors += len(batch)
                                if total_errors <= 100:
                                    print(f"\nBatch error at line ~{line_num}: {batch_error}")
                            batch = []

                    except Exception as e:
                        total_errors += 1
                        if total_errors <= 10:
                            print(f"\nError on line {line_num}: {e}")

                    pbar.update(1)

                # Insert remaining batch
                if batch:
                    try:
                        execute_batch(
                            cursor,
                            """
                            INSERT INTO embeddings (concept, vector)
                            VALUES (%s, %s::vector)
                            ON CONFLICT (concept) DO NOTHING
                            """,
                            batch
                        )
                        conn.commit()
                        total_loaded += len(batch)
                    except Exception as batch_error:
                        conn.rollback()
                        total_errors += len(batch)
                        print(f"\nFinal batch error: {batch_error}")

        cursor.close()
        print(f"\nEmbeddings loaded: {total_loaded:,}")
        print(f"Errors encountered: {total_errors:,}")

        log_operation(conn, log_id, 'completed', total_loaded)
        return total_loaded

    except Exception as e:
        print(f"Error loading embeddings: {e}")
        log_operation(conn, log_id, 'failed', total_loaded, str(e))
        raise


def create_indexes_if_needed(conn):
    """
    Run ANALYZE to update statistics after data load
    """
    print("\nAnalyzing tables...")
    cursor = conn.cursor()
    cursor.execute("ANALYZE edges")
    cursor.execute("ANALYZE nodes")
    cursor.execute("ANALYZE relations")
    cursor.execute("ANALYZE embeddings")
    conn.commit()
    cursor.close()
    print("Table analysis complete")


def print_statistics(conn):
    """Print loading statistics"""
    cursor = conn.cursor()

    print("\n" + "="*60)
    print("LOADING STATISTICS")
    print("="*60)

    cursor.execute("SELECT COUNT(*) FROM edges")
    edge_count = cursor.fetchone()[0]
    print(f"Total edges: {edge_count:,}")

    cursor.execute("SELECT COUNT(*) FROM nodes")
    node_count = cursor.fetchone()[0]
    print(f"Total nodes: {node_count:,}")

    cursor.execute("SELECT COUNT(*) FROM relations")
    relation_count = cursor.fetchone()[0]
    print(f"Total relations: {relation_count:,}")

    cursor.execute("SELECT COUNT(DISTINCT relation) FROM edges")
    used_relations = cursor.fetchone()[0]
    print(f"Relations used in edges: {used_relations:,}")

    cursor.execute("SELECT COUNT(DISTINCT language) FROM nodes")
    languages = cursor.fetchone()[0]
    print(f"Languages: {languages:,}")

    # Check if embeddings table exists and has data
    cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'embeddings')")
    has_embeddings = cursor.fetchone()[0]
    if has_embeddings:
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_count = cursor.fetchone()[0]
        print(f"Embeddings: {embeddings_count:,}")

    # Top 5 relations
    print("\nTop 5 most common relations:")
    cursor.execute("""
        SELECT r.label, COUNT(*) as count
        FROM edges e
        JOIN relations r ON e.relation = r.uri
        GROUP BY r.label
        ORDER BY count DESC
        LIMIT 5
    """)
    for label, count in cursor.fetchall():
        print(f"  {label}: {count:,}")

    # Top 5 languages
    print("\nTop 5 languages by node count:")
    cursor.execute("""
        SELECT language, COUNT(*) as count
        FROM nodes
        WHERE language IS NOT NULL
        GROUP BY language
        ORDER BY count DESC
        LIMIT 5
    """)
    for lang, count in cursor.fetchall():
        print(f"  {lang}: {count:,}")

    print("="*60 + "\n")
    cursor.close()


def main():
    """Main loading process"""
    print("ConceptNet Data Loader")
    print("="*60)

    # Download data
    assertions_file = download_assertions()
    embeddings_file = download_embeddings()

    # Connect to database
    conn = connect_db()

    # Check if edges already loaded
    edges_loaded = check_if_loaded(conn)

    # Check if nodes need extraction
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM nodes")
    nodes_count = cursor.fetchone()[0]

    # Check if embeddings need loading
    cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'embeddings')")
    has_embeddings_table = cursor.fetchone()[0]
    embeddings_count = 0
    if has_embeddings_table:
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        embeddings_count = cursor.fetchone()[0]
    cursor.close()

    if edges_loaded:
        print("\nEdges already loaded in database!")
        if nodes_count == 0:
            print("Nodes table is empty - will extract nodes from edges.")
        elif embeddings_count == 0 and has_embeddings_table:
            print("Embeddings table is empty - will load embeddings.")
        elif not has_embeddings_table or (embeddings_count > 0 and nodes_count > 0):
            print_statistics(conn)
            response = input("Do you want to reload? This will skip existing records. (y/N): ")
            if response.lower() != 'y':
                print("Exiting without changes.")
                conn.close()
                return

    try:
        # Load assertions if needed
        if not edges_loaded:
            load_assertions(conn, assertions_file)

        # Extract nodes if needed
        if nodes_count == 0:
            extract_nodes(conn)

        # Load embeddings if needed
        if has_embeddings_table and embeddings_count == 0:
            load_embeddings(conn, embeddings_file)

        # Update statistics
        create_indexes_if_needed(conn)

        # Print results
        print_statistics(conn)

        print("\n✓ Data loading complete!")

    except Exception as e:
        print(f"\n✗ Data loading failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
