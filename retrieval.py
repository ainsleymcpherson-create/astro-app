"""
Runtime retrieval module. Import this into app.py or prompt_builder.py.

Loads the precomputed embeddings JSON once, embeds the incoming query,
and returns the top-k most similar chunks via plain numpy cosine
similarity -- no vector DB needed at this scale.

Category filtering supports nesting: passing category="synastry_readings"
matches every chunk under that top-level folder, including nested ones
like "synastry_readings/relationship_synastry". Passing the more
specific "synastry_readings/relationship_synastry" matches only that
subfolder. Matching is by exact string OR by prefix + "/", so
"synastry_readings" never accidentally matches an unrelated folder
like "synastry_readings_old".

Requires: pip install voyageai numpy
"""

import json
from pathlib import Path

import numpy as np
import voyageai

EMBEDDINGS_PATH = Path("data/reference_embeddings.json")
EMBED_MODEL = "voyage-3"

_client = voyageai.Client()


def load_reference_data(path: Path = EMBEDDINGS_PATH) -> tuple[list[dict], np.ndarray]:
    with open(path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    matrix = np.array([c["embedding"] for c in chunks])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / norms
    return chunks, normalized


def _category_matches(chunk_category: str, filter_category: str) -> bool:
    """True if chunk_category is exactly filter_category, or nested
    under it (e.g. "synastry_readings/relationship_synastry" is nested
    under "synastry_readings")."""
    return (
        chunk_category == filter_category
        or chunk_category.startswith(filter_category + "/")
    )


def retrieve(
    query: str,
    chunks: list[dict],
    normalized_matrix: np.ndarray,
    top_k: int = 4,
    category: str | None = None,
) -> list[dict]:
    """
    If category is given, only chunks whose category matches (exactly,
    or as a nested subfolder) are considered. Pass None to search
    across all categories.
    """
    if category is not None:
        indices = [
            i for i, c in enumerate(chunks)
            if _category_matches(c.get("category", ""), category)
        ]
        if not indices:
            return []
        sub_matrix = normalized_matrix[indices]
    else:
        indices = list(range(len(chunks)))
        sub_matrix = normalized_matrix

    result = _client.embed([query], model=EMBED_MODEL, input_type="query")
    query_vec = np.array(result.embeddings[0])
    query_vec = query_vec / np.linalg.norm(query_vec)

    similarities = sub_matrix @ query_vec
    ranked_local = np.argsort(similarities)[::-1][:top_k]
    top_indices = [indices[i] for i in ranked_local]

    return [
        {**chunks[i], "score": float(normalized_matrix[i] @ query_vec)}
        for i in top_indices
    ]


def format_context_block(retrieved_chunks: list[dict]) -> str:
    """Format retrieved chunks for injection into the Claude prompt."""
    parts = []
    for chunk in retrieved_chunks:
        parts.append(f"[Source: {chunk['source']}]\n{chunk['text']}")
    return "\n\n---\n\n".join(parts)
