# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5050 \
    COOKED_ENV=production \
    COOKED_DB_PATH=/app/data/cooked.db \
    UPLOAD_FOLDER=/app/uploads

# Install system dependencies for SQLite, Pillow, and health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    libjpeg62-turbo \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user and group
RUN groupadd -r cooked && useradd -r -g cooked -d /app -s /sbin/nologin cooked

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Create directories for persistent SQLite database and user uploads
RUN mkdir -p /app/data /app/uploads && \
    chown -R cooked:cooked /app

# Switch to non-root user
USER cooked

# Expose web application port
EXPOSE 5050

# Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-5050}/api/health || exit 1

# Production WSGI Server entrypoint using Gunicorn with dynamic PORT & high concurrency
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5050} --workers 4 --threads 16 --worker-class gthread --backlog 2048 --worker-tmp-dir /dev/shm --timeout 60 --access-logfile - --error-logfile - app:app"]


