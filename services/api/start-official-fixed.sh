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

# run_api.py is baked into the image; exec so Python is PID 1 and SIGTERM
# is forwarded directly to it (needed for OTel batch processors to flush).
cd /app
exec python /app/run_api.py
