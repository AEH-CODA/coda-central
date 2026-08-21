"""
One-time, offline dev tool. NOT imported or run by the running nl2sparql service.

Renders data/nl2sparql_examples.json into data/nl2sparql_examples.md -- a human-readable mirror
of the RAG corpus, grouped by category. Purely a documentation aid; nothing at runtime reads the
.md file.

Run by hand whenever data/nl2sparql_examples.json gains/changes entries (from the nl2sparql/
directory):

    python -m scripts.offline.render_examples_markdown

(Or run scripts/offline/refresh_examples.py, which also rebuilds the embeddings CSV.)

New categories are picked up automatically (rendered under a title-cased heading derived from
the category slug) -- CATEGORY_TITLES below only overrides the handful worth a nicer heading.
"""
import json
from collections import defaultdict

from scripts.embedding_config import EXAMPLES_MARKDOWN_PATH, EXAMPLES_PATH

CATEGORY_TITLES = {
    "patient_lookup": "Patient lookup",
    "visit_lookup": "Visit lookup",
    "vitals": "Vitals (blood pressure)",
    "diagnosis": "Diagnosis",
    "investigation": "Investigation (labs/tests)",
    "vision": "Vision",
    "refraction": "Refraction",
    "exam_finding": "Anterior segment exam findings",
    "systemic_history": "Systemic history",
    "drug_prescription": "Drug prescriptions",
    "procedure_advice": "Procedure advice",
    "general_advice": "General advice (glasses)",
    "treatment_advice": "Treatment advice",
    "refraction_correction": "Refraction correction advice",
    "surgery_advice": "Surgery advice",
    "oct": "OCT details",
    "cohort_filter": "Cohort filtering (patients matching a visit criterion → all their records)",
    "text_search": "Fuzzy / keyword text search over free-text fields",
    "multi_hop": "Multi-hop / cross-entity",
    "aggregation": "Aggregation",
}

CAVEATS_BLOCK = """**Known data-sparsity caveat:** `SurgeryAdvice` has exactly 1 instance in the entire repository (patient
`CODA-PT-3B8B2BB5`, diagnosed with Immature cataract). Any query joining a diagnosis to `SurgeryAdvice` is technically
answerable but not statistically meaningful -- treat as "insufficient surgery data", not a real population pattern.
No example pair is included for this to avoid the RAG corpus reinforcing single-instance answers as reliable. Likewise,
`OctDetails.image_eye_laterality` is only populated on 2 of 1907 scans -- treat as effectively unset. Separately, a small
number of `scan_id` values are shared across two different patients/visits in the source data -- this is a genuine
upstream data-quality issue, not a query bug; don't assume scan_id is a reliable unique key.
"""


def render(examples: list[dict]) -> str:
    by_cat = defaultdict(list)
    for ex in examples:
        by_cat[ex["category"]].append(ex)

    lines = []
    lines.append("# NL2SPARQL Example Pairs -- `june-sample`\n")
    lines.append(f"**{len(examples)} natural-language <-> SPARQL pairs**, each executed against the live `june-sample` GraphDB repository ")
    lines.append("(`http://localhost:7200/repositories/june-sample`) and confirmed to return a correct result set.\n")
    lines.append("Companion machine-readable file: `nl2sparql_examples.json` (same content, structured as a JSON array of ")
    lines.append("`{category, nl_query, sparql}` objects) -- this is the RAG retrieval corpus for the NL2SPARQL service. ")
    lines.append("**Whenever this file changes, run `python -m scripts.offline.refresh_examples` from the nl2sparql/ ")
    lines.append("directory and commit the updated `nl2sparql_examples_embeddings.csv` and `nl2sparql_examples.md`** -- ")
    lines.append("the running service loads the CSV at startup and will refuse to start if its row count doesn't match ")
    lines.append("this file.\n")
    lines.append("All queries use `PREFIX ns1: <http://clinical-example.org/ontology/>`. See `NL2SPARQL_JUNE_SAMPLE_SCHEMA_REPORT.md` ")
    lines.append("(repo root) for the full schema/data-dictionary background these examples are grounded in.\n")
    lines.append(CAVEATS_BLOCK)
    lines.append("---\n")

    ordered_categories = [c for c in CATEGORY_TITLES if c in by_cat]
    ordered_categories += sorted(c for c in by_cat if c not in CATEGORY_TITLES)

    for cat in ordered_categories:
        title = CATEGORY_TITLES.get(cat, cat.replace("_", " ").title())
        lines.append(f"## {title}\n")
        for ex in by_cat[cat]:
            lines.append(f"**NL:** {ex['nl_query']}\n")
            lines.append("```sparql")
            lines.append(ex["sparql"])
            lines.append("```\n")

    return "\n".join(lines)


def main():
    with open(EXAMPLES_PATH) as f:
        examples = json.load(f)
    print(f"Loaded {len(examples)} examples from {EXAMPLES_PATH}")

    markdown = render(examples)
    with open(EXAMPLES_MARKDOWN_PATH, "w") as f:
        f.write(markdown)
    print(f"Wrote {EXAMPLES_MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
