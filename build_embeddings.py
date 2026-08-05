"""
One-time preprocessing script: chunk reference documents and embed them.
Run this in Colab whenever you add/change reference material, then commit
the resulting data/reference_embeddings.json to your repo.

Supports arbitrarily nested category folders, e.g.:
    reference_docs/
        personal_readings/
            dignities.pdf
        synastry_readings/
            professional_synastry/
                workplace_notes.pdf
            relationship_synastry/
                synastry_prompt_tweaks.pdf
            parent_child_synastry/
                family_notes.pdf

Each chunk is tagged with:
  - category: the full relative folder path, e.g.
    "synastry_readings/relationship_synastry"
  - top_category: just the first path segment, e.g. "synastry_readings"
This lets retrieval filter either broadly (top_category) or precisely
(category) -- see retrieval.py.

NOTE ON FILE TYPES: Google Drive ".gdoc" files are NOT real documents --
they're small pointer/shortcut files linking back to the live Google
Doc, with no actual text content. Open each doc directly in Google
Docs and use File -> Download -> PDF (or "Web page (.html)"/plain
text) to get a real file, then upload THAT into reference_docs/.
".gdoc" files are silently skipped by this script.

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
SOURCE_DIR = Path("reference_docs")
OUTPUT_PATH = Path("data/reference_embeddings.json")
EMBED_MODEL = "voyage-3"
MIN_CHUNK_CHARS = 200
VALID_EXTENSIONS = {".pdf", ".txt", ".md"}


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, source_name: str, category: str, top_category: str) -> list[dict]:
    """
    Split on blank-line-separated sections rather than fixed character
    windows, so a chunk stays semantically whole.
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
                "top_category": top_category,
            })
    return chunks


def main():
    client = voyageai.Client()  # reads VOYAGE_API_KEY from env

    if not SOURCE_DIR.exists():
        print(f"'{SOURCE_DIR}' not found — create it and add category subfolders.")
        return

    all_chunks = []
    skipped_gdocs = []

    # Walk every file at any depth under reference_docs/
    for file_path in SOURCE_DIR.rglob("*"):
        if not file_path.is_file():
            continue

        if file_path.suffix.lower() == ".gdoc":
            skipped_gdocs.append(str(file_path.relative_to(SOURCE_DIR)))
            continue

        if file_path.suffix.lower() not in VALID_EXTENSIONS:
            continue

        # category = the file's folder path relative to reference_docs,
        # e.g. "synastry_readings/relationship_synastry"
        relative_dir = file_path.parent.relative_to(SOURCE_DIR)
        category = relative_dir.as_posix()  # forward slashes, cross-platform
        if category == ".":
            category = "general"  # file sitting directly in reference_docs/
        top_category = category.split("/")[0]

        text = extract_text(file_path)
        chunks = chunk_text(
            text, source_name=file_path.name,
            category=category, top_category=top_category,
        )
        all_chunks.extend(chunks)
        print(f"[{category}] {file_path.name}: {len(chunks)} chunks")

    if skipped_gdocs:
        print(f"\nSkipped {len(skipped_gdocs)} .gdoc shortcut file(s) "
              f"(not real documents -- see docstring):")
        for g in skipped_gdocs:
            print(f"  - {g}")

    if not all_chunks:
        print("\nNo chunks found — check reference_docs/ structure and file types.")
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
