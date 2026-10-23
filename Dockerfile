FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt ./
COPY backend/requirements.txt ./backend_requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt -r backend_requirements.txt && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" python-multipart python-dotenv google-genai

COPY backend/ ./backend/
COPY bukit_jelutong/ ./bukit_jelutong/

WORKDIR /workspace/backend

ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}