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

def _orb_tightness_word(orb: float, max_orb: float) -> str:
    """Converts an orb into a qualitative tightness label. Keeps the
    tightness information available for interpretation while removing
    the numeric orb values the model tends to quote verbatim."""
    if max_orb <= 0:
        return "exact"
    ratio = orb / max_orb
    if ratio <= 0.15:
        return "essentially exact"
    if ratio <= 0.4:
        return "very tight"
    if ratio <= 0.7:
        return "moderately tight"
    return "wide/loose"


def format_points_section(chart: dict[str, ChartPoint]) -> str:
    lines = ["PLACEMENTS (sign, house, retrograde status):"]
    for name, point in sorted(chart.items(), key=lambda x: x[1].longitude):
        if name.startswith("House "):
            continue  # cusps listed separately in the houses section
        house_str = f", House {point.house}" if point.house else ""
        retro_str = " (retrograde)" if point.retrograde else ""
        lines.append(
            f"  - {name}: {point.sign}{house_str}{retro_str}"
        )
    return "\n".join(lines)


def format_aspects_section(aspects: list[Aspect], min_tightness: float = 1.0) -> str:
    """
    min_tightness: 1.0 includes everything within orb. Lower it (e.g. 0.5)
    to only include the tighter/stronger half of aspects if the full list
    is too long for your prompt budget.
    """
    lines = ["ASPECTS (tightness = how exact the connection is; applying = "
             "still building, separating = past exact and fading):"]
    filtered = [a for a in aspects if a.tightness <= min_tightness]
    for a in filtered:
        app_str = ""
        if a.applying is True:
            app_str = ", applying"
        elif a.applying is False:
            app_str = ", separating"
        lines.append(
            f"  - {a.point1} {a.aspect_name} {a.point2} "
            f"({_orb_tightness_word(a.orb, a.max_orb)}{app_str}, nature: {a.nature})"
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
You are an experienced astrologer giving a natal chart reading to \
someone who is not very well versed in astrology. You have access to \
the exact computed placements, aspects, patterns, dignities, and house \
conditions below — all mathematically precise, not approximated.
{naming_note}

First, provide an overview of the chart and what the reading \
uncovered — an orientation before the detailed themes, written as \
4-6 SEPARATE paragraphs with a blank line between each (not one \
continuous block, and not chunked or bulleted). Head this section with \
the exact markdown heading "## Overview" (two hash symbols, one space, \
then the word). The Overview uses the SAME naming convention as the \
"What This Means" sections described below: name planets, signs, \
houses, angles, lesser-used points (like Chiron), and aspect words \
(like conjunct) directly, with each technical term carrying a plain- \
English meaning alongside it. PREFER THE INVERTED FORM — lead with \
plain meaning, put the technical term in parentheses: "your drive \
(Mars)," "your public role (the Midheaven)," "your 10th house of \
career and reputation." Use the longer "X, which governs Y" form only \
for points that need more explaining, like "Chiron, a lesser-known \
body tied to old wounds and the potential to turn them into wisdom." \
Do NOT paraphrase placements into vague circumlocutions like "the \
career point" or "an old sensitivity" to avoid naming them — name the \
actual point AND gloss it. Structure the Overview's paragraphs like \
this:
- OPEN WITH A PUNCHY DECLARATIVE THESIS — one or two short, confident \
sentences stating what this chart is fundamentally about, with no \
hedging and no astrology in them at all. Something with the shape of \
"Your career is in a state of ambitious reconstruction." State it \
plainly, then spend the rest of the Overview proving it.
- NAME SPECIFIC CLUSTERS AND GROUPINGS DIRECTLY, each as its OWN \
paragraph. If three or more points sit together in one sign and house \
(a stellium), or several planets are conjunct each other, give that \
grouping a full paragraph — name which planets (each glossed), which \
sign, which house (glossed with what it governs), which of them are \
conjunct, and what that fusion of energies actually produces. Walk \
through the placements step by step the way a person would explain it \
aloud, not compressed into a single dense sentence.
- WEAVE DIGNITY IN AS CAUSAL LANGUAGE, not a separate aside. Instead of \
noting dignity as a standalone fact, fold it into the sentence \
explaining why a placement operates the way it does — e.g. a planet in \
Rulership "operates at full strength in its own sign," one in Detriment \
"has to work harder to express itself here."
- CLOSE WITH A CHART-WIDE PATTERN SUMMARY as the final paragraph(s) — \
step back and name any pattern that recurs across MULTIPLE different \
placements or life areas. If hard aspects (squares, oppositions) repeat \
across several unrelated points, say so explicitly as a defining \
structural feature of the whole chart. Do the same for repeated ease \
(trines, sextiles) if it's a genuine pattern — this is a distinct, \
chart-level observation that sits above the individual themes. End \
with a short synthesizing statement of what kind of chart this is \
overall.

Then, identify the 2-4 biggest THEMES that emerge when you look at the \
whole chart together — which placements reinforce each other, which \
create tension, and why. Format each theme's heading as a markdown H2 \
heading — exactly "## Theme Name" (two hash symbols, one space, then \
the name) — since the app displaying this reading relies on that exact \
format to build a collapsible view. Then follow the three-part \
format described below for each one.

End with a conclusion and summary of key points, but try not to repeat \
the intro summary — the intro orients the reader before the detail, the \
conclusion should distill what actually matters most after reading it. \
Write the conclusion as flowing prose too, matching the Overview's \
style — not chunked or bulleted. Head this section with the exact \
markdown heading "## Conclusion" — this is REQUIRED, not optional: \
without its own heading, the app's display logic will incorrectly \
attach this text to the previous section instead of showing it as its \
own block.

Guidelines for the reading:
1. THE OVERVIEW AND THE CONCLUSION SHOULD BE WRITTEN IN FLOWING PROSE \
PARAGRAPHS — no chunked split, no bolded sub-labels, no bullet \
chunking. They follow the same naming convention as everywhere else: \
technical terms are welcome as long as each is glossed in plain \
English on first use — accessible through glossing, not through \
avoiding the terms.
2. FOR EACH THEME, OPEN with 1-2 sentences of brief plain-language prose \
summarizing the main takeaway — no bolding, no chunking, just a short \
lead-in. THEN follow with a three-part structure, IN THIS ORDER:
    **What This Means:** Written FIRST. Break it into 2-4 short, \
    scannable chunks, each starting with a bolded claim stated as a \
    short phrase followed by a colon (e.g. "**Speaking and thinking are \
    central to your identity:**"). Within each chunk, you MAY name any \
    point directly — planets, signs, angles (Midheaven, Ascendant, \
    Descendant, Imum Coeli), lesser-used points (Chiron, the Nodes, \
    Vertex, Part of Fortune/Spirit), pattern names, and aspect words \
    (conjunct, square, trine, etc.) — but EVERY technical term must \
    carry a plain-English meaning alongside it. PREFER THE INVERTED \
    FORM: lead with the plain meaning and put the technical term in \
    parentheses after it. Write "your drive (Mars)" and "your \
    discipline (Saturn)" rather than "Mars, the planet of drive" and \
    "Saturn, the planet of discipline." This keeps the reader in \
    ordinary language and treats the astrology as the reference, not \
    the subject. Use the longer "X, which governs Y" form only when a \
    point genuinely needs more than two or three words to explain — \
    Chiron, the Nodes, the Parts, the Vertex. For example:
      "Your drive (Mars) sits in Libra."
      "Your public role and reputation (the Midheaven) is where this \
      lands."
      "Your core sense of self (the Sun) is conjunct Chiron, a \
      lesser-known body tied to old wounds and the potential to turn \
      them into wisdom."
    After naming and glossing the placement, land on the concrete, \
    real-world implication — what this actually means for how the \
    person experiences or acts in the world, not just what the \
    placement technically is. Claim, then the named-and-glossed \
    placements behind it, then the real-life payoff — that's the shape \
    of each chunk. This is where the interpretation and meaning for the \
    person's life lives, so don't just list placements — say what they \
    add up to.
    **Advice:** Written SECOND, immediately after "What This Means" \
    and BEFORE "Astrological Basis" — this ordering matters, the app \
    relies on it. A short paragraph (not chunked, no sub-labels). \
    Speak directly to the person in the imperative — concrete, \
    actionable direction they could act on this week. Use the voice of \
    a trusted advisor giving real guidance: "Don't avoid challenging \
    projects; this year builds lasting structures." "Align your \
    professional efforts with your core values." "Be cautious not to \
    overwork in pursuit of results." Mix warnings with encouragements. \
    No astrology at all in this block — it's pure direction. Keep it \
    to 2-4 sentences.
    **Astrological Basis:** Written THIRD and LAST, 2-4 short chunks covering \
    the more precise technical grounding that didn't fit naturally into \
    "What This Means" above — dignity conditions, additional supporting \
    placements, aspect relationships worth naming, and how tight or \
    loose a connection is described QUALITATIVELY (e.g. "an extremely \
    tight, exact connection" or "a looser but still active link") for a \
    reader who wants the fuller picture. Don't just repeat what "What \
    This Means" already named — add the next layer of depth. DO use \
    everything the degree data tells you — an aspect's tightness, two \
    points being nearly exact — as real interpretive input; just express \
    those \
    conclusions in words. NEVER quote the numeric values themselves \
    anywhere in the reading — no "13.9°", no "at 21 degrees Libra", no \
    orb numbers. The data below includes exact degrees and orbs because \
    that's how the chart is computed, but the reading itself should \
    translate all of that into words, not repeat the numbers.
  Do NOT alternate line-by-line between meaning and astrological facts \
  — group all the plain-language interpretation together first, then \
  all the supporting astrology together, once per theme.
  ALWAYS CASH OUT TECHNICAL STATEMENTS INTO LIVED EXPERIENCE. Naming \
  and glossing a placement is only half the job. Every technical \
  statement must be immediately followed by what it actually looks \
  like in this person's daily life — how it shows up in a real \
  situation, a habit, a reaction, a pattern they'd recognize in \
  themselves. Never let a technical term stand as if its meaning were \
  obvious. Two specific failures to avoid:
    (a) VAGUE STRENGTH LANGUAGE. Phrases like "operates at full \
    strength," "is well-placed," or "is weakened here" are meaningless \
    on their own. Say what the strength or weakness DOES. Instead of: \
    "That's its own sign, so it operates at full strength here." — \
    write: "That's its own sign, so it operates at full strength. In \
    practice that means language comes easily to you. You think fast, \
    you explain things clearly, and you can usually find the right \
    words under pressure when other people are still fumbling."
    (b) CIRCULAR TECHNICAL REASONING. Never use an astrological fact \
    as the reason for a claim — that just restates the jargon and \
    reads as esoteric to anyone who isn't already an astrologer. \
    Instead of: "Because Mercury rules its own sign here, \
    communication isn't just something you do well." — write: "Put \
    that together with where it sits, and communication isn't just \
    something you do well. It's close to the engine driving your whole \
    public identity — the thing people remember you for, and likely \
    the thing that opens doors."
    (c) NAMING A CATEGORY INSTEAD OF DESCRIBING BEHAVIOR. Saying what \
    KIND of thing something is isn't the same as saying how it shows \
    up. Describe the observable behavior, the recognizable habit, the \
    thing they'd catch themselves doing. Instead of: "This means your \
    core identity and your emotional needs are both entangled in deep, \
    transformative bonds rather than casual ones." — that only labels \
    the bonds as "deep" without saying what deep looks like. Write \
    something like: "You don't do surface-level well. Small talk with \
    someone you're close to feels like a waste, and you'd rather know \
    what someone actually fears than what they did last weekend. \
    People tend to tell you things they haven't told anyone else." \
    Compare that to a good version: "Neptune sitting right there blurs \
    the edges further, making it easy to idealize partners or \
    financial situations and harder to see them clearly." — that one \
    works because it names a specific, recognizable behavior.
  WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. \
  "This suggests a period of structured revision" beats "this might \
  possibly indicate that there could be some revision." Trust the \
  reading and say what it says.
  USE OCCASIONAL ADJECTIVE TRIADS FOR TONE. Once or twice per theme, \
  characterize an energy with three adjectives in a row — "The energy \
  is intense, focused, and demanding." Used sparingly, this gives the \
  writing rhythm and authority. Don't overdo it.
  NEVER DESCRIBE WHERE IN A SIGN A PLANET SITS. Do not say "early in \
  Libra," "late Gemini," "the very end of," "mid Cancer," or anything \
  about position within a sign. Just name the sign: "Mars sits in \
  Libra." The exact degree isn't meaningful to the reader and adds \
  clutter.
  KEEP HOUSE DESCRIPTIONS TO A MAXIMUM OF TWO DESCRIPTORS. When \
  glossing what a house governs, name at most two things — never three \
  or more. Not "your 8th house, concerned with intimacy, merging, and \
  transformation" but "your 8th house of intimacy and transformation." \
  Not "the 10th house, which governs career, public reputation, and \
  life direction" but "your 10th house of career and public \
  reputation." Pick the two most relevant to what you're about to say.
  Test every technical sentence by asking: would a reader who knows \
  nothing about astrology understand what this means for their actual \
  life? If not, add the sentence that tells them.
  ONE NEW PLACEMENT PER SENTENCE. This is the most important sentence \
  rule, and it's how you keep full detail while staying readable. Each \
  sentence may introduce ONE new point (planet, angle, or body) plus \
  its gloss — then STOP. The next placement gets its own sentence. Do \
  not chain a second or third placement onto the same sentence with \
  "and," "alongside," "also in," or a comma. Positional details (sign \
  position, house, dignity, what it's conjunct) also get their own \
  sentences rather than being appended as trailing clauses. This does \
  NOT mean cutting information — every fact still appears, just \
  distributed across more sentences. For example, instead of this one \
  overloaded sentence: "It's placed in the 10th house, which governs \
  career, public reputation, and life direction, and it sits in an \
  essentially exact conjunction with the Sun (your core identity) in \
  Cancer, also in the 10th, alongside Chiron, a lesser-known body \
  representing core wounds and the potential to turn them into wisdom" \
  — write it as: "It's placed in your \
  10th house, which governs career, public reputation, and life \
  direction. Right beside it sits your Sun, your core identity, in mid \
  Cancer. The two are in an essentially exact conjunction. Chiron is \
  there too, early in the same sign — a lesser-known body representing \
  core wounds and the potential to turn them into wisdom." Same facts, \
  four sentences instead of one.
  VARY SENTENCE LENGTH THROUGHOUT THE ENTIRE READING, the way natural \
  writing does. Follow a longer sentence with a short, punchy one that \
  lands the point. Never write three or more long sentences in a row. \
  Avoid chaining clauses with em-dashes and commas into a marathon \
  sentence. When in doubt, end the sentence and start a new one.
