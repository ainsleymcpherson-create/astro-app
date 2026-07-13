# Astrology Chart Calculator

Computes birth charts with full support for lesser-used points that most
astrology tools skip — Part of Fortune, Part of Spirit, the Lunar Nodes,
Vertex, and Chiron — alongside standard planets, aspects (including
detected patterns like Grand Trines, T-Squares, and Yods), essential
dignity, and house interpretation that actually explains empty houses
through their ruling planet rather than ignoring them.

Includes a Streamlit web interface for interactive local testing, and
generates a ready-to-use LLM prompt for full chart interpretation.

## Setup

**1. Install Python 3.10+** if you don't already have it.

**2. Clone this repo and install dependencies:**
```bash
git clone <your-repo-url>
cd astro-app
pip install -r requirements.txt
```
(Consider using a virtual environment: `python3 -m venv venv && source venv/bin/activate` before the pip install.)

**3. Download the Chiron ephemeris file (one-time):**
```bash
python3 download_ephemeris.py
```
This downloads `seas_18.se1` into a local `./ephe` folder. The standard
planets work without this (pyswisseph has a built-in approximation), but
Chiron specifically needs it.

**4. Run the app:**
```bash
streamlit run app.py
```
This opens a browser tab at `http://localhost:8501` with the interactive interface.

## Project structure

| File | Purpose |
|---|---|
| `app.py` | Streamlit frontend — the entry point |
| `chart_points.py` | Core ephemeris calculations (planets, angles, houses, Nodes, Part of Fortune/Spirit, Vertex, Chiron) |
| `aspect_engine.py` | Aspect detection + pattern recognition (Grand Trines, T-Squares, Grand Crosses, Yods, Stelliums) |
| `dignity.py` | Essential dignity (Rulership, Exaltation, Detriment, Fall) |
| `house_interpretation.py` | House themes + empty-house interpretation via ruling planet |
| `prompt_builder.py` | Assembles all computed data into an LLM-ready interpretation prompt |
| `birth_input.py` | Geocodes a location string and resolves the correct historical timezone automatically |
| `download_ephemeris.py` | One-time setup script for the Chiron data file |

## Deploying publicly (later)

This same codebase deploys to [Streamlit Community Cloud](https://streamlit.io/cloud)
for free, with no code changes:

1. Push this repo to GitHub (public repo required for the free tier)
2. Go to share.streamlit.io, connect your GitHub account, point it at this repo and `app.py`
3. Add a `packages.txt` file if the deploy environment needs system-level build tools for pyswisseph (check Streamlit Cloud's build logs if the deploy fails on the pyswisseph install step)
4. The `./ephe` folder needs to be committed to the repo (or downloaded via a startup script) since Streamlit Cloud won't have run `download_ephemeris.py` for you

## License

Add an open-source license of your choice (MIT is a common default for
this kind of project) before making the repo public.
