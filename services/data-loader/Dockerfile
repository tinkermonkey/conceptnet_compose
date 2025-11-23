FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config.py .
COPY download_data.py .
COPY loader.py .

# Create data directories
RUN mkdir -p /data/raw /data/processed

# Run the loader
CMD ["python", "loader.py"]
