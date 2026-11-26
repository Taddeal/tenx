# Architecture

## Overview

`storyboard.json` is the single contract shared across all pipeline stages, validated against `schema/storyboard.schema.json` before execution. Every stage reads only what it needs from `storyboard.json` and writes deterministic, cached artifacts to `outputs/`.

```
                    ┌───────────────────────────┐
                    │      storyboard.json      │
                    │  (validated JSON Schema)  │
                    └─────────────┬─────────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┐
        ▼                         ▼                         ▼
┌───────────────┐         ┌───────────────┐         ┌───────────────┐
│  01_narration │         │ 02_keyframes  │         │   04_music    │
│ Gemini 3.8 TTS│         │ CF FLUX.2/1   │         │ ACE-Step 1.5  │
└───────┬───────┘         └───────┬───────┘         └───────┬───────┘
        │                         │                         │
        │ (01b_radio_cut)         ▼                         │
        │                 ┌───────────────┐                 │
        │                 │   03_shots    │                 │
        │                 │Wan2.2/KenBurns│                 │
        │                 └───────┬───────┘                 │
        │                         │                         │
        └─────────────────────────┼─────────────────────────┘
                                  ▼
                          ┌───────────────┐
                          │  05_assemble  │
                          │ FFmpeg Export │
                          └───────┬───────┘
                                  │
                     ┌────────────┴────────────┐
                     ▼                         ▼
              film_16x9.mp4             film_9x16.mp4
```

## Stage Contracts

| Stage | Script | Inputs | Outputs | Cache Key |
|-------|--------|--------|---------|-----------|
| 0 | `pipeline/00_validate.py` | `storyboard.json`, `schema/storyboard.schema.json` | Exit 0/1 | N/A |
| Smoke | `pipeline/smoke_test.py` | `.env` API keys | `runs.jsonl` entries | N/A |
| 1 | `pipeline/01_narration.py` | `shots[].narration_amharic`, `narration.{model,voice,style}` | `outputs/narration/shot_NN.wav` | SHA-256 `(text, model, voice, style)` |
| 1b | `pipeline/01b_radio_cut.py` | `outputs/narration/*.wav`, `storyboard.json` | `outputs/final/radio_cut.mp4` | Rebuilt on demand |
| 2 | `pipeline/02_keyframes.py` | `style`, `characters`, `shots[].{image_prompt,seed}` | `outputs/references/character_sheet.png`, `outputs/keyframes/shot_NN.png` | SHA-256 `(full_prompt, seed, ref_hash)` |
| 3 | `pipeline/03_shots.py` | `outputs/keyframes/shot_NN.png`, `outputs/shots/wan/shot_NN.mp4`, `shots[].camera` | `outputs/shots/shot_NN.mp4` | SHA-256 `(source, kf_stat, duration, direction)` |
| 4 | `pipeline/04_music.py` | `storyboard["music"]` | `outputs/music/generation_params.json` (`score.wav` from Kaggle) | N/A |
| 5 | `pipeline/05_assemble.py` | `shots/*.mp4`, `narration/*.wav`, `music/score.wav`, `end_card` | `outputs/final/film_16x9.mp4`, `outputs/final/film_9x16.mp4`, `subtitles.srt` | Rebuilt deterministically |

## Key Engineering Decisions

### 1. Audio-Driven Shot Timing (No Truncated Narration)
Instead of forcing TTS narration into rigid preset shot durations with FFmpeg `-shortest`, `03_shots.py` and `05_assemble.py` compute:
`effective_duration = max(planned_duration, measured_tts_duration + 0.8s)`
If a Wan 2.2 clip (typically 5s) is shorter than `effective_duration`, `05_assemble.py` freezes the final frame cleanly via `tpad=stop_mode=clone` and pads narration audio to match, guaranteeing subtitles and speech never drift or clip.

### 2. Upscaled Ken Burns (Anti-Shimmer)
FFmpeg's `zoompan` filter rounds pan coordinates to integer pixels on native 720p frames, producing visible jitter. `03_shots.py` upscales input keyframes 3× (`3840×2160`) using Lanczos before `zoompan`, then scales back to `1280×720` at 24 fps.

### 3. Prompt-Conditioned Keyframes with Automatic Fallback (and Opt-In Reference)
`02_keyframes.py` first generates `outputs/references/character_sheet.png` for look development, then generates `1280×720` keyframes via `@cf/black-forest-labs/flux-2-klein-4b` using deterministic seeds, fixed `East African Ethiopian` character descriptors, and unified `style.block` (`CF_ENABLE_IMAGE_REF=0` by default after Experiment 4 showed `input_image_0` copied all 4 lineup characters into 1–2 person shots; set `CF_ENABLE_IMAGE_REF=1` to opt into multipart reference conditioning). If `flux-2-klein-4b` fails or flags `code 3030`, it falls back cleanly to `seed+100` (`flux2-txt-altseed`) and then `@cf/black-forest-labs/flux-1-schnell` without passing `seed`.

### 4. Windows Path & Ethiopic Font Safety
- `pipeline/utils.py` automatically inspects Windows User PATH (`HKCU\Environment`) and WinGet package directories if `ffmpeg`/`ffprobe` are not yet in the active shell PATH.
- `05_assemble.py` executes FFmpeg inside the temporary build directory with relative subtitle/concat paths so `C:\` drive colons never break FFmpeg's filter parser.
- End cards are rendered with Pillow using Windows `ebrima.ttf` (with Linux `AbyssinicaSIL` / `NotoSansEthiopic` fallback) so Ge'ez script renders cleanly without tofu boxes.

## Caching & Partial Regeneration

Each stage saves per-shot hashes in `outputs/<stage>/.cache.json`. Modifying one shot's `narration_amharic` or `image_prompt` in `storyboard.json` and re-running `make film` (or `python run_pipeline.py`) regenerates only that shot and re-assembles the final MP4s.

## Failure Handling & Retries

- `01_narration.py`: Up to 3 attempts with linear backoff (`3s`, `6s`) for transient 503/429 responses; every attempt (error or success) is appended to `runs.jsonl`.
- `02_keyframes.py`: Multi-tier fallback (`flux-2-klein` with ref -> `flux-2-klein` text -> `flux-1-schnell`).
- `03_shots.py`: Preserves Wan 2.2 clips in `outputs/shots/wan/` while automatically falling back to upscaled Ken Burns for any shot lacking a Wan clip.
- Partial recovery: `python run_pipeline.py --from N` resumes from stage `N`.
