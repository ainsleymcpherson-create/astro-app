"""
resources_page.py

The "Resources" page in the native Streamlit multi-page navigation —
a glossary reference for the signs, planets/points, and houses used
throughout the readings. This whole file IS the page: st.navigation
points at this file path directly, and Streamlit executes it top to
bottom whenever this page is selected (same convention as any
Streamlit multi-page app).
"""

import streamlit as st

# Standard workaround for Streamlit's known session-state-loss-on-page-
# switch issue (streamlit/streamlit#5689, #11115) — re-touching every
# existing key forces it to be properly preserved across page visits,
# protecting things like the computed chart on the Readings page.
for _k in list(st.session_state.keys()):
    st.session_state[_k] = st.session_state[_k]

SIGN_INFO = {
    "Aries": (
        "Fire, Cardinal, ruled by Mars",
        "Aries is the first sign of the zodiac, and it carries a real "
        "'first mover' quality — direct, instinctive, and comfortable "
        "acting before every detail is worked out. Where Aries energy is "
        "strong, there's usually genuine courage and a willingness to "
        "take the first step that other placements might hesitate on. "
        "The tradeoff is follow-through: Aries initiates far more "
        "naturally than it sustains, and can lose interest once the "
        "novelty of starting something wears off. Conflict isn't "
        "avoided here — it's often approached head-on, sometimes before "
        "it's fully necessary. Patience, both with others and with slow "
        "processes, is usually the real growth edge."
    ),
    "Taurus": (
        "Earth, Fixed, ruled by Venus",
        "Taurus brings a grounded, sensory quality — a genuine need for "
        "physical comfort, stability, and things that can actually be "
        "trusted to last. This isn't laziness so much as a real "
        "resistance to being rushed or destabilized; Taurus energy wants "
        "to build something solid rather than move fast. Once committed "
        "to a person, project, or routine, that commitment tends to be "
        "durable and reliable, sometimes to the point of real "
        "stubbornness when change is being pushed from outside. Taurus "
        "also has a strong relationship to the physical world — taste, "
        "texture, and tangible quality genuinely matter here, not as "
        "vanity but as a real source of security."
    ),
    "Gemini": (
        "Air, Mutable, ruled by Mercury",
        "Gemini is curious, quick, and fundamentally interested in "
        "variety — gathering information from many angles rather than "
        "settling into one fixed viewpoint. This produces real "
        "adaptability and a genuine talent for communication, since "
        "Gemini energy naturally translates between different ideas or "
        "people. The challenge is depth versus breadth: interest can "
        "move on before a subject or commitment is fully explored, and "
        "focus can genuinely scatter across too many open threads at "
        "once. Gemini also tends to process feelings by talking or "
        "thinking them through rather than simply sitting with them."
    ),
    "Cancer": (
        "Water, Cardinal, ruled by the Moon",
        "Cancer is protective and deeply emotionally attuned, oriented "
        "around safety, belonging, and care — for itself and for "
        "others. Despite being a Cardinal sign (meaning it initiates "
        "rather than just responds), that initiation usually shows up "
        "as care-taking: creating a home, a sense of family, or "
        "emotional security for a group. Cancer is genuinely sensitive "
        "to the emotional tone of a room and can absorb others' "
        "feelings without quite meaning to. When it feels unsafe, the "
        "instinct is to withdraw and protect rather than confront "
        "directly — the challenge is learning that not every "
        "vulnerability requires a defensive shell."
    ),
    "Leo": (
        "Fire, Fixed, ruled by the Sun",
        "Leo is warm, expressive, and oriented toward being genuinely "
        "seen and valued — not from vanity, but from a real need for "
        "authentic recognition of what's actually being offered. As a "
        "Fixed fire sign, Leo sustains creative effort and loyalty once "
        "genuinely engaged, unlike the more scattered fire energy of "
        "Aries or Sagittarius. There's real generosity here too — Leo "
        "energy often wants others to shine as well, provided its own "
        "contribution is acknowledged. The growth edge is usually "
        "learning that self-worth doesn't require an audience — that "
        "genuine value doesn't evaporate without applause."
    ),
    "Virgo": (
        "Earth, Mutable, ruled by Mercury",
        "Virgo is precise, service-oriented, and genuinely "
        "detail-attentive — it notices what's slightly off and has a "
        "real drive to fix or improve it. This makes Virgo energy "
        "excellent at refinement, troubleshooting, and practical "
        "problem-solving, though it's rarely the energy that initiates "
        "something from nothing. Under stress, that same precision can "
        "turn inward as self-criticism or outward as over-analysis of "
        "things that don't actually need fixing. Virgo's real strength "
        "is competence quietly applied — showing care through useful "
        "action rather than declarations."
    ),
    "Libra": (
        "Air, Cardinal, ruled by Venus",
        "Libra is relational and fairness-oriented, and it initiates "
        "through seeking balance, partnership, and genuine consensus "
        "rather than unilateral action. There's a real gift here for "
        "seeing multiple sides of a situation and finding where "
        "compromise is actually possible — though that same "
        "even-handedness can make timely, decisive action genuinely "
        "difficult. Libra energy often defines itself partly through "
        "relationship to others, for better (real diplomatic skill) and "
        "for worse (difficulty being alone with an unpopular decision). "
        "Aesthetic sense tends to matter here too — harmony isn't just "
        "social, it's visual and environmental."
    ),
    "Scorpio": (
        "Water, Fixed, ruled by Pluto (traditionally Mars)",
        "Scorpio is intense, private, and instinctively drawn to what's "
        "beneath the surface — the real motive, the unspoken feeling, "
        "the thing everyone else is avoiding. As a Fixed water sign, "
        "Scorpio sustains deep focus and real loyalty once trust has "
        "genuinely been earned, but that trust isn't given easily or "
        "quickly. There's a real capacity for transformation here — "
        "Scorpio energy doesn't shy away from difficult change, and "
        "often handles crisis better than calm. The tradeoff is a "
        "tendency toward control or suspicion when feeling exposed, "
        "since vulnerability doesn't come naturally."
    ),
    "Sagittarius": (
        "Fire, Mutable, ruled by Jupiter",
        "Sagittarius is expansive and meaning-seeking, oriented toward "
        "the big picture, the underlying philosophy, or the horizon "
        "rather than fine detail. This produces real optimism and a "
        "genuine hunger for growth — through travel, ideas, education, "
        "or belief systems that make sense of the world. Sagittarius "
        "energy is honest, sometimes bluntly so, since diplomacy can "
        "feel like it gets in the way of the actual point. The real "
        "growth edge is usually follow-through on the practical, "
        "unglamorous details that turn a big idea into something "
        "genuinely finished."
    ),
    "Capricorn": (
        "Earth, Cardinal, ruled by Saturn",
        "Capricorn is disciplined and long-game oriented, and it "
        "initiates through building structure, taking on real "
        "responsibility, and playing for outcomes that take years, not "
        "days. There's genuine capacity for sustained effort here — "
        "Capricorn energy is comfortable with delayed reward in a way "
        "few other signs are, and tends to earn authority through "
        "demonstrated competence rather than charisma. The real risk is "
        "under-valuing rest, play, or anything that doesn't visibly "
        "build toward a goal — Capricorn can mistake constant "
        "productivity for actual worth."
    ),
    "Aquarius": (
        "Air, Fixed, ruled by Uranus (traditionally Saturn)",
        "Aquarius is independent-minded and idea-driven, and as a Fixed "
        "air sign it sustains genuine commitment to principles, causes, "
        "or communities over time, even when that commitment costs "
        "personal closeness. There's real value placed on being "
        "authentically original here — following the crowd, even a "
        "crowd Aquarius agrees with, can feel like a small betrayal of "
        "self. This can produce genuine innovation, but also a real "
        "difficulty with emotional intimacy, since ideas are often more "
        "comfortable territory than feelings. Aquarius tends to care "
        "about humanity broadly and can sometimes struggle with the "
        "individual person right in front of it."
    ),
    "Pisces": (
        "Water, Mutable, ruled by Neptune (traditionally Jupiter)",
        "Pisces is absorptive and imaginative, and it adapts by "
        "dissolving rigid boundaries — between self and others, between "
        "reality and possibility, between what's literal and what's "
        "felt. This produces real empathy and genuine creative or "
        "spiritual sensitivity, often a real gift for art, healing, or "
        "simply understanding what someone else is going through "
        "without being told. The tradeoff is a real difficulty holding "
        "personal limits — Pisces can lose track of where it ends and "
        "someone else begins, or retreat into imagination rather than "
        "face something difficult directly."
    ),
}

