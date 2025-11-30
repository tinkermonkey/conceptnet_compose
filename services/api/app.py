"""
ConceptNet API Service
Provides REST API endpoints for querying ConceptNet graph data
"""
import json
import psycopg2
from psycopg2 import pool
from flask import Flask, jsonify, request
from config import DB_CONFIG, API_HOST, API_PORT, DEBUG, DEFAULT_LIMIT, MAX_LIMIT, DB_POOL_MIN, DB_POOL_MAX

app = Flask(__name__)

# Database connection pool
db_pool = None


def init_db_pool():
    """Initialize database connection pool"""
    global db_pool
    try:
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            DB_POOL_MIN,
            DB_POOL_MAX,
            **DB_CONFIG
        )
        print(f"Database pool created (min={DB_POOL_MIN}, max={DB_POOL_MAX})")
    except Exception as e:
        print(f"Error creating database pool: {e}")
        raise


# Initialize pool at module load time
init_db_pool()


def get_db_connection():
    """Get a connection from the pool"""
    return db_pool.getconn()


def return_db_connection(conn):
    """Return a connection to the pool"""
    db_pool.putconn(conn)


def format_node(node_uri):
    """Format a node URI into ConceptNet API format"""
    # Extract language and term from URI like /c/en/apple
    parts = node_uri.split('/')
    if len(parts) >= 4 and parts[1] == 'c':
        language = parts[2]
        term = '/'.join(parts[3:])
        return {
            '@id': node_uri,
            'term': node_uri,
            'label': term.replace('_', ' '),
            'language': language
        }
    return {
        '@id': node_uri,
        'term': node_uri,
        'label': node_uri,
        'language': 'unknown'
    }


def format_edge(row):
    """Format an edge row into ConceptNet API format

    Args:
        row: tuple of (uri, relation, relation_label, start_node, end_node,
                      weight, dataset, surface_text, metadata)
    """
    uri = row[0]
    relation = row[1]
    start_node = row[3]
    end_node = row[4]
    weight = float(row[5]) if row[5] else 1.0
    surface_text = row[7]

    # Build @id in format: /r/RelatedTo/c/en/apple/c/en/fruit
    # Remove leading slashes from nodes for concatenation
    start_clean = start_node.lstrip('/')
    end_clean = end_node.lstrip('/')
    edge_id = f"{relation}/{start_clean}/{end_clean}"

    edge = {
        '@id': edge_id,
        'start': format_node(start_node),
        'end': format_node(end_node),
        'weight': weight,
        'surfaceText': surface_text if surface_text else None
    }

    # Add metadata if present
    if row[8]:
        try:
            metadata = json.loads(row[8])
            if 'dataset' in metadata:
                edge['dataset'] = metadata['dataset']
            if 'license' in metadata:
                edge['license'] = metadata['license']
        except:
            pass

    return edge


@app.route('/')
def index():
    """API root endpoint"""
    return jsonify({
        'name': 'ConceptNet API',
        'version': '5.7.0',
        'endpoints': {
            '/': 'This help message',
            '/health': 'Health check',
            '/c/<path:concept>': 'Get edges for a concept',
            '/query': 'Query edges with filters',
            '/stats': 'Database statistics',
            '/relations': 'List all relations',
            '/relatedness': 'Compute semantic similarity between two concepts',
            '/related': 'Find semantically related concepts',
        },
        'documentation': 'https://github.com/commonsense/conceptnet5/wiki/API'
    })


