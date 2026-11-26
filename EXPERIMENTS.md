# Experiments Log

Each entry records: hypothesis → change → result.

## Experiment 1: TTS Voice & Automatic `429` Fallback (`Schedar` on `gemini-3.8-flash-tts` → `gemini-3.8-flash-lite-tts`)
- **Hypothesis:** Selecting prebuilt voice `Schedar` on `gemini-3.8-flash-tts` with automatic fallback to `gemini-3.8-flash-lite-tts` on `429` produces consistent Amharic narration even across free-tier daily quota caps (`10 RPD`).
- **Change:** Replaced placeholder `Kore`/`Zephyr` voice config in `storyboard.json` with `Schedar` and added REST `429` fallback routing in `pipeline/01_narration.py`.
- **Result:** Verified in production: during the personalized Addisu rebuild, Shots 1–5 ran on `gemini-3.8-flash-tts` (`avg 7.96s`), Shot 6 hit the rolling `10 RPD` limit (`429`), and `01_narration.py` seamlessly switched to `gemini-3.8-flash-lite-tts` for Shots 6, 7, 9, 10, 11 (`avg 6.95s`, `0` failures).

## Experiment 2: Amharic Narration Pacing & Personalization (`107.60s` → `68.23s`)
- **Hypothesis:** Tightening verbose Amharic clauses, replacing `"unhurried"` in `narration.style` with `"warm, clear, natural Ethiopian storytelling"`, personalizing the hero as `Addisu` (`አዲሱ`), and letting Shot 8 stand as a `3.5s` silent dramatic beat will bring total runtime strictly inside `60–90s`.
- **Change:** Iterated from initial verbose cut (`93.44s` speech → `107.60s` total) to tightened Addisu lines (`10` narrated shots + `1` silent beat + `5s` end card) and rebuilt `radio_cut.mp4`.
- **Result:** **Confirmed.** Pure speech dropped from `93.44s` to **`49.41s`**, bringing total runtime from `107.60s` down to **`68.23s`** (`-39.4s`), sitting cleanly in the middle of the `60–90s` target while staying within 10 TTS calls.

## Experiment 3: Style Block & Cultural Prompt Specificity (`Shot 4` & `Shot 5`)
- **Hypothesis:** Replacing generic terms (`"Ethiopian family"`, `"jebena"`, `"innocent young relative"`) with explicit East African physical descriptors and concrete cultural objects (`"black clay Ethiopian jebena coffee pot"`, `"tiny white handleless sini cups"`, `"mesob basket table"`, `"innocent adult Ethiopian man"`) will eliminate Western/brass-teapot drift in `flux-2-klein-4b`.
- **Change:** Updated only `shots[3]`, `shots[4]`, and `shots[7]` in `storyboard.json` and re-ran `02_keyframes.py` (cache skipped Shots 1–3, 6–7, 9–11).
- **Result:** Dramatic visual improvement on Shot 4 (authentic woven mesob, black clay coffee pot, white sini cups, traditional netela/gabi) and Shot 5 (adult Ethiopian man with curly hair instead of a child). Only 3 keyframes regenerated (`13.59s`, `11.21s`, plus Shot 8).

## Experiment 4: Multi-Character Reference Sheet Conditioning (`flux2-ref`) vs Fixed Prompt Conditioning (`flux2-txt`)
- **Hypothesis:** Passing `outputs/references/character_sheet.png` via `input_image_0` (`flux2-ref`) to `@cf/black-forest-labs/flux-2-klein-4b` will give stronger cross-shot character consistency than prompt-only generation (`flux2-txt`).
- **Change:** After fixing the `403` WAF block (`User-Agent` + `<512px` JPEG resize), generated all 11 Addisu shots with `flux2-ref` (`input_image_0 = character_sheet.png`), inspected the PNGs visually, and compared against `flux2-txt` with fixed East African character blocks.
- **Result:** **Hypothesis refuted (crucial visual discovery).** Because `flux-2-klein-4b`'s `input_image_0` acts as an image-to-image spatial edit reference rather than a face-ID extractor, passing the 4-person lineup sheet pasted all 4 lineup characters and the beige wall into single/two-person shots (`shot_01` spawned extra adults, `shot_02` produced a disembodied arm, `shot_07` turned Addisu sitting alone into a 4-person lineup). Setting `CF_ENABLE_IMAGE_REF=0` (`flux2-txt` default) restored clean cinematic framing while maintaining outfit/face continuity via fixed character descriptions and `style.block`.