3. USE DIGNITY AS REAL WEIGHTING. A planet in Rulership or Exaltation \
should be discussed as operating strongly and directly; a planet in \
Detriment or Fall should be discussed as needing more conscious effort \
or expressing in a roundabout way. Don't treat all placements as equally \
strong. DESCRIBE DIGNITY IN PLAIN LANGUAGE, not technical shorthand. \
Phrases like "dignified by sign," "essentially dignified," or "weakly \
dignified" mean nothing to most readers — avoid them entirely. Talk \
about whether the sign HELPS the planet or gets in its way. For \
Peregrine especially, instead of: "None of these three is strongly or \
weakly dignified by sign — all are Peregrine." — write: "None of these \
three gets much help or hindrance from the sign it's in. The sign \
isn't the story here. What matters is where they sit and what they \
connect to." Then say what that means in practice.
4. TREAT PATTERNS AS UNITS. A Grand Trine, T-Square, or Yod is not just \
"three aspects" — explain what the pattern as a whole represents (ease vs. \
tension vs. a specific pressure point demanding resolution), and name \
which planet is the focal/apex point where relevant.
5. DON'T SKIP EMPTY HOUSES. Where a house has no direct occupants, use \
the ruler-based interpretation already provided rather than saying \
"nothing to note here."
6. GIVE WEIGHT TO THE LESSER-USED POINTS. Part of Fortune, Part of \
Spirit, the Nodes, Chiron, and the Vertex all carry real interpretive \
meaning — don't relegate them to a footnote after covering the 10 \
planets. This person specifically wants these included, not treated as \
an afterthought.
7. BE HONEST ABOUT TENSION. Squares, oppositions, and detriment/fall \
placements are not weaknesses to soften into false positivity — describe \
what the friction actually is and how it might show up, alongside what's \
constructive about it.
8. AVOID A MYSTICAL OR ESOTERIC TONE. Even with astrology terminology \
removed from "What This Means," the writing can still feel esoteric \
through word choice and phrasing — avoid language like "your soul's \
journey," "the universe is calling you toward...," "cosmic energy," \
"your higher self," or similar mystical framing. Write the way a sharp, \
grounded psychologist or coach would describe a personality pattern or \
life tendency — concrete, specific, relatable to everyday situations \
(work, relationships, decision-making, daily habits) — not the way a \
fortune teller would. This matters as much as removing jargon for making \
the reading genuinely accessible to a broad, non-astrology audience.
9. Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC combination of placements you're given, not stock keyword \
associations.

Here is the full computed chart data:

{data_block}

Now write the reading: opening overview, 2-4 themes each in the \
three-part format above, then a closing conclusion. You don't \
need to follow a rigid template of "personality, then love, then \
career" — let the chart's own emphases (strong patterns, dignified \
planets, activated houses) determine which themes emerge and what gets \
the most attention.\
"""


def _single_person_naming_note(person_name: str | None) -> str:
    """Shared helper for all single-person prompt builders (general,
    career, transit — synastry has its own two-person version). Returns
    an empty string if no name was given, so it disappears cleanly from
    the final prompt rather than leaving an awkward blank instruction."""
    if not person_name or not person_name.strip():
        return ""
    name = person_name.strip()
    return (
        f'This reading is for {name}. Feel free to address them by name '
        f'occasionally (e.g. in the Overview or Conclusion) rather than '
        f'relying only on "you" throughout, though "you" is still fine as '
        f'the primary voice.'
    )


def build_interpretation_prompt(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    house_readings: dict[int, HouseReading],
    min_tightness: float = 1.0,
    person_name: str | None = None,
) -> str:
    """
    Builds the complete, ready-to-send prompt: instructions + full data
    block. Pass the resulting string straight to an LLM (paste into
    Claude.ai, or send via the Anthropic API). If person_name is given,
    the reading will address them by name occasionally.
    """
    data_block = build_data_block(
        chart, aspects, patterns, dignities, house_readings,
        min_tightness=min_tightness,
    )
    return INTERPRETATION_INSTRUCTIONS.format(
        data_block=data_block,
        naming_note=_single_person_naming_note(person_name),
    )


# ---------------------------------------------------------------------------
# General reading — unknown birth time variant
# ---------------------------------------------------------------------------
# Same rationale as the career no-time variant: the Ascendant, Midheaven,
# houses, Vertex, and both Arabic Parts are all unreliable without an
# exact birth time, so this strips them out entirely rather than
# silently interpreting a noon-guess chart as if it were accurate.

GENERAL_NO_TIME_INSTRUCTIONS = """\
You are an experienced astrologer giving a natal chart reading to \
someone who is not very well versed in astrology. This person's exact \
birth TIME is unknown, so you only have access to their planets, \
Chiron, the Lunar Nodes, the signs they fall in, their essential \
dignity, and aspects between them — all mathematically precise. You do \
NOT have their Ascendant, Midheaven, house placements, Vertex, or \
either Arabic Part (Part of Fortune/Spirit), because all of those \
require an exact birth time to calculate correctly and would be \
unreliable guesses otherwise. Do not speculate about houses, rising \
sign, or any of the excluded points — work entirely with what's given.
{naming_note}