@app.route('/health')
def health():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return_db_connection(conn)

        return jsonify({
            'status': 'healthy',
            'database': 'connected'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500


@app.route('/stats')
def stats():
    """Get database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Get counts
        cursor.execute("SELECT COUNT(*) FROM edges")
        edge_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM nodes")
        node_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM relations")
        relation_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT language) FROM nodes WHERE language IS NOT NULL")
        language_count = cursor.fetchone()[0]

        # Check if embeddings table exists
        cursor.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'embeddings')")
        has_embeddings = cursor.fetchone()[0]
        embeddings_count = 0
        if has_embeddings:
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            embeddings_count = cursor.fetchone()[0]

        cursor.close()
        return_db_connection(conn)

        result = {
            'edges': edge_count,
            'nodes': node_count,
            'relations': relation_count,
            'languages': language_count
        }

        if has_embeddings:
            result['embeddings'] = embeddings_count

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/c/<path:concept>')
def get_concept(concept):
    """
    Get edges for a specific concept
    Query parameters:
    - limit: number of results (default 50, max 1000)
    - offset: pagination offset (default 0)
    - rel: filter by relation
    """
    # Normalize concept URI
    if not concept.startswith('/c/'):
        concept = f'/c/{concept}'

    # Get query parameters
    limit = min(int(request.args.get('limit', DEFAULT_LIMIT)), MAX_LIMIT)
    offset = int(request.args.get('offset', 0))
    rel_filter = request.args.get('rel')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT
                e.uri,
                e.relation,
                r.label as relation_label,
                e.start_node,
                e.end_node,
                e.weight,
                e.dataset,
                e.surface_text,
                e.metadata
            FROM edges e
            LEFT JOIN relations r ON e.relation = r.uri
            WHERE e.start_node = %s OR e.end_node = %s
        """
        params = [concept, concept]

        # Add relation filter if specified
        if rel_filter:
            if not rel_filter.startswith('/r/'):
                rel_filter = f'/r/{rel_filter}'
            query += " AND e.relation = %s"
            params.append(rel_filter)

        # Add ordering and pagination
        query += " ORDER BY e.weight DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Format results
        edges = [format_edge(row) for row in rows]

        cursor.close()
        return_db_connection(conn)

        # Build @id for the query
        query_id = f"{concept}?limit={limit}&offset={offset}"
        if rel_filter:
            query_id += f"&rel={rel_filter}"

        return jsonify({
            '@id': query_id,
            'edges': edges
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/query')
def query():
    """
    Query edges with flexible filters
    Query parameters:
    - start: filter by start node
    - end: filter by end node
    - rel: filter by relation
    - node: filter by either start or end node
    - limit: number of results (default 50, max 1000)
    - offset: pagination offset (default 0)
    - minWeight: minimum edge weight
    """
    # Get query parameters
    start = request.args.get('start')
    end = request.args.get('end')
    rel = request.args.get('rel')
    node = request.args.get('node')
    limit = min(int(request.args.get('limit', DEFAULT_LIMIT)), MAX_LIMIT)
    offset = int(request.args.get('offset', 0))
    min_weight = request.args.get('minWeight')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Build query
        query = """
            SELECT
                e.uri,
                e.relation,
                r.label as relation_label,
                e.start_node,
                e.end_node,
                e.weight,
                e.dataset,
                e.surface_text,
                e.metadata
            FROM edges e
            LEFT JOIN relations r ON e.relation = r.uri
            WHERE 1=1
        """
        params = []

        # Add filters
        if start:
            if not start.startswith('/c/'):
                start = f'/c/{start}'
            query += " AND e.start_node = %s"
            params.append(start)

        if end:
            if not end.startswith('/c/'):
                end = f'/c/{end}'
            query += " AND e.end_node = %s"
            params.append(end)

        if node:
            if not node.startswith('/c/'):
                node = f'/c/{node}'
            query += " AND (e.start_node = %s OR e.end_node = %s)"
            params.extend([node, node])

        if rel:
            if not rel.startswith('/r/'):
                rel = f'/r/{rel}'
            query += " AND e.relation = %s"
            params.append(rel)

        if min_weight:
            query += " AND e.weight >= %s"
            params.append(float(min_weight))

        # Add ordering and pagination
        query += " ORDER BY e.weight DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Format results
        edges = [format_edge(row) for row in rows]

        cursor.close()
        return_db_connection(conn)

        # Build @id for the query
        query_params = []
        if start:
            query_params.append(f"start={start}")
        if end:
            query_params.append(f"end={end}")
        if node:
            query_params.append(f"node={node}")
        if rel:
            query_params.append(f"rel={rel}")
        if min_weight:
            query_params.append(f"minWeight={min_weight}")
        query_params.append(f"limit={limit}")
        query_params.append(f"offset={offset}")

        query_id = f"/query?{'&'.join(query_params)}"

        return jsonify({
            '@id': query_id,
            'edges': edges
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/relations')
def get_relations():
    """Get all available relations"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT uri, label, description
            FROM relations
            ORDER BY label
        """)
        rows = cursor.fetchall()

        relations = [
            {
                'uri': row[0],
                'label': row[1],
                'description': row[2]
            }
            for row in rows
        ]

        cursor.close()
        return_db_connection(conn)

        return jsonify({
            'relations': relations,
            'count': len(relations)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/relatedness')
def get_relatedness():
    """
    Compute semantic similarity (cosine similarity) between two concepts
    Query parameters:
    - node1: first concept URI (e.g., /c/en/dog)
    - node2: second concept URI (e.g., /c/en/puppy)

    Returns similarity score between 0 and 1 (higher = more similar)
    """
    node1 = request.args.get('node1')
    node2 = request.args.get('node2')

    if not node1 or not node2:
        return jsonify({
            'error': 'Missing required parameters',
            'message': 'Both node1 and node2 parameters are required'
        }), 400

    # Normalize concept URIs
    if not node1.startswith('/c/'):
        node1 = f'/c/en/{node1}'
    if not node2.startswith('/c/'):
        node2 = f'/c/en/{node2}'

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Compute cosine similarity using pgvector's <=> operator
        # <=> returns cosine distance (0 = identical, 2 = opposite)
        # We convert to similarity: 1 - (distance / 2)
        cursor.execute("""
            SELECT
                e1.concept,
                e2.concept,
                1 - (e1.vector <=> e2.vector) as similarity
            FROM embeddings e1, embeddings e2
            WHERE e1.concept = %s AND e2.concept = %s
        """, (node1, node2))

        result = cursor.fetchone()

        if not result:
            # Check which concepts are missing
            cursor.execute("SELECT concept FROM embeddings WHERE concept IN (%s, %s)", (node1, node2))
            found = [row[0] for row in cursor.fetchall()]
            cursor.close()
            return_db_connection(conn)

            missing = []
            if node1 not in found:
                missing.append(node1)
            if node2 not in found:
                missing.append(node2)

            return jsonify({
                'error': 'Concepts not found',
                'message': f'No embeddings found for: {", ".join(missing)}',
                'node1': node1,
                'node2': node2
            }), 404

        cursor.close()
        return_db_connection(conn)

        return jsonify({
            'node1': result[0],
            'node2': result[1],
            'similarity': float(result[2])
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/related')
def get_related():
    """
    Find semantically related concepts using vector similarity
    Query parameters:
    - node: concept URI (e.g., /c/en/dog)
    - limit: number of results (default 10, max 100)

    Returns list of most similar concepts ordered by similarity
    """
    node = request.args.get('node')
    limit = min(int(request.args.get('limit', 10)), 100)

    if not node:
        return jsonify({
            'error': 'Missing required parameter',
            'message': 'node parameter is required'
        }), 400

    # Normalize concept URI
    if not node.startswith('/c/'):
        node = f'/c/en/{node}'

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Find K nearest neighbors using HNSW index
        # <=> operator uses the index for fast similarity search
        cursor.execute("""
            SELECT
                e2.concept,
                1 - (e1.vector <=> e2.vector) as similarity
            FROM embeddings e1, embeddings e2
            WHERE e1.concept = %s
                AND e2.concept != %s
            ORDER BY e1.vector <=> e2.vector
            LIMIT %s
        """, (node, node, limit))

        rows = cursor.fetchall()

        if not rows:
            # Check if the concept exists
            cursor.execute("SELECT concept FROM embeddings WHERE concept = %s", (node,))
            found = cursor.fetchone()
            cursor.close()
            return_db_connection(conn)

            if not found:
                return jsonify({
                    'error': 'Concept not found',
                    'message': f'No embedding found for: {node}',
                    'node': node
                }), 404

        cursor.close()
        return_db_connection(conn)

        related = [
            {
                'concept': row[0],
                'similarity': float(row[1])
            }
            for row in rows
        ]

        return jsonify({
            'node': node,
            'related': related,
            'count': len(related),
            'limit': limit
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'error': 'Not found',
        'message': 'The requested endpoint does not exist'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    return jsonify({
        'error': 'Internal server error',
        'message': str(error)
    }), 500


if __name__ == '__main__':
    # Initialize database pool
    init_db_pool()

    # Run Flask app
    print(f"Starting ConceptNet API on {API_HOST}:{API_PORT}")
    app.run(host=API_HOST, port=API_PORT, debug=DEBUG)
