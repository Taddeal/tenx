# Heritage Short Film & Pipeline Report: *የእውነት ፈተና — The Test of Truth*

**Author:** Taddeal Moges (`taddealmoges@gmail.com`)  
**Repository:** https://github.com/Taddeal/tenx  
**Primary Run Command:** `python run_pipeline.py` (or `make film` on Unix)  
**Deliverables:** `outputs/final/film_16x9.mp4` (`68.3s`) & `outputs/final/film_9x16.mp4` (`68.2s`), plus standalone Afaan Oromo (`om`) and Tigrinya (`ti`) exports in `outputs/benchmarks/`

---

## 1. What I Set Out to Make and For Whom

I built both a **68-second Amharic short film** (*የእውነት ፈተና — The Test of Truth*) and an **automated, contract-driven multi-model film studio pipeline** that regenerates the entire production from a single validated `storyboard.json` file.

- **Audience (`DESIGN.md`):** Primarily young Ethiopian adults (20–30s) watching vertical `9:16` video on mobile and sharing cultural reflections with peers; secondarily Ethiopian family members and diaspora viewers nostalgic for highland village life and intergenerational wisdom.
- **Story & Intent:** A young Ethiopian man named **Addisu (`አዲሱ`)** grows up with two rules from his father: *always respect your elders*, and *always stand for the truth*. Years later, when a respected elder's son steals family money and an innocent relative is blamed, the elder begs Addisu to stay silent. Addisu resolves the apparent contradiction calmly and respectfully—speaking the truth without disrespecting his elders—leaving audiences with the proverb: *"አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።"* (*"Respect your elders, but never deny the truth."*).
- **Technical Specification:** `68.3s` (`16:9`, `14.17 MB`) and `68.2s` (`9:16`, `16.12 MB`), Amharic narration via Gemini 3.8 TTS (`Schedar`), original 72 BPM A-minor score (`krar`, `masinko`, `washint`) via ACE-Step 1.5 (`seed=777`) sidechain-ducked beneath narration, loudness-normalized audio, synchronized burned-in English subtitles (safe-area wrapped for vertical phone playback), and a crisp `"This film was made with AI"` Ethiopic/English end card rendered via Pillow + `ebrima.ttf`.

---

## 2. Pipeline Architecture & Engineering Guarantees

One schema-validated contract ([storyboard.json](storyboard.json) against [storyboard.schema.json](schema/storyboard.schema.json)) coordinates six clean stages:

1. **Stage 0 (`00_validate.py`):** Validates duration targets (`60–90s`), required fields, and schema constraints before any API calls occur.
2. **Stage 1 (`01_narration.py`) & 1b (`01b_radio_cut.py`):** Calls Gemini Interactions REST API (`gemini-3.8-flash-tts` with `429` fallback to `gemini-3.8-flash-lite-tts`), removes stale silent WAVs (`Shot 08`), and builds a black-screen prototype `radio_cut.mp4` before generating visuals.
3. **Stage 2 (`02_keyframes.py`):** Generates `outputs/references/character_sheet.png` for look development, generates base `1280×720` stills via Cloudflare Workers AI (`@cf/black-forest-labs/flux-2-klein-4b`), and supports per-shot single-subject Golden Reference conditioning (`reference_shot_id`) with automatic `seed+100` (`flux2-ref-altseed` / `flux2-txt-altseed`) and `@cf/black-forest-labs/flux-1-schnell` fallbacks.
4. **Stage 3 (`03_shots.py`):** Preserves Kaggle Wan 2.2 clips in `outputs/shots/wan/` when present, falling back cleanly to 3× Lanczos upscaled (`3840×2160`) anti-shimmer FFmpeg Ken Burns motion clips matched to actual measured TTS durations.
5. **Stage 4 (`04_music.py` + `notebooks/acestep_music.ipynb`):** Saves `outputs/music/generation_params.json`, orchestrates Kaggle T4 ACE-Step 1.5 (`uv` + Python 3.12) across 3 candidate seeds (`42, 123, 777`), and integrates `outputs/music/score.wav`.
6. **Stage 5 (`05_assemble.py`):** Locks video length to `max(planned_duration, measured_tts_duration + 0.8s)` (`tpad=stop_mode=clone`, `apad`), applies `sidechaincompress` ducking (`threshold=0.02, ratio=6, attack=300ms, release=1500ms`) + loudness normalization, renders Ge'ez end cards (`ebrima.ttf`), burns dual-wrapped subtitles (`42` chars `16:9` / `34` chars `9:16`), and exports both aspect ratios.