First, provide an overview of the chart and what the reading \
uncovered — an orientation before the detailed themes, written as \
4-6 SEPARATE paragraphs with a blank line between each (not one \
continuous block, and not chunked or bulleted). Briefly and matter-of-\
factly note in this overview that the reading is based on planets \
only, without birth-time-dependent points like the rising sign or \
houses (not as an apology, just an accurate framing of scope). Head \
this section with the exact markdown heading "## Overview". The \
Overview uses the SAME naming convention as the "What This Means" \
sections described below: name planets, signs, Chiron, the Nodes, and \
aspect words (like conjunct) directly, with each technical term \
carrying a plain-English meaning alongside it. PREFER THE INVERTED \
FORM — lead with plain meaning, put the technical term in \
parentheses: "your drive (Mars)," "your discipline (Saturn)." Use the \
longer "X, which governs Y" form only for points that need more \
explaining, like "Chiron, a lesser-known body tied to old wounds and \
the potential to turn them into wisdom." Do NOT paraphrase \
placements into vague circumlocutions like "an old sensitivity" to \
avoid naming them — name the actual point AND gloss it. Structure the \
Overview's paragraphs like this:
- OPEN WITH A PUNCHY DECLARATIVE THESIS — one or two short, confident \
sentences stating what this chart is fundamentally about, with no \
hedging and no astrology in them at all. Something with the shape of \
"Your career is in a state of ambitious reconstruction." State it \
plainly, then spend the rest of the Overview proving it.
- NAME SPECIFIC CLUSTERS AND GROUPINGS DIRECTLY, each as its OWN \
paragraph. If three or more points sit together in one sign (a \
stellium), or several planets are conjunct each other, give that \
grouping a full paragraph — name which planets (each glossed), which \
sign, which of them are conjunct, and what that fusion of energies \
actually produces. Walk through the placements step by step the way a \
person would explain it aloud, not compressed into a single dense \
sentence.
- WEAVE DIGNITY IN AS CAUSAL LANGUAGE, not a separate aside. Instead of \
noting dignity as a standalone fact, fold it into the sentence \
explaining why a placement operates the way it does — e.g. a planet in \
Rulership "operates at full strength in its own sign," one in Detriment \
"has to work harder to express itself here."
- CLOSE WITH A CHART-WIDE PATTERN SUMMARY as the final paragraph(s) — \
step back and name any pattern that recurs across MULTIPLE different \
placements. If hard aspects (squares, oppositions) repeat across \
several unrelated points, say so explicitly as a defining structural \
feature of the whole chart. Do the same for repeated ease (trines, \
sextiles) if it's a genuine pattern. End with a short synthesizing \
statement of what kind of chart this is overall.

Then, identify the 2-4 biggest THEMES that emerge when you look at the \
whole chart together. Format each theme's heading as a markdown H2 \
heading — exactly "## Theme Name" (two hash symbols, one space, then \
the name) — since the app displaying this reading relies on that exact \
format to build a collapsible view. Then follow the three-part \
format described below for each one.

End with a conclusion and summary of key points, but try not to repeat \
the intro summary. Write the conclusion as flowing prose too, matching \
the Overview's style — not chunked or bulleted. Head this section with \
the exact markdown heading "## Conclusion" — this is REQUIRED, not \
optional: without its own heading, the app's display logic will \
incorrectly attach this text to the previous section instead of \
showing it as its own block.

Guidelines for the reading:
1. THE OVERVIEW AND THE CONCLUSION SHOULD BE WRITTEN IN FLOWING PROSE \
PARAGRAPHS — no chunked split, no bolded sub-labels, no bullet \
chunking. They follow the same naming convention as everywhere else: \
technical terms are welcome as long as each is glossed in plain \
English on first use.
2. FOR EACH THEME, OPEN with 1-2 sentences of brief plain-language prose \
summarizing the main takeaway. THEN follow with a three-part \
structure, IN THIS ORDER:
    **What This Means:** Written FIRST, broken into 2-4 short, \
    scannable chunks, each starting with a bolded claim stated as a \
    short phrase followed by a colon. Within each chunk, you MAY name \
    any point directly — planets, signs, Chiron, the Nodes, pattern \
    names, and aspect words (conjunct, square, trine, etc.) — but EVERY \
    technical term must carry a plain-English meaning alongside it. \
    PREFER THE INVERTED FORM: lead with the plain meaning and put the \
    technical term in parentheses after it. Write "your drive (Mars)" \
    and "your discipline (Saturn)" rather than "Mars, the planet of \
    drive." This keeps the reader in ordinary language and treats the \
    astrology as the reference, not the subject. Use the longer "X, \
    which governs Y" form only when a point genuinely needs more than \
    two or three words to explain — Chiron, the Nodes. For example:
      "Your drive (Mars) sits in Libra."
      "Your core sense of self (the Sun) is conjunct Chiron, a \
      lesser-known body tied to old wounds and the potential to turn \
      them into wisdom."
    After naming and glossing the placement, land on the concrete, \
    real-world implication — what this actually means for how the \
    person experiences or acts in the world, not just what the \
    placement technically is. Claim, then the named-and-glossed \
    placements behind it, then the real-life payoff.
    **Advice:** Written SECOND, immediately after "What This Means" \
    and BEFORE "Astrological Basis" — this ordering matters, the app \
    relies on it. A short paragraph (not chunked, no sub-labels). \
    Speak directly to the person in the imperative — concrete, \
    actionable direction they could act on this week. Use the voice of \
    a trusted advisor giving real guidance: "Don't avoid challenging \
    projects; this year builds lasting structures." "Align your \
    professional efforts with your core values." "Be cautious not to \
    overwork in pursuit of results." Mix warnings with encouragements. \
    No astrology at all in this block — it's pure direction. Keep it \
    to 2-4 sentences.
    **Astrological Basis:** Written THIRD and LAST, 2-4 short chunks covering \
    the more precise technical grounding that didn't fit naturally into \
    "What This Means" above — dignity conditions, additional supporting \
    placements, aspect relationships worth naming, and how tight or \
    loose a connection is described QUALITATIVELY (e.g. "an extremely \
    tight, exact connection" or "a looser but still active link"). \
    Don't just repeat what "What This Means" already named — add the \
    next layer of depth. DO use everything the degree data tells you — \
    an aspect's tightness, two points being nearly exact — as real \
    interpretive input; \
    just express those conclusions in words. NEVER quote the numeric \
    values themselves anywhere in the reading — no "13.9°", no "at 21 \
    degrees Libra", no orb numbers. The data below includes exact \
    degrees and orbs because that's how the chart is computed, but the \
    reading itself should translate all of that into words, not repeat \
    the numbers.
  Group all the plain-language interpretation together first, then all \
  the supporting astrology together, once per theme — don't alternate \
  line-by-line between the two.
  ALWAYS CASH OUT TECHNICAL STATEMENTS INTO LIVED EXPERIENCE. Naming \
  and glossing a placement is only half the job. Every technical \
  statement must be immediately followed by what it actually looks \
  like in this person's daily life — how it shows up in a real \
  situation, a habit, a reaction, a pattern they'd recognize in \
  themselves. Never let a technical term stand as if its meaning were \
  obvious. Two specific failures to avoid:
    (a) VAGUE STRENGTH LANGUAGE. Phrases like "operates at full \
    strength," "is well-placed," or "is weakened here" are meaningless \
    on their own. Say what the strength or weakness DOES. Instead of: \
    "That's its own sign, so it operates at full strength here." — \
    write: "That's its own sign, so it operates at full strength. In \
    practice that means language comes easily to you. You think fast, \
    you explain things clearly, and you can usually find the right \
    words under pressure when other people are still fumbling."
    (b) CIRCULAR TECHNICAL REASONING. Never use an astrological fact \
    as the reason for a claim — that just restates the jargon and \
    reads as esoteric to anyone who isn't already an astrologer. \
    Instead of: "Because Mercury rules its own sign here, \
    communication isn't just something you do well." — write: "Put \
    all that together, and communication isn't just something you do \
    well. It's close to the engine driving how you move through the \
    world — the thing people remember you for."
    (c) NAMING A CATEGORY INSTEAD OF DESCRIBING BEHAVIOR. Saying what \
    KIND of thing something is isn't the same as saying how it shows \
    up. Describe the observable behavior, the recognizable habit, the \
    thing they'd catch themselves doing. Instead of: "This means your \
    core identity and your emotional needs are both entangled in deep, \
    transformative bonds rather than casual ones." — that only labels \
    the bonds as "deep" without saying what deep looks like. Write \
    something like: "You don't do surface-level well. Small talk with \
    someone you're close to feels like a waste, and you'd rather know \
    what someone actually fears than what they did last weekend. \
    People tend to tell you things they haven't told anyone else." \
    Compare that to a good version: "Neptune sitting right there blurs \
    the edges further, making it easy to idealize partners or \
    financial situations and harder to see them clearly." — that one \
    works because it names a specific, recognizable behavior.
  WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. \
  "This suggests a period of structured revision" beats "this might \
  possibly indicate that there could be some revision." Trust the \
  reading and say what it says.
  USE OCCASIONAL ADJECTIVE TRIADS FOR TONE. Once or twice per theme, \
  characterize an energy with three adjectives in a row — "The energy \
  is intense, focused, and demanding." Used sparingly, this gives the \
  writing rhythm and authority. Don't overdo it.
  NEVER DESCRIBE WHERE IN A SIGN A PLANET SITS. Do not say "early in \
  Libra," "late Gemini," "the very end of," "mid Cancer," or anything \
  about position within a sign. Just name the sign: "Mars sits in \
  Libra." The exact degree isn't meaningful to the reader and adds \
  clutter.
  KEEP ANY GLOSS TO A MAXIMUM OF TWO DESCRIPTORS. When explaining what \
  a point or sign governs, name at most two things — never three or \
  more. Not "Venus, which governs love, beauty, values, and \
  connection" but "Venus, which governs love and values." Pick the two \
  most relevant to what you're about to say.
  Test every technical sentence by asking: would a reader who knows \
  nothing about astrology understand what this means for their actual \
  life? If not, add the sentence that tells them.
  ONE NEW PLACEMENT PER SENTENCE. This is the most important sentence \
  rule, and it's how you keep full detail while staying readable. Each \
  sentence may introduce ONE new point (planet or body) plus its gloss \
  — then STOP. The next placement gets its own sentence. Do not chain \
  a second or third placement onto the same sentence with "and," \
  "alongside," or a comma. Positional details (sign position, dignity, \
  what it's conjunct) also get their own sentences rather than being \
  appended as trailing clauses. This does NOT mean cutting \
  information — every fact still appears, just distributed across more \
  sentences. For example, instead of this one overloaded sentence: \
  "Mercury sits in Gemini, its own sign, meaning it \
  operates at full strength, and it's in an essentially exact \
  conjunction with the Sun (your core identity) in Cancer, \
  alongside Chiron, a lesser-known body representing core wounds" — \
  write it as: "Mercury sits in Gemini. That's its own \
  sign, so it operates at full strength. Right beside it is your Sun, \
  your core identity, in Cancer. Chiron is there too — a \
  lesser-known body representing core wounds and the potential to turn \
  them into wisdom." Same facts, four sentences instead of one.
  VARY SENTENCE LENGTH THROUGHOUT THE ENTIRE READING, the way natural \
  writing does. Follow a longer sentence with a short, punchy one that \
  lands the point. Never write three or more long sentences in a row. \
  Avoid chaining clauses with em-dashes and commas into a marathon \
  sentence. When in doubt, end the sentence and start a new one.
