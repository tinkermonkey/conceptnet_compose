#!/bin/bash
# Validation script for ConceptNet deployment

echo "ConceptNet Deployment Validation"
echo "================================="
echo ""

# Check Docker
echo -n "Checking Docker... "
if command -v docker &> /dev/null; then
    echo "✓ $(docker --version)"
else
    echo "✗ Docker not found"
    exit 1
fi

# Check Docker Compose
echo -n "Checking Docker Compose... "
if command -v docker-compose &> /dev/null; then
    echo "✓ $(docker-compose --version)"
else
    echo "✗ Docker Compose not found"
    exit 1
fi

# Check .env file
echo -n "Checking .env file... "
if [ -f .env ]; then
    echo "✓ Found"
else
    echo "✗ Not found (copy from .env.example)"
    exit 1
fi

# Validate docker-compose.yml
echo -n "Validating docker-compose.yml... "
if docker-compose config --quiet; then
    echo "✓ Valid"
else
    echo "✗ Invalid"
    exit 1
fi

# Check required files
echo ""
echo "Checking required files:"
files=(
    "docker-compose.yml"
    "services/postgres/init-scripts/01-create-schema.sql"
    "services/postgres/init-scripts/02-create-indexes.sql"
    "services/data-loader/Dockerfile"
    "services/data-loader/loader.py"
    "services/api/Dockerfile"
    "services/api/app.py"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (missing)"
        exit 1
    fi
done

echo ""
echo "================================="
echo "✓ All validation checks passed!"
echo ""
echo "Next steps:"
echo "  1. docker-compose up -d postgres"
echo "  2. docker-compose run --rm data-loader"
echo "  3. docker-compose up -d api"
echo "  4. curl http://localhost:8084/health"
