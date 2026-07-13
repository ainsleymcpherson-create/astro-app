"""
prompt_builder.py

Takes everything the other modules compute (chart points, aspects,
patterns, dignity, house readings) and assembles it into a single,
well-structured prompt suitable for handing to an LLM for interpretation.

The goal of the instruction wrapper isn't just "explain this chart" — it
specifically steers the LLM toward the things generic pop-astrology
content skips: treating dignity as a real weighting factor, explaining
empty houses through their ruler rather than ignoring them, and reading
aspect PATTERNS (grand trines, T-squares, yods) as integrated units
rather than restating each individual aspect in isolation.

Depends on chart_points.py, aspect_engine.py, dignity.py,
house_interpretation.py — but only for their return TYPES; this module
just formats whatever data structures those already produce.
"""

from __future__ import annotations
from chart_points import ChartPoint
from aspect_engine import Aspect, AspectPattern
from dignity import DignityResult
from house_interpretation import HouseReading


# ---------------------------------------------------------------------------
# Section formatters — each turns one piece of computed data into a clean
# text block. Kept separate so you can mix/match sections if you ever want
# a shorter prompt (e.g. skip house system nuance, just do points+aspects).
# ---------------------------------------------------------------------------

def format_points_section(chart: dict[str, ChartPoint]) -> str:
    lines = ["PLACEMENTS (sign, house, retrograde status):"]
    for name, point in sorted(chart.items(), key=lambda x: x[1].longitude):
        if name.startswith("House "):
            continue  # cusps listed separately in the houses section
        house_str = f", House {point.house}" if point.house else ""
        retro_str = " (retrograde)" if point.retrograde else ""
        lines.append(
            f"  - {name}: {point.sign_degree:.1f}° {point.sign}{house_str}{retro_str}"
        )
    return "\n".join(lines)


def format_aspects_section(aspects: list[Aspect], min_tightness: float = 1.0) -> str:
    """
    min_tightness: 1.0 includes everything within orb. Lower it (e.g. 0.5)
    to only include the tighter/stronger half of aspects if the full list
    is too long for your prompt budget.
    """
    lines = ["ASPECTS (orb = how exact; applying = still building, "
             "separating = past exact and fading):"]
    filtered = [a for a in aspects if a.tightness <= min_tightness]
    for a in filtered:
        app_str = ""
        if a.applying is True:
            app_str = ", applying"
        elif a.applying is False:
            app_str = ", separating"
        lines.append(
            f"  - {a.point1} {a.aspect_name} {a.point2} "
            f"(orb {a.orb:.2f}°{app_str}, nature: {a.nature})"
        )
    return "\n".join(lines)


def format_patterns_section(patterns: dict[str, list[AspectPattern]]) -> str:
    lines = ["ASPECT PATTERNS (multi-point configurations — read these as "
             "integrated units, not just their individual aspects):"]
    any_found = False
    for kind, plist in patterns.items():
        for p in plist:
            any_found = True
            label = kind.replace("_", " ").title()
            lines.append(f"  - {label}: {', '.join(p.points)}")
    if not any_found:
        lines.append("  - None detected within the configured orbs.")
    return "\n".join(lines)


def format_dignity_section(dignities: dict[str, DignityResult]) -> str:
    lines = ["PLANETARY DIGNITY (how comfortable/strong each planet is in "
             "its sign — weight interpretations accordingly, don't treat "
             "every placement as equally strong):"]
    for planet, d in dignities.items():
        lines.append(f"  - {planet} in {d.sign}: {d.status} ({d.score:+d})")
    return "\n".join(lines)


def format_houses_section(house_readings: dict[int, HouseReading]) -> str:
    lines = ["HOUSES (occupied houses are directly activated; empty houses "
             "are read through their ruling planet's condition — this is "
             "already worked out below, use it rather than treating empty "
             "houses as blank):"]
    for num, reading in house_readings.items():
        lines.append(f"\n  House {num} ({reading.sign_on_cusp}):")
        lines.append(f"  {reading.interpretation}")
    return "\n".join(lines)