POINT_INFO = {
    "Sun": (
        "Core identity, vitality, and what a person is fundamentally "
        "expressing or growing toward. The Sun represents the central "
        "organizing theme of a chart — not just a personality trait, but "
        "the ongoing project of becoming more fully who someone actually "
        "is. Its sign describes the flavor of that expression, its house "
        "describes where in life it's most naturally expressed, and its "
        "dignity describes how easily that expression comes."
    ),
    "Moon": (
        "Emotional instinct, what feels safe, and how a person processes "
        "feeling beneath the surface of conscious thought. Where the Sun "
        "is who someone is trying to become, the Moon is closer to who "
        "someone already is on an instinctive, often unconscious level — "
        "the reactions that show up before any deliberate thought "
        "happens. It's strongly tied to a sense of home, comfort, and "
        "what genuinely provides emotional security."
    ),
    "Mercury": (
        "Communication and thinking style — how information gets "
        "gathered, processed, and expressed, whether that's quick and "
        "verbal or slower and more written/considered. Mercury governs "
        "not just speech but the whole cognitive process: how someone "
        "learns, how they argue a point, and whether they think out loud "
        "or need private processing time before speaking."
    ),
    "Venus": (
        "Values, aesthetic sense, and how a person relates, attracts, "
        "and builds rapport with others. Venus describes what someone "
        "considers genuinely beautiful, valuable, or worth pursuing — in "
        "relationships, in taste, and in what they're willing to "
        "compromise for versus hold firm on. It's as much about "
        "self-worth and personal values as it is about romantic "
        "attraction."
    ),
    "Mars": (
        "Drive, assertion, and how a person pursues goals or handles "
        "conflict and competition. Mars describes the raw energy behind "
        "action — how someone goes after what they want, how directly "
        "they express anger or push back, and what genuinely motivates "
        "them to move rather than wait. Its condition often reveals "
        "whether assertion comes easily or requires real effort."
    ),
    "Jupiter": (
        "Growth, expansion, and where a person finds meaning, "
        "confidence, or opportunity. Jupiter represents the areas of "
        "life that tend to expand naturally — through luck, "
        "overconfidence, genuine opportunity, or sometimes overreach. "
        "It's traditionally associated with philosophy, higher "
        "learning, travel, and the belief systems someone uses to make "
        "sense of the world."
    ),
    "Saturn": (
        "Structure, discipline, and the areas of life that require "
        "sustained effort and mature over time rather than arriving "
        "easily. Saturn is often experienced as restriction or "
        "difficulty, but it's more accurately the planet of real, "
        "earned mastery — what doesn't come naturally at first but "
        "becomes genuinely solid once built. Its placement often points "
        "to where someone carries real responsibility or a fear of "
        "inadequacy."
    ),
    "Uranus": (
        "Disruption, independence, and the drive toward genuine "
        "originality or sudden change. Uranus represents the impulse to "
        "break from convention, sometimes constructively and sometimes "
        "just for the sake of not conforming. It moves slowly enough "
        "that its house placement (specific to an individual) often "
        "matters more than its sign (shared by a whole generation)."
    ),
    "Neptune": (
        "Imagination, dissolution of boundaries, idealism, and "
        "spiritual or artistic sensitivity. Neptune blurs the line "
        "between what's real and what's imagined or hoped for — capable "
        "of real inspiration, compassion, and creative vision, but also "
        "genuine confusion, denial, or escapism when its energy isn't "
        "grounded by something more concrete elsewhere in the chart."
    ),
    "Pluto": (
        "Deep transformation, power, and what a person must face and "
        "rebuild rather than avoid. Pluto represents the parts of life "
        "that resist surface-level fixes and instead require something "
        "closer to a genuine death-and-rebirth process — often "
        "connected to control, power dynamics, or deeply held fears "
        "that only loosen their grip once actually confronted."
    ),
    "Chiron": (
        "The 'wounded healer' — a core sensitivity or old wound that, "
        "when worked with rather than avoided, becomes a genuine source "
        "of insight or healing capacity for others. Chiron's placement "
        "often points to an area where someone has felt genuinely "
        "inadequate or hurt, and paradoxically, where they often end up "
        "offering real wisdom to others precisely because they know "
        "that terrain so well."
    ),
    "North Node": (
        "The direction of growth a person is meant to develop toward — "
        "often unfamiliar, effortful, or even uncomfortable at first, "
        "precisely because it isn't already second nature. Working "
        "toward the North Node's themes tends to feel like real "
        "stretching rather than easy comfort, but it's where meaningful "
        "long-term development tends to happen."
    ),
    "South Node": (
        "Innate, familiar patterns a person naturally falls back on — "
        "comfortable and well-practiced, but not where genuine growth "
        "lies. The South Node isn't something to eliminate so much as a "
        "well-worn default that's worth using consciously rather than "
        "leaning on automatically whenever the more effortful North "
        "Node direction feels too hard."
    ),
    "Ascendant": (
        "The rising sign — how a person initiates and comes across to "
        "others, and the lens through which they meet the world. It's "
        "also the cusp of the 1st house, and it requires an exact birth "
        "time to calculate correctly, since it shifts roughly one "
        "degree every four minutes. Often described as the 'mask' or "
        "first impression, distinct from someone's deeper Sun or Moon "
        "nature."
    ),
    "Descendant": (
        "The cusp of the 7th house, sitting exactly opposite the "
        "Ascendant — associated with partnership, and with what a "
        "person seeks in or unconsciously projects onto significant "
        "others. Where the Ascendant is how someone shows up, the "
        "Descendant often describes what someone is drawn to complete "
        "themselves through relationship."
    ),
    "Midheaven": (
        "The cusp of the 10th house — public role, career direction, "
        "and reputation. The Midheaven describes the identity someone "
        "builds in the world at large, as opposed to the more private "
        "self described by the Ascendant or the even more private "
        "Imum Coeli."
    ),
    "Imum Coeli": (
        "The cusp of the 4th house, opposite the Midheaven — home, "
        "roots, and private emotional foundation. Often associated with "
        "family background and the psychological 'floor' someone "
        "returns to beneath their public-facing identity."
    ),
    "Vertex": (
        "A lesser-used, more mathematically abstract point sometimes "
        "associated with fated encounters or significant turning "
        "points, especially in relationships. It requires an exact "
        "birth time and location to calculate, and becomes unreliable "
        "near the polar circles."
    ),
    "Anti-Vertex": (
        "The point directly opposite the Vertex, completing that same "
        "axis. Interpreted similarly, though generally given less "
        "individual weight than the Vertex itself."
    ),
    "Part of Fortune": (
        "A calculated point (not a planet) traditionally tied to where "
        "ease, vitality, or good fortune shows up most naturally. Its "
        "formula depends on whether someone was born during the day or "
        "night, and — like the Ascendant — it requires an exact birth "
        "time to be meaningful."
    ),
    "Part of Spirit": (
        "A calculated point representing conscious will and purpose — "
        "the classical counterpart to the more fated, bodily Part of "
        "Fortune. Where Part of Fortune points to where things come "
        "easily, Part of Spirit points to where deliberate effort and "
        "intention tend to pay off."
    ),
}

