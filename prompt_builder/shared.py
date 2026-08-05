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
# Naming, age, and relationship-stage guidance — shared across natal,
# career, transit, and synastry prompt builders.
# ---------------------------------------------------------------------------

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


def _age_guidance(age: int | None, compact: bool = False) -> str:
    """
    Builds age-based emphasis guidance for the General reading — real
    astrological theory, not generic advice: which placements carry
    the most FELT weight tends to track actual planetary cycles, most
    defensibly the Saturn return (~29-30) and the "midlife" transit
    stack (~39-42).

    This is ADDED EMPHASIS, never exclusion. Returns an empty string if
    age is None. compact=True produces a shorter version for the lean
    summary-only prompt.
    """
    if age is None:
        return ""

    if compact:
        if age < 29:
            stage = (
                f"This person is {age}, before their Saturn return "
                f"(~29-30). Emphasize the Moon, Ascendant, Mercury, the "
                f"South Node, the personal planets, and the 1st/3rd/5th "
                f"houses more than outer-planet or legacy themes — "
                f"without ignoring anything genuinely significant."
            )
        elif age < 40:
            stage = (
                f"This person is {age}, past their Saturn return but "
                f"before the ~39-42 midlife transit stack. Saturn and "
                f"the North Node are becoming live, felt questions now "
                f"rather than theoretical ones — weight them accordingly, "
                f"alongside the personal planets that still matter."
            )
        else:
            stage = (
                f"This person is {age}, past the ~39-42 midlife transit "
                f"stack (Uranus opposition, Neptune square, Pluto square "
                f"to natal). Emphasize Saturn, the North Node, the "
                f"Midheaven/10th house, the outer planets' natal "
                f"placements, the 4th/8th/12th houses, and Chiron's "
                f"integrated wisdom side more than early-life themes."
            )
        return f"\nAGE-BASED EMPHASIS: {stage} This is added emphasis, not exclusion.\n"

    if age < 29:
        stage = f"""\
This person is {age} years old, before their Saturn return (Saturn's \
~29-year orbit back to its natal position — the most defensible \
astrological dividing line for this, not an arbitrary cutoff). Give \
EXTRA WEIGHT to: the Moon (emotional patterns, family conditioning — \
largely inherited rather than chosen at this stage), the Ascendant \
(how they learned to present and survive, often before consciously \
shaping a persona), Mercury (learning style), the South Node (old, \
automatic, inherited patterns that dominate before conscious growth \
work begins), the personal planets generally (Sun, Moon, Mercury, \
Venus, Mars — the fast-moving, immediate, day-to-day identity-forming \
layer), and the 1st, 3rd, and 5th houses (self, learning, play, \
creative self-expression). Saturn, the North Node, and outer-planet \
themes can still appear if genuinely significant, but shouldn't be \
centered the way they would for someone older."""
    elif age < 40:
        stage = f"""\
This person is {age} years old — past their Saturn return (~29-30) but \
before the "midlife" transit stack (~39-42, when Uranus opposes, \
Neptune squares, and Pluto squares their own natal positions in rough \
succession). This is a genuine transitional stage: give EXTRA WEIGHT \
to Saturn (structure, responsibility, mastery — no longer just \
theoretical now that the Saturn return has actually been lived \
through) and the North Node (the conscious growth direction becomes a \
live, workable question rather than a distant idea). The personal \
planets and Moon/Ascendant still matter and shouldn't be dropped, but \
Saturn and the North Node deserve real, active attention here in a way \
they wouldn't for someone younger."""
    else:
        stage = f"""\
This person is {age} years old, past the "midlife" transit stack \
(~39-42, when Uranus opposes, Neptune squares, and Pluto squares their \
own natal positions in rough succession — a real, felt shift, not a \
cultural cliché). Give EXTRA WEIGHT to: Saturn and the North Node in \
full (both fully live by this point), the Midheaven/10th house \
(public role and legacy, now that a career actually exists to reflect \
on), the outer planets' natal placements (Jupiter, Saturn, Uranus, \
Neptune, Pluto — now carrying real felt weight from having lived \
through their slower cycles, not just generational background), the \
4th, 8th, and 12th houses (roots and legacy, shared resources and \
transformation, reflection), and Chiron's INTEGRATED side — turning \
the old wound into something offered to others — rather than just the \
rawer wound-focused reading more appropriate for a younger chart."""

    return f"""\

AGE-BASED EMPHASIS: {stage}

This is ADDED EMPHASIS, not exclusion. A placement outside this \
person's current life-stage focus can still matter and should still \
be covered if it's genuinely significant — an exact conjunction, a \
defining stellium, a pattern involving it — just don't center it as \
heavily as you would for someone at a different life stage. Don't \
mention the underlying theory (Saturn return, midlife transit stack) \
explicitly in the reading itself unless it's genuinely relevant to \
name — this guidance is about where you place emphasis, not something \
to explain to the reader.
"""