Every stage caches outputs by SHA-256 content hashes (`.cache.json`), logs parameters, seeds, latencies, and errors to `runs.jsonl` (summarized by `pipeline/analyze_runs.py`), keeps `.env` secrets gitignored, and passes `6/6` automated unit tests (`tests/test_pipeline.py`).

---

## 3. What I Learned From My Audience (`User Tests #1 & #2`)

### User Test #1: Radio / Early Rough Cut (`2026-11-25`, 3 Ethiopian Peers)
- **What they said:** (1) At **`107.60s`**, the rough cut exceeded the `60–90s` ceiling and dragged through the elder's plea and climax (`Shots 6 & 9`); (2) calling the hero generically `"the young man"` (`ወጣቱ`) felt impersonal rather than a family story; (3) formal phrasing sounded stiff and accented in Gemini TTS (`ወጣቱ`, `የአንድ የተከበረ ሽማግሌ`, `ክብር መንሳት`).
- **What changed (`Experiment 2`, `DESIGN.md`):** Renamed the protagonist **Addisu (`አዲሱ`)**, rewrote all 10 narrated lines into natural spoken Amharic (e.g., respectful plural `"እባክህ ዝም በል አሉት"`), removed `"unhurried"` from `narration.style` (`"warm, clear, natural Ethiopian storytelling"`), and converted Shot 8 (standing up) into a `3.5s` silent visual beat. Pure speech dropped from **`93.44s` → `49.41s`** (`-44.03s`) and runtime dropped from **`107.60s` → `68.23s`**, fitting squarely inside `60–90s` and `10` daily TTS calls.

### User Test #2: Near-Final Scored Cut (`2026-11-26`, 3 Peers, `seed=777` Score)
- **What they said:** The ~68s pacing, Addisu personalization, natural Amharic delivery, and `seed=777` ACE-Step score resonated strongly—**however, viewers noticed visual character misalignment on Addisu across different scenes** (notably Shot 9's darker `flux-1-schnell` fallback beard/collar and Shot 10's shifted build/posture, plus subtle late-film face/clothing drift after Shot 7).
- **What changed (`Experiments 9 & 12`, `DESIGN.md`):**
  1. First regenerated Shots `9–10` on `flux-2-klein-4b` so Addisu stayed clean-shaven and standing beside the Elder.
  2. When closer review still showed late-film drift across Shots `7–11`, introduced single-subject **`reference_shot_id: 3`** (`shot_03.png`) conditioning in `02_keyframes.py` + `storyboard.json`, regenerating Shots `7–11` (`flux2-ref`, `6.02s–12.08s`) and re-exporting all films cleanly (`0` TTS calls needed).

---

## 4. The Hardest Problem and How I Solved It

Two deeply coupled bottlenecks required the most engineering persistence:

1. **Cross-Shot Character Consistency on Distilled Image Models Without Face-ID Adapters (`Experiments 3, 4, 12`; `Failures 8, 9, 11`):**  
   Calling Cloudflare `flux-2-klein-4b` with binary image conditioning initially hit a `403 HTML` WAF block until we added a custom `User-Agent` and downscaled inputs `<512px` (`480×270` JPEG). Once `HTTP 200` succeeded, passing our 4-person `character_sheet.png` backfired: `flux-2-klein-4b` treated `input_image_0` as a spatial image-edit canvas, cloning all four lineup bodies and studio walls into 1- and 2-person scenes. Disabling the 4-person lineup sheet (`CF_ENABLE_IMAGE_REF=0`) restored clean composition, and my later breakthrough (`Experiment 12`) showed that passing **only a single-subject Golden Reference portrait** (`shot_03.png` via `"reference_shot_id": 3`) locked Addisu's exact eyebrows, mustache shadow, short Afro, and dual vertical `tibeb` shirt trim across Shots `7–11`—provided multi-person ensembles (`Shot 4`) remained text-conditioned (`flux2-txt`) and `generate_with_fallback()` tried `flux2-ref-altseed` (`seed+100`) before dropping reference mode on false-positive `code 3030` flags.

