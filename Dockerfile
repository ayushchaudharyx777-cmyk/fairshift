# FairShift — Production Container for Google Cloud Run
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install pinned Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source and static assets
COPY app/ ./app/
COPY static/ ./static/

# Create a non-root system user for security compliance on Cloud Run
RUN useradd -m -u 1001 fairshiftuser && \
    chown -R fairshiftuser:fairshiftuser /app

USER fairshiftuser

EXPOSE 8080

# Run uvicorn on $PORT (default 8080)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
