FROM python:3.11-slim

WORKDIR /app

# Install system curl tools (optional, for health checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY showcase_admin/requirements-dev.txt requirements.txt
RUN pip install --no-cache-dir --index-url https://pypi.org/simple -r requirements.txt

# Copy application codes and frontend static assets
COPY showcase_admin/app app/
COPY showcase_admin/frontend frontend/

# Volume mount point for persistent SQLite disk on GKE
VOLUME /data
EXPOSE 8000

# Run server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
