"""
Configuration for ConceptNet API
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

# API configuration
API_HOST = os.getenv('API_HOST', '0.0.0.0')
API_PORT = int(os.getenv('API_PORT', 8084))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'

# Query limits
DEFAULT_LIMIT = 50
MAX_LIMIT = 1000

# Connection pool settings
DB_POOL_MIN = 2
DB_POOL_MAX = 10
