"""
One-time, offline dev tool. NOT imported or run by the running nl2sparql service.

Convenience wrapper for the single most common maintenance action: you added or edited entries
in data/nl2sparql_examples.json and need everything derived from it regenerated. Runs, in order:

  1. build_examples_embeddings.main()   -- rebuilds data/nl2sparql_examples_embeddings.csv
  2. render_examples_markdown.main()    -- rebuilds data/nl2sparql_examples.md

Run by hand (from the nl2sparql/ directory):

    python -m scripts.offline.refresh_examples

Then commit the three changed files (nl2sparql_examples.json, .csv, .md).

This does NOT touch the GraphDB schema snapshot (ontology_block.txt / known_schema.json) --
run generate_ontology_snapshot.py separately if the schema itself changed.
"""
from scripts.offline import build_examples_embeddings, render_examples_markdown


def main():
    print("== Step 1/2: rebuilding example embeddings ==")
    build_examples_embeddings.main()
    print("\n== Step 2/2: rendering examples markdown ==")
    render_examples_markdown.main()
    print("\nDone. Review and commit the updated files under scripts/data/.")


if __name__ == "__main__":
    main()
