I'll help you find information about hosting the ConceptNet API locally. Let me search for the current documentation and Docker options.Based on my research, I can provide you with a comprehensive guide for hosting ConceptNet API locally. Since the public API has been down, you have several options, and I'll walk you through the Docker-based approach that would work well with your 32GB RAM server.

## Current State of ConceptNet

The official ConceptNet Docker images are quite outdated (version 5.5.x from ~2016-2017), and the maintainer expressed frustration with Docker for reproducible research and was about to give up supporting the Docker version. The latest stable version is ConceptNet 5.8.1, but the Docker ecosystem hasn't kept up.

## Recommended Approaches

### Option 1: Docker Compose with PostgreSQL (Most Flexible)

Since you have a local server with 32GB RAM, this approach would work well. Here's a custom Docker Compose setup:

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:13
    container_name: conceptnet-db
    restart: always
    environment:
      POSTGRES_USER: conceptnet
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-conceptnet123}
      POSTGRES_DB: conceptnet5
    ports:
      - "5432:5432"
    volumes:
      - ./postgres-data:/var/lib/postgresql/data
      - ./init-scripts:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U conceptnet -d conceptnet5"]
      interval: 10s
      timeout: 5s
      retries: 5

  conceptnet-api:
    build: 
      context: .
      dockerfile: Dockerfile
    container_name: conceptnet-api
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      CONCEPTNET_DB_USER: conceptnet
      CONCEPTNET_DB_PASSWORD: ${POSTGRES_PASSWORD:-conceptnet123}
      CONCEPTNET_DB_NAME: conceptnet5
      CONCEPTNET_DB_HOSTNAME: postgres
      CONCEPTNET_DB_PORT: 5432
    ports:
      - "8084:8084"
    volumes:
      - ./data:/home/conceptnet/data
    restart: unless-stopped

volumes:
  postgres-data:
```

And a corresponding Dockerfile:

```dockerfile
FROM ubuntu:20.04

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    python3.8 \
    python3-pip \
    python3-dev \
    libhdf5-dev \
    libmecab-dev \
    mecab-ipadic-utf8 \
    postgresql-client \
    git \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create conceptnet user
RUN useradd -m -s /bin/bash conceptnet

USER conceptnet
WORKDIR /home/conceptnet

# Clone ConceptNet repository
RUN git clone https://github.com/commonsense/conceptnet5.git
WORKDIR /home/conceptnet/conceptnet5

# Install Python dependencies
RUN pip3 install --user -e ".[vectors]"
RUN pip3 install --user flask psycopg2-binary

# Expose API port
EXPOSE 8084

# Start script
COPY --chown=conceptnet:conceptnet start.sh /home/conceptnet/start.sh
RUN chmod +x /home/conceptnet/start.sh

CMD ["/home/conceptnet/start.sh"]
```

### Option 2: Use Pre-built Data

You can download a pre-built list of all the edges (assertions) in ConceptNet 5.7 in a gzipped, tab-separated text file. The data is available from:

1. **Assertions CSV**: Download from the ConceptNet downloads page
2. **Raw Data from Zenodo**: The raw data is hosted on Zenodo at https://zenodo.org/record/998169/files/conceptnet-raw-data-5.5.zip

For ConceptNet 5.8 data, you would need to:
1. Download the assertions CSV
2. Load it into PostgreSQL
3. Run the ConceptNet API against it

### Option 3: AWS AMI Alternative (Not AWS)

The conceptnet-deployment repository describes how to set up ConceptNet using either Packer or Puppet, which will take care of almost all of the steps for you. You can use the Puppet scripts on your local server:

```bash
# Clone the deployment repository
git clone https://github.com/commonsense/conceptnet-deployment
cd conceptnet-deployment

# Run the Puppet setup (on a fresh Ubuntu 20.04 machine)
sudo ./setup-with-puppet.sh

# Switch to conceptnet user and build
sudo su conceptnet
cd ~/conceptnet5
./build.sh
```

## Data Loading Strategy

For your local setup, I recommend:

1. **Start with PostgreSQL in Docker** for easy management
2. **Download pre-built data** to avoid the 18+ hour build process
3. **Load the data** using a custom import script:

```python
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch

# Load the assertions CSV
df = pd.read_csv('conceptnet-assertions-5.7.0.csv', sep='\t', header=None)

# Connect to PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    database="conceptnet5",
    user="conceptnet",
    password="conceptnet123"
)

# Create tables and load data
# (You'll need to reference the ConceptNet schema for exact structure)
```

## Memory Considerations

The build process requires 30 GB of RAM, so your 32GB server should handle it, but just barely. If you're only running the API (not building from scratch), you'll need much less:

- API server alone: ~4-8GB RAM
- PostgreSQL with full dataset: ~8-12GB RAM
- Total for running system: ~16-20GB RAM

## Quick Start Path

Given your constraints and the API being down, I recommend:

1. Use the Docker Compose setup above
2. Download the pre-built ConceptNet 5.7 assertions from their downloads page
3. Write a simple Python script to load the CSV into PostgreSQL
4. Run the ConceptNet API against your local database

This avoids the complex build process and gets you running quickly on your local server without AWS costs.

Would you like me to help you create the specific loading scripts or elaborate on any part of this setup?