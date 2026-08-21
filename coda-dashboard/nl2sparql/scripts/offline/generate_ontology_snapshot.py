"""
One-time, offline dev tool. NOT imported or run by the running nl2sparql service.

Queries the live GraphDB repository (GRAPHDB_URL / GRAPHDB_REPO from .env) and writes two
static, checked-in files under scripts/data/ that the running service reads at import time:

  - data/ontology_block.txt : the "Classes / Key Relationships / Attribute Reference" text
                               spliced into the NL2SPARQL prompt (replaces the old hand-typed
                               block).
  - data/known_schema.json  : flat sets of real class/predicate local names, used by main.py's
                               post-generation validation step.

Run by hand whenever the GraphDB schema changes materially (from the nl2sparql/ directory):

    python -m scripts.offline.generate_ontology_snapshot

The running service never calls GraphDB itself -- rerun this and commit the two output files.
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

from scripts.embedding_config import KNOWN_SCHEMA_PATH, ONTOLOGY_BLOCK_PATH

load_dotenv()

GRAPHDB_URL = os.getenv("GRAPHDB_URL")
GRAPHDB_REPO = os.getenv("GRAPHDB_REPO")
ONT_NS = "http://clinical-example.org/ontology/"

# Meta/RDF/OWL/RDFS classes and properties that describe the ontology itself, not clinical data.
# These come from the vocabulary's self-description triples and would just be noise in the prompt.
META_NAMESPACES = (
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/2002/07/owl#",
    "http://proton.semanticweb.org/protonsys#",
)

# Skip these ontology-namespace predicates too -- they describe the schema, not instance data.
META_LOCAL_PREDICATES = {"subPropertyOf", "subClassOf", "domain", "range"}

MAX_ENUM_VALUES = 15          # only surface a "closed vocabulary" hint if <= this many distinct values
MAX_ENUM_COVERAGE_CHECK = 400  # cap on distinct-value query result size we bother enumerating
MIN_CLASS_INSTANCES_FOR_ENUM = 10  # skip enum detection for classes this sparse -- not statistically meaningful


def looks_like_non_enumerable(predicate_local_name: str) -> bool:
    """Date and ID-like fields can have <= MAX_ENUM_VALUES distinct values purely by sampling
    coincidence (e.g. a sparse class), not because they're a real closed vocabulary. Free-text
    dates in particular are already covered by the gotchas cheat-sheet -- listing a handful of
    sample date strings as if they were the only valid values would actively mislead the prompt."""
    name = predicate_local_name.lower()
    return "date" in name or name.endswith("_id") or name == "id"


def run_query(query: str) -> dict:
    endpoint = f"{GRAPHDB_URL}/repositories/{GRAPHDB_REPO}"
    resp = requests.post(
        endpoint,
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"query": query},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def local_name(uri: str) -> str:
    return uri.rstrip("/").split("/")[-1].split("#")[-1]


def is_meta_uri(uri: str) -> bool:
    return any(uri.startswith(ns) for ns in META_NAMESPACES)


def get_classes() -> list[tuple[str, int]]:
    """Return [(class_local_name, instance_count), ...] for clinical-example.org classes only."""
    q = """
    SELECT ?class (COUNT(?s) as ?count) WHERE {
      ?s a ?class .
      FILTER(STRSTARTS(STR(?class), "%s"))
    } GROUP BY ?class ORDER BY DESC(?count)
    """ % ONT_NS
    data = run_query(q)
    out = []
    for b in data["results"]["bindings"]:
        out.append((local_name(b["class"]["value"]), int(b["count"]["value"])))
    return out


def get_class_properties(class_local_name: str) -> list[dict]:
    """For one class, return per-property profile: name, count, whether it's an object property
    (points to another class instance) or a datatype property, datatype, and a sample value."""
    q = """
    PREFIX ns1: <%s>
    SELECT ?p (COUNT(*) as ?cnt) (SAMPLE(?o) as ?sample) (SAMPLE(DATATYPE(?o)) as ?dt)
           (SAMPLE(isURI(?o)) as ?isUri)
    WHERE {
      ?s a ns1:%s .
      ?s ?p ?o .
      FILTER(?p != rdf:type)
      FILTER(STRSTARTS(STR(?p), "%s"))
    } GROUP BY ?p ORDER BY DESC(?cnt)
    """ % (ONT_NS, class_local_name, ONT_NS)
    data = run_query(q)
    props = []
    for b in data["results"]["bindings"]:
        p_local = local_name(b["p"]["value"])
        is_uri = b.get("isUri", {}).get("value") == "true"
        props.append({
            "name": p_local,
            "count": int(b["cnt"]["value"]),
            "is_object_property": is_uri,
            "datatype": local_name(b["dt"]["value"]) if b.get("dt") else None,
            "sample": b.get("sample", {}).get("value", ""),
        })
    return props


def get_object_property_targets(predicate_local_name: str) -> list[str]:
    """For an object property (e.g. hasAdviceItem), return the distinct rdf:type class names
    its objects actually have. This is what generically discovers fan-out relationships like
    hasAdviceItem -> {DrugPrescription, ProcedureAdvice, GeneralAdvice, TreatmentAdvice,
    RefractionCorrection, SurgeryAdvice} without hardcoding any of them."""
    q = """
    PREFIX ns1: <%s>
    SELECT ?targetClass (COUNT(*) as ?count) WHERE {
      ?s ns1:%s ?o .
      ?o a ?targetClass .
      FILTER(STRSTARTS(STR(?targetClass), "%s"))
    } GROUP BY ?targetClass ORDER BY DESC(?count)
    """ % (ONT_NS, predicate_local_name, ONT_NS)
    data = run_query(q)
    return [local_name(b["targetClass"]["value"]) for b in data["results"]["bindings"]]


def get_distinct_values(class_local_name: str, predicate_local_name: str) -> list[tuple[str, int]] | None:
    """Return [(value, count), ...] for a datatype property if it looks like a small closed
    vocabulary (<= MAX_ENUM_VALUES distinct values), else None."""
    q = """
    PREFIX ns1: <%s>
    SELECT ?v (COUNT(*) as ?count) WHERE {
      ?s a ns1:%s ; ns1:%s ?v .
    } GROUP BY ?v ORDER BY DESC(?count) LIMIT %d
    """ % (ONT_NS, class_local_name, predicate_local_name, MAX_ENUM_COVERAGE_CHECK)
    data = run_query(q)
    bindings = data["results"]["bindings"]
    if len(bindings) == 0 or len(bindings) > MAX_ENUM_VALUES:
        return None
    return [(b["v"]["value"], int(b["count"]["value"])) for b in bindings]


def main():
    if not GRAPHDB_URL or not GRAPHDB_REPO:
        print("ERROR: GRAPHDB_URL / GRAPHDB_REPO not set in nl2sparql/.env", file=sys.stderr)
        sys.exit(1)

    print(f"Querying {GRAPHDB_URL}/repositories/{GRAPHDB_REPO} ...")
    classes = get_classes()
    print(f"Found {len(classes)} clinical-example.org classes with instances.")

    known_classes = set()
    known_predicates = set()
    class_profiles = {}          # class_name -> list[prop dict]
    object_property_targets = {}  # predicate_name -> list[target class names]
    enumerations = {}             # (class_name, prop_name) -> list[(value, count)]

    for cls, count in classes:
        known_classes.add(cls)
        props = get_class_properties(cls)
        class_profiles[cls] = props
        for p in props:
            known_predicates.add(p["name"])
            if p["is_object_property"]:
                if p["name"] not in object_property_targets:
                    targets = get_object_property_targets(p["name"])
                    object_property_targets[p["name"]] = targets
                    known_classes.update(targets)
            else:
                if p["name"] in META_LOCAL_PREDICATES:
                    continue
                if count < MIN_CLASS_INSTANCES_FOR_ENUM:
                    continue
                if looks_like_non_enumerable(p["name"]):
                    continue
                enum_key = (cls, p["name"])
                if enum_key not in enumerations:
                    vals = get_distinct_values(cls, p["name"])
                    if vals:
                        enumerations[enum_key] = vals
        print(f"  {cls}: {count} instances, {len(props)} properties profiled")

    # ---------- render ontology_block.txt ----------
    lines = []
    lines.append("Ontology (auto-generated from live GraphDB schema -- see scripts/generate_ontology_snapshot.py)")
    lines.append(f"PREFIX ns1: <{ONT_NS}>")
    lines.append("")
    lines.append("Classes: " + ", ".join(cls for cls, _ in classes))
    lines.append("")
    lines.append("Key Relationships (predicate -> target class(es); '|' = a property that can point to more than one type):")
    for pred, targets in sorted(object_property_targets.items()):
        lines.append(f"- {pred} -> " + " | ".join(targets))
    lines.append("")
    lines.append("Attribute Reference (class: datatype properties, with sample values):")
    for cls, _ in classes:
        datatype_props = [p for p in class_profiles[cls] if not p["is_object_property"]]
        if not datatype_props:
            continue
        parts = []
        for p in datatype_props:
            parts.append(p["name"])
        lines.append(f"- {cls}: " + ", ".join(parts))
    lines.append("")
    lines.append("Closed vocabularies observed (use these exact values in FILTERs where relevant):")
    for (cls, prop), vals in sorted(enumerations.items()):
        val_str = ", ".join(f'"{v}"' for v, _ in vals)
        lines.append(f"- {cls}.{prop}: {val_str}")

    with open(ONTOLOGY_BLOCK_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nWrote {ONTOLOGY_BLOCK_PATH} ({len(lines)} lines)")

    # ---------- render known_schema.json ----------
    known_schema = {
        "classes": sorted(known_classes),
        "predicates": sorted(known_predicates),
    }
    with open(KNOWN_SCHEMA_PATH, "w") as f:
        json.dump(known_schema, f, indent=2)
    print(f"Wrote {KNOWN_SCHEMA_PATH} "
          f"({len(known_schema['classes'])} classes, {len(known_schema['predicates'])} predicates)")


if __name__ == "__main__":
    main()
