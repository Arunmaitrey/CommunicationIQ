FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies. Tier 0 (fast, ~seconds) and Tier 1 — the
# speech engine: faster-whisper, torch, transformers — are separate layers
# so a requirements.txt-only change doesn't invalidate the multi-GB Tier 1
# layer on every rebuild.
#
# Without this, `docker-compose up --build` gives every teammate Tier 0 only
# (timing measures, no real transcription) — the container starts and
# /healthz looks fine, but pronunciation, accuracy, grammar and content all
# report unscored, silently, with no error to notice.
COPY requirements.txt requirements-engine.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-engine.txt

# Pre-download the speech models at build time rather than at each
# container's first request. Every teammate's container then starts warm
# and offline-capable, instead of racing a several-hundred-MB Hugging Face
# download — and whatever that host's own TLS/network setup does to it —
# the moment the first student answer needs scoring.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small.en', device='cpu', compute_type='int8')" \
    && python -c "from transformers import Wav2Vec2Processor, Wav2Vec2ForCTC; Wav2Vec2Processor.from_pretrained('facebook/wav2vec2-base-960h'); Wav2Vec2ForCTC.from_pretrained('facebook/wav2vec2-base-960h')"

# Copy application code
COPY app/ app/

EXPOSE 8010

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8010"]
