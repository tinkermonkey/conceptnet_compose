"""
Configuration for ConceptNet Data Loader
"""
import os

# Database configuration
DB_CONFIG = {
    'host': os.getenv('CONCEPTNET_DB_HOSTNAME', 'postgres'),
    'port': int(os.getenv('CONCEPTNET_DB_PORT', 5432)),
    'database': os.getenv('CONCEPTNET_DB_NAME', 'conceptnet5'),
    'user': os.getenv('CONCEPTNET_DB_USER', 'conceptnet'),
    'password': os.getenv('CONCEPTNET_DB_PASSWORD', 'conceptnet123'),
}

# Data source URLs
DATA_SOURCES = {
    'assertions': {
        'url': 'https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz',
        'filename': 'conceptnet-assertions-5.7.0.csv.gz',
        'uncompressed': 'conceptnet-assertions-5.7.0.csv',
    },
    'embeddings': {
        'url': 'https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz',
        'filename': 'numberbatch-en-19.08.txt.gz',
        'uncompressed': 'numberbatch-en-19.08.txt',
    }
}

# Directory paths
DATA_DIR = '/data'
RAW_DATA_DIR = os.path.join(DATA_DIR, 'raw')
PROCESSED_DATA_DIR = os.path.join(DATA_DIR, 'processed')

# Loading configuration
BATCH_SIZE = 10000  # Number of rows to insert at once
CHUNK_SIZE = 8192   # Chunk size for file downloads