## Experiment 5: Ken Burns Direction & Anti-Shimmer Upscaling
- **Hypothesis:** Upscaling keyframes 3× (`3840×2160`) before FFmpeg `zoompan` and matching motion direction to storyboard camera cues will produce smooth 720p shots without pixel-rounding jitter.
- **Change:** Implemented `scale=3840:-2:flags=lanczos` prior to `zoompan` in `pipeline/03_shots.py` with direction mapping (`push_in`, `pull_out`, `pan_right`, `pan_up`).
- **Result:** All 11 720p 24fps shots rendered locally in `1.67s–12.25s` each (total `~49.5s` for `102.6s` of footage) with smooth camera motion and zero pixel-rounding shimmer.

## Experiment 6: `FLUX.2 klein 4B` (16:9 Native `1280×720`) vs `FLUX.1 schnell`
- **Hypothesis:** `FLUX.2 klein 4B` with native `1280×720` dimensions and explicit `seed` control will produce sharper 16:9 frames and more reproducible character shots than `FLUX.1 schnell` (which rejects `seed` and defaults to square `1024×1024`).
- **Change:** Smoke-tested `flux-1-schnell` (`4.52s`), then generated the character sheet and all 11 keyframes on `flux-2-klein-4b` at `1280×720`.
- **Result:** Confirmed: `flux-2-klein-4b` honored `1280×720` and `seed` across all 12 images (`avg 17.5s` on sheet, `~17.3s` incl. Shot 8 retry across 11 shots), whereas `flux-1-schnell` returned HTTP 400 `code 5006` when passed `seed`.

## Experiment 7: Subtitle Wrapping & 9:16 Safe-Area Placement
- **Hypothesis:** Splitting English subtitles at ~42 chars (16:9) and ~34 chars (9:16) with `MarginV=38` (virtual ASS coords) keeps captions readable without overflowing vertical phone UI overlays.
- **Change:** Implemented dual SRT generation (`subtitles_16x9.srt` and `subtitles_9x16.srt`) in `pipeline/05_assemble.py` and visually inspected extracted frames at `t=12s` on both `16:9` and `9:16`.
- **Result:** `16:9` rendered cleanly in 2 centered lines (`FontSize=20`). On `9:16`, `FontSize=11` wrapped into 3 lines in our extracted frame, so updated `9:16` style in `05_assemble.py` to `FontSize=9, MarginL=20, MarginR=20, MarginV=42` for the next assembly pass.

## Experiment 8: Ducking Parameters
- **Hypothesis:** `sidechaincompress` (`threshold=0.02, ratio=6, attack=300ms, release=1500ms`) produces natural music ducking under Amharic narration.
- **Change:** Added `outputs/music/score.wav` (`80.0s`, `14.65 MB`) and ran full `python -u run_pipeline.py` (`Stage 5` completed in `65.0s`).
- **Result:** **Confirmed.** Full mix exported `film_16x9.mp4` (`68.3s`, `13.68 MB`) and `film_9x16.mp4` (`68.2s`, `15.62 MB`). FFmpeg `ebur128` verification measured integrated loudness at **`-15.6 LUFS`** (`LRA: 6.4 LU`, `LRA high: -14.0 LUFS`), cleanly ducking the instrumental score under Addisu's Amharic speech and swelling during Shot 8 (`3.5s` silent beat) and the end card.

## Experiment 9: Music Tempo & Spotting (`ACE-Step 1.5` Candidate Comparison)
- **Hypothesis:** `72 BPM` in `A minor` (`krar`, `masinko`, `washint`) matches the reflective, moral pacing of the narration without competing with the voice.
- **Change:** Generated 3 × `80.0s` instrumental candidates on Kaggle GPU T4 using `notebooks/acestep_music.ipynb` (`acestep-v15-turbo` + `acestep-5Hz-lm-0.6B`, Python `3.12` via `uv`):
  - `seed=42`: `43.29s`
  - `seed=123`: `41.11s`
  - `seed=777`: `41.91s`
- **Result:** All 3 seeds succeeded (`126.31s` total generation across 3 tracks). Selected **`seed=777`** (`score_seed_777.wav` → `outputs/music/score.wav`) after auditioning all three candidates under narration — its melody felt catchy and fitted the emotional progression of Addisu's story best without competing with the Amharic voiceover.

## Experiment 10: Hash-Based Selective Regeneration
- **Hypothesis:** Hashing `(prompt + style + character_descriptions + seed)` per shot in `.cache.json` enables single-shot regeneration in <20s without touching unaffected shots.
- **Change:** Edited Shots 4, 5, 8 in `storyboard.json` and re-ran `02_keyframes.py`, then bumped only Shot 8 seed to `2008`.
- **Result:** Verified: Run 2 skipped 8/11 shots (`0 API calls` for cached shots) and regenerated only Shots 4, 5, 8; Run 3 skipped 10/11 shots and regenerated only Shot 8 (`87.53s`).