2. **Cross-Platform Runtime & Windows/Kaggle Failure Modes (`Failures 3–7, 10, 12`):**  
   On Windows, FFmpeg failed silent `PATH` lookup after WinGet install (`ensure_ffmpeg_in_path()` via `HKCU\Environment`), `requests` failed SSL verification (`truststore`), FFmpeg filtergraphs choked on `C:` colons in `subtitles=` (fixed via relative `cwd` paths), `Arial` rendered Amharic as tofu boxes (replaced with Pillow + `ebrima.ttf`), FFmpeg 9.1 hung indefinitely when given `-b:a 192k` on mono AAC (`-nostdin` + dropping fixed mono bitrate), and `zoompan` shimmered on 720p stills (`3×` Lanczos upscale before `zoompan`). On Kaggle, `ACE-Step 1.5` failed on Python `3.13` (`uv python install 3.12`) and then crashed on import because Jupyter leaked `MPLBACKEND=module://matplotlib_inline.backend_inline` into the isolated `.venv` (`os.environ['MPLBACKEND'] = 'Agg'` + `subprocess.run(..., check=True)`).

---

## 5. Suggested Practices Tested Honestly

- **Practice That Beat My Instinct (Helped): Building a Narration-Only `radio_cut.mp4` + Shared JSON Contract Before Generating Pictures.**  
  My instinct was to skip audio-only prototypes and start generating keyframes and video immediately. Following the Radio Cut practice (`01b_radio_cut.py` in `6.86s`) exposed a `107.60s` runtime overrun (`+17.6s` above limit), generic protagonist framing, and stiff Amharic words *before* spending image or video quota. Paired with `storyboard.json` + SHA-256 caching, every later User Test #2 revision regenerated only affected shots with zero redundant TTS API calls.

- **Suggested Practice That Did Not Work as Expected (With Evidence): Using the Multi-Character Turnaround `character_sheet.png` as Direct Image Conditioning Across Shots (`Experiment 4`, `Failure 11`).**  
  Standard advice is to generate a multi-pose character sheet first and pass it into every subsequent shot. While `character_sheet.png` helped establish visual design, passing it into `flux-2-klein-4b`'s `input_image_0` actively broke composition—spawning extra adults in `Shot 01`, a disembodied arm in `Shot 02`, and four people sitting on a wall in `Shot 07`. Documented evidence forced me to disable the lineup sheet as a runtime input (`CF_ENABLE_IMAGE_REF=0`), use fixed East African descriptors for ensemble shots, and restrict image conditioning strictly to a single-subject Golden Reference portrait (`reference_shot_id: 3`) in `Experiment 12`.

---

## 6. Raising the Ceiling: Multi-Language Ethiopian Films (`Afaan Oromo` & `Tigrinya`)

To test generalizability beyond the floor requirement, I parameterized [05_assemble.py](pipeline/05_assemble.py) and built [benchmark_languages.py](pipeline/benchmark_languages.py) to dub all 10 narrated shots and assemble **separate standalone `16:9` & `9:16` films** in **Afaan Oromo (`om`)** and **Tigrinya (`ti`)**—without altering `python run_pipeline.py`'s Amharic-only default (`Experiments 11`, `Failures 13–14`, `outputs/benchmarks/benchmark_summary.json`):

| Language | Script / Font (`ebrima.ttf`) | Speech Duration | Standalone `16:9` / `9:16` Outputs | Measured TTS Observations |
|----------|------------------------------|-----------------|------------------------------------|---------------------------|
| **Amharic (`am`)** | Ethiopic (`0` missing glyphs) | `49.41s` | `film_16x9.mp4` (`68.3s`) / `film_9x16.mp4` (`68.2s`) | Natural pacing (`1.38–1.50 words/s`), clean stress |
| **Afaan Oromo (`om`)** | Latin Qubee (`0` missing glyphs) | `52.89s` | `film_om_16x9.mp4` (`72.1s`) / `film_om_9x16.mp4` (`72.0s`) | `9/10` on `flash-tts` before `10 RPD` fallback |
| **Tigrinya (`ti`)** | Ethiopic incl. `ስቕ`/`ቕ` (`0` missing glyphs) | `52.58s` | `film_ti_16x9.mp4` (`70.4s`) / `film_ti_9x16.mp4` (`70.2s`) | `1/10` on `flash-tts`, `9/10` on `flash-lite-tts` |

