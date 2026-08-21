FROM python:3.14-slim-trixie

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download the RAG embedding model into the image at build time, so the running
# container never needs network access to embed a query and starts up fast. Must stay
# consistent with scripts/embedding_config.py (single source of truth for model/cache path).
RUN python -c "from scripts.embedding_config import EMBEDDING_MODEL_NAME, FASTEMBED_CACHE_DIR; from fastembed import TextEmbedding; TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=FASTEMBED_CACHE_DIR)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9000"]