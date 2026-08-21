from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import re
import json
import logging
from groq import Groq
from scripts.runtime.postprocessing import strip_sparql, header_footer
from scripts.runtime.rag_retriever import retriever
from scripts.embedding_config import ONTOLOGY_BLOCK_PATH, KNOWN_SCHEMA_PATH

app = FastAPI(title="NL to SPARQL Service - RAG-assisted")

load_dotenv()

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# Note: GRAPHDB_URL / GRAPHDB_REPO are intentionally not read here -- this service never calls
# GraphDB itself. They're read by the offline dev tools in scripts/generate_ontology_snapshot.py,
# run by hand to regenerate ontology_block.txt / known_schema.json when the schema changes.

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY not set")

groq_client = Groq(api_key=GROQ_API_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Static, one-time-generated schema artifacts (see scripts/generate_ontology_snapshot.py).
# Loaded once at import time. The running service never queries GraphDB itself; rerun that
# script by hand and commit its output whenever the GraphDB schema changes materially.
# ----------------------------------------------------------------------------
with open(ONTOLOGY_BLOCK_PATH) as f:
    ONTOLOGY_BLOCK = f.read()

with open(KNOWN_SCHEMA_PATH) as f:
    _known_schema = json.load(f)
    KNOWN_TOKENS = set(_known_schema["classes"]) | set(_known_schema["predicates"])

GOTCHAS_BLOCK = """Known data quirks -- apply these when relevant:
- Refraction fields (reSphere, reCylinder, reAxis, rePHVA, leSphere, leCylinder, leAxis, lePHVA) and
  number_of_sittings_advice / sitting_num_completed are stored as xsd:string even though they look
  numeric. Cast with xsd:decimal(?x) or xsd:integer(?x) before any numeric comparison.
- age is free text like "65 Years 4 Months 17 Days", not a number. For age-range questions, extract
  the leading integer, e.g. BIND(xsd:integer(REPLACE(?age, "^(\\\\d+)\\\\s+Years?.*$", "$1")) AS ?ageYears).
- Only visitDate is a real xsd:date. Every advice-item date (drug_advice_date, procedure_advice_date,
  surgery_advice_date, treatment_advice_date, refractive_advice_date) is an unreliable xsd:string,
  often empty -- do not attempt to xsd:date-cast or numerically compare these.
- Boolean-like fields are inconsistently cased across classes (e.g. "true" vs "True") -- match with
  LCASE(?x) = "true" rather than an exact string match when checking a boolean-like field.
- Diagnosis, ExamFinding, VisionItem, and RefractionItem are all independent 1-to-many children of
  Visit. Joining more than one of them directly in a flat SELECT multiplies rows (cartesian product).
  When a query needs two or more of them together, use a GROUP_CONCAT subselect per child instead.
- Prefer human-readable columns over raw IDs (e.g. diagnosisName over diagnosis, visitDate over visit)
  unless the user explicitly asks for the identifier or it's the only way to answer the question.
"""

class NLQuery(BaseModel):
    query: str

def _format_examples_block(examples: list[dict]) -> str:
    parts = ["Examples (real, verified queries against this exact schema -- follow their join and filter patterns; do not copy literal values unless they match the user's query):\n"]
    for ex in examples:
        parts.append(f"NL: {ex['nl_query']}\nSPARQL:\n{ex['sparql']}\n")
    return "\n".join(parts)

def build_smart_prompt(nl_query: str, retrieved_examples: list[dict]) -> str:
    """Build the translation prompt from the static schema snapshot + retrieved few-shot examples."""

    examples_block = _format_examples_block(retrieved_examples)

    prompt = f"""You are a SPARQL expert. Generate minimal, efficient SELECT queries ONLY.

{ONTOLOGY_BLOCK}

{GOTCHAS_BLOCK}

{examples_block}

User Query: {nl_query}

Return ONLY a valid SPARQL SELECT query. No explanations."""

    return prompt

def _extract_ns1_tokens(sparql_query: str) -> set[str]:
    """Extract every ns1:XXX local name referenced in the query (class or predicate position)."""
    return set(re.findall(r"ns1:(\w+)", sparql_query))

def _find_unknown_tokens(sparql_query: str) -> list[str]:
    used = _extract_ns1_tokens(sparql_query)
    unknown = sorted(used - KNOWN_TOKENS)
    return unknown

def _call_groq(prompt: str, extra_system_note: str = "") -> str:
    system_content = (
        "You are a SPARQL expert generating minimal, efficient queries against the given ontology. "
        "Only use classes and predicates that appear in the Ontology/Attribute Reference sections -- "
        "never invent or guess a predicate name. Prefer readable display columns "
        "(e.g. diagnosisName, visitDate, systolicBP, drug_name) over raw ID columns unless the user "
        "explicitly asks for the identifier."
    )
    if extra_system_note:
        system_content += " " + extra_system_note

    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0
    )
    return response.choices[0].message.content.strip()

