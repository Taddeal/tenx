# Failures Log

Real blockers encountered during development and execution, what was tried, and what fixed or worked around them.

## Failure 1: Gemini Image Models Unavailable on Free Tier (`429 RESOURCE_EXHAUSTED`)
- **What happened:** Probing `gemini-3.1-flash-image` in `pipeline/smoke_test.py` failed in 0.50s with `429 RESOURCE_EXHAUSTED` ("You exceeded your current quota, please check your plan and billing details").
- **What I tried:** Verified the available model list via `client.models.list()` and tested `gemini-3.1-flash-image` on the free-tier Gemini API key.
- **What fixed it / Workaround:** Confirmed that frontier Gemini image generation requires paid billing, while `gemini-3.8-flash-tts` works cleanly on the free tier. Routed Stage 2 keyframes to Cloudflare Workers AI (`@cf/black-forest-labs/flux-2-klein-4b` with `@cf/black-forest-labs/flux-1-schnell` fallback).

## Failure 2: Transient `503 UNAVAILABLE` on `gemini-3.8-flash`
- **What happened:** Smoke test call to `gemini-3.8-flash` failed after 4.03s with `503 UNAVAILABLE` ("This model is currently experiencing high demand").
- **What I tried:** Logged the latency and error in `runs.jsonl`, implemented automatic linear backoff retries (3 attempts) in `01_narration.py`, and avoided relying on live LLM calls during deterministic pipeline execution.
- **What fixed it:** Retry wrappers handle transient spikes without aborting the batch.

## Failure 3: Windows FFmpeg Not Found in Active Shell PATH After `winget install`
- **What happened:** After installing FFmpeg via `winget`, `ffmpeg` was present in Windows User `PATH` (`HKCU\Environment`) under `%LOCALAPPDATA%\Microsoft\WinGet\Packages\...`, but the active IDE/agent shell did not inherit the updated `PATH`.
- **What I tried:** Checked `where.exe ffmpeg` vs the Windows registry User `Path` environment variable.
- **What fixed it:** Added `ensure_ffmpeg_in_path()` in `pipeline/utils.py` to inspect `HKCU\Environment` and WinGet package directories automatically before invoking `ffmpeg` or `ffprobe`.

## Failure 4: FFmpeg Windows Filter Bugs (`subtitles=C:\...`, Arial Ethiopic Tofu, and `-shortest` Speech Clipping)
- **What happened:**
  1. Passing an absolute Windows path (`C:\Users\...`) to FFmpeg's `subtitles=` filter causes a filtergraph parsing failure due to the drive colon (`C:`) and backslashes.
  2. FFmpeg `drawtext` using `Arial` cannot render Ge'ez / Amharic characters (`አዛውንቶችን አክብር...`), producing blank boxes.
  3. Using `-shortest` when muxing TTS WAVs onto fixed-length shots truncated Amharic speech whenever TTS exceeded the initial estimate (e.g., Shot 1 TTS measured 8.96s vs 7.0s planned).
- **What fixed it:**
  1. Run FFmpeg assembly from inside `outputs/final/_build_tmp` using relative paths (`subtitles=subtitles_16x9.srt` and relative `concat_list.txt`).
  2. Render end cards and radio cut cards via Pillow using Windows `ebrima.ttf` (with Linux `AbyssinicaSIL` / `NotoSansEthiopic` fallback).
  3. Compute `effective_duration = max(planned, tts_duration + 0.8s)` in `03_shots.py` and `05_assemble.py`, padding video via `tpad=stop_mode=clone` and audio via `apad` so speech is never clipped and subtitles stay locked in sync.

## Failure 5: FFmpeg `zoompan` Micro-Jitter on Native 720p Stills
- **What happened:** Standard `zoompan` on 1024×576 or 1280×720 inputs rounds pan/zoom coordinates to integer pixels, causing visible frame-to-frame shimmer during slow Ken Burns moves.
- **What fixed it:** Added a 3× Lanczos upscale (`scale=3840:-2:flags=lanczos`) prior to `zoompan` in `03_shots.py`, then output crisp 1280×720 frames.

## Failure 6: Stalled HTTP Call on Shot 11 Narration (`gemini-3.8-flash-tts`) & 10 RPD Free Limit
- **What happened:** Shot 11 hung >90s in `google-genai` `interactions.create()`, and once switched to `requests` we hit two things: Windows SSL `SSLCertVerificationError` in `requests` and `gemini-3.8-flash-tts`'s free-tier daily cap (`10 requests per day`).
- **What I tried:** Tested raw REST calls with `requests`, discovered `truststore.inject_into_ssl()` fixes Windows SSL certs cleanly, and added fallback routing to `gemini-3.8-flash-lite-tts` on `429`.
- **What fixed it:** `pipeline/01_narration.py` now uses REST with `truststore` + strict `(10, 35)` second timeouts + automatic fallback to `gemini-3.8-flash-lite-tts`.

## Failure 7: FFmpeg 9.1 Hang on `-c:a aac -b:a 192k` with Mono 48kHz Audio
- **What happened:** Rendering radio cut clips with `channel_layouts=mono` + `-c:a aac -b:a 192k` + `apad=whole_dur=...` caused FFmpeg 9.1 on Windows to hang indefinitely at 0 bytes output.
- **What I tried:** Isolated flags one by one in subprocess tests with `10s` timeouts.
- **What fixed it:** Added `-nostdin`, replaced `apad=whole_dur=...` with `apad,atrim=0:{dur}` + `-shortest` + `-framerate 24`, and removed `-b:a 192k` on mono AAC streams; clip rendering dropped from hanging to ~0.5s per clip.

