# CODA Semantic Map Explorer

This workspace now includes an AYA-style semantic map explorer generated from `coda_schema.jsonld`.

## Files

- `generate_coda_semantic_map.py`: Reads `coda_schema.jsonld` and writes `coda_semantic_map_data.json`.
- `build_pages_site.py`: Rebuilds map data and prepares the publishable `site/` folder for GitHub Pages.
- `coda_semantic_map_viewer.html`: Standalone browser viewer for the generated semantic map.
- `coda_semantic_map_viewer.js`: Client-side logic for the explorer UI.
- `coda_semantic_map_data.json`: Generated navigation/data payload consumed by the viewer.
- `.github/workflows/deploy-pages.yml`: Auto-deploys `site/` to GitHub Pages on `main` pushes.

## Generate the data

```bash
/Users/varnitamathur/coda-aeh/coda-data-model/.venv/bin/python generate_coda_semantic_map.py
```

## View it locally

Serve the workspace directory with any static file server, then open `coda_semantic_map_viewer.html`.

One simple option is:

```bash
cd /Users/varnitamathur/coda-aeh/coda-data-model
/Users/varnitamathur/coda-aeh/coda-data-model/.venv/bin/python generate_coda_semantic_map.py
/Users/varnitamathur/coda-aeh/coda-data-model/.venv/bin/python -m http.server 8000
```

## Deploy to GitHub Pages

1. Push these changes to the `main` branch.
2. In GitHub repo settings, open **Pages** and ensure **Source** is set to **GitHub Actions**.
3. The workflow `Deploy CODA Viewer to GitHub Pages` will build and publish automatically.

Expected URL (project site):

- `https://aeh-coda.github.io/coda-data-model/`
- Viewer page: `https://aeh-coda.github.io/coda-data-model/coda_semantic_map_viewer.html`

## What it shows

- Group hierarchy derived from each variable's `schemaReconstruction`
- Variable detail cards with metadata and descriptions
- Value mapping tables showing local values and `targetClass`
- Search across groups, variables, descriptions, and mapped values