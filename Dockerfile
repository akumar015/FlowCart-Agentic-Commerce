# Stage 1: Build the React 19 Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend & Unified Production Server
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application and SQLite databases
COPY api.py main.py mcp_server.py ./
COPY chat_agent ./chat_agent
COPY databases ./databases
COPY scripts ./scripts

# Copy built frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Railway provides PORT dynamically at runtime
ENV PORT=8000
EXPOSE 8000

# Start Uvicorn bound to 0.0.0.0 and Railway's dynamic PORT
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT}"]
