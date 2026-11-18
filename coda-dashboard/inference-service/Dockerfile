# One image, two containers: inference-api (uvicorn main:app) and inference-worker (python worker.py).
# tensorflow[and-cuda] ships the CUDA/cuDNN wheels, so the same image runs on a T4 (with the nvidia runtime,
# see docker-compose.gpu.yml) or falls back to CPU. Model packages are bind-mounted at /models.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    TF_FORCE_GPU_ALLOW_GROWTH=true \
    DATA_DIR=/data \
    MODELS_DIR=/models

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 coda \
    && mkdir -p /data/jobs \
    && chown -R coda:coda /data
USER coda

EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
