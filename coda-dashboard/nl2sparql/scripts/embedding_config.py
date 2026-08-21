"""
Shared constants for the RAG pipeline -- the single source of truth for where every generated
artifact lives. Imported by:
  - scripts/offline/*.py  (one-time dev tools that generate the files under scripts/data/)
  - scripts/runtime/*.py  (the running service, which only ever reads those files)
  - Dockerfile            (build-time embedding-model cache warmup)

Keeping the embedding model name in one place guarantees the corpus and the incoming query are
always embedded with the exact same model -- a mismatch here would silently make retrieval
meaningless. Keeping the data paths in one place means scripts/data/ can be reorganized without
hunting down hardcoded paths elsewhere.
"""
import os

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
FASTEMBED_CACHE_DIR = os.path.join(SCRIPT_DIR, "..", ".fastembed_cache")

EXAMPLES_PATH = os.path.join(DATA_DIR, "nl2sparql_examples.json")
EXAMPLES_MARKDOWN_PATH = os.path.join(DATA_DIR, "nl2sparql_examples.md")
EMBEDDINGS_CSV_PATH = os.path.join(DATA_DIR, "nl2sparql_examples_embeddings.csv")
ONTOLOGY_BLOCK_PATH = os.path.join(DATA_DIR, "ontology_block.txt")
KNOWN_SCHEMA_PATH = os.path.join(DATA_DIR, "known_schema.json")