def build_data_block(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    house_readings: dict[int, HouseReading],
    min_tightness: float = 1.0,
) -> str:
    """Combines every section into one data block, ready to slot into a prompt."""
    return "\n\n".join([
        format_points_section(chart),
        format_aspects_section(aspects, min_tightness=min_tightness),
        format_patterns_section(patterns),
        format_dignity_section(dignities),
        format_houses_section(house_readings),
    ])


# ---------------------------------------------------------------------------
# Full prompt assembly
# ---------------------------------------------------------------------------

INTERPRETATION_INSTRUCTIONS = """\
You are an experienced astrologer giving a natal chart reading. You have \
access to the exact computed placements, aspects, patterns, dignities, \
and house conditions below — all mathematically precise, not approximated.

Guidelines for the reading:
1. SYNTHESIZE, don't enumerate. Don't just restate each placement one by \
one ("Sun in Cancer means X, Moon in Leo means Y"). Instead, identify the \
2-4 biggest THEMES that emerge when you look at everything together — \
which placements reinforce each other, which create tension, and why.
2. USE DIGNITY AS REAL WEIGHTING. A planet in Rulership or Exaltation \
should be discussed as operating strongly and directly; a planet in \
Detriment or Fall should be discussed as needing more conscious effort \
or expressing in a roundabout way. Don't treat all placements as equally \
strong.
3. TREAT PATTERNS AS UNITS. A Grand Trine, T-Square, or Yod is not just \
"three aspects" — explain what the pattern as a whole represents (ease vs. \
tension vs. a specific pressure point demanding resolution), and name \
which planet is the focal/apex point where relevant.
4. DON'T SKIP EMPTY HOUSES. Where a house has no direct occupants, use \
the ruler-based interpretation already provided rather than saying \
"nothing to note here."
5. GIVE WEIGHT TO THE LESSER-USED POINTS. Part of Fortune, Part of \
Spirit, the Nodes, Chiron, and the Vertex all carry real interpretive \
meaning — don't relegate them to a footnote after covering the 10 \
planets. This person specifically wants these included, not treated as \
an afterthought.
6. BE HONEST ABOUT TENSION. Squares, oppositions, and detriment/fall \
placements are not weaknesses to soften into false positivity — describe \
what the friction actually is and how it might show up, alongside what's \
constructive about it.
7. Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC combination of placements you're given, not stock keyword \
associations.

Here is the full computed chart data:

{data_block}

Now write the reading. Organize it however makes sense for what you're \
seeing in this specific chart — you don't need to follow a rigid \
template of "personality, then love, then career." Let the chart's own \
emphases (strong patterns, dignified planets, activated houses) guide \
what gets the most attention.\
"""


def build_interpretation_prompt(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    house_readings: dict[int, HouseReading],
    min_tightness: float = 1.0,
) -> str:
    """
    Builds the complete, ready-to-send prompt: instructions + full data
    block. Pass the resulting string straight to an LLM (paste into
    Claude.ai, or send via the Anthropic API).
    """
    data_block = build_data_block(
        chart, aspects, patterns, dignities, house_readings,
        min_tightness=min_tightness,
    )
    return INTERPRETATION_INSTRUCTIONS.format(data_block=data_block)


# ---------------------------------------------------------------------------
# NOTES for extension
# ---------------------------------------------------------------------------
# - If the full prompt gets too long for your LLM's context comfort, lower
#     min_tightness (e.g. 0.5) to drop looser/weaker aspects and keep only
#     the tightest, most significant ones.
# - For synastry later, this same pattern (format each data type, combine
#     into one instructed prompt) will extend naturally — you'd just add
#     a second chart's data block and adjust the instructions to focus on
#     inter-chart aspects rather than a single natal reading.
