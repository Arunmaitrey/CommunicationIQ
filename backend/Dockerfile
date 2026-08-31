FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install the API and lightweight Faster Whisper engine together. There is no
# Torch/Wav2Vec2 pronunciation stack in this build.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the speech models at build time rather than at each
# container's first request. Every teammate's container then starts warm
# and offline-capable, instead of racing a several-hundred-MB Hugging Face
# download — and whatever that host's own TLS/network setup does to it —
# the moment the first student answer needs scoring.
# Copy application code
COPY app/ app/

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
