from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SITE_DIR = ROOT / "site"

TOP_LEVEL_SUFFIXES = {".html", ".js", ".json", ".jsonld", ".css"}
TOP_LEVEL_EXCLUDE = {
    "package-lock.json",
    "CODA-Data-Model-v0.0.2-DataDictionary.csv",
    "CODA-Data-Model-v0.0.2-Vocabulary.csv",
}
DIRECTORIES_TO_COPY = ["data_model_html"]


def run_generator() -> None:
    generator = ROOT / "generate_coda_semantic_map.py"
    subprocess.run([sys.executable, str(generator)], check=True, cwd=ROOT)


def reset_site_dir() -> None:
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)


def copy_top_level_files() -> None:
    for entry in ROOT.iterdir():
        if not entry.is_file():
            continue
        if entry.name in TOP_LEVEL_EXCLUDE:
            continue
        if entry.suffix.lower() in TOP_LEVEL_SUFFIXES:
            shutil.copy2(entry, SITE_DIR / entry.name)


def copy_required_directories() -> None:
    for directory_name in DIRECTORIES_TO_COPY:
        source = ROOT / directory_name
        target = SITE_DIR / directory_name
        if source.exists() and source.is_dir():
            shutil.copytree(source, target)


def write_nojekyll() -> None:
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    run_generator()
    reset_site_dir()
    copy_top_level_files()
    copy_required_directories()
    write_nojekyll()
    print(f"Prepared GitHub Pages artifact in {SITE_DIR}")


if __name__ == "__main__":
    main()
