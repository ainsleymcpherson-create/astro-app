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

SIGN_INFO = {
    "Aries": ("Fire, Cardinal, ruled by Mars",
              "Direct, initiating energy — the instinct to act first and "
              "ask questions later. Comfortable starting things, less "
              "naturally drawn to finishing or maintaining them."),
    "Taurus": ("Earth, Fixed, ruled by Venus",
               "Steady, sensory, and resistant to being rushed. Values "
               "security, comfort, and consistency — slow to change "
               "course but reliable once committed."),
    "Gemini": ("Air, Mutable, ruled by Mercury",
               "Curious, quick, and communicative — gathers information "
               "from many angles rather than settling on one. Thrives on "
               "variety; can scatter focus across too many threads."),
    "Cancer": ("Water, Cardinal, ruled by the Moon",
               "Protective and emotionally attuned, oriented around "
               "safety and belonging. Initiates through care-taking; "
               "sensitive to the emotional tone of a room."),
    "Leo": ("Fire, Fixed, ruled by the Sun",
            "Warm, expressive, and oriented toward being genuinely seen. "
            "Sustains creative effort once engaged; wants recognition for "
            "what's offered, not just to perform."),
    "Virgo": ("Earth, Mutable, ruled by Mercury",
              "Precise, service-oriented, and detail-attentive. Improves "
              "and refines rather than initiates; can default to "
              "self-criticism or over-analysis under stress."),
    "Libra": ("Air, Cardinal, ruled by Venus",
              "Relational and fairness-oriented, initiates through "
              "seeking balance and partnership. Weighs multiple "
              "perspectives carefully — sometimes at the cost of a "
              "timely decision."),
    "Scorpio": ("Water, Fixed, ruled by Pluto (traditionally Mars)",
                "Intense, private, and drawn to what's beneath the "
                "surface. Sustains deep focus and loyalty once trust is "
                "earned; guarded until then."),
    "Sagittarius": ("Fire, Mutable, ruled by Jupiter",
                    "Expansive and meaning-seeking, oriented toward the "
                    "big picture over fine detail. Adapts by exploring "
                    "new territory — geographic, intellectual, or "
                    "philosophical."),
    "Capricorn": ("Earth, Cardinal, ruled by Saturn",
                  "Disciplined and long-game oriented, initiates through "
                  "structure and responsibility. Comfortable with delayed "
                  "reward; can under-value rest or play."),
    "Aquarius": ("Air, Fixed, ruled by Uranus (traditionally Saturn)",
                 "Independent-minded and idea-driven, sustains commitment "
                 "to principles or community over individual closeness. "
                 "Values being genuinely original."),
    "Pisces": ("Water, Mutable, ruled by Neptune (traditionally Jupiter)",
               "Absorptive and imaginative, adapts by dissolving rigid "
               "boundaries between self and surroundings. Deeply "
               "empathetic; can lose track of personal limits."),
}

POINT_INFO = {
    "Sun": "Core identity, vitality, and what a person is fundamentally "
           "expressing or growing toward. The chart's central organizing "
           "theme.",
    "Moon": "Emotional instinct, what feels safe, and how a person "
            "processes feeling beneath the surface of conscious thought.",
    "Mercury": "Communication and thinking style — how information gets "
               "gathered, processed, and expressed.",
    "Venus": "Values, aesthetic sense, and how a person relates, "
             "attracts, and builds rapport.",
    "Mars": "Drive, assertion, and how a person pursues goals or handles "
            "conflict and competition.",
    "Jupiter": "Growth, expansion, and where a person finds meaning, "
               "confidence, or opportunity.",
    "Saturn": "Structure, discipline, and the areas of life that require "
              "sustained effort and mature over time rather than "
              "arriving easily.",
    "Uranus": "Disruption, independence, and the drive toward genuine "
              "originality or sudden change.",
    "Neptune": "Imagination, dissolution of boundaries, idealism, and "
               "spiritual or artistic sensitivity.",
    "Pluto": "Deep transformation, power, and what a person must face "
             "and rebuild rather than avoid.",
    "Chiron": "The 'wounded healer' — a core sensitivity that, when "
              "worked with rather than avoided, becomes a genuine source "
              "of insight or healing capacity for others.",
    "North Node": "The direction of growth a person is meant to develop "
                  "toward — often unfamiliar or effortful at first.",
    "South Node": "Innate, familiar patterns a person naturally falls "
                  "back on — comfortable, but not where growth lies.",
    "Ascendant": "The rising sign — how a person initiates and comes "
                 "across to others, and the lens through which they meet "
                 "the world. Also the cusp of the 1st house.",
    "Descendant": "The cusp of the 7th house — partnership, and what a "
                  "person seeks in or projects onto significant others.",
    "Midheaven": "The cusp of the 10th house — public role, career "
                 "direction, and reputation.",
    "Imum Coeli": "The cusp of the 4th house — home, roots, and private "
                  "emotional foundation.",
    "Vertex": "A lesser-used point sometimes associated with fated "
              "encounters or turning points, especially in relationships.",
    "Anti-Vertex": "The point directly opposite the Vertex, completing "
                   "that same axis.",
    "Part of Fortune": "A calculated point (not a planet) traditionally "
                       "tied to where ease, vitality, or good fortune "
                       "shows up most naturally.",
    "Part of Spirit": "A calculated point representing conscious will "
                      "and purpose — the counterpart to the more fated "
                      "Part of Fortune.",
}

HOUSE_INFO = {
    1: "Self, identity, physical body, and how a person initiates and "
       "comes across to others.",
    2: "Resources, money, possessions, self-worth, and what a person "
       "values.",
    3: "Communication, siblings, short trips, everyday learning, and "
       "the immediate environment.",
    4: "Home, family, roots, ancestry, emotional foundations, and one "
       "parent.",
    5: "Creativity, romance, self-expression, children, pleasure, and "
       "risk-taking.",
    6: "Daily work, routines, health habits, service, and the body as a "
       "functioning system.",
    7: "Partnerships, marriage, open relationships, contracts, and how "
       "a person meets others.",
    8: "Shared resources, intimacy, transformation, death/rebirth, and "
       "other people's money.",
    9: "Philosophy, higher education, long-distance travel, belief "
       "systems, and publishing.",
    10: "Career, public reputation, life direction, authority, and the "
        "other parent.",
    11: "Community, friendships, groups, hopes, and long-term goals.",
    12: "The unconscious, solitude, spirituality, hidden matters, and "
        "self-undoing.",
}

st.title("📚 Resources")
st.caption("A reference glossary for the signs, planets/points, and "
           "houses used throughout your readings.")

category = st.radio(
    "Category", ["Signs", "Planets & Points", "Houses"],
    horizontal=True, label_visibility="collapsed",
)

if category == "Signs":
    for sign, (essentials, description) in SIGN_INFO.items():
        with st.expander(sign):
            st.caption(essentials)
            st.write(description)
elif category == "Planets & Points":
    for name, description in POINT_INFO.items():
        with st.expander(name):
            st.write(description)
else:
    for house_num, description in HOUSE_INFO.items():
        with st.expander(f"House {house_num}"):
            st.write(description)
