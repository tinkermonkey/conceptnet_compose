#!/usr/bin/env python3
"""
Load Numberbatch embeddings with observable progress
"""
import sys
import time
import psycopg2
from pathlib import Path
from datetime import timedelta
from psycopg2.extras import execute_batch

from config import DB_CONFIG
from download_data import download_embeddings


def get_connection():
    """Get database connection"""
    return psycopg2.connect(**DB_CONFIG)


class ProgressTracker:
    """Track loading progress with periodic output"""

    def __init__(self, total_rows, description="Loading"):
        self.total_rows = total_rows
        self.description = description
        self.start_time = time.time()
        self.last_print = 0
        self.rows_processed = 0

    def update(self, rows_processed):
        """Update progress - prints every batch to ensure visibility"""
        self.rows_processed = rows_processed
        current_time = time.time()

        # Print update every batch (no carriage return, just newlines)
        # This ensures Docker logs capture every update
        if rows_processed - self.last_print >= 5000:
            elapsed = current_time - self.start_time
            rate = rows_processed / elapsed if elapsed > 0 else 0
            remaining = self.total_rows - rows_processed
            eta_seconds = remaining / rate if rate > 0 else 0
            eta = timedelta(seconds=int(eta_seconds))
            percent = (rows_processed / self.total_rows) * 100

            print(f"[{self.description}] {rows_processed:,}/{self.total_rows:,} "
                  f"({percent:.1f}%) | {rate:.0f} vectors/sec | ETA: {eta}")
            sys.stdout.flush()
            self.last_print = rows_processed

    def finish(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        rate = self.rows_processed / elapsed if elapsed > 0 else 0
        print(f"\n✓ {self.description} complete!")
        print(f"  Total: {self.rows_processed:,} vectors")
        print(f"  Time: {timedelta(seconds=int(elapsed))}")
        print(f"  Rate: {rate:.0f} vectors/sec")
        sys.stdout.flush()


def count_lines(filepath):
    """Count lines in file"""
    print(f"Counting vectors in {filepath.name}...")
    sys.stdout.flush()
    with open(filepath, 'r', encoding='utf-8') as f:
        count = sum(1 for _ in f) - 1  # Subtract header
    print(f"  Total vectors: {count:,}")
    sys.stdout.flush()
    return count


def main():
    """Load embeddings"""
    print("="*70)
    print("ConceptNet Numberbatch Embeddings Loader")
    print("="*70)
    sys.stdout.flush()

    # Parse throttle argument (delay in seconds between batches)
    throttle_delay = 0
    for arg in sys.argv:
        if arg.startswith('--throttle='):
            try:
                throttle_delay = float(arg.split('=')[1])
                print(f"⚙️  Throttle enabled: {throttle_delay}s delay between batches")
            except ValueError:
                print("⚠️  Invalid throttle value, using no delay")
    sys.stdout.flush()

    # Download embeddings
    embeddings_file = download_embeddings()
    print(f"Embeddings file: {embeddings_file}")
    sys.stdout.flush()

    # Check existing
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM embeddings")
    existing = cursor.fetchone()[0]

    if existing > 0:
        print(f"\n⚠️  Found {existing:,} existing embeddings")
        print("This will ADD new embeddings (duplicates will be skipped)")
        sys.stdout.flush()

        if '--yes' not in sys.argv and '-y' not in sys.argv:
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                sys.exit(0)

    # Count total
    total_lines = count_lines(Path(embeddings_file))

    # Load embeddings
    print("\n" + "="*70)
    print("LOADING EMBEDDINGS")
    print("="*70)
    sys.stdout.flush()

    batch = []
    batch_size = 5000
    total_loaded = 0
    total_errors = 0

    progress = ProgressTracker(total_lines, "Embeddings")

    try:
        with open(embeddings_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Skip header
                if line_num == 1:
                    continue

                try:
                    parts = line.strip().split(' ')
                    if len(parts) < 301:
                        total_errors += 1
                        continue

                    concept = parts[0]
                    if not concept.startswith('/c/'):
                        concept = f'/c/en/{concept}'

                    vector = [float(x) for x in parts[1:301]]
                    batch.append((concept, vector))

                    if len(batch) >= batch_size:
                        execute_batch(
                            cursor,
                            "INSERT INTO embeddings (concept, vector) "
                            "VALUES (%s, %s::vector) ON CONFLICT (concept) DO NOTHING",
                            batch
                        )
                        conn.commit()
                        total_loaded += len(batch)
                        batch = []
                        progress.update(line_num - 1)

                        # Throttle if requested
                        if throttle_delay > 0:
                            time.sleep(throttle_delay)

                except Exception as e:
                    total_errors += 1
                    if total_errors <= 10:
                        print(f"Error on line {line_num}: {e}")
                        sys.stdout.flush()

            # Insert remaining
            if batch:
                execute_batch(
                    cursor,
                    "INSERT INTO embeddings (concept, vector) "
                    "VALUES (%s, %s::vector) ON CONFLICT (concept) DO NOTHING",
                    batch
                )
                conn.commit()
                total_loaded += len(batch)

        progress.finish()

        if total_errors > 0:
            print(f"\n⚠️  Errors encountered: {total_errors:,}")

        # Final count
        cursor.execute("SELECT COUNT(*) FROM embeddings")
        final_count = cursor.fetchone()[0]
        print(f"\n✓ Total embeddings in database: {final_count:,}")
        sys.stdout.flush()

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

    print("\n" + "="*70)
    print("✓ EMBEDDINGS LOADING COMPLETE!")
    print("="*70)
    sys.stdout.flush()


if __name__ == '__main__':
    main()
