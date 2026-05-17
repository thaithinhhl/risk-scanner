# --- Giai đoạn 1: Builder ---
FROM python:3.10-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Tạo môi trường ảo ảo để cài thư viện
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Giai đoạn 2: Runner ---
FROM python:3.10-slim

WORKDIR /app

# Chỉ copy môi trường ảo đã cài xong thư viện từ builder sang
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy mã nguồn dự án
COPY . .

# Mở port
EXPOSE 8000

# Chạy FastAPI Backend
CMD sh -c "python -m uvicorn infra.api.app:app --host 0.0.0.0 --port ${PORT:-8000}"