3. USE DIGNITY AS REAL WEIGHTING. A planet in Rulership or Exaltation \
should be discussed as operating strongly and directly; a planet in \
Detriment or Fall should be discussed as needing more conscious effort \
or expressing in a roundabout way. Dignity carries extra weight in this \
format, since fewer other signals (no houses) are available. DESCRIBE \
DIGNITY IN PLAIN LANGUAGE, not technical shorthand. Phrases like \
"dignified by sign," "essentially dignified," or "weakly dignified" \
mean nothing to most readers — avoid them entirely. Talk about whether \
the sign HELPS the planet or gets in its way. For Peregrine especially, \
instead of: "None of these three is strongly or weakly dignified by \
sign — all are Peregrine." — write: "None of these three gets much \
help or hindrance from the sign it's in. The sign isn't the story \
here. What matters is what they connect to." Then say what that means \
in practice.
4. TREAT PATTERNS AS UNITS. A Grand Trine, T-Square, or Yod is not just \
"three aspects" — explain what the pattern as a whole represents (ease vs. \
tension vs. a specific pressure point demanding resolution), and name \
which planet is the focal/apex point where relevant. Only planet-to-\
planet patterns are available here (no patterns involving angles or \
houses, since those aren't part of this chart).
5. GIVE WEIGHT TO THE LESSER-USED POINTS THAT ARE STILL AVAILABLE. \
Chiron and the Lunar Nodes both carry real interpretive meaning even \
without a birth time — don't relegate them to a footnote after covering \
the 10 planets. (Part of Fortune, Part of Spirit, and the Vertex are NOT \
available in this format, since all three require an exact birth time.)
6. BE HONEST ABOUT TENSION. Squares, oppositions, and detriment/fall \
placements are not weaknesses to soften into false positivity — describe \
what the friction actually is and how it might show up, alongside what's \
constructive about it.
7. AVOID A MYSTICAL OR ESOTERIC TONE. Even with astrology terminology \
removed from "What This Means," the writing can still feel esoteric \
through word choice and phrasing — avoid language like "your soul's \
journey," "the universe is calling you toward...," "cosmic energy," \
"your higher self," or similar mystical framing. Write the way a sharp, \
grounded psychologist or coach would describe a personality pattern or \
life tendency — concrete, specific, relatable to everyday situations — \
not the way a fortune teller would.
8. Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC combination of placements you're given, not stock keyword \
associations.

Here is the full computed chart data — planets, Chiron, and the Lunar \
Nodes only (no Ascendant, houses, Vertex, or Arabic Parts, since none \
of those are reliable without an exact birth time):

{data_block}

Now write the reading: opening overview, 2-4 themes each in the \
three-part format above, then a closing conclusion. Let the \
chart's own emphases (strong patterns, dignified planets) determine \
which themes emerge.\
"""


def build_interpretation_prompt_no_time(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    min_tightness: float = 1.0,
    person_name: str | None = None,
) -> str:
    """
    General reading prompt for when birth time is unknown or approximate.
    Filters out every birth-time-dependent point (Ascendant, Midheaven,
    houses, Vertex, both Arabic Parts) rather than silently including
    unreliable data. If person_name is given, the reading will address
    them by name occasionally.
    """
    data_block = build_data_block_no_time(
        chart, aspects, patterns, dignities, min_tightness=min_tightness,
    )
    return GENERAL_NO_TIME_INSTRUCTIONS.format(
        data_block=data_block,
        naming_note=_single_person_naming_note(person_name),
    )


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
{naming_note}

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

First, provide an overview of the chart and what the reading \
uncovered — an orientation before the detailed sections, written as a \
few flowing paragraphs (not chunked or bulleted — see formatting \
guidelines below). Head this section with the exact markdown heading \
"## Overview". OPEN WITH A PUNCHY DECLARATIVE THESIS — one or two \
short, confident sentences stating what this chart means for this \
person's work life, with no hedging. Something with the shape of \
"Your career runs on structured ambition." State it plainly, then \
spend the rest of the Overview proving it. Use the SAME naming \
convention as "Career Implications" below: name planets, signs, \
houses, and angles directly, PREFERRING THE INVERTED FORM — lead with \
plain meaning, technical term in parentheses: "your discipline \
(Saturn)," "your public role (the Midheaven)."

Then, go into the following sections. Format each one as a markdown H2 \
heading — exactly "## Section Name" (two hash symbols, one space, then \
the name) — since the app displaying this reading relies on that exact \
format to build a collapsible view. Use them as your section headers:

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
conclusion should distill what actually matters most after reading it. \
Write the conclusion as flowing prose too, matching the Overview's \
style — not chunked or bulleted. Head this section with the exact \
markdown heading "## Conclusion" — this is REQUIRED, not optional: \
without its own heading, the app's display logic will incorrectly \
attach this text to the previous section instead of showing it as its \
own block.

General guidelines that still apply:
- THE OVERVIEW AND THE CONCLUSION SHOULD BE WRITTEN IN PLAIN FLOWING \
PROSE — no "Career Implications" / "Astrological Basis" split, no \
bolded sub-labels, no bullet chunking. Just a few well-written \
paragraphs in accessible, jargon-light language. These two are meant \
to read as a narrative frame around the detailed sections, not another \
structured breakdown — the structure below is specifically for the six \
section headers, not for these bookending pieces.
- FOR THE SIX SECTION HEADERS ONLY (Professional Strengths through \
Professional Growth Trajectory), OPEN EACH SECTION with 1-2 sentences \
of brief plain-language prose summarizing the main takeaway of that \
section — no bolding, no chunking, just a short lead-in sentence or \
two, similar in style to the Overview. THEN, after that brief summary, \
follow with the three-part structure below. Every one of the six \
sections should have this same shape: short prose summary first, then \
chunked detail.
- FOR THE SIX SECTION HEADERS ONLY (Professional Strengths through \
Professional Growth Trajectory), USE A THREE-PART FORMAT AT THE \
SECTION LEVEL, not per individual claim. Structure the detail AFTER \
the brief summary above as exactly three consolidated parts, IN THIS \
ORDER:
    **Career Implications:** Written FIRST. Do NOT write this as one \
    dense paragraph — break it into 2-4 short, scannable chunks, each \
    just 1-3 sentences, using either short bullet points or brief bolded \
    sub-labels (e.g. "**Daily reliability:** ...", "**Building your \
    network:** ..."). You MAY name any point directly — planets, signs, \
    angles, lesser-used points, aspect words — but PREFER THE INVERTED \
    FORM: lead with plain meaning, technical term in parentheses ("your \
    drive (Mars)" rather than "Mars, the planet of drive"). Use the \
    longer "X, which governs Y" form only for points that need more \
    explaining. Cover what this part of the chart actually means for \
    this person professionally, in plain business/career language — \
    and always cash the technical fact out into what it actually looks \
    like day to day: a habit, a reaction, a recognizable pattern at \
    work, not just a label. This is where the actual interpretation \
    and takeaways for the reader live — lead with this so the reader \
    gets the point immediately.
    **Advice:** Written SECOND, right after Career Implications and \
    BEFORE Astrological Basis — this ordering matters, the app relies \
    on it. A short paragraph, not chunked. Speak directly to the person \
    in the imperative — concrete, actionable career direction. Mix \
    warnings with encouragements. No astrology in this block. 2-4 \
    sentences.
    **Astrological Basis:** Written THIRD. Also break this into 2-4 \
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
  first, then all the supporting astrology together. This chunked \
  three-part structure applies ONLY to the six section headers — the \
  Overview and Conclusion stay in prose, per the note above.
- WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. Use \
an occasional adjective triad for tone ("The energy here is intense, \
focused, and demanding") — once or twice per section, not more.
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
    person_name: str | None = None,
) -> str:
    """
    Same data, different lens: builds a prompt focused specifically on
    work/career — happiness at work, colleague interaction style, work
    style, and strengths/weaknesses from a professional standpoint. If
    person_name is given, the reading will address them by name
    occasionally.
    """
    data_block = build_data_block(
        chart, aspects, patterns, dignities, house_readings,
        min_tightness=min_tightness,
    )
    return CAREER_INTERPRETATION_INSTRUCTIONS.format(
        data_block=data_block,
        naming_note=_single_person_naming_note(person_name),
    )

# ---------------------------------------------------------------------------
# Unknown birth time variant
# ---------------------------------------------------------------------------
# Several chart elements depend directly on the precise birth time and
# location: the Ascendant, Midheaven, all house cusps, the Vertex, and
# both Arabic Parts (Fortune and Spirit, since both are calculated from
# the Ascendant). Using a noon default when the real time is unknown
# doesn't approximate these — it effectively randomizes them, since the
# Ascendant alone moves roughly 1° every 4 minutes. Rather than silently
# feed the LLM wrong data, this variant filters those points out
# entirely and works only with what's actually reliable without an
# exact time: the planets, Chiron, the Nodes, their signs, their
# dignity, and aspects between them.