HOUSE_INFO = {
    1: (
        "Self, Identity & First Impressions",
        "The 1st house governs the physical body, personal identity, and "
        "how a person initiates and comes across to others before "
        "anyone gets to know them more deeply. It's ruled by the "
        "Ascendant, and planets placed here tend to color someone's "
        "outward presentation strongly, almost like a second layer of "
        "personality on top of the Sun and Moon."
    ),
    2: (
        "Resources, Money & Self-Worth",
        "The 2nd house covers tangible resources — money, possessions, "
        "and material security — but also the less tangible sense of "
        "personal value someone assigns to themselves. What's placed "
        "here often describes not just how someone earns or holds onto "
        "resources, but what they fundamentally believe they deserve."
    ),
    3: (
        "Communication & the Immediate Environment",
        "The 3rd house is about everyday communication, short trips, "
        "siblings, and the immediate environment someone moves through "
        "day to day — school, neighbors, casual learning. It's a more "
        "local, concrete counterpart to the bigger-picture 9th house on "
        "the opposite side of the chart."
    ),
    4: (
        "Home, Family & Emotional Foundations",
        "The 4th house represents home, family, ancestry, and the "
        "emotional foundation someone builds their life on top of. "
        "Traditionally linked to one parent (conventions vary), it's "
        "less about the literal house someone lives in and more about "
        "the deep sense of roots and belonging underneath everything "
        "else."
    ),
    5: (
        "Creativity, Romance & Genuine Pleasure",
        "The 5th house covers creative self-expression, romance, "
        "children, and pleasure — the things someone does not out of "
        "obligation but because they genuinely want to. It's often "
        "where a person's most authentic, playful creativity shows up, "
        "distinct from the more disciplined creative output tied to "
        "career houses."
    ),
    6: (
        "Daily Work, Routine & Health",
        "The 6th house governs daily work, routines, health habits, and "
        "service — the unglamorous, repeated actions that make up most "
        "of ordinary life. It also relates to peer-level colleagues, "
        "distinct from the more authority-oriented 10th house, and to "
        "the body as a functioning, maintained system."
    ),
    7: (
        "Partnerships & How We Meet Others",
        "The 7th house covers marriage, open partnerships, business "
        "contracts, and how someone approaches one-on-one relationships "
        "generally. Sitting opposite the 1st house, it often describes "
        "qualities a person seeks in others to balance or complete their "
        "own self-presentation."
    ),
    8: (
        "Shared Resources, Intimacy & Transformation",
        "The 8th house covers shared resources (joint finances, "
        "inheritance, other people's money), deep intimacy, and "
        "transformation — the kind of change that comes through real "
        "crisis or vulnerability rather than gradual adjustment. It's "
        "traditionally associated with death and rebirth in both literal "
        "and psychological senses."
    ),
    9: (
        "Philosophy, Higher Learning & Travel",
        "The 9th house covers higher education, philosophy, "
        "long-distance travel, and belief systems — the search for "
        "meaning on a bigger scale than the everyday learning of the "
        "3rd house. Publishing and teaching are traditionally tied here "
        "too, since both involve sharing a worldview broadly."
    ),
    10: (
        "Career, Reputation & Public Role",
        "The 10th house governs career, public reputation, and life "
        "direction — the identity someone builds in the world at large. "
        "Ruled by the Midheaven, it's traditionally linked to the other "
        "parent (conventions vary) and to the legacy or authority "
        "someone works to establish."
    ),
    11: (
        "Community, Friendship & Long-Term Goals",
        "The 11th house covers community, friendships, group "
        "involvement, and long-term hopes or goals — the network of "
        "people and aspirations someone builds beyond their immediate "
        "family or romantic partnerships. It's often where a sense of "
        "belonging to something larger than oneself shows up."
    ),
    12: (
        "The Unconscious, Solitude & Hidden Matters",
        "The 12th house governs the unconscious mind, solitude, "
        "spirituality, and matters that stay hidden — including "
        "self-undoing patterns someone isn't fully aware they're "
        "repeating. It's traditionally the most private, least "
        "outward-facing house, associated with retreat, rest, and "
        "what happens beneath conscious awareness."
    ),
}

