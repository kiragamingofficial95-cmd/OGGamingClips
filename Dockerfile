FROM python:3.12-slim-bookworm

WORKDIR /app

# Install FFmpeg
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install pip, setuptools, wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install core Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY ./app ./app
COPY ./tests ./tests

# Create data directories
RUN mkdir -p /data/{sources,transcripts,candidates,clips,metadata,failed}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" || exit 1

# Start worker or API
CMD ["python", "-m", "app.main"]