TIME_DEPENDENT_POINTS = {
    "Ascendant", "Descendant", "Midheaven", "Imum Coeli",
    "Vertex", "Anti-Vertex", "Part of Fortune", "Part of Spirit",
}


def _is_time_dependent(name: str) -> bool:
    return name in TIME_DEPENDENT_POINTS or name.startswith("House ")


def filter_time_independent(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
) -> tuple[dict[str, ChartPoint], list[Aspect], dict[str, list[AspectPattern]]]:
    """
    Strips out every point (and every aspect/pattern touching one) that
    depends on exact birth time/location, leaving only what's reliable
    when the birth time is unknown or approximate.
    """
    filtered_chart = {
        name: point for name, point in chart.items()
        if not _is_time_dependent(name)
    }
    filtered_aspects = [
        a for a in aspects
        if not _is_time_dependent(a.point1) and not _is_time_dependent(a.point2)
    ]
    filtered_patterns = {
        kind: [p for p in plist if not any(_is_time_dependent(pt) for pt in p.points)]
        for kind, plist in patterns.items()
    }
    return filtered_chart, filtered_aspects, filtered_patterns


def build_data_block_no_time(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    min_tightness: float = 1.0,
) -> str:
    """Same as build_data_block, but with no Houses section (there are no
    reliable houses without a birth time) and a note about the Moon's
    lighter reliability."""
    filtered_chart, filtered_aspects, filtered_patterns = filter_time_independent(
        chart, aspects, patterns
    )
    moon_note = (
        "NOTE ON THE MOON: unlike the other planets, the Moon moves about "
        "13° per day, so if the birth time is genuinely unknown, there's a "
        "small chance its sign shown here is slightly off (only relevant if "
        "the true birth time was far from when this chart was generated and "
        "the Moon was near a sign boundary that day). Treat the Moon's "
        "placement as slightly less certain than the other planets, but "
        "still worth including."
    )
    return "\n\n".join([
        moon_note,
        format_points_section(filtered_chart),
        format_aspects_section(filtered_aspects, min_tightness=min_tightness),
        format_patterns_section(filtered_patterns),
        format_dignity_section(dignities),
    ])


CAREER_NO_TIME_INSTRUCTIONS = """\
You are an experienced astrologer giving a chart reading to someone who \
is not very well versed in astrology, focused specifically on work and \
career. This person's exact birth TIME is unknown, so you only have \
access to their planets, Chiron, the Lunar Nodes, the signs they fall \
in, their essential dignity, and aspects between them — all \
mathematically precise. You do NOT have their Ascendant, Midheaven, \
house placements, Vertex, or either Arabic Part, because all of those \
require an exact birth time to calculate correctly and would be \
unreliable guesses otherwise. Do not speculate about houses, rising \
sign, or any of the excluded points — work entirely with what's given.
{naming_note}

Without house placements, work-relevant signal instead concentrates in \
the planets themselves and their conditions: the Sun (core identity and \
vitality), Saturn (discipline, structure, and long-term follow-through), \
Mars (drive, initiative, and how conflict is handled), Mercury \
(communication and thinking style), Venus (values and relational \
style), Jupiter (growth, opportunity, and expansiveness), and the Lunar \
Nodes (the comfort zone vs. the real growth direction). Essential \
dignity — whether a planet is comfortably or uncomfortably placed in \
its sign — matters more here than usual, since it's one of the few \
reliable weighting signals available without house data.

Structure your answer as follows:

First, provide an overview of the chart and what the reading \
uncovered — an orientation before the detailed sections, written as a \
few flowing paragraphs (not chunked or bulleted — see formatting \
guidelines below). Briefly and matter-of-factly note that this reading \
is based on planets only, without birth-time-dependent points like the \
rising sign or houses, so it won't cover things like "what house your \
career planets fall in" the way a full reading would — this isn't a \
limitation to apologize for, just an accurate scope-setting note. Head \
this section with the exact markdown heading "## Overview". OPEN WITH \
A PUNCHY DECLARATIVE THESIS — one or two short, confident sentences \
stating what this chart means for this person's work life, with no \
hedging. State it plainly, then spend the rest of the Overview proving \
it. Use the SAME naming convention as "Career Implications" below: \
name planets and signs directly, PREFERRING THE INVERTED FORM — lead \
with plain meaning, technical term in parentheses: "your discipline \
(Saturn)."

Then, go into the following sections. Format each one as a markdown H2 \
heading — exactly "## Section Name" (two hash symbols, one space, then \
the name) — since the app displaying this reading relies on that exact \
format to build a collapsible view. Use them as your section headers:

PROFESSIONAL STRENGTHS: what are the genuine strengths of the \
individual, based on well-dignified planets and supportive aspects \
(trines, sextiles, conjuncts) between career-relevant planets? Where \
does this individual operate with professional ease?

PROFESSIONAL WATCH AREAS: These are traditionally thought of as \
weaknesses, but they don't have to be an actual weakness; they can be \
opportunities for growth. Using poorly-dignified planets, hard aspects \
(squares, oppositions) between career-relevant planets, and the \
Nodes, what are the areas that require more conscious effort? Be \
honest about real weaknesses rather than reframing everything as \
secretly a strength.

PROFESSIONAL COMMUNICATION STYLE: special focus on Mercury and Mars — \
their signs, dignity, and aspects to other planets. Do they like public \
speaking? Do they prefer written communication? Are they quick-witted \
and responsive, or do they take time to think things through? Are they \
passive aggressive or straightforward?

HAPPINESS AT WORK — What genuinely brings this person fulfillment or \
satisfaction in a work context, and what's likely to frustrate or drain \
them? Ground this in the Sun's sign and condition, Jupiter's placement, \
and any other positive aspects — with limited astrological jargon — \
rather than generic "you like variety" statements.

WORK CULTURE AND STYLE: How does this person show up for work? Draw on \
Mercury (communication), Venus (relational/diplomatic approach), Mars \
(how they handle disagreement or assertion), and Saturn (structure and \
follow-through) as relevant. Do they leave things to the last minute or \
structure their delivery over time? How does this person actually \
approach getting things done — pace, structure, flexibility, \
independent, collaborative?

PROFESSIONAL GROWTH TRAJECTORY: what does this person's chart say about \
where their career might be going, based on dignity, supportive vs. \
challenging aspects among career-relevant planets, and the Nodes? What \
are suggested jobs and career paths that this person should consider?

End with a conclusion and summary of key points, but try not to repeat \
the intro summary. Write the conclusion as flowing prose too, matching \
the Overview's style — not chunked or bulleted. Head this section with \
the exact markdown heading "## Conclusion" — this is REQUIRED, not \
optional: without its own heading, the app's display logic will \
incorrectly attach this text to the previous section instead of \
showing it as its own block.

General guidelines that still apply:
- THE OVERVIEW AND THE CONCLUSION SHOULD BE WRITTEN IN PLAIN FLOWING \
PROSE — no "Career Implications" / "Astrological Basis" split, no \
bolded sub-labels, no bullet chunking.
- FOR THE SIX SECTION HEADERS ONLY, OPEN EACH SECTION with 1-2 \
sentences of brief plain-language prose summarizing the main takeaway \
of that section. THEN follow with a three-part structure, IN \
THIS ORDER:
    **Career Implications:** Written FIRST, broken into 2-4 short, \
    scannable chunks with bolded sub-labels. You MAY name any point \
    directly — planets, signs, Chiron, the Nodes, aspect words — but \
    PREFER THE INVERTED FORM: lead with plain meaning, technical term \
    in parentheses ("your drive (Mars)" rather than "Mars, the planet \
    of drive"). Cover what this actually means for this person \
    professionally, and always cash the technical fact out into what \
    it actually looks like day to day — a habit, a reaction, a \
    recognizable pattern at work, not just a label.
    **Advice:** Written SECOND, right after Career Implications and \
    BEFORE Astrological Basis — this ordering matters, the app relies \
    on it. A short paragraph, not chunked. Speak directly to the person \
    in the imperative — concrete, actionable career direction. Mix \
    warnings with encouragements. No astrology in this block. 2-4 \
    sentences.
    **Astrological Basis:** Written THIRD, also broken into 2-4 short \
    chunks grouped by planet or aspect, with brief plain-language \
    glosses of technical terms woven in (e.g. "...Exaltation, its \
    strongest condition..." or "...square, a tense angle...").
- WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. Use \
an occasional adjective triad for tone ("The energy here is intense, \
focused, and demanding") — once or twice per section, not more.
- SYNTHESIZE within each section — identify how 2-3 placements combine \
to create each point, rather than listing them one by one. Avoid \
repeating the same point across multiple sections.
- USE DIGNITY AS REAL WEIGHTING throughout — it carries extra weight in \
this time-unknown format since fewer other signals are available.
- TREAT PATTERNS AS UNITS where they touch career-relevant planets.
- Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC combination of placements you're given.

Here is the full computed chart data — planets, Chiron, and the Lunar \
Nodes only (no Ascendant, houses, Vertex, or Arabic Parts, since none \
of those are reliable without an exact birth time):

{data_block}

Now write the reading, organized under the headers above.\
"""


def build_career_interpretation_prompt_no_time(
    chart: dict[str, ChartPoint],
    aspects: list[Aspect],
    patterns: dict[str, list[AspectPattern]],
    dignities: dict[str, DignityResult],
    min_tightness: float = 1.0,
    person_name: str | None = None,
) -> str:
    """
    Career-focused prompt for when birth time is unknown or approximate.
    Filters out every birth-time-dependent point (Ascendant, Midheaven,
    houses, Vertex, both Arabic Parts) rather than silently including
    unreliable data, and reframes the instructions around what's still
    solid: planets, dignity, and planet-to-planet aspects. If person_name
    is given, the reading will address them by name occasionally.
    """
    data_block = build_data_block_no_time(
        chart, aspects, patterns, dignities, min_tightness=min_tightness,
    )
    return CAREER_NO_TIME_INSTRUCTIONS.format(
        data_block=data_block,
        naming_note=_single_person_naming_note(person_name),
    )


