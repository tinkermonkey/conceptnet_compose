#!/bin/bash
set -e

echo "Starting ConceptNet API..."

# Wait for database to be ready
echo "Waiting for database..."
until PGPASSWORD=$CONCEPTNET_DB_PASSWORD psql -h "$CONCEPTNET_DB_HOSTNAME" -U "$CONCEPTNET_DB_USER" -d "$CONCEPTNET_DB_NAME" -c '\q' 2>/dev/null; do
  echo "Database is unavailable - sleeping"
  sleep 2
done

echo "Database is ready!"

# Start gunicorn
exec gunicorn \
    --bind 0.0.0.0:8084 \
    --workers 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    app:app
