FROM python:3.11-slim

# Optional: GPU support — uncomment if using CUDA
# FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app.py .

# Download model at build time (optional — can mount at runtime instead)
# RUN python -c "from transformers import AutoModel, AutoTokenizer; \
#     AutoTokenizer.from_pretrained('mainguyen9/vietlegal-harrier-0.6b'); \
#     AutoModel.from_pretrained('mainguyen9/vietlegal-harrier-0.6b')"

ENV EMBED_MODEL=mainguyen9/vietlegal-harrier-0.6b
ENV EMBED_BATCH_SIZE=512

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD curl -f http://localhost:${PORT:-8080}/health || exit 1

CMD sh -c "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"