def _clean_and_validate_shape(raw_text: str) -> dict:
    """Strip formatting and do the cheap structural checks. Returns either
    {"ok": True, "sparql": ...} or {"ok": False, "status": "ERROR", "reason": ...}."""
    sparql_query = strip_sparql(raw_text)

    if sparql_query.startswith("{"):
        return {"ok": False, "status": "ERROR", "reason": sparql_query}

    if "SELECT" not in sparql_query.upper():
        return {"ok": False, "status": "ERROR", "reason": "Model did not return a SELECT query"}

    return {"ok": True, "sparql": header_footer(sparql_query)}

@app.post("/translate")
def translate(nl: NLQuery):
    nl_query = nl.query

    try:
        logger.info(f"Processing: {nl_query}")

        retrieved_examples = retriever.retrieve(nl_query, k=5)
        logger.info(f"Retrieved examples: {[e['nl_query'] for e in retrieved_examples]}")

        prompt = build_smart_prompt(nl_query, retrieved_examples)

        raw = _call_groq(prompt)
        logger.info(f"Generated SPARQL (attempt 1): {raw}")

        shape_check = _clean_and_validate_shape(raw)
        if not shape_check["ok"]:
            return {"status": shape_check["status"], "reason": shape_check["reason"]}
        sparql_query = shape_check["sparql"]

        unknown_tokens = _find_unknown_tokens(sparql_query)

        if unknown_tokens:
            logger.warning(f"Unknown schema tokens in attempt 1: {unknown_tokens}")
            correction_note = (
                f"Your previous answer used undefined predicate/class name(s): "
                f"{', '.join(unknown_tokens)}. These do not exist in this ontology -- do not use them. "
                f"Re-read the Ontology and Attribute Reference sections and only use names listed there."
            )
            raw_retry = _call_groq(prompt, extra_system_note=correction_note)
            logger.info(f"Generated SPARQL (attempt 2, corrective retry): {raw_retry}")

            retry_shape_check = _clean_and_validate_shape(raw_retry)
            if retry_shape_check["ok"]:
                retry_unknown_tokens = _find_unknown_tokens(retry_shape_check["sparql"])
                if not retry_unknown_tokens:
                    return {"sparql": retry_shape_check["sparql"], "status": "SUCCESS"}
                # Retry still has unknown tokens -- surface a warning rather than silently
                # returning a query that will execute and quietly yield zero/wrong rows.
                return {
                    "sparql": retry_shape_check["sparql"],
                    "status": "WARNING",
                    "unknown_tokens": retry_unknown_tokens,
                    "reason": "Generated SPARQL references predicate/class names not found in the schema; results may be empty or incorrect.",
                }
            # Retry didn't even produce a valid SELECT shape -- fall back to the first attempt,
            # flagged, rather than discarding it entirely.
            return {
                "sparql": sparql_query,
                "status": "WARNING",
                "unknown_tokens": unknown_tokens,
                "reason": "Generated SPARQL references predicate/class names not found in the schema; results may be empty or incorrect.",
            }

        return {"sparql": sparql_query, "status": "SUCCESS"}

    except Exception as e:
        logger.error(f"Error: {e}")
        return {"status": "ERROR", "reason": str(e)}