def _relationship_stage_guidance(stage: str | None, compact: bool = False) -> str:
    """
    Builds relationship-stage emphasis guidance for Relationship
    Synastry. stage should be "new" or "mature"; any other value
    (including None) returns an empty string. This is ADDED EMPHASIS,
    never exclusion — same pattern as _age_guidance above.
    """
    if stage not in ("new", "mature"):
        return ""

    if compact:
        if stage == "new":
            focus = (
                "This is a NEW relationship. Emphasize Venus-Mars contacts "
                "(the classic, immediately-felt attraction signal), "
                "Sun-Moon and Moon-Moon contacts (whether you click and "
                "feel understood right away), Mercury-Mercury contacts "
                "(whether conversation flows from the start), angle "
                "contacts (a planet landing on someone's Ascendant or "
                "Descendant — first-impression energy), and Vertex "
                "contacts (the 'fated encounter' marker) more than "
                "long-term commitment signal."
            )
        else:
            focus = (
                "This is a MATURE, established relationship. Emphasize "
                "Saturn contacts (commitment and staying power, only "
                "legible once structure has actually been tested over "
                "time), Node contacts (shared destiny or growth "
                "direction, usually only clear in hindsight), Pluto "
                "contacts (power dynamics and transformation, which "
                "deepen with real intimacy), and the 4th/8th/10th house "
                "overlays (shared home, shared resources, public "
                "partnership role) more than first-impression signal."
            )
        return f"\nRELATIONSHIP-STAGE EMPHASIS: {focus} This is added emphasis, not exclusion.\n"

    if stage == "new":
        focus = """\
This is a NEW relationship — early enough that only the fast, felt \
layer of synastry signal is really testable yet. Give EXTRA WEIGHT to: \
Venus-Mars contacts (the classic, immediately-felt attraction signal), \
Sun-Moon and Moon-Moon contacts (whether you click and feel understood \
right away), Mercury-Mercury contacts (whether conversation flows from \
the start), angle contacts — a planet landing on someone's Ascendant \
or Descendant (first-impression, "I noticed you immediately" energy), \
and Vertex contacts (often described as the "fated encounter" marker, \
felt as instant significance). These all involve fast-moving personal \
planets or first-impression angles — exactly the layer that's visible \
before real shared history exists. Saturn, Node, and Pluto contacts \
can still appear if genuinely significant, but shouldn't be centered \
the way they would for an established relationship, since staying \
power and shared destiny genuinely can't be assessed this early."""
    else:
        focus = """\
This is a MATURE, established relationship — enough real time and real \
stakes have passed that the slower layer of synastry signal is now \
genuinely legible. Give EXTRA WEIGHT to: Saturn contacts (commitment \
and staying power don't reveal themselves until you've actually tested \
whether structure feels grounding or restrictive over time), Node \
contacts (a sense of shared destiny or growth direction usually only \
becomes legible in hindsight, after years together), Pluto contacts \
(power dynamics and transformation deepen with real intimacy — they \
don't fully activate until the stakes are real), and the 4th, 8th, and \
10th house overlays (shared home, shared resources, and public \
partnership role only become relevant once you're actually building a \
life together, not dating). Venus-Mars and other fast-impression \
signal can still appear if genuinely significant, but shouldn't be \
centered the way it would for a brand-new relationship — that layer \
already did its job getting you here."""

    return f"""\

RELATIONSHIP-STAGE EMPHASIS: {focus}

This is ADDED EMPHASIS, not exclusion. A contact outside this \
relationship's current stage can still matter and should still be \
covered if it's genuinely significant — an exact conjunction, a \
defining pattern — just don't center it as heavily as you would for \
the other stage. Don't mention the underlying theory (why fast signal \
matters early vs. why slow signal matters later) explicitly in the \
reading itself unless it's genuinely relevant to name — this guidance \
is about where you place emphasis, not something to explain to the \
reader.
"""


# ---------------------------------------------------------------------------
# Unknown birth time variant — filtering shared by natal and career
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Transit data block
# ---------------------------------------------------------------------------

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


def _transit_theme_guidance(theme: str | None) -> str:
    """
    Shared helper for both transit prompt builders (full and
    summary-only). General gets no special instruction. Romantic and
    Career each redirect which transits get prioritized without
    excluding genuinely major transits outside that focus.
    """
    if not theme or theme == "General":
        return ""
    if theme == "Romantic":
        return (
            "\nThis reading has a ROMANTIC/RELATIONSHIP FOCUS. When choosing "
            "which transits to lead with, prioritize ones touching the 5th "
            "house (romance), 7th house (partnership), 8th house (intimacy "
            "and merging), Venus, Mars, or the Moon. A transit outside these "
            "areas can still appear if it's genuinely too significant to "
            "leave out, but the overview and the majority of themes should "
            "center on what's happening romantically right now.\n"
        )
    if theme == "Career":
        return (
            "\nThis reading has a CAREER/WORK FOCUS. When choosing which "
            "transits to lead with, prioritize ones touching the 10th house "
            "(career and reputation), 6th house (daily work), 2nd house "
            "(income and resources), Saturn, the Midheaven, or Jupiter. A "
            "transit outside these areas can still appear if it's genuinely "
            "too significant to leave out, but the overview and the "
            "majority of themes should center on what's happening "
            "professionally right now.\n"
        )
    return ""


# ---------------------------------------------------------------------------
# Synastry data block
# ---------------------------------------------------------------------------

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
    include_house_overlays: bool = False,
) -> str:
    # House overlay data is excluded by default — for Professional
    # Synastry specifically, it's exactly the kind of mechanical
    # astrology detail that reads as astrology-plumbing rather than
    # business insight. Relationship and Parent/Child synastry opt
    # back in explicitly.
    sections = [
        format_synastry_points_section(synastry_result["filtered_chart_a"], "A"),
        format_synastry_points_section(synastry_result["filtered_chart_b"], "B"),
        "PERSON A'S DIGNITY:\n" + format_dignity_section(dignities_a),
        "PERSON B'S DIGNITY:\n" + format_dignity_section(dignities_b),
        format_synastry_aspects_section(synastry_result["aspects"], min_tightness=min_tightness),
    ]
    if include_house_overlays:
        sections.append(format_house_overlay_section(
            synastry_result.get("overlay_a_in_b", []),
            "PERSON A'S PLANETS IN PERSON B'S HOUSES",
        ))
        sections.append(format_house_overlay_section(
            synastry_result.get("overlay_b_in_a", []),
            "PERSON B'S PLANETS IN PERSON A'S HOUSES",
        ))
    return "\n\n".join(sections)
