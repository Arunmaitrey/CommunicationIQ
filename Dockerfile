# ============================================================
# CommunicationIQ — single Dockerfile for frontend + backend
# ============================================================
# Build:  docker build -t commiq .
# Run:    docker run -p 8010:8010 -p 3010:3010 commiq
# ============================================================

# --------------- Stage 1: Python backend ---------------
FROM python:3.12-slim AS backend

WORKDIR /backend

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .
RUN mkdir -p assets/avatars assets/audio tmp

EXPOSE 8010

# --------------- Stage 2: Node frontend deps ---------------
FROM node:20-alpine AS frontend-deps

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# --------------- Stage 3: Node frontend build ---------------
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY --from=frontend-deps /frontend/node_modules ./node_modules
COPY frontend/ .

ARG NEXT_PUBLIC_API_URL=http://localhost:8010/api/v1
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# --------------- Stage 4: Node frontend runner ---------------
FROM node:20-alpine AS frontend-runner

WORKDIR /frontend
ENV NODE_ENV=production

COPY --from=frontend-builder /frontend/.next/standalone ./
COPY --from=frontend-builder /frontend/.next/static ./.next/static
COPY --from=frontend-builder /frontend/public ./public

EXPOSE 3010

# --------------- Stage 5: Final combined image ---------------
FROM python:3.12-slim AS final

WORKDIR /app

# Install Python runtime deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev nodejs npm && \
    rm -rf /var/lib/apt/lists/*

# Copy backend
COPY --from=backend /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=backend /backend /app/backend
RUN mkdir -p /app/backend/assets/avatars /app/backend/assets/audio /app/backend/tmp

# Copy frontend
COPY --from=frontend-runner /frontend /app/frontend

# Startup script: launch both services
COPY docker-start.sh /app/docker-start.sh
RUN chmod +x /app/docker-start.sh

EXPOSE 8010 3010

CMD ["/app/docker-start.sh"]
