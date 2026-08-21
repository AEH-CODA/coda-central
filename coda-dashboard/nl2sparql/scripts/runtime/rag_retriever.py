"""
Runtime RAG retrieval. Loads the pre-computed example embeddings CSV (built once, offline, by
scripts/offline/build_examples_embeddings.py) and the example corpus JSON at import time. The
only embedding computed at request time is the single incoming NL query -- the corpus is never
re-embedded here.
"""
import json
import logging

import numpy as np
import pandas as pd
from fastembed import TextEmbedding

from scripts.embedding_config import (
    EMBEDDING_MODEL_NAME,
    EMBEDDINGS_CSV_PATH,
    EXAMPLES_PATH,
    FASTEMBED_CACHE_DIR,
)

logger = logging.getLogger(__name__)

_DIM_COLUMN_PREFIX = "dim_"


class RagRetriever:
    def __init__(self):
        with open(EXAMPLES_PATH) as f:
            self._examples = json.load(f)

        df = pd.read_csv(EMBEDDINGS_CSV_PATH)
        if len(df) != len(self._examples):
            raise RuntimeError(
                f"nl2sparql_examples_embeddings.csv has {len(df)} rows but "
                f"nl2sparql_examples.json has {len(self._examples)} entries -- "
                f"rerun `python -m scripts.build_examples_embeddings` after editing the examples file."
            )

        dim_cols = [c for c in df.columns if c.startswith(_DIM_COLUMN_PREFIX)]
        self._ids = df["id"].to_numpy()
        self._matrix = df[dim_cols].to_numpy(dtype=np.float32)
        norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._unit_matrix = self._matrix / norms

        logger.info(f"Loaded {len(self._ids)} example embeddings (dim={self._matrix.shape[1]})")

        self._model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=FASTEMBED_CACHE_DIR)
        logger.info(f"Loaded embedding model {EMBEDDING_MODEL_NAME}")

    def retrieve(self, nl_query: str, k: int = 5) -> list[dict]:
        """Return the top-k most similar examples as {category, nl_query, sparql} dicts,
        most similar first."""
        query_vec = np.array(next(self._model.embed([nl_query])), dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            query_norm = 1.0
        query_unit = query_vec / query_norm

        similarities = self._unit_matrix @ query_unit
        top_k_idx = np.argsort(-similarities)[:k]

        results = []
        for idx in top_k_idx:
            example_id = int(self._ids[idx])
            example = self._examples[example_id]
            results.append({
                "category": example["category"],
                "nl_query": example["nl_query"],
                "sparql": example["sparql"],
                "similarity": float(similarities[idx]),
            })
        return results


# Loaded once per process at import time -- main.py imports `retriever` directly.
retriever = RagRetriever()