DIGNITY_INFO = [
    ("Rulership (Domicile)", "+5",
     "A planet is in Rulership when it sits in the sign it governs — "
     "Mars in Aries, Venus in Taurus, and so on. This is the strongest "
     "essential dignity: the planet is most 'at home,' expressing its "
     "core nature directly and without friction. Modern astrology "
     "layers additional co-rulers onto three signs alongside their "
     "traditional ruler — Pluto co-rules Scorpio (traditionally Mars), "
     "Uranus co-rules Aquarius (traditionally Saturn), and Neptune "
     "co-rules Pisces (traditionally Jupiter). This app checks both "
     "the traditional and modern ruler for those three signs."),
    ("Exaltation", "+4",
     "A planet is Exalted in a sign where its qualities are especially "
     "amplified or honored — a placement of distinction, even if it's "
     "not the planet's own sign. The Sun is exalted in Aries, the Moon "
     "in Taurus, Jupiter in Cancer, Mercury in Virgo, Saturn in Libra, "
     "Mars in Capricorn, and Venus in Pisces. Not every planet has a "
     "traditionally recognized exaltation sign — Uranus, Neptune, and "
     "Pluto don't have one in this system, since exaltation is an "
     "older technique that predates their discovery."),
    ("Peregrine", "0",
     "A planet is Peregrine when it has no essential dignity at all in "
     "its current sign — not ruling, not exalted, not in detriment, "
     "not in fall. This is genuinely neutral territory: the planet "
     "isn't specially strengthened or weakened by sign placement, so "
     "its expression depends more on aspects, house placement, and the "
     "rest of the chart than on the sign itself."),
    ("Fall", "-4",
     "A planet is in Fall in the sign directly opposite its "
     "exaltation — the most uncomfortable placement in this system, "
     "even more awkward than Detriment in some traditions. The Sun "
     "falls in Libra, the Moon in Scorpio, Jupiter in Capricorn, "
     "Mercury in Pisces, Saturn in Aries, Mars in Cancer, and Venus in "
     "Virgo. A planet in Fall doesn't lose its underlying meaning — it "
     "just tends to express that meaning with real difficulty or "
     "self-doubt until it's consciously worked with."),
    ("Detriment", "-5",
     "A planet is in Detriment in the sign directly opposite the one "
     "it rules — real friction with its natural mode of expression. "
     "Mars in Libra, Venus in Aries, and so on. This doesn't mean the "
     "planet is 'bad' there, just that its usual way of operating "
     "doesn't fit naturally with that sign's energy, so it often has "
     "to work harder or find an unconventional approach to express "
     "itself well."),
]