## Failure 8: Cloudflare Workers AI `flux-2-klein-4b` Multipart Image Input Returning `403` HTML WAF Block
- **What happened:** Passing `input_image_0` (both as 1280×720 PNG and resized <512px JPEG) via `multipart/form-data` to `@cf/black-forest-labs/flux-2-klein-4b` returned `HTTP 403 text/html` (Cloudflare WAF block page), whereas text-only `multipart/form-data` (`flux2-txt`) returned `200 OK` consistently in ~7.5–19.7s.
- **What I tried:** Resized `character_sheet.png` below Cloudflare's 512×512 limit (`480×270` JPEG) and added a custom `User-Agent`, confirming the token/gateway rejects multipart binary file uploads (`403 text/html`).
- **What fixed it:** Automatic fallback chain in `02_keyframes.py` (`flux2-ref` → `flux2-txt` → `flux1-schnell`) routed seamlessly to `flux2-txt` while keeping visual consistency via fixed `style.block`, fixed `characters[].description`, and deterministic per-shot seeds (`1001–1011`).

## Failure 9: False-Positive Safety Flag (`code 3030`) & `flux-1-schnell` Seed Schema Rejection (`code 5006`)
- **What happened:** Regenerating Shot 8 with `seed=1008` triggered Cloudflare `code 3030` ("Your output has been flagged"), and the `flux-1-schnell` fallback then failed with `code 5006` (`Additional or unevaluated properties '/seed' at '/' not allowed`).
- **What I tried:** Inspected `runs.jsonl` error JSON, verified `flux-1-schnell` on Workers AI only accepts `prompt` and `steps` (not `seed`).
- **What fixed it:** Removed `seed` from `call_flux1_schnell()`, added automatic `seed + 100` retry tier (`flux2-txt-altseed`) in `02_keyframes.py`, and updated Shot 8's seed to `2008`; Shot 8 then rendered cleanly via `flux-2-klein-4b`.

## Failure 10: Kaggle Python 3.13 Incompatible with `ACE-Step 1.5` (`requires <3.13,>=3.11`)
- **What happened:** Running `pip install -e .` on Kaggle failed with `ERROR: Package 'ace-step' requires a different Python: 3.13.18 not in '<3.13,>=3.11'`, causing `ModuleNotFoundError: No module named 'loguru'`.
- **What I tried:** Checked ACE-Step 1.5 `pyproject.toml` constraints (`>=3.11,<3.13`) and Kaggle's default runtime (Python 3.13.18).
- **What fixed it:** Updated `notebooks/acestep_music.ipynb` to install `uv`, provision an isolated Python 3.12 environment (`uv python install 3.12 && uv sync --python 3.12`), and execute the generation script inside it (`uv run --python 3.12 python ...`) with `ensure_main_model` / `ensure_lm_model`.

## Failure 11: Multi-Person Lineup Reference Bleeding in `flux-2-klein-4b` (`flux2-ref`)
- **What happened:** Once `flux2-ref` (`User-Agent` + `480×270` JPEG) succeeded with HTTP 200, visual inspection of Shots 1, 2, 4, 7, 8, and 9 revealed that `flux-2-klein-4b` treated the 4-person `character_sheet.png` as an image-editing canvas — cloning extra people, background walls, and even an extra arm into 1- and 2-person scenes.
- **What I tried:** Inspected generated frames directly and compared against `flux2-txt` runs with identical seeds and fixed `East African Ethiopian` character/style descriptors.
- **What fixed it:** Kept `character_sheet.png` for look development, set `CF_ENABLE_IMAGE_REF` default to `"0"` (`flux2-txt`) in `02_keyframes.py`, and enriched `father` and `boy` descriptors in `storyboard.json` so every scene renders clean framing without lineup bleeding.

## Failure 12: Kaggle `MPLBACKEND=module://matplotlib_inline.backend_inline` Crash Inside `uv` Python 3.12 Venv (Stage 4 / ACE-Step 1.5)
- **What happened:** Kaggle runs Jupyter notebooks on Python 3.13 with `MPLBACKEND=module://matplotlib_inline.backend_inline` exported in the shell environment. Running `uv run --python 3.12 python generate_candidates.py` inside the isolated ACE-Step venv failed during `from acestep.handler import AceStepHandler` (`lightning` → `torchmetrics` → `matplotlib`) with `ValueError: Key backend: 'module://matplotlib_inline.backend_inline' is not a valid value for backend`, and IPython `!cmd` silently continued committing the notebook without creating `/kaggle/working/music_candidates/`.
- **What I tried:** Inspected the Kaggle execution log line-by-line (lines 188–252).
- **What fixed it:** Set `os.environ['MPLBACKEND'] = 'Agg'` at line 1 of `generate_candidates.py` before importing `acestep`, passed `env['MPLBACKEND'] = 'Agg'` with `subprocess.run(..., check=True)` in Cell 3 so errors fail loudly instead of silently, and exported `00_music_candidates.zip` / `00_music_runs.jsonl` cleanly above `ACE-Step-1.5` in Kaggle's Output tree.

