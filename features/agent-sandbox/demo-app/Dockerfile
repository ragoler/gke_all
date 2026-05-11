FROM python:3.11-slim

WORKDIR /app

# Create secure non-root user and group with UID/GID 1000 to satisfy GKE security policies
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Change ownership of the application directories to appuser
RUN chown -R appuser:appgroup /app

EXPOSE 8888

# Switch to non-root user context
USER 1000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888"]
