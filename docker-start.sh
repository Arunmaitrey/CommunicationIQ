#!/bin/sh
# CommunicationIQ — startup script for combined Docker image
# Launches both backend (uvicorn) and frontend (next) in parallel.

echo "Starting CommunicationIQ..."

# Start backend in background
cd /app/backend
uvicorn app.main:app --host 0.0.0.0 --port 8010 &
BACKEND_PID=$!

# Start frontend in background
cd /app/frontend
node server.js &
FRONTEND_PID=$!

echo "Backend running on port 8010"
echo "Frontend running on port 3010"

# Wait for either process to exit
wait $BACKEND_PID $FRONTEND_PID