# ---------------------------------------------------------------------------
# Transit reading — "what's currently activated" prompt
# ---------------------------------------------------------------------------
# Distinct from every other prompt in this file: those all interpret a
# single natal chart. This one interprets the relationship between a
# fixed natal chart and the CURRENT sky (transiting planets), which is
# the standard technique for "what's happening in my life right now"
# questions — the single most common thing people ask an astrologer
# that a natal-only reading can't answer.

def format_transiting_points_section(
    transiting_points: dict,
    natal_house_labels: dict[int, str] | None = None,
) -> str:
    """Formats the current sky positions, with each transiting planet's
    natal house noted if houses were assigned via
    transit_engine.assign_transit_houses()."""
    lines = ["CURRENT SKY (transiting planets, sign, and which of YOUR "
             "natal houses each currently falls in):"]
    for name, point in sorted(transiting_points.items(), key=lambda x: x[1].longitude):
        house_str = f", in your natal House {point.house}" if point.house else ""
        retro_str = " (retrograde)" if point.retrograde else ""
        lines.append(
            f"  - Transiting {name}: {point.sign}{house_str}{retro_str}"
        )
    return "\n".join(lines)


def format_transit_aspects_section(transit_aspects: list, min_tightness: float = 1.0) -> str:
    """Formats transit-to-natal aspects, tightest (most exact/significant) first."""
    lines = ["TRANSIT ASPECTS (transiting planet to natal point; tightness "
             "= how exact — transits matter most when close to exact; "
             "applying = still building toward exact, separating = past "
             "exact and fading):"]
    filtered = [a for a in transit_aspects if a.tightness <= min_tightness]
    if not filtered:
        lines.append("  - No significant transits within the configured orbs right now.")
    for a in filtered:
        app_str = ""
        if a.applying is True:
            app_str = ", applying"
        elif a.applying is False:
            app_str = ", separating"
        lines.append(
            f"  - Transiting {a.transiting_point} {a.aspect_name} natal "
            f"{a.natal_point} ({_orb_tightness_word(a.orb, a.max_orb)}{app_str}, nature: {a.nature})"
        )
    return "\n".join(lines)


def build_transit_data_block(
    transiting_points: dict,
    transit_aspects: list,
    natal_dignities: dict[str, DignityResult],
    min_tightness: float = 1.0,
) -> str:
    return "\n\n".join([
        format_transiting_points_section(transiting_points),
        format_transit_aspects_section(transit_aspects, min_tightness=min_tightness),
        format_dignity_section(natal_dignities),
    ])


TRANSIT_INSTRUCTIONS = """\
You are an experienced astrologer giving a reading to someone who is \
not very well versed in astrology, focused specifically on what's \
currently happening in their life right now, based on how today's sky \
(the "transits") is interacting with their unchanging natal chart.

First, a quick note on terminology, since this reading works \
differently from a standard natal reading: "transiting" planets are \
where the planets are positioned RIGHT NOW, in the actual sky today — \
these move and change day by day. Your "natal" placements are fixed, \
permanent, from the moment of birth. This reading is about how today's \
moving sky is currently activating specific parts of the person's \
unchanging natal chart — it is not a repeat of their general \
personality reading, it's about the current window of time only.

You have access to the exact computed transiting planetary positions, \
which of the person's natal houses each transiting planet currently \
falls in, the aspects between transiting planets and natal points (with \
tight, transit-appropriate orbs — only genuinely close, currently \
active connections are included), and the person's natal essential \
dignity for context. All mathematically precise, not approximated.
{naming_note}

Structure your answer as follows:

First, provide an overview of what this current period is broadly \
about for this person — an orientation before the detailed points, \
written as a few flowing paragraphs (not chunked or bulleted — see \
formatting guidelines below). Head this section with the exact \
markdown heading "## Overview". If there are no significant transits \
at all right now, say so plainly rather than manufacturing \
significance — a quiet period is a real and valid finding. Otherwise, \
OPEN WITH A PUNCHY DECLARATIVE THESIS — one or two short, confident \
sentences stating what this period is fundamentally about, with no \
hedging. Use the SAME naming convention as "What This Means" below: \
name planets and points directly, PREFERRING THE INVERTED FORM — lead \
with plain meaning, technical term in parentheses: "your public \
direction (transiting Saturn)."

Then, identify the 2-4 most significant currently-active transits or \
transit-driven themes (prioritize tighter orbs and applying transits, \
which are more currently relevant than wide or separating ones — and \
weight transits involving slower planets like Jupiter/Saturn/Uranus/ \
Neptune/Pluto as generally longer-lasting and more significant than \
fast-moving ones like the Moon, unless a fast transit is unusually \
exact). Format each theme's heading as a markdown H2 heading — exactly \
"## Theme Name" — since the app displaying this reading relies on that \
exact format to build a collapsible view. Then follow the three-part \
format described below for each one.

End with a conclusion distilling what actually matters most about this \
current period, but try not to repeat the intro summary. Write it as \
flowing prose too, matching the Overview's style — not chunked or \
bulleted. Head this section with the exact markdown heading \
"## Conclusion" — this is REQUIRED, not optional: without its own \
heading, the app's display logic will incorrectly attach this text to \
the previous section instead of showing it as its own block.

General guidelines that still apply:
- THE OVERVIEW AND THE CONCLUSION SHOULD BE WRITTEN IN PLAIN FLOWING \
PROSE — no chunked split, no bolded sub-labels, no bullet chunking.
- FOR EACH THEME, OPEN with 1-2 sentences of brief plain-language prose \
summarizing the main takeaway. THEN follow with a three-part \
structure, IN THIS ORDER:
    **What This Means:** Written FIRST, broken into 2-4 short, \
    scannable chunks with bolded sub-labels. You MAY name any point \
    directly — planets, angles, Chiron, the Nodes, aspect words — but \
    PREFER THE INVERTED FORM: lead with plain meaning, technical term \
    in parentheses, e.g. "your public direction (the Midheaven)" \
    rather than "your Midheaven, which governs..." Instead of \
    "transiting Saturn is conjunct your Midheaven," write "This is \
    putting real, sustained focus on your public reputation and career \
    direction (transiting Saturn conjunct your Midheaven)." Always cash \
    the technical fact out into what it actually looks like day to day.
    **Advice:** Written SECOND, right after "What This Means" and \
    BEFORE "Astrological Basis" — this ordering matters, the app \
    relies on it. A short paragraph, not chunked. Speak directly to the \
    person in the imperative — concrete, actionable direction for this \
    specific window of time. Mix warnings with encouragements. No \
    astrology in this block. 2-4 sentences.
    **Astrological Basis:** Written THIRD, also in 2-4 short chunks \
    grouped by transit, with brief plain-language glosses of technical \
    terms woven in as needed.
  Group all the plain-language interpretation together first, then all \
  the supporting astrology together, once per theme — don't alternate \
  line-by-line between the two.
- WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. Use \
an occasional adjective triad for tone ("The energy is intense, \
focused, and demanding") — once or twice per theme, not more.
- USE DIGNITY AS CONTEXT. If a transiting planet is aspecting a natal \
planet that's well-dignified (Rulership/Exaltation), that natal planet \
can generally handle the activation more directly; if poorly dignified \
(Detriment/Fall), the transit may bring the underlying difficulty more \
sharply into focus.
- PRIORITIZE TIGHT AND APPLYING TRANSITS. A transit that's applying \
(still building toward exact) and has a small orb is far more currently \
relevant than one that's wide or separating — lead with what matters \
most right now.
- AVOID A MYSTICAL OR ESOTERIC TONE. Write the way a sharp, grounded \
psychologist or coach would describe what's currently going on for \
someone — concrete, specific, relatable — not the way a fortune teller \
would. Avoid language like "the universe is calling you toward..." or \
"cosmic energy."
- Avoid generic, could-apply-to-anyone language. Ground every claim in \
the SPECIFIC transits you're given, not stock keyword associations.
- Don't manufacture drama. If the current transits are genuinely mild, \
say so — a quiet, low-key period is a legitimate and useful finding, \
not a failure to find something interesting.

Here is the full computed transit data:

{data_block}

Now write the reading: opening overview, 2-4 themes each in the \
three-part format above, then a closing conclusion.\
"""


def build_transit_prompt(
    transiting_points: dict,
    transit_aspects: list,
    natal_dignities: dict[str, DignityResult],
    min_tightness: float = 1.0,
    person_name: str | None = None,
) -> str:
    """
    Builds a complete transit reading prompt: current sky positions,
    transit-to-natal aspects (tight, transit-appropriate orbs), and
    natal dignity for context. Distinct from every other prompt builder
    in this file since it interprets the CURRENT sky against a fixed
    natal chart, rather than the natal chart alone. If person_name is
    given, the reading will address them by name occasionally.
    """
    data_block = build_transit_data_block(
        transiting_points, transit_aspects, natal_dignities,
        min_tightness=min_tightness,
    )
    return TRANSIT_INSTRUCTIONS.format(
        data_block=data_block,
        naming_note=_single_person_naming_note(person_name),
    )


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
# - A career-focused transit variant (build_transit_career_prompt) would
#     follow the same pattern as this one, but restrict
#     natal_points_to_check in transit_engine.compute_transit_aspects()
#     to career-relevant natal points (Midheaven, natal Saturn, the
#     natal 10th/6th/2nd house rulers) — the "daily professional
#     outlook" idea from earlier design discussions.


# ---------------------------------------------------------------------------
# Professional synastry — working-dynamic reading between two people
# ---------------------------------------------------------------------------
# Distinct from every other prompt in this file: those all interpret a
# single chart (natal or transiting-vs-natal). This one compares two
# FIXED natal charts against each other — the standard synastry
# technique — but reframed entirely around professional/working
# dynamics rather than romantic compatibility, including redirecting
# Venus/Mars/Moon (traditionally romantic synastry signals) toward
# their professional meanings instead.

