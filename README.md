# የእውነት ፈተና — The Test of Truth

A ~68-second Ethiopian short film about **Addisu (`አዲሱ`)**, a young man who must choose between respecting a family elder and speaking the truth to save an innocent person. Narrated in Amharic (`gemini-3.8-flash-tts` with automatic `gemini-3.8-flash-lite-tts` fallback) with English subtitles, an original Ethiopian instrumental score (`ACE-Step 1.5`), and exported in both `16:9` (`1280×720`) and `9:16` (`720×1280`).

**Made with an automated, storyboard-driven AI pipeline.** One contract file (`storyboard.json`) drives every stage.

## Quick Start

```bash
# 1. Clone and enter the repository
git clone https://github.com/Taddeal/tenx.git
cd tenx

# 2. Configure API keys (never commit .env)
cp .env.example .env
# Set GEMINI_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN

# 3. Install Python dependencies (requires Python 3.10+ and FFmpeg)
pip install -r requirements.txt

# 4. Run the entire pipeline with one command (Windows / macOS / Linux)
python run_pipeline.py
# Or on Linux/macOS with GNU Make:
make film

# Optional Phase 1, Ceiling & Unit Tests (`python run_pipeline.py` stays Amharic-only):
python pipeline/smoke_test.py
python run_pipeline.py --radio-cut          # Phase 1: narration + radio_cut.mp4
python pipeline/benchmark_languages.py     # Ceiling: separate full 16:9/9:16 films in Afaan Oromo & Tigrinya
python -m unittest discover -s tests -v    # Contract & rendering tests
```

### Run Individual Stages

```bash
python run_pipeline.py --stage 0   # Validate storyboard against JSON Schema
python run_pipeline.py --stage 1   # Generate Amharic narration (Gemini 3.8 Flash TTS)
python run_pipeline.py --stage 2   # Generate character reference sheet & keyframes (Cloudflare FLUX)
python run_pipeline.py --stage 3   # Generate moving shots (Wan 2.2 or smooth Ken Burns)
python run_pipeline.py --stage 4   # Print/save ACE-Step 1.5 music generation parameters
python run_pipeline.py --stage 5   # Assemble 16:9 & 9:16 MP4s (ducking, subtitles, -14 LUFS, end card)
```

## Pipeline Architecture

```
storyboard.json (+ schema/storyboard.schema.json)
        │
        ├──▶ 00_validate.py    Schema & semantic contract validation
        ├──▶ 01_narration.py   Gemini 3.8 Flash TTS → outputs/narration/shot_NN.wav
        ├──▶ 01b_radio_cut.py  Phase 1 prototype → outputs/final/radio_cut.mp4
        ├──▶ 02_keyframes.py   Cloudflare FLUX.2 klein / FLUX.1 schnell
        │                      → outputs/references/character_sheet.png
        │                      → outputs/keyframes/shot_NN.png
        ├──▶ 03_shots.py       Wan 2.2 TI2V-5B (Kaggle) or upscaled Ken Burns (FFmpeg)
        │                      → outputs/shots/shot_NN.mp4
        ├──▶ 04_music.py       ACE-Step 1.5 score prep → outputs/music/score.wav
        └──▶ 05_assemble.py    FFmpeg mix, sidechain ducking, subtitles, -14 LUFS, end card
                               → outputs/final/film_16x9.mp4 & film_9x16.mp4
```

Every stage caches outputs by SHA-256 content hash (prompt/text + parameters + seed). Changing one narration line or one shot prompt regenerates **only that shot**. Every model call logs parameters, latency, seed, and cost estimate to `runs.jsonl`.

## Kaggle GPU Notebooks

- [notebooks/wan22_shots.ipynb](notebooks/wan22_shots.ipynb) — Run Wan 2.2 TI2V-5B on Kaggle 2×T4 GPU and place clips in `outputs/shots/wan/shot_NN.mp4`
- [notebooks/acestep_music.ipynb](notebooks/acestep_music.ipynb) — Generate 3 ACE-Step 1.5 score candidates and save the selected one to `outputs/music/score.wav`

## Cost & Documentation

All stages run on free tiers or local open-source FFmpeg. See:
- [DESIGN.md](DESIGN.md) — Audience, intent, user tests (radio cut & near-final cut), shot reasons
- [ARCHITECTURE.md](ARCHITECTURE.md) — Stage contracts, caching, failure handling
- [EXPERIMENTS.md](EXPERIMENTS.md) — Hypotheses, changes, and measured results
- [FAILURES.md](FAILURES.md) — Blockers encountered and resolutions
- [COSTS.md](COSTS.md) — Measured latencies, GPU minutes, and list-price equivalents
- [ETHICS.md](ETHICS.md) — Consent, model licences, AI labelling plan

## Core Message

> "አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።"  
> *Respect your elders, but never deny the truth.*