ASPECT_INFO = [
    ("Conjunction", "0°", "8°", "major", "blended/intensified",
     "The tightest possible aspect — two points sitting essentially on "
     "top of each other. Their energies blend and intensify rather "
     "than interact from a distance, which makes a conjunction feel "
     "less like a 'relationship' between two planets and more like a "
     "fusion of them. Whether that reads as a strength or a strain "
     "depends heavily on which two points are involved and their "
     "individual dignity."),
    ("Sextile", "60°", "4°", "major", "easy/opportunity",
     "A supportive, easygoing angle — the two points work well "
     "together, but the aspect doesn't force anything to happen on its "
     "own. A sextile represents a genuine opportunity or natural "
     "talent that still needs to be actively used to matter; it's "
     "helpful potential rather than automatic ease."),
    ("Square", "90°", "7°", "major", "tension/friction",
     "One of the two classic 'hard' aspects — real, active tension "
     "between the two points that demands attention and resolution "
     "rather than sitting quietly in the background. Squares are "
     "often where the most genuine growth happens, precisely because "
     "they can't easily be ignored the way an easier aspect can."),
    ("Trine", "120°", "7°", "major", "flowing/harmonious",
     "The most naturally harmonious major aspect — the two points "
     "support each other with real ease, often to the point that the "
     "talent or strength involved is taken for granted rather than "
     "deliberately developed. Because a trine doesn't create friction, "
     "it can sometimes represent an underused gift rather than an "
     "active one."),
    ("Opposition", "180°", "8°", "major", "polarity/awareness",
     "Two points facing each other directly across the chart — real "
     "tension, but of a different flavor than a square. Where a "
     "square creates friction that demands action, an opposition "
     "creates awareness of two competing needs that usually require "
     "genuine balancing rather than a clean resolution."),
    ("Semisextile", "30°", "2°", "minor", "mild friction",
     "A subtle, minor connection between two points that are "
     "adjacent but not directly related — a little awkward, a little "
     "unfamiliar, but rarely a major factor on its own. Semisextiles "
     "tend to matter more as part of a larger pattern than as a "
     "standalone influence."),
    ("Semisquare", "45°", "2°", "minor", "low-grade tension",
     "A minor 'hard' aspect — a lower-intensity cousin of the square, "
     "producing real but manageable friction rather than a major "
     "demand for resolution. Often shows up as a persistent minor "
     "irritant rather than a dramatic conflict."),
    ("Sesquiquadrate", "135°", "2°", "minor", "low-grade tension",
     "Another minor hard aspect, similar in flavor to the semisquare "
     "but at a different angle. Represents a background source of "
     "friction that tends to build up gradually rather than announce "
     "itself all at once."),
    ("Quincunx", "150°", "3°", "minor", "adjustment/awkward fit",
     "A genuinely awkward angle — the two points involved have very "
     "little natural relationship to each other, since 150° doesn't "
     "correspond to any clean geometric division of the circle the "
     "way the major aspects do. Quincunxes often require ongoing, "
     "conscious adjustment rather than ever fully resolving, since "
     "the two areas of life involved just don't naturally speak the "
     "same language."),
    ("Quintile", "72°", "2°", "minor", "creative/talent",
     "A minor aspect tied to creativity and individual talent — based "
     "on dividing the circle by five rather than the more common "
     "divisions behind the major aspects. Quintiles are traditionally "
     "read as a specific, sometimes unusual skill or creative gift "
     "rather than a general strength or tension."),
]

