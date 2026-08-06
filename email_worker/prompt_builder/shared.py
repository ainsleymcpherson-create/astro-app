"""
prompt_builder/shared.py

Shared building blocks used by every reading-type module in this
package: RAG retrieval helpers, section formatters (points, aspects,
patterns, dignity, houses, transits, synastry), the birth-time
filtering used for "unknown time" variants, and the naming/age/
relationship-stage guidance helpers reused across natal, career,
transit, and synastry prompts.

Every other module in prompt_builder/ imports from this file rather
than duplicating any of this logic.
"""

from __future__ import annotations
from chart_points import ChartPoint
from aspect_engine import Aspect, AspectPattern
from dignity import DignityResult
from house_interpretation import HouseReading
from retrieval import load_reference_data, retrieve, format_context_block


# ---------------------------------------------------------------------------
# RAG helpers — loads precomputed reference embeddings once, retrieves
# relevant chunks at prompt-build time, and formats them for injection.
# ---------------------------------------------------------------------------

_reference_chunks = None
_reference_matrix = None


def _get_reference_data():
    global _reference_chunks, _reference_matrix
    if _reference_chunks is None:
        _reference_chunks, _reference_matrix = load_reference_data()
    return _reference_chunks, _reference_matrix


def _reference_context_block(query: str, category: str, top_k: int = 4) -> str:
    """Retrieves relevant reference material and formats it for prompt
    injection. Returns an empty string (never None) if no reference
    material exists for this category yet, so it disappears cleanly
    from the prompt rather than leaving a broken placeholder."""
    chunks, matrix = _get_reference_data()
    retrieved = retrieve(query, chunks, matrix, top_k=top_k, category=category)
    if not retrieved:
        return ""
    return (
        "\n\nREFERENCE MATERIAL (grounding for the Astrological Basis "
        "sections — use where relevant, use your own knowledge to fill "
        "in anything not covered here):\n\n" + format_context_block(retrieved)
    )


def _build_retrieval_query(chart, aspects, dignities, max_items: int = 6) -> str:
    """Builds a compact retrieval query from the tightest aspects and
    any notably dignified/undignified planets — the placements most
    likely to actually drive the reading's content."""
    terms = []
    tightest = sorted(aspects, key=lambda a: a.tightness)[:max_items]
    for a in tightest:
        terms.append(f"{a.point1} {a.aspect_name} {a.point2}")
    for planet, d in dignities.items():
        if d.status in ("Rulership", "Exaltation", "Detriment", "Fall"):
            terms.append(f"{planet} in {d.sign} ({d.status})")
    return ", ".join(terms[:max_items + 4])


def _build_transit_retrieval_query(transit_aspects, max_items: int = 6) -> str:
    """Same idea as _build_retrieval_query, but for transit aspects,
    which use transiting_point/natal_point instead of point1/point2."""
    tightest = sorted(transit_aspects, key=lambda a: a.tightness)[:max_items]
    return ", ".join(
        f"transiting {a.transiting_point} {a.aspect_name} natal {a.natal_point}"
        for a in tightest
    )


def _build_synastry_retrieval_query(synastry_result, max_items: int = 6) -> str:
    """Same idea again, but for cross-chart synastry aspects."""
    tightest = sorted(synastry_result["aspects"], key=lambda a: a.tightness)[:max_items]
    return ", ".join(
        f"Person A's {a.person_a_point} {a.aspect_name} Person B's {a.person_b_point}"
        for a in tightest
    )


# ---------------------------------------------------------------------------
# Section formatters — each turns one piece of computed data into a clean
# text block. Kept separate so you can mix/match sections if you ever want
# a shorter prompt (e.g. skip house system nuance, just do points+aspects).
# ---------------------------------------------------------------------------

def _orb_tightness_word(orb: float, max_orb: float) -> str:
    """Converts an orb into a qualitative tightness label. Keeps the
    tightness information available for inter