## Experiment 11: Raising the Ceiling — Separate Full-Film Dubs in Afaan Oromo (`om`) & Tigrinya (`ti`) vs Amharic (`am`)
- **Hypothesis:** Parameterizing `05_assemble.py` (`assemble_film`) lets the pipeline produce standalone `60–90s` (`16:9` + `9:16`) films in Afaan Oromo and Tigrinya using the same keyframes, shots, and `seed=777` score — exposing full-run pacing, rate-limit, and pronunciation trade-offs across all 10 spoken shots without breaking `run_pipeline.py`'s Amharic-only contract.
- **Change:** Expanded `pipeline/benchmark_languages.py` from 3 beats to all 10 narrated shots in `om` and `ti`, added `3 RPM` wait handling (`48s` retry on `per minute` `429` before falling back on daily limits), parameterized `05_assemble.py`, and built separate standalone films (`outputs/benchmarks/{om,ti}/final/film_{lang}_{16x9,9x16}.mp4`).
- **Result:**
  - **Three standalone films delivered (`16:9` & `9:16` each):**
    - `am` (baseline): `49.41s` speech → `68.3s` (`16:9`) / `68.2s` (`9:16`)
    - `om`: `52.89s` speech (`9/10` on `gemini-3.8-flash-tts`, Shot 10 on `flash-lite-tts` after `10 RPD`) → **`72.1s` (`16:9`, `14.48 MB`) / `72.0s` (`9:16`, `16.08 MB`)**
    - `ti`: `52.58s` speech (`1` on `flash-tts`, `9` on `flash-lite-tts`; Shot 07 rescued after `48s` wait on `flash-lite-tts` `3 RPM` limit) → **`70.4s` (`16:9`, `14.27 MB`) / `70.2s` (`9:16`, `15.82 MB`)**
  - **Visual/Font (`ebrima.ttf`):** `0` missing glyphs across `am`, `om`, and `ti` (including Tigrinya `ስቕ` / `ቕ`, `ኣ`, `ኽ`, `ሕ`; verified rendered frames from both exported MP4s).
  - **Audio/Phonology findings:** On Beats 2, 6, 11 audited directly: `om` preserved pacing well but flattened Qubee `dh` → `d` (`"dhugaadhaaf dhaabbadhu"` → `"duggaadaf daabadu"`) and `c` → `"ch"`, while `ti` on `flash-lite-tts` rushed Beat 6 to `2.44 words/s` and truncated `"ንኣዲሱ"` → `"ናአዱ"`. Full `flash-tts` stayed noticeably cleaner, confirming Amharic remains strongest for production while showing exact bottlenecks for future multi-language TTS improvement.

## Experiment 12: Single-Subject Golden Reference (`reference_shot_id`) vs. 4-Person Lineup Reference Sheet
- **Hypothesis:** While passing the 4-person `character_sheet.png` to `flux-2-klein-4b` `input_image_0` caused lineup bleeding (Experiment 4), passing a **single-person Golden Reference portrait** (`shot_03.png`) via per-shot `reference_shot_id: 3` will lock Addisu's exact face, curly Afro, mustache shadow, and white vertical-stripe embroidered shirt across later shots (`07–11`) without cloning extra figures.
- **Change:** Added `reference_shot_id` support to `schema/storyboard.schema.json`, `storyboard.json` (Shots `7–11`), and `pipeline/02_keyframes.py` (including SHA-256 hashing of `shot_03.png` and `flux2-ref-altseed` `seed+100` retry before dropping reference). Prototyped on Shots 4 and 7–11 first before full rebuild.
- **Result:** **Confirmed for Addisu-anchored scenes (`07–11`), with an explicit boundary on ensembles.**
  - Testing `reference_shot_id=3` on ensemble wide Shot 04 cloned Addisu's face onto three men and replaced the clay `jebena`/`mesob`, so Shots `4–5` stayed prompt-conditioned (`flux2-txt`).
  - Applying `reference_shot_id=3` across **Shots 7, 8, 9, 10, and 11** kept Addisu virtually indistinguishable from Shot 3 across every scene (`flux2-ref` latencies `6.02s–12.08s`, `0` failed shots), eliminating the late-film character drift observed in review. All 3 language cuts (`am`, `om`, `ti`) were re-exported cleanly.