st.title("📚 Resources")
st.caption("A reference glossary for the signs, planets/points, and "
           "houses used throughout your readings.")

tab_signs, tab_points, tab_houses, tab_dignity, tab_aspects = st.tabs(
    ["Signs", "Planets & Points", "Houses", "Dignity", "Aspects"]
)

with tab_signs:
    for sign, (essentials, description) in SIGN_INFO.items():
        st.subheader(sign)
        st.caption(essentials)
        st.write(description)
        st.divider()

with tab_points:
    for name, description in POINT_INFO.items():
        st.subheader(name)
        st.write(description)
        st.divider()

with tab_houses:
    for house_num, (theme, description) in HOUSE_INFO.items():
        st.subheader(f"House {house_num} — {theme}")
        st.write(description)
        st.divider()

with tab_dignity:
    st.write(
        "Essential dignity describes how 'at home' or 'out of place' a "
        "planet is, based purely on which sign it occupies — one of the "
        "oldest techniques in astrology, predating modern psychological "
        "approaches by centuries. It's a natural companion to aspects: "
        "a hard aspect from a well-dignified planet tends to play out "
        "very differently than the same aspect from a debilitated one, "
        "which is why every reading in this app weights dignity "
        "alongside sign, house, and aspect data rather than treating "
        "sign placement alone as the full picture."
    )
    st.divider()
    for name, score, description in DIGNITY_INFO:
        st.subheader(name)
        st.caption(f"Score: {score}")
        st.write(description)
        st.divider()