### Insights Discovered From Audio Inspection & Telemetry
1. **Uncovered `3 RPM` Burst Limits on *Both* Gemini TTS Tiers:** Logs revealed `gemini-3.8-flash-tts` AND `gemini-3.8-flash-lite-tts` enforce `3 requests/minute` on top of `10 RPD`. Initially treating every `429` as daily exhaustion prematurely downgraded Tigrinya Beat 6 (`Shot 06 ti`) to `flash-lite-tts`. Adding a `48s` wait on `"per minute"` `429` responses in `synthesize_with_rpm_awareness()` cleanly rescued `[ti] Shot 07`.
2. **Exact Phonological Failure Boundaries:** Listening directly to synthesized WAVs showed *why* multi-language Ethiopian TTS still needs human QA:
   - On `flash-lite-tts`, Tigrinya Beat 6 accelerated to **`2.44 words/s` (`9.25 chars/s`)**, truncating `"ንኣዲሱ"` (`Addisu`) to `"ናአዱ"` (`na'addu`) and slurring `"ዓቢ ሰብኣይ"`. Even full `flash-tts` (`Shot 02`) pulled Tigrinya pharyngeals (`ሓ`, `ዓ`) toward Amharic phonology.
   - On full `flash-tts`, Afaan Oromo kept warm cadence (`6.40s` avg latency) **but collapsed Qubee orthography**: implosive `dh` flattened to plain `d` (`"dhugaadhaaf dhaabbadhu"` → `"duggaadaf daabadu"`), and ejective `c` in `"cal jedhi"` was read as Amharic/English `"ch"`.
   - **Visual contrast:** `ebrima.ttf` rendered every Tigrinya character cleanly (`0` tofu boxes, including `ስቕ`/`ቕ` and `ኣ`/`ኽ`/`ሕ`).

---

## 7. Measured Costs, Latencies & Ethics Summary

Cumulative measurements logged in `runs.jsonl` and `pipeline/analyze_runs.py` across all development, User Test rebuilds, and multi-language ceiling runs:

- **Gemini 3.8 TTS (`flash-tts` + `flash-lite-tts`):** `26` successful film/benchmark calls on `flash-tts` (`16` narration + `10` `om`/`ti` benchmark, plus `1` smoke test; `avg 6.87–11.10s`) + `15` successful `flash-lite-tts` fallback calls (`avg 5.38–6.95s`); `$0.00` paid (commercial TTS equivalent `~$0.06–$0.14`).
- **Cloudflare Workers AI (`flux-2-klein-4b` + `flux-1-schnell`):** `48` successful film/iteration image calls (`44` `flux-2-klein-4b` keyframes + `2` reference sheets + `2` `flux-1-schnell` fallbacks, plus `1` smoke test; `avg 15.56s` primary / `4.22s` fallback); `$0.00` paid (commercial equivalent `~$0.15–$0.72`).
- **Kaggle T4 GPU (`ACE-Step 1.5`):** `3 × 80s` candidates (`seed=42`: `43.29s`, `seed=123`: `41.11s`, `seed=777`: `41.91s`; `126.31s` inference + ~2 min setup, `$0.00` quota).
- **Local FFmpeg + Pillow (`Ken Burns`, `Radio Cut`, `Assembly`):** `29` Ken Burns shots (`89.73s` CPU) + `19.41s` radio cut + `7` Amharic & `4` multi-language film assemblies (`1,024.20s` CPU, `$0.00`).
- **Out-of-pocket spend:** **`$0.00`** (optional Wan 2.2 TI2V-5B Diffusers notebook upgraded in `notebooks/wan22_shots.ipynb` for T4 GPU offloading).
- **Consent & AI Transparency (`ETHICS.md`):** Fictional story and fictional AI-generated cast only; synthetic prebuilt voice `Schedar` (zero voice cloning); commercial-safe open weights (`Apache 2.0` FLUX.2 klein / Wan 2.2, `MIT` ACE-Step 1.5); visible `"This film was made with AI"` end card and platform AI disclosure enabled.

---

## 8. What I Would Build Next

1. **Distinguish `3 RPM` vs. `10 RPD` inside `01_narration.py`:** Port the `48s` `"per minute"` sleep from `benchmark_languages.py` directly into the main Stage 1 narrator so burst multi-shot runs never needlessly downgrade quality to `flash-lite-tts`.
2. **Multi-Reference Masking & Pronunciation QA Gate:** Extend `reference_shot_id` to pass separate cropped references for both the Elder (`shot_06.png`) and Addisu (`shot_03.png`) in Shot 10 without identity bleed, and add an automated Whisper/ASR round-trip pronunciation check to flag dropped syllables like `"ንኣዲሱ" → "ናአዱ"` in `ti`/`om` dubs.
3. **Controlled Wan 2.2 vs. Ken Burns Blind Evaluation & Family Web UI:** Run a blind 5-person comparison between 720p `Wan 2.2 TI2V-5B` clips and 3× Lanczos Ken Burns shots once higher-VRAM GPU access allows, and expose `storyboard.json` through a minimal web form so non-technical relatives can produce stories in their own language with one click.
