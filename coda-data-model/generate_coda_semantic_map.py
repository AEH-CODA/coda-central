from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


WORKSPACE_DIR = Path(__file__).resolve().parent
INPUT_PATH = WORKSPACE_DIR / "coda_schema.jsonld"
OUTPUT_PATH = WORKSPACE_DIR / "coda_semantic_map_data.json"


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return slug.strip("-")


def unique_labels(labels: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for label in labels:
        if label and label not in seen:
            seen.add(label)
            result.append(label)
    return result


def normalize_schema_node(node: dict) -> dict:
    return {
        "type": node.get("@type") or node.get("type") or "schema:ClassNode",
        "classId": node.get("class") or node.get("classId"),
        "classLabel": node.get("classLabel") or node.get("class_label"),
        "aestheticLabel": node.get("aestheticLabel") or node.get("aesthetic_label"),
        "predicate": node.get("predicate"),
        "placement": node.get("placement"),
    }


def normalize_variable(name: str, variable: dict) -> dict:
    schema_reconstruction = [
        normalize_schema_node(node)
        for node in variable.get("schemaReconstruction", variable.get("schema_reconstruction", []))
    ]

    value_terms = variable.get("valueMapping", {}).get("terms") or variable.get("value_mapping", {}).get("terms", {})
    terms = [
        {
            "label": label,
            "targetClass": payload.get("targetClass") or payload.get("target_class"),
        }
        for label, payload in value_terms.items()
    ]

    path_labels = unique_labels(
        [
            node.get("aestheticLabel") or node.get("classLabel") or node.get("classId")
            for node in schema_reconstruction
            if node.get("type") == "schema:ClassNode" and not node.get("placement")
        ]
    )

    fallback_path = [variable.get("section") or "Uncategorized"]

    return {
        "name": name,
        "id": variable.get("@id", f"schema:variable/{name}"),
        "type": variable.get("@type"),
        "dataType": variable.get("dataType") or variable.get("data_type"),
        "predicate": variable.get("predicate"),
        "classId": variable.get("class"),
        "section": variable.get("section"),
        "fieldType": variable.get("fieldType") or variable.get("field_type"),
        "sqlType": variable.get("sqlType") or variable.get("sql_type"),
        "description": variable.get("description") or variable.get("local_definition") or "",
        "schemaReconstruction": schema_reconstruction,
        "valueMapping": terms,
        "path": path_labels or fallback_path,
    }


def create_tree_node(node_id: str, label: str, node_type: str, path: list[str]) -> dict:
    return {
        "id": node_id,
        "label": label,
        "type": node_type,
        "path": path,
        "children": [],
        "variableIds": [],
    }


def count_variables(node: dict) -> int:
    if node.get("type") == "variable":
        return 1
    return sum(count_variables(child) for child in node.get("children", []))


def build_tree(variables: list[dict]) -> dict:
    root = create_tree_node("root", "CODA Semantic Map", "root", [])
    tree_index = {root["id"]: root}

    for variable in variables:
        current = root
        segments = variable["path"]

        for index, segment in enumerate(segments):
            segment_path = segments[: index + 1]
            node_id = f"group:{'/'.join(slugify(part) for part in segment_path)}"
            child = tree_index.get(node_id)

            if child is None:
                child = create_tree_node(node_id, segment, "group", segment_path)
                tree_index[node_id] = child
                current["children"].append(child)

            current = child
            if variable["name"] not in current["variableIds"]:
                current["variableIds"].append(variable["name"])

        current["children"].append(
            {
                "id": f"variable:{variable['name']}",
                "label": variable["name"],
                "type": "variable",
                "path": variable["path"],
                "variableId": variable["name"],
            }
        )

    return root


def build_output(schema: dict) -> dict:
    variables_object = schema.get("schema", {}).get("variables", {})
    variables = [
        normalize_variable(name, variable) for name, variable in variables_object.items()
    ]

    groups = {segment for variable in variables for segment in variable["path"]}
    mapped_variable_count = sum(1 for variable in variables if variable["valueMapping"])
    value_mapping_count = sum(len(variable["valueMapping"]) for variable in variables)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "title": schema.get("title", "CODA Semantic Map"),
        "sourceFile": "coda_schema.jsonld",
        "stats": {
            "variableCount": len(variables),
            "mappedVariableCount": mapped_variable_count,
            "groupCount": len(groups),
            "valueMappingCount": value_mapping_count,
        },
        "tree": build_tree(variables),
        "variables": variables,
    }


def main() -> None:
    schema = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    output = build_output(schema)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"Generated {OUTPUT_PATH.name} with {output['stats']['variableCount']} variables and "
        f"{output['stats']['groupCount']} groups."
    )


if __name__ == "__main__":
    main()