with tab_aspects:
    st.write(
        "An aspect is a meaningful angular relationship between two "
        "points in a chart — how far apart they sit on the 360° "
        "wheel. Each aspect type corresponds to a specific angle, and "
        "each carries its own character, from the intensity of a "
        "conjunction (0° apart) to the tension of a square (90° apart) "
        "to the ease of a trine (120° apart). An 'orb' is the margin "
        "of error allowed around that exact angle — a Sun-Moon square "
        "doesn't need to be exactly 90.00° apart to count, just within "
        "the configured orb. Major aspects use wider orbs and carry "
        "more weight; minor aspects use tighter orbs and represent "
        "more subtle, specific influences."
    )
    st.divider()
    st.subheader("Major Aspects")
    st.caption("Wider orbs, generally the most significant influences in a chart.")
    for name, angle, orb, category, nature, description in ASPECT_INFO:
        if category != "major":
            continue
        st.markdown(f"**{name}** — {angle} apart, {orb} orb *({nature})*")
        st.write(description)
        st.divider()
    st.subheader("Minor Aspects")
    st.caption("Tighter orbs, more subtle or specific than the major aspects.")
    for name, angle, orb, category, nature, description in ASPECT_INFO:
        if category != "minor":
            continue
        st.markdown(f"**{name}** — {angle} apart, {orb} orb *({nature})*")
        st.write(description)
        st.divider()
