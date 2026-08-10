"""
prompt_builder/ package

Split from the original single prompt_builder.py file into modules by
reading type, for easier navigation and editing. Every name that used
to be importable as `from prompt_builder import X` still works exactly
the same way — this __init__.py re-exports everything, so app.py,
email_worker/app.py, and any other caller need ZERO changes.

Module layout:
    shared.py     - RAG helpers, section formatters, data block
                    builders, naming/age/relationship-stage guidance,
                    unknown-birth-time filtering. Used by every other
                    module below.
    natal.py      - General reading (full, summary-only, no-time)
    career.py     - Career/Work reading (full, summary-only, no-time)
    transit.py    - Transit reading (full, summary-only)
    synastry.py   - Professional, Relationship, and Parent/Child
                    synastry (each full + summary-only)
    deep_dive.py  - Lilith, Chiron, Lunar Nodes deep dives, and
                    Ask an Astrologer (each full + summary-only where
                    applicable)
"""

from .shared import (
    # Section formatters (occasionally imported directly, e.g. by app.py)
    format_points_section,
    format_aspects_section,
    format_patterns_section,
    format_dignity_section,
    format_houses_section,
    build_data_block,
    build_data_block_no_time,
    filter_time_independent,
    format_transiting_points_section,
    format_transit_aspects_section,
    build_transit_data_block,
    format_synastry_points_section,
    format_synastry_aspects_section,
    format_house_overlay_section,
    build_synastry_data_block,
    TIME_DEPENDENT_POINTS,
    PROMPT_CACHE_SPLIT_MARKER,
    split_prompt_for_caching,
    strip_cache_marker,
)

from .natal import (
    INTERPRETATION_INSTRUCTIONS,
    build_interpretation_prompt,
    SUMMARY_ONLY_INSTRUCTIONS,
    build_summary_only_prompt,
    build_summary_only_prompt_no_time,
    GENERAL_NO_TIME_INSTRUCTIONS,
    build_interpretation_prompt_no_time,
)

from .career import (
    CAREER_INTERPRETATION_INSTRUCTIONS,
    build_career_interpretation_prompt,
    CAREER_SUMMARY_ONLY_INSTRUCTIONS,
    build_career_summary_only_prompt,
    CAREER_NO_TIME_INSTRUCTIONS,
    build_career_interpretation_prompt_no_time,
    CAREER_NO_TIME_SUMMARY_ONLY_INSTRUCTIONS,
    build_career_summary_only_prompt_no_time,
)

from .transit import (
    TRANSIT_INSTRUCTIONS,
    build_transit_prompt,
    TRANSIT_SUMMARY_ONLY_INSTRUCTIONS,
    build_transit_summary_only_prompt,
)

from .synastry import (
    PROFESSIONAL_SYNASTRY_INSTRUCTIONS,
    build_professional_synastry_prompt,
    PROFESSIONAL_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS,
    build_professional_synastry_summary_only_prompt,
    RELATIONSHIP_SYNASTRY_INSTRUCTIONS,
    build_relationship_synastry_prompt,
    RELATIONSHIP_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS,
    build_relationship_synastry_summary_only_prompt,
    PARENT_CHILD_SYNASTRY_INSTRUCTIONS,
    build_parent_child_synastry_prompt,
    PARENT_CHILD_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS,
    build_parent_child_synastry_summary_only_prompt,
)

from .deep_dive import (
    LILITH_DEEP_DIVE_INSTRUCTIONS,
    build_lilith_deep_dive_prompt,
    LILITH_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS,
    build_lilith_deep_dive_summary_only_prompt,
    CHIRON_DEEP_DIVE_INSTRUCTIONS,
    build_chiron_deep_dive_prompt,
    CHIRON_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS,
    build_chiron_deep_dive_summary_only_prompt,
    LUNAR_NODES_DEEP_DIVE_INSTRUCTIONS,
    build_lunar_nodes_deep_dive_prompt,
    LUNAR_NODES_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS,
    build_lunar_nodes_deep_dive_summary_only_prompt,
    ASK_AN_ASTROLOGER_INSTRUCTIONS,
    build_ask_an_astrologer_prompt,
)

__all__ = [
    # shared
    "format_points_section", "format_aspects_section",
    "format_patterns_section", "format_dignity_section",
    "format_houses_section", "build_data_block", "build_data_block_no_time",
    "filter_time_independent", "format_transiting_points_section",
    "format_transit_aspects_section", "build_transit_data_block",
    "format_synastry_points_section", "format_synastry_aspects_section",
    "format_house_overlay_section", "build_synastry_data_block",
    "TIME_DEPENDENT_POINTS",
    # natal
    "INTERPRETATION_INSTRUCTIONS", "build_interpretation_prompt",
    "SUMMARY_ONLY_INSTRUCTIONS", "build_summary_only_prompt",
    "build_summary_only_prompt_no_time", "GENERAL_NO_TIME_INSTRUCTIONS",
    "build_interpretation_prompt_no_time",
    # career
    "CAREER_INTERPRETATION_INSTRUCTIONS", "build_career_interpretation_prompt",
    "CAREER_SUMMARY_ONLY_INSTRUCTIONS", "build_career_summary_only_prompt",
    "CAREER_NO_TIME_INSTRUCTIONS", "build_career_interpretation_prompt_no_time",
    "CAREER_NO_TIME_SUMMARY_ONLY_INSTRUCTIONS",
    "build_career_summary_only_prompt_no_time",
    # transit
    "TRANSIT_INSTRUCTIONS", "build_transit_prompt",
    "TRANSIT_SUMMARY_ONLY_INSTRUCTIONS", "build_transit_summary_only_prompt",
    # synastry
    "PROFESSIONAL_SYNASTRY_INSTRUCTIONS", "build_professional_synastry_prompt",
    "PROFESSIONAL_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS",
    "build_professional_synastry_summary_only_prompt",
    "RELATIONSHIP_SYNASTRY_INSTRUCTIONS", "build_relationship_synastry_prompt",
    "RELATIONSHIP_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS",
    "build_relationship_synastry_summary_only_prompt",
    "PARENT_CHILD_SYNASTRY_INSTRUCTIONS", "build_parent_child_synastry_prompt",
    "PARENT_CHILD_SYNASTRY_SUMMARY_ONLY_INSTRUCTIONS",
    "build_parent_child_synastry_summary_only_prompt",
    # deep dive
    "LILITH_DEEP_DIVE_INSTRUCTIONS", "build_lilith_deep_dive_prompt",
    "LILITH_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS",
    "build_lilith_deep_dive_summary_only_prompt",
    "CHIRON_DEEP_DIVE_INSTRUCTIONS", "build_chiron_deep_dive_prompt",
    "CHIRON_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS",
    "build_chiron_deep_dive_summary_only_prompt",
    "LUNAR_NODES_DEEP_DIVE_INSTRUCTIONS", "build_lunar_nodes_deep_dive_prompt",
    "LUNAR_NODES_DEEP_DIVE_SUMMARY_ONLY_INSTRUCTIONS",
    "build_lunar_nodes_deep_dive_summary_only_prompt",
    "ASK_AN_ASTROLOGER_INSTRUCTIONS", "build_ask_an_astrologer_prompt",
]
