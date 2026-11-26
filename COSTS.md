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
| Radio Cut | Local FFmpeg + Pillow | 2 | 0 | 9.71s | 19.41s | `radio_cut.mp4` (latest Addisu cut: `68.2s`) | \$0 (Local) |
| Reference Sheet | `@cf/black-forest-labs/flux-2-klein-4b` | 2 | 0 | 18.71s | 37.42s | `outputs/references/character_sheet.png` | \$0 (Free tier) |
| Keyframes (Primary) | `@cf/black-forest-labs/flux-2-klein-4b` | 35 | 20 | 16.20s | 566.86s | v1 + Addisu `1280×720` PNGs (Errors: `flux2-ref`, `5006`, `3030`) | \$0 (Free tier) |
| Keyframes (Fallback) | `@cf/black-forest-labs/flux-1-schnell` | 2 | 1 | 4.22s | 8.44s | Automatic fallback when `flux-2-klein-4b` returned `3030` (Shot 9) | \$0 (Free tier) |
| Moving Shots (Motion) | Local `ffmpeg-ken-burns` (3× Lanczos) | 22 | 0 | 3.45s | 75.87s | `11` v1 clips + `11` Addisu `720p` `24fps` clips | \$0 (Local) |
| Moving Shots (Hero AI Video) | `Wan 2.2 TI2V-5B` (Kaggle 2×T4) | [Optional Kaggle run] | — | — | — | Hero clips (`outputs/shots/wan/`) | \$0 (Kaggle quota) |
| Music Score | `ACE-Step 1.5` (`acestep-v15-turbo` + `0.6B` LM, Kaggle T4) | 3 (`42, 123, 777`) | 0 (post `MPLBACKEND` + Python `3.12` fix) | 42.10s | 126.31s | 3 × `80.0s` WAVs → selected `seed 42` (`score.wav`, `14.65 MB`) | \$0 (Kaggle quota) |
| Assembly (`16:9` + `9:16`) | Local FFmpeg + Pillow | 4 | 0 | 104.01s | 416.04s | Latest (`65.0s` w/ `score.wav`): `film_16x9.mp4` (`68.3s`, `13.68 MB`), `film_9x16.mp4` (`68.2s`, `15.62 MB`) | \$0 (Local) |

## Free Tier Limits Observed

| Service | Documented / Observed Limit | Actual Usage | Notes |
|---------|-----------------------------|--------------|-------|
| Gemini TTS (`gemini-3.8-flash-tts`) | **10 requests/day** free tier | 16 OK / 1 `429` | `01_narration.py` falls back cleanly to `gemini-3.8-flash-lite-tts` (`5` OK, `0` errors) |
| Gemini Image (`gemini-3.1-flash-image`) | 0 free-tier quota (`429`) | 1 probe call | Requires paid billing |
| Cloudflare Workers AI (`flux-2-klein-4b` / `flux-1-schnell`) | ~10,000 neurons/day free | 39 OK total across v1 & v2 | Fit across daily refreshes at \$0 cost; automatic fallback to `flux-1-schnell` on `3030` |
| Kaggle GPU (`T4` / `2× T4`) | ~30 GPU hours/week | ~3–4 GPU minutes (`ACE-Step 1.5`) | Generated 3 × `80s` music tracks (`126.31s` inference + ~2 min setup) via `uv` Python 3.12 |

## List-Price Equivalent Estimate

What the **latest Addisu final cut** (`68.2s`, `10` active TTS clips totaling `49.41s` audio, `1` reference sheet + `11` keyframes) and prior iteration runs would cost on commercial APIs:
- **TTS Narration** (21 cumulative clips / `142.85s` audio across v1 + v2): ~\$0.04–\$0.09 (Addisu cut alone: 10 clips / `49.41s`, ~\$0.02)
- **Keyframes & Reference Sheets** (39 successful FLUX images @ ~\$0.003–\$0.015/image): ~\$0.12–\$0.59 (Addisu cut alone: 12 images, ~\$0.04–\$0.18)
- **Local FFmpeg Ken Burns & Assembly** (351.71s + 75.87s + 19.41s local CPU): \$0.00
- **Total actual out-of-pocket cost:** **\$0.00** (cumulative list-price equivalent across all experiments so far: **~\$0.16–\$0.68**).