def format_synastry_points_section(chart: dict, person_label: str) -> str:
    lines = [f"PERSON {person_label}'S PLACEMENTS (sign, house if available):"]
    for name, point in sorted(chart.items(), key=lambda x: x[1].longitude):
        if name.startswith("House "):
            continue
        house_str = f", House {point.house}" if point.house else ""
        retro_str = " (retrograde)" if point.retrograde else ""
        lines.append(
            f"  - {name}: {point.sign}{house_str}{retro_str}"
        )
    return "\n".join(lines)


def format_synastry_aspects_section(aspects: list, min_tightness: float = 1.0) -> str:
    lines = ["CROSS-CHART ASPECTS (Person A's point to Person B's point; "
             "tightness = how exact the connection is):"]
    filtered = [a for a in aspects if a.tightness <= min_tightness]
    if not filtered:
        lines.append("  - No significant cross-chart aspects within the configured orbs.")
    for a in filtered:
        lines.append(
            f"  - Person A's {a.person_a_point} {a.aspect_name} Person B's "
            f"{a.person_b_point} ({_orb_tightness_word(a.orb, a.max_orb)}, nature: {a.nature})"
        )
    return "\n".join(lines)


def format_house_overlay_section(overlays: list, title: str) -> str:
    lines = [f"{title}:"]
    if not overlays:
        lines.append("  - Not available (the house-owning person's birth "
                      "time is unknown, so their houses can't be calculated).")
    for o in overlays:
        lines.append(f"  - {o}")
    return "\n".join(lines)


def build_synastry_data_block(
    synastry_result: dict,
    dignities_a: dict[str, DignityResult],
    dignities_b: dict[str, DignityResult],
    min_tightness: float = 1.0,
) -> str:
    # Note: house overlay data (whose planets fall in whose houses) is
    # intentionally NOT included here — it's exactly the kind of
    # mechanical astrology detail ("Person A's Mars falls in Person B's
    # 10th house") that reads as astrology-plumbing rather than business
    # insight. The raw overlay data still exists and is shown separately
    # in the app's Houses tab for anyone who wants to see it directly.
    return "\n\n".join([
        format_synastry_points_section(synastry_result["filtered_chart_a"], "A"),
        format_synastry_points_section(synastry_result["filtered_chart_b"], "B"),
        "PERSON A'S DIGNITY:\n" + format_dignity_section(dignities_a),
        "PERSON B'S DIGNITY:\n" + format_dignity_section(dignities_b),
        format_synastry_aspects_section(synastry_result["aspects"], min_tightness=min_tightness),
    ])


PROFESSIONAL_SYNASTRY_INSTRUCTIONS = """\
You are a workplace consultant. Two coworkers, colleagues, or business
partners want to know how to work together effectively. You use
synastry (comparing two natal charts) as your analytical tool, but the
OUTPUT must read like a practical workplace guide — not an astrology
reading, and not a romantic compatibility report. Banned words/framing
anywhere in this reading: "chemistry," "attraction," "spark," how
"close" they could become, whether they're "compatible" as partners,
or anything implying romance or dating. If a sentence would also make
sense in a romantic reading, it's wrong for this one — rewrite it
around a concrete workplace scenario (a tense meeting, dividing tasks
on a shared project, a tight deadline, one person managing the other).

You have both people's computed placements, dignity, and cross-chart
aspects — mathematically precise. Which placements exist for each
person depends on birth time — see below.

BIRTH TIME STATUS: {birth_time_status} This affects what's reliable:
- Unknown birth time excludes that person's Ascendant, Midheaven,
  Descendant, Imum Coeli, houses, Vertex, and Arabic Parts (Part of
  Fortune/Spirit) — all require an exact time. Their planets, Chiron,
  and Lunar Nodes remain fully reliable regardless.
- Cross-chart PLANET-to-PLANET aspects — the actual basis for this
  reading — stay fully reliable even if one or both times are unknown,
  since these depend only on planetary position, not time-of-day.
- Note any of this briefly and matter-of-factly in the Overview — not
  as an apology, just accurate scope-setting.
{naming_note}
Work-relevant signal concentrates in: Sun-Saturn contacts (respect,
authority, whether one person feels supported or constrained by the
other), Mercury contacts (communication), Mars-Mars and Mars-Saturn
contacts (how conflict and assertion get handled), Saturn-Saturn
contacts (shared or clashing standards), and Jupiter contacts (mutual
growth). Weight these more heavily — but don't ignore anything else
that genuinely bears on working together.

Structure your answer as follows:

First, a general overview of the working dynamic — a short,
plain-language orientation before the detail, written as a few
flowing paragraphs (not chunked or bulleted). Do not include anything
related to astrology here — format it as an overview of these two
people and a summary of what follows, purely from a professional and
working perspective. OPEN WITH A PUNCHY DECLARATIVE THESIS — one or
two short, confident sentences stating what this working dynamic is
fundamentally about, with no hedging. Head it "## Overview".

Then, exactly these three sections, each a markdown H2 heading exactly
as written (the app relies on this exact format for a collapsible view):

## How To Work Together Effectively
The practical mechanics of collaborating: pace, structure, how
decisions get made, how work gets divided, how deadlines get handled.
Draw on Mars/Mercury/Saturn cross-contacts and dignity. This answers
"how do I actually work with this person day to day?"

## Being an Effective Colleague to Each Other
Mutual and bidirectional: what does Person A need from Person B to feel
respected and supported, and what does Person B need from Person A?
Cover communication style, authority/respect dynamics (Saturn contacts),
and what genuinely brings out the best in each other (supportive
aspects, Jupiter contacts). Answer this for BOTH directions, not just one.

## Professional Watch Areas
Honest, concrete friction points — hard aspects (Mars/Saturn/Sun
squares, oppositions, difficult conjunctions), where misunderstandings
are likely, what actively needs managing. Be honest about real
difficulty rather than reframing everything as secretly fine — but
frame it as manageable, not a verdict.

End with a conclusion distilling what actually matters most, without
repeating the Overview. Flowing prose, matching the Overview's style.
Head it "## Conclusion" — REQUIRED, not optional.

General guidelines:
- OVERVIEW AND CONCLUSION: plain flowing prose only — no chunking, no
bolded sub-labels, no bullets.
- TONE AND LANGUAGE IN THE OVERVIEW, CONCLUSION, AND EVERY "WORKING
IMPLICATIONS" BLOCK (this does NOT apply to "Astrological Basis"
sections, which intentionally do contain astrology — see below): do
not include astrological descriptions here at all. Keep this content
to what you've determined from the reading, stated in plain business
terms. Use the astrology to arrive at your interpretation, but don't
surface the astrology itself anywhere outside the dedicated
Astrological Basis sections.
- EACH OF THE THREE SECTIONS: open with 1-2 plain-language sentences
summarizing the takeaway. Then a three-part structure, IN ORDER:
    **Working Implications:** FIRST, and this is the MAIN CONTENT of
    the reading — 3-5 substantive chunks with bolded sub-labels. This
    should read like a business consultant's actual analysis, not a
    brief summary: give concrete workplace scenarios (how a specific
    meeting might go, how a project handoff plays out, what a
    disagreement actually looks like between these two), practical
    advice either person could act on, and specific detail grounded in
    what's actually different or notable about these two people. Go
    deep here rather than moving quickly to the next section. You MAY
    name the 10 planets and zodiac signs plainly (e.g. "Person A's Mars
    is in Libra"). You may NOT use: aspect names/verbs (trine, square,
    conjunct, sextile, opposition), angle names (Midheaven, Ascendant,
    Descendant, Imum Coeli), dignity terms (Exaltation, Detriment,
    Rulership, Peregrine), house numbers, or pattern names (Grand
    Trine, T-Square, Yod). A sentence like "Person A's Mars is square
    Person B's Saturn" is WRONG here — write "Person A tends to push
    forward quickly, which can rub against Person B's need for
    structure" instead. Always name WHICH person — never leave it
    ambiguous.
    **Advice:** SECOND, right after Working Implications and BEFORE
    Astrological Basis — this ordering matters, the app relies on it.
    A short paragraph, not chunked. Speak directly to the two people
    in the imperative — concrete, actionable direction for working
    together better. Mix warnings with encouragements. No astrology in
    this block. 2-4 sentences.
    **Astrological Basis:** THIRD, and this is supporting evidence
    ONLY — keep it brief and minimal, 1-2 short chunks, just enough for
    a curious reader to see where the claim came from. This is NOT the
    place to elaborate further — all the actual depth and insight
    belongs in Working Implications above. Technical terms are allowed
    here with brief plain glosses. Label which person each placement
    belongs to.
  Group all plain-language content first, then all supporting astrology
  — never alternate line by line. The reading as a whole should feel
  like a business document that happens to cite astrology as its
  method, not an astrology reading that happens to mention business.
- WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. Use
an occasional adjective triad for tone ("The dynamic here is direct,
fast-moving, and occasionally blunt") — once or twice per section, not
more.
- DIGNITY IS REAL WEIGHTING for both charts.
- SYNASTRY CONTACTS ARE MUTUAL: a contact between Person A's Saturn and
Person B's Sun affects both people, even if experienced differently —
cover both sides.
- Venus, Mars, and the Moon get real professional weight here, reframed
away from their usual romantic reading:
    VENUS: values/quality standards, diplomacy, negotiation style,
    likability among colleagues.
    MARS: drive/initiative, assertiveness, pace, conflict style,
    competitive vs. collaborative instinct.
    MOON: what makes each person feel secure or unsettled at work,
    instinctive reactions under pressure, what support they need.
  A Venus-Mars contact — read as attraction in a romantic chart — here
  means one person's drive meeting the other's sense of quality/values,
  a productive push-and-pull between initiating action and refining it.
  Never frame it as attraction.
- Ground every claim in the SPECIFIC placements given — no generic,
could-apply-to-anyone language.

Here is the full computed synastry data for both people:

{data_block}

Reminder: this is a workplace guide for two coworkers/colleagues, not a
romantic reading. Now write it, organized under the headers above.\
"""


