FROM python:3.11-slim

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app ./app

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

EXPOSE 8080

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=15s \
    --retries=3 \
    CMD python -c "import urllib.request; \
        response = urllib.request.urlopen('http://localhost:8080/health'); \
        raise SystemExit(0 if response.status == 200 else 1)" || exit 1

CMD ["python", "-m", "app.main"]