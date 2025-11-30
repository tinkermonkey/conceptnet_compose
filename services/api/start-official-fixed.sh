#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
until PGPASSWORD=$POSTGRES_PASSWORD psql -h "$DB_HOST" -U "$POSTGRES_USER" -d "$DB_NAME" -c '\q' 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping"
  sleep 2
done

echo "PostgreSQL is up - starting ConceptNet API..."

# Set database connection environment variables for ConceptNet
export CONCEPTNET_DB_NAME="$DB_NAME"
export CONCEPTNET_DB_USER="$POSTGRES_USER"
export CONCEPTNET_DB_PASSWORD="$POSTGRES_PASSWORD"
export CONCEPTNET_DB_HOSTNAME="$DB_HOST"

# Create a wrapper script to run the API with correct host binding
cd /app
cat > /app/run_api.py << 'EOF'
#!/usr/bin/env python3
"""
Wrapper to run ConceptNet API with proper host binding
"""
from conceptnet_web.api import app

if __name__ == '__main__':
    # Run with host=0.0.0.0 to allow external access
    app.run(host='0.0.0.0', port=8084, debug=False)
EOF

chmod +x /app/run_api.py
python /app/run_api.py
