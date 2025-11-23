FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY config.py .
COPY app.py .
COPY start.sh .

# Make start script executable
RUN chmod +x start.sh

# Expose API port
EXPOSE 8084

# Run the application
CMD ["./start.sh"]
