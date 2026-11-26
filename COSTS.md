# Costs & Latency Measurements

Measured latency, GPU minutes, and list-price equivalent cost per pipeline stage (cumulative across all iterations from `runs.jsonl` via `python pipeline/analyze_runs.py`).

## Measured Stage Summary

| Stage | Model / Tool | Successful Calls | Errors / Fallbacks | Avg Latency | Total Time | Output / Notes | Cost Paid |
|-------|-------------|------------------|--------------------|-------------|------------|----------------|-----------|
| Smoke Test | `gemini-3.8-flash-tts` | 1 | 0 | 7.77s | 7.77s | 182 KB WAV (`3.64s` audio) | \$0 (Free tier) |
| Smoke Test | `gemini-3.8-flash` | 0 | 1 | — | — | `503 UNAVAILABLE` probe | \$0 |
| Smoke Test | `gemini-3.1-flash-image` | 0 | 1 | — | — | `429 RESOURCE_EXHAUSTED` (paid-only) | \$0 |
| Smoke Test | `@cf/black-forest-labs/flux-1-schnell` | 1 | 1 | 4.52s | 4.52s | 1024×1024 fallback probe | \$0 (Free tier) |
| Narration | `gemini-3.8-flash-tts` | 16 | 1 | 11.10s | 177.63s | `116.19s` audio across v1 + v2 (`429` hit at 10 RPD) | \$0 (Free tier) |
| Narration (Fallback) | `gemini-3.8-flash-lite-tts` | 5 | 0 | 6.95s | 34.73s | `26.66s` audio (`Schedar` fallback on Shots 6, 7, 9, 10, 11) | \$0 (Free tier) |
| Multi-Lang Dubs (`om` + `ti`) | `gemini-3.8-flash-tts` | 10 | 2 | 6.87s | 68.68s | `55.18s` audio (`om` Shots 1–9 + `ti` Shot 2; hit `3 RPM` & `10 RPD`) | \$0 (Free tier) |
| Multi-Lang Fallback (`om`/`ti`) | `gemini-3.8-flash-lite-tts` | 10 | 1 | 5.68s | 56.79s | `50.29s` audio (`om` Shot 10 + `ti` 9 shots; rescued `3 RPM` w/ `48s` wait) | \$0 (Free tier) |
| Multi-Lang Assembly (`om` + `ti`) | Local FFmpeg + Pillow | 4 | 0 | 87.39s | 349.56s | Rebuilt standalone `film_om_{16x9,9x16}.mp4` & `film_ti_{16x9,9x16}.mp4` | \$0 (Local) |
| Radio Cut | Local FFmpeg + Pillow | 2 | 0 | 9.71s | 19.41s | `radio_cut.mp4` (latest Addisu cut: `68.2s`) | \$0 (Local) |
| Reference Sheet | `@cf/black-forest-labs/flux-2-klein-4b` | 2 | 0 | 18.71s | 37.42s | `outputs/references/character_sheet.png` | \$0 (Free tier) |
| Keyframes (Primary) | `@cf/black-forest-labs/flux-2-klein-4b` | 44 | 24 | 15.56s | 684.59s | Incl. `shot_03.png` Golden Reference (`flux2-ref`) Shots `07–11` | \$0 (Free tier) |
| Keyframes (Fallback) | `@cf/black-forest-labs/flux-1-schnell` | 2 | 1 | 4.22s | 8.44s | Automatic fallback probe/iteration on Workers AI | \$0 (Free tier) |
| Moving Shots (Motion) | Local `ffmpeg-ken-burns` (3× Lanczos) | 29 | 0 | 3.09s | 89.73s | Includes Golden-Reference Shots `07–11` (`720p`, `24fps`) | \$0 (Local) |
| Moving Shots (Hero AI Video) | `Wan 2.2 TI2V-5B` (Kaggle 2×T4) | [Optional Kaggle run] | — | — | — | Hero clips (`outputs/shots/wan/`) | \$0 (Kaggle quota) |
| Music Score | `ACE-Step 1.5` (`acestep-v15-turbo` + `0.6B` LM, Kaggle T4) | 3 (`42, 123, 777`) | 0 (post `MPLBACKEND` + Python `3.12` fix) | 42.10s | 126.31s | 3 × `80.0s` WAVs → selected `seed 777` (`score.wav`, `14.65 MB`) | \$0 (Kaggle quota) |
| Assembly (`16:9` + `9:16`) | Local FFmpeg + Pillow | 7 | 0 | 96.38s | 674.64s | Latest (`film_16x9.mp4`: `68.3s` / `14.17 MB`, `film_9x16.mp4`: `68.2s` / `16.12 MB`) | \$0 (Local) |

## Free Tier Limits Observed

| Service | Documented / Observed Limit | Actual Usage | Notes |
|---------|-----------------------------|--------------|-------|
| Gemini TTS (`gemini-3.8-flash-tts`) | **3 RPM** & **10 RPD** free tier | 26 OK / 3 `429` (film + `om`/`ti`) | Both `flash-tts` and `flash-lite-tts` (`15` OK total) enforce `3 RPM` on burst calls |
| Gemini Image (`gemini-3.1-flash-image`) | 0 free-tier quota (`429`) | 1 probe call | Requires paid billing |
| Cloudflare Workers AI (`flux-2-klein-4b` / `flux-1-schnell`) | ~10,000 neurons/day free | 41 OK total across v1, v2 & Test 2 | Fit across daily refreshes at \$0 cost; Shots 9 & 10 re-aligned directly on `flux-2-klein-4b` |
| Kaggle GPU (`T4` / `2× T4`) | ~30 GPU hours/week | ~3–4 GPU minutes (`ACE-Step 1.5`) | Generated 3 × `80s` music tracks (`126.31s` inference + ~2 min setup) via `uv` Python 3.12 |

## List-Price Equivalent Estimate

What the **latest Addisu final cut** (`68.2s`, `10` active TTS clips totaling `49.41s` audio, `1` reference sheet + `11` keyframes) and prior iteration runs would cost on commercial APIs:
- **TTS Narration** (21 cumulative clips / `142.85s` audio across v1 + v2): ~\$0.04–\$0.09 (Addisu cut alone: 10 clips / `49.41s`, ~\$0.02)
- **Keyframes & Reference Sheets** (41 successful FLUX images @ ~\$0.003–\$0.015/image): ~\$0.12–\$0.62 (Addisu cut alone: 12 images, ~\$0.04–\$0.18)
- **Local FFmpeg Ken Burns & Assembly** (674.64s + 349.56s + 89.73s + 19.41s local CPU): \$0.00
- **Total actual out-of-pocket cost:** **\$0.00** (cumulative list-price equivalent across all experiments so far: **~\$0.16–\$0.71**).
