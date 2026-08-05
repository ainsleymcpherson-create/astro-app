"""
One-time preprocessing script: chunk reference documents and embed them.
Run this in Colab whenever you add/change reference material, then commit
the resulting data/reference_embeddings.json to your repo.

Expects reference_docs/ to contain subfolders by category, e.g.:
    reference_docs/
        personal_readings/
            dignities.pdf
            house_meanings.pdf
        synastry/
            synastry_aspects.pdf

Each chunk is tagged with its category (the subfolder name) so retrieval
can later be filtered to only the relevant reading type.

Requires: pip install voyageai pypdf
Set VOYAGE_API_KEY as an environment variable before running.
"""

import os
import json
import re
from pathlib import Path

import voyageai
from pypdf import PdfReader

# --- CONFIG ---
SOURCE_DIR = Path("reference_docs")        # contains category subfolders
OUTPUT_PATH = Path("data/reference_embeddings.json")
EMBED_MODEL = "voyage-3"                    # good general-purpose Voyage model
MIN_CHUNK_CHARS = 200                       # skip tiny fragments
VALID_EXTENSIONS = {".pdf", ".txt", ".md"}


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, source_name: str, category: str) -> list[dict]:
    """
    Split on blank-line-separated sections rather than fixed character
    windows, so a chunk stays semantically whole (e.g. one planet-in-sign
    entry, one house description).
    """
    raw_sections = re.split(r"\n\s*\n", text)

    chunks = []
    for section in raw_sections:
        section = section.strip()
        if len(section) >= MIN_CHUNK_CHARS:
            chunks.append({
                "text": section,
                "source": source_name,
                "category": category,
            })
    return chunks


def find_category_folders(source_dir: Path) -> list[Path]:
    """Return immediate subfolders of source_dir; each one is a category."""
    return [p for p in source_dir.iterdir() if p.is_dir()]


def main():
    client = voyageai.Client()  # reads VOYAGE_API_KEY from env

    if not SOURCE_DIR.exists():
        print(f"'{SOURCE_DIR}' not found — create it and add category subfolders.")
        return

    category_folders = find_category_folders(SOURCE_DIR)

    all_chunks = []

    if category_folders:
        # Subfolder mode: reference_docs/<category>/<files>
        for folder in category_folders:
            category = folder.name
            for file_path in folder.glob("*"):
                if file_path.suffix.lower() not in VALID_EXTENSIONS:
                    continue
                text = extract_text(file_path)
                chunks = chunk_text(text, source_name=file_path.name, category=category)
                all_chunks.extend(chunks)
                print(f"[{category}] {file_path.name}: {len(chunks)} chunks")
    else:
        # Fallback: files directly in reference_docs/, no category
        for file_path in SOURCE_DIR.glob("*"):
            if file_path.suffix.lower() not in VALID_EXTENSIONS:
                continue
            text = extract_text(file_path)
            chunks = chunk_text(text, source_name=file_path.name, category="general")
            all_chunks.extend(chunks)
            print(f"{file_path.name}: {len(chunks)} chunks")

    if not all_chunks:
        print("No chunks found — check reference_docs/ structure and file types.")
        return

    # Embed in batches (Voyage has batch limits; 128 is safe)
    texts = [c["text"] for c in all_chunks]
    embeddings = []
    batch_size = 128
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        result = client.embed(batch, model=EMBED_MODEL, input_type="document")
        embeddings.extend(result.embeddings)

    for chunk, vector in zip(all_chunks, embeddings):
        chunk["embedding"] = vector

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f)

    categories_found = sorted(set(c["category"] for c in all_chunks))
    print(f"\nSaved {len(all_chunks)} chunks with embeddings to {OUTPUT_PATH}")
    print(f"Categories: {categories_found}")


if __name__ == "__main__":
    main()
