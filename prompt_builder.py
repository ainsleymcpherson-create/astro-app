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
# Career/work-focused variant
# ---------------------------------------------------------------------------
# Same underlying chart data, but the instruction wrapper steers the LLM
# toward four specific work-related questions rather than a general
# personality reading. Traditionally, career-relevant signal concentrates
# in the 10th house (career/public role) and its ruler, the 6th house
# (daily work, routines, colleagues at the peer/task level), the 2nd
# house (what you're compensated for, self-worth), the Midheaven itself,
# and the classic "how you act" planets — Sun, Saturn, Mars, Mercury,
# Venus. The instructions point the LLM at these without discarding the
# rest of the chart, since real synthesis sometimes pulls in placements
# outside that traditional list (a Grand Trine touching the MC, a Yod
# apex sitting in the 6th house, etc.).

CAREER_INTERPRETATION_INSTRUCTIONS = """\
You are an experienced astrologer giving a chart reading to someone who \
is not very well versed in astrology, focused specifically on work and \
career. You have access to the exact computed placements, aspects, \
patterns, dignities, and house conditions below — all mathematically \
precise, not approximated.

Traditionally, work-relevant signal concentrates in a few specific \
places — the 10th house and its ruler (career, public role, authority), \
the 6th house (daily work, routines, service, peer-level colleagues), \
the 2nd house (what you're compensated for, material self-worth), the \
Midheaven itself, and the planets Sun, Saturn, Mars, Mercury, and Venus \
(identity, discipline/structure, drive and assertion, communication and \
thinking style, and relational/diplomatic style, respectively). Weight \
these more heavily than you would in a general reading — but don't \
ignore other placements if they genuinely bear on work (a Grand Trine \
touching the Midheaven, a Yod apex sitting in the 6th house, Chiron in \
a career-relevant house, etc. all still matter here). That being said, \
take a look at the entire chart and look for areas that may not be in \
the traditional work-relevant signals.

Structure your answer as follows:

First, provide a general and summarized overview of the chart and what \
the reading uncovered — a short, plain-language orientation before the \
detailed sections.

Then, go into the following sections. Use them as your section headers:

PROFESSIONAL STRENGTHS: what are the genuine strengths of the \
individual? Where does this individual operate with professional ease? \
Include any supportive aspects (trines, sextiles, conjuncts, etc.) as \
leverage points.

PROFESSIONAL WATCH AREAS: These are traditionally thought of as \
weaknesses, but they don't have to be an actual weakness; they can be \
opportunities for growth or areas that the person should be aware of as \
potential pitfalls or difficulties. Be honest about real weaknesses \
rather than reframing everything as secretly a strength.

PROFESSIONAL COMMUNICATION STYLE: special focus on mercury, mars, \
rising, third house, 11th house, 6th house. Based on what you see in \
the chart, what are the strengths and weaknesses of this individual, \
particularly as it relates to communication. Some questions you may \
answer here: Do they like public speaking? Do they prefer written \
communication? Are they quick-witted and responsive, or do they take \
time to think things through before responding? Are they passive \
aggressive or straightforward? Do they like communications after \
hours, or do they prefer to keep their work and home life separate?

HAPPINESS AT WORK — What genuinely brings this person fulfillment or \
satisfaction in a work context, and what's likely to frustrate or drain \
them? Ground this in specific chart placements (but provide a \
description with limited astrological jargon) rather than generic "you \
like variety" statements. Include a focus on the houses that deal with \
career, even if they are empty. Include any other positive aspects that \
would contribute to a happy work environment. Also include details \
about the type of workplace that a person would be most interested in \
(do they like to be on their feet all day, on the move, stationary, do \
they prefer a solitary environment or something more social)? Ground \
this in helping the person identify what makes them truly happy in a \
professional context. Include the 5th house, as this can indicate what \
makes a person truly happy or where their creativity would be best \
focused.

WORK CULTURE AND STYLE: How does this person show up for work? Do they \
prefer remote work or in-office interaction? Draw on the 6th house \
(daily work relationships), Mercury (communication style), Venus \
(relational/diplomatic approach), Mars (how they handle disagreement or \
assertion), and the Moon (emotional needs in a working relationship) as \
relevant. Do they leave things to the last minute or do they structure \
their delivery over time? Include anything else about what type of \
environment they prefer and what they do not prefer. Include a special \
focus on the 3rd, 6th, 10th and 11th houses. How does this person \
actually approach getting things done — pace, structure, flexibility, \
independent, collaborative? Are they likely to follow through or are \
they more scattered? Also consider: Mars, Saturn, Mercury, 6th house.

PROFESSIONAL GROWTH TRAJECTORY: what does this person's chart say about \
where their career might be going? Are they going to struggle through a \
career path, or are they going to be promoted with ease? What are \
suggested jobs and career paths that this person should consider, given \
the readings and outputs of the other sections?

End with a conclusion and summary of key points, but try not to repeat \
the intro summary — the intro orients the reader before the detail, the \
conclusion should distill what actually matters most after reading it.

General guidelines that still apply:
- USE A TWO-PART FORMAT AT THE SECTION LEVEL, not per individual claim. \
For EACH section (Overview, each of the headers below, and the \
Conclusion), structure it as exactly two consolidated parts, IN THIS \
ORDER:
    **Career Implications:** Written FIRST. Do NOT write this as one \
    dense paragraph — break it into 2-4 short, scannable chunks, each \
    just 1-3 sentences, using either short bullet points or brief bolded \
    sub-labels (e.g. "**Daily reliability:** ...", "**Building your \
    network:** ...") so a reader can scan and absorb it quickly rather \
    than parse a wall of text. Cover what this part of the chart \
    actually means for this person professionally, in plain business/ \
    career language with NO astrology jargon at all. This is where the \
    actual interpretation, advice, and takeaways for the reader live — \
    lead with this so the reader gets the point immediately.
    **Astrological Basis:** Written SECOND. Also break this into 2-4 \
    short, scannable chunks rather than one dense paragraph — group by \
    placement or pattern (e.g. "**Saturn:** ...", "**Supporting \
    aspects:** ...", "**Part of Fortune:** ..."), each chunk just 1-3 \
    sentences, with brief plain-language glosses of technical terms \
    woven in as needed (e.g. "...Exaltation, its strongest \
    condition..." or "...square, a tense angle..."). Cover all the \
    relevant placements, aspects, dignity, and patterns that support \
    the interpretation above. This is the supporting evidence for the \
    reader who wants to know why, presented after the takeaway rather \
    than before it — use the same short-chunk, scannable style as \
    Career Implications, not flowing prose.
  Do NOT alternate line-by-line between career interpretation and \
  astrological facts — group all the career interpretation together \
  first, then all the supporting astrology together, once per section. \
  This applies to every section including the Overview and Conclusion.
- SYNTHESIZE within each section — don't just list placements one by \
one, identify how 2-3 placements combine to create each point you make. \
Focus on the most important items, not the entire list. Where possible, \
avoid repeating across sections — pick the section where each piece of \
information makes the most sense to include, rather than restating it \
everywhere it could theoretically apply.
- USE DIGNITY AS REAL WEIGHTING throughout.
- TREAT PATTERNS AS UNITS where they touch career-relevant points.
- DON'T SKIP EMPTY HOUSES — if the 6th, 10th, or 2nd house has no \
occupants, use the ruler-based interpretation already provided.
- INCLUDE general astrological components, such as Sun, Moon, Mars, \
Venus, Mercury, Jupiter, Saturn, Uranus, Neptune, Pluto, the houses, \
the aspects, the signs. Do not include everything you come up with; \
synthesize the information and choose the highest priority items for \
personal career understanding, development, and growth.
- GIVE WEIGHT TO LESSER-USED POINTS where relevant to work (Part of \
Fortune for what brings ease, Saturn's condition for discipline, Chiron \
if it touches a career house, north/south node).
- Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC combination of placements you're given.

Here is the full computed chart data — placements (sign, house, \
retrograde status), aspects (orb = how exact; applying = still \
building, separating = past exact and fading), aspect patterns, \
planetary dignity, and houses (occupied houses are directly activated; \
empty houses are read through their ruling planet's condition):

{data_block}

Now write the reading, organized under the headers above.\
"""


def build_career_interpretation_prompt(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    house_readings: dict[int, HouseReading],
    min_tightness: float = 1.0,
) -> str:
    """
    Same data, different lens: builds a prompt focused specifically on
    work/career — happiness at work, colleague interaction style, work
    style, and strengths/weaknesses from a professional standpoint.
    """
    data_block = build_data_block(
        chart, aspects, patterns, dignities, house_readings,
        min_tightness=min_tightness,
    )
    return CAREER_INTERPRETATION_INSTRUCTIONS.format(data_block=data_block)


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
# - Additional lens variants (relationship-focused, financial-focused,
#     etc.) can follow the exact same pattern as
#     build_career_interpretation_prompt(): a new INSTRUCTIONS template
#     plus a thin wrapper function reusing build_data_block().