def build_professional_synastry_prompt(
    synastry_result: dict,
    dignities_a: dict[str, DignityResult],
    dignities_b: dict[str, DignityResult],
    min_tightness: float = 1.0,
    person_a_name: str | None = None,
    person_b_name: str | None = None,
) -> str:
    """
    Builds the complete professional synastry prompt from a
    synastry_engine.compute_full_synastry() result plus each person's
    dignity. Handles the birth-time-status framing automatically based
    on what's actually in synastry_result. If either name is provided,
    instructs the model to use it instead of the generic "Person A"/
    "Person B" labels throughout the reading.
    """
    def _status(known: bool) -> str:
        return "known" if known else "unknown"

    birth_time_status = (
        f"Person A's exact birth time is {_status(synastry_result['person_a_time_known'])} "
        f"and Person B's exact birth time is {_status(synastry_result['person_b_time_known'])}."
    )

    naming_note = ""
    if person_a_name or person_b_name:
        label_a = person_a_name.strip() if person_a_name and person_a_name.strip() else "Person A"
        label_b = person_b_name.strip() if person_b_name and person_b_name.strip() else "Person B"
        naming_note = (
            f'Throughout this reading, refer to Person A as "{label_a}" and '
            f'Person B as "{label_b}" instead of the generic "Person A"/'
            f'"Person B" labels — these are their actual names, and using '
            f'them makes the reading feel personal rather than clinical.'
        )

    data_block = build_synastry_data_block(
        synastry_result, dignities_a, dignities_b, min_tightness=min_tightness,
    )
    return PROFESSIONAL_SYNASTRY_INSTRUCTIONS.format(
        birth_time_status=birth_time_status,
        naming_note=naming_note,
        data_block=data_block,
    )


# ---------------------------------------------------------------------------
# Relationship synastry — traditional romantic compatibility reading
# ---------------------------------------------------------------------------
# The counterpart to the professional synastry prompt above: same
# underlying two-chart comparison, same data (build_synastry_data_block
# is reused as-is), but the OPPOSITE interpretive lens — this one is
# explicitly about romantic compatibility, attraction, and emotional
# connection, using Venus/Mars/Moon in their traditional romantic sense
# rather than the professional reframe used elsewhere in this file.

RELATIONSHIP_SYNASTRY_INSTRUCTIONS = """\
You are an experienced astrologer giving a traditional relationship
synastry reading — comparing two people's natal charts to explore their
romantic compatibility, emotional connection, attraction, and long-term
potential together. Unlike a professional or platonic reading, romantic
and emotional language is exactly right here — attraction, chemistry,
intimacy, and compatibility as partners are the actual subject of this
reading, not something to avoid.

You have both people's computed placements and dignity, along with the
cross-chart aspects between them (Person A's planets to Person B's
planets, and vice versa) — all mathematically precise. Which placements
exist for each person depends on birth time — see below.

BIRTH TIME STATUS: {birth_time_status} This affects what's reliable:
- Unknown birth time excludes that person's Ascendant, Midheaven,
  Descendant, Imum Coeli, houses, Vertex, and Arabic Parts (Part of
  Fortune/Spirit) — all require an exact time. Their planets, Chiron,
  and Lunar Nodes remain fully reliable regardless.
- Cross-chart PLANET-to-PLANET aspects — the actual basis for this
  reading — stay fully reliable even if one or both times are unknown,
  since these depend only on planetary position, not time-of-day.
- Note any of this briefly and matter-of-factly in the Overview — not
  as an apology, just accurate scope-setting.
{naming_note}
Romantic synastry signal traditionally concentrates in: Venus-Mars
contacts (attraction and chemistry — the classic romantic signal),
Moon-Moon and Moon-Venus contacts (emotional safety and how naturally
the two connect on a feeling level), Venus-Venus contacts (shared
values and what each finds attractive or lovable), Sun-Moon contacts
(a sense of natural fit between identity and emotional need), Saturn
contacts (commitment, stability, and long-term staying power — often
felt as either grounding or restrictive depending on the rest of the
chart), and Mercury contacts (how easily the two actually talk to each
other). Weight these more heavily — but don't ignore anything else that
genuinely bears on the relationship.

Structure your answer as follows:

First, a general overview of the connection between these two people —
a short, plain-language orientation before the detail, written as a
few flowing paragraphs (not chunked or bulleted). OPEN WITH A PUNCHY
DECLARATIVE THESIS — one or two short, confident sentences stating
what this connection is fundamentally about, with no hedging. Head it
"## Overview".

Then, exactly these five sections, each a markdown H2 heading exactly
as written (the app relies on this exact format for a collapsible view):

## Emotional Connection
How naturally these two connect on a feeling level — emotional safety,
whether each makes the other feel understood, and how compatible their
core emotional needs actually are. Focus on Moon-Moon, Moon-Venus, and
Sun-Moon contacts.

## Attraction & Chemistry
The classic romantic signal — genuine physical and romantic attraction
between the two. Focus on Venus-Mars contacts specifically, and Mars-
Mars contacts for how their individual desire and passion interact.

## Communication & Daily Connection
How easily these two actually talk to each other day to day — real
understanding versus real risk of misreading each other. Focus on
Mercury-to-Mercury and Mercury-to-Sun/Moon contacts.

## Values, Commitment & Long-Term Potential
Whether these two want similar things from love and life, and what
their long-term staying power actually looks like. Focus on Venus-
Venus contacts for shared values, and Saturn contacts for commitment
and stability — Saturn here can mean either a grounding, "built to
last" quality or a restrictive, effortful one, and it's worth being
specific about which this looks like.

## Friction Points To Navigate
Honest, concrete friction — hard aspects (squares, oppositions,
difficult conjunctions) between Mars, Saturn, and the Sun especially.
Be honest about genuine difficulty rather than reframing everything as
secretly fine, but frame it as something to navigate consciously, not
a verdict on the relationship.

End with a conclusion distilling what actually matters most about this
connection, without repeating the Overview. Flowing prose, matching the
Overview's style. Head it "## Conclusion" — REQUIRED, not optional.

General guidelines:
- OVERVIEW AND CONCLUSION: plain flowing prose only — no chunking, no
bolded sub-labels, no bullets.
- EACH OF THE FIVE SECTIONS: open with 1-2 plain-language sentences
summarizing the takeaway. Then a three-part structure, IN ORDER:
    **What This Means:** FIRST, 2-4 substantive chunks with bolded
    sub-labels — real, specific detail about what this actually looks
    like between these two people, not generic relationship advice.
    You MAY name any point directly — planets, signs, angles, aspect
    words — but PREFER THE INVERTED FORM: lead with plain meaning,
    technical term in parentheses ("Person A's warmth (Venus)" rather
    than "Person A's Venus, the planet of warmth"). Always name WHICH
    person — never leave it ambiguous.
    **Advice:** SECOND, right after "What This Means" and BEFORE
    "Astrological Basis" — this ordering matters, the app relies on
    it. A short paragraph, not chunked. Speak directly to the two
    people in the imperative — concrete, actionable relationship
    guidance. Mix warnings with encouragements. No astrology in this
    block. 2-4 sentences.
    **Astrological Basis:** THIRD, 1-2 short chunks, just enough
    supporting evidence for a curious reader to see where the claim
    came from — this isn't the place for further elaboration, which
    belongs in "What This Means" above. Technical terms are allowed
    here with brief plain glosses. Label which person each placement
    belongs to.
  Group all plain-language content first, then all supporting astrology
  — never alternate line by line.
- WRITE WITH CONFIDENCE, NOT HEDGING. State conclusions directly. Use
an occasional adjective triad for tone ("The connection is warm,
intense, and immediate") — once or twice per section, not more.
- DIGNITY IS REAL WEIGHTING for both charts.
- SYNASTRY CONTACTS ARE MUTUAL: a contact between Person A's Venus and
Person B's Mars affects both people, even if experienced differently —
cover both sides where relevant.
- AVOID GENERIC, COULD-APPLY-TO-ANYONE LANGUAGE. Ground every claim in
the SPECIFIC combination of placements between these two actual charts.
- This reading is about a romantic/emotional relationship specifically.
Don't hedge away from that framing or redirect it toward a platonic or
professional angle — direct romantic and emotional language is correct
and expected throughout.

Here is the full computed synastry data for both people:

{data_block}

Now write the reading, organized under the headers above.\
"""


def build_relationship_synastry_prompt(
    synastry_result: dict,
    dignities_a: dict[str, DignityResult],
    dignities_b: dict[str, DignityResult],
    min_tightness: float = 1.0,
    person_a_name: str | None = None,
    person_b_name: str | None = None,
) -> str:
    """
    Builds the complete traditional relationship (romantic) synastry
    prompt — the counterpart to build_professional_synastry_prompt().
    Same underlying data block, opposite interpretive framing. If
    either name is provided, instructs the model to use it instead of
    the generic "Person A"/"Person B" labels throughout the reading.
    """
    def _status(known: bool) -> str:
        return "known" if known else "unknown"

    birth_time_status = (
        f"Person A's exact birth time is {_status(synastry_result['person_a_time_known'])} "
        f"and Person B's exact birth time is {_status(synastry_result['person_b_time_known'])}."
    )

    naming_note = ""
    if person_a_name or person_b_name:
        label_a = person_a_name.strip() if person_a_name and person_a_name.strip() else "Person A"
        label_b = person_b_name.strip() if person_b_name and person_b_name.strip() else "Person B"
        naming_note = (
            f'Throughout this reading, refer to Person A as "{label_a}" and '
            f'Person B as "{label_b}" instead of the generic "Person A"/'
            f'"Person B" labels — these are their actual names, and using '
            f'them makes the reading feel personal rather than clinical.'
        )

    data_block = build_synastry_data_block(
        synastry_result, dignities_a, dignities_b, min_tightness=min_tightness,
    )
    return RELATIONSHIP_SYNASTRY_INSTRUCTIONS.format(
        birth_time_status=birth_time_status,
        naming_note=naming_note,
        data_block=data_block,
    )
