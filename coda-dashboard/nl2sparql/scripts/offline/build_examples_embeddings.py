"""
One-time, offline dev tool. NOT imported or run by the running nl2sparql service.

Embeds every nl_query in data/nl2sparql_examples.json exactly once and writes the vectors to a
static, checked-in CSV under data/. The running service (scripts/runtime/rag_retriever.py) only
ever loads this CSV and embeds the single incoming NL query per request -- it never re-embeds
the corpus.

Run by hand whenever data/nl2sparql_examples.json gains/changes entries (from the nl2sparql/
directory):

    python -m scripts.offline.build_examples_embeddings

(Or run scripts/offline/refresh_examples.py, which also regenerates the markdown mirror.)
"""
import json

import pandas as pd
from fastembed import TextEmbedding

from scripts.embedding_config import (
    EMBEDDING_MODEL_NAME,
    EMBEDDINGS_CSV_PATH,
    EXAMPLES_PATH,
    FASTEMBED_CACHE_DIR,
)


def main():
    with open(EXAMPLES_PATH) as f:
        examples = json.load(f)
    print(f"Loaded {len(examples)} examples from {EXAMPLES_PATH}")

    model = TextEmbedding(model_name=EMBEDDING_MODEL_NAME, cache_dir=FASTEMBED_CACHE_DIR)
    nl_queries = [ex["nl_query"] for ex in examples]
    vectors = list(model.embed(nl_queries))
    dim = len(vectors[0])
    print(f"Embedded {len(vectors)} queries, dim={dim}")

    rows = []
    for i, (ex, vec) in enumerate(zip(examples, vectors)):
        row = {"id": i, "category": ex["category"], "nl_query": ex["nl_query"]}
        for d in range(dim):
            row[f"dim_{d}"] = float(vec[d])
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(EMBEDDINGS_CSV_PATH, index=False)
    print(f"Wrote {EMBEDDINGS_CSV_PATH} ({df.shape[0]} rows, {df.shape[1]} columns)")


if __name__ == "__main__":
    main()
