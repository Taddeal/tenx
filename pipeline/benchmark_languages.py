"""
Raising the Ceiling: Multi-Language Ethiopian TTS & Rendering Benchmark.

Tests how the Heritage Short pipeline behaves on Afaan Oromo (om) and Tigrinya (ti)
against our Amharic (am) baseline across three dimensions:
  1. Ethiopic / Latin font glyph coverage (especially Tigrinya-specific Ethiopic e.g. ቕ / ኣ)
  2. Gemini 3.8 TTS latency, quota fallback, speaking rate (chars/s & words/s), and prosody
  3. End-card + A/B audio-video reel generation (outputs/benchmarks/compare_am_om_ti.mp4)

Reuses pipeline/01_narration.py (call_tts_rest) and pipeline/05_assemble.py (fonts, FFmpeg).
"""

import importlib
import json
import os
import subprocess
import sys
import time
from PIL import Image, ImageDraw

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from pipeline.utils import (
    ensure_ffmpeg_in_path,
    get_audio_duration,
    inject_windows_certs,
    load_cache,
    load_storyboard,
    log_call,
    save_cache,
    stable_hash,
)

mod_narr = importlib.import_module("pipeline.01_narration")
mod_asm = importlib.import_module("pipeline.05_assemble")

inject_windows_certs()

# Three contrasting beats from Addisu's storyboard:
#   Shot 02: Core advice (warm imperative, proper noun "Addisu")
#   Shot 06: Elder's plea (dialogue shift, Tigrinya uvular 'ቕ' in ስቕ, Oromo doubled vowels)
#   Shot 11: Moral synthesis (compound sentence & proverb pacing)
LANGUAGE_PACKS = {
    "am": {
        "name": "Amharic",
        "script": "Ethiopic (Ge'ez)",
        "style": "warm, clear, natural Ethiopian storytelling",
        "end_card_proverb": "አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።",
        "end_card_title": "የእውነት ፈተና  —  The Test of Truth",
        "beats": {
            2: "አዲሱ ልጄ፣ አዛውንቶችን አክብር፤ ሁልጊዜም ለእውነት ቁም።",
            6: "የወሰደው የአንድ ሽማግሌ ልጅ ነበር። ሽማግሌውም አዲሱን፣ እባክህ ዝም በል አሉት።",
            11: "አዲሱ ተረዳ፤ ማክበር ማለት ስህተትን መደበቅ አይደለም።",
        },
    },
    "om": {
        "name": "Afaan Oromo",
        "script": "Qubee (Latin + glottal/ejectives)",
        "style": "warm, clear, natural Afaan Oromo Ethiopian storytelling",
        "end_card_proverb": "Manguddoota kabaji; dhugaa garuu hin ganin.",
        "end_card_title": "Qormaata Dhugaa  —  The Test of Truth",
        "beats": {
            2: "Ilma koo Addisu, manguddoota kabaji; yeroo hundas dhugaadhaaf dhaabbadhu.",
            6: "Kan fudhate ilma jaarsaa ture. Jaarsichis Addisuudhaan, maaloo cal jedhi jedheen.",
            11: "Addisuun ni hubate; kabajuun dogoggora dhoksuu miti.",
        },
    },
    "ti": {
        "name": "Tigrinya",
        "script": "Ethiopic (incl. Tigrinya ቐ-series)",
        "style": "warm, clear, natural Tigrinya Ethiopian storytelling",
        "end_card_proverb": "ንዓበይቲ ኣኽብር፤ ንሓቂ ግን ኣይትኽሓድ።",
        "end_card_title": "ፈተና ሓቂ  —  The Test of Truth",
        "beats": {
            2: "ወደይ ኣዲሱ፣ ንዓበይቲ ኣኽብር፤ ኩሉ ግዜ ድማ ንሓቂ ደው በል።",
            6: "ዝወሰዶ ወዲ ሓደ ዓቢ ሰብኣይ ነበረ። እቲ ዓቢ ሰብኣይ ድማ ንኣዲሱ፣ በጃኻ ስቕ በል በሎ።",
            11: "ኣዲሱ ተረዲኡ፤ ምኽባር ማለት ጌጋ ምሕባእ ኣይኮነን።",
        },
    },
}


def check_font_glyphs(font, text):
    """Detect whether Pillow's active font renders real outlines or .notdef tofu boxes."""
    missing = []
    notdef_bytes = bytes(font.getmask("\ufffe"))
    for ch in sorted(set(text)):
        if ch.isspace():
            continue
        glyph_bytes = bytes(font.getmask(ch))
        if glyph_bytes == notdef_bytes or not glyph_bytes:
            missing.append(ch)
    return missing


def render_language_end_card(lang_code, pack, storyboard, out_png):
    ec = storyboard.get("end_card", {})
    sb_copy = {
        "meta": {
            "title": storyboard["meta"]["title"],
            "title_amharic": pack["end_card_title"].split("  —  ")[0],
        },
        "end_card": {
            "text_amharic": pack["end_card_proverb"],
            "text_english": ec.get("text_english", "Respect your elders, but never deny the truth."),
            "ai_disclosure": ec.get("ai_disclosure", "This film was made with AI"),
        },
    }
    return mod_asm.create_end_card_image(sb_copy, out_png)


def synthesize_benchmark_beat(api_key, models, text, voice, style, lang_code, shot_id):
    last_err = None
    for model in models:
        t0 = time.time()
        try:
            audio = mod_narr.call_tts_rest(api_key, model, text, voice, style, timeout_s=35)
            return audio, model, round(time.time() - t0, 2)
        except Exception as e:
            latency = round(time.time() - t0, 2)
            last_err = e
            err_str = str(e)
            log_call({
                "stage": "benchmark_language",
                "provider": "gemini",
                "language": lang_code,
                "model": model,
                "shot_id": shot_id,
                "parameters": {"voice": voice, "style": style},
                "seed": None,
                "latency_seconds": latency,
                "cost_estimate": "free tier",
                "status": "error",
                "error": err_str[:280],
            })
            if "429" in err_str or "too_many_requests" in err_str or "getaddrinfo" in err_str:
                continue
    raise RuntimeError(f"TTS failed for {lang_code} shot {shot_id}: {last_err}")


def build_comparison_reel(ffmpeg_bin, out_dir, results):
    """Build a side-by-side playable A/B reel cycling Shot 02 -> 06 -> 11 across am/om/ti."""
    tmp_dir = os.path.join(out_dir, "_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    clips = []
    font_title = mod_asm.find_ethiopic_font(26)
    font_sub = mod_asm.find_latin_font(22)

    for shot_id in (2, 6, 11):
        kf = os.path.join(PROJECT_ROOT, "outputs", "keyframes", f"shot_{shot_id:02d}.png")
        for lang_code in ("am", "om", "ti"):
            wav_path = os.path.join(PROJECT_ROOT, results[lang_code][shot_id]["wav_path"])
            dur = round(get_audio_duration(wav_path) + 0.6, 2)
            card_png = os.path.join(tmp_dir, f"slide_{shot_id}_{lang_code}.png")
            img = Image.open(kf).convert("RGBA").resize((1280, 720))
            overlay = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)
            draw.rectangle([0, 0, 1280, 88], fill=(20, 14, 10, 200))
            draw.rectangle([0, 595, 1280, 720], fill=(20, 14, 10, 215))
            pack = LANGUAGE_PACKS[lang_code]
            label = f"Shot {shot_id:02d}  |  {pack['name']} ({lang_code})  |  {results[lang_code][shot_id]['model']}"
            wrapped = mod_asm.wrap_subtitle(pack["beats"][shot_id], max_chars=48)
            draw.text((640, 44), label, font=font_sub, fill=(245, 215, 150), anchor="mm")
            draw.multiline_text((640, 658), wrapped, font=font_title, fill=(255, 250, 240), anchor="mm", align="center", spacing=8)
            Image.alpha_composite(img, overlay).convert("RGB").save(card_png)

            clip_mp4 = os.path.join(tmp_dir, f"clip_{shot_id}_{lang_code}.mp4")
            subprocess.run(
                [
                    ffmpeg_bin, "-y", "-nostdin",
                    "-loop", "1", "-framerate", "24", "-i", card_png,
                    "-i", wav_path,
                    "-vf", "format=yuv420p",
                    "-af", f"aresample=48000,aformat=channel_layouts=stereo,apad,atrim=0:{dur}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
                    "-c:a", "aac", "-t", str(dur),
                    clip_mp4,
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            clips.append(os.path.basename(clip_mp4))

    concat_txt = os.path.join(tmp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for name in clips:
            f.write(f"file '{name}'\n")

    out_mp4 = os.path.join(out_dir, "compare_am_om_ti.mp4")
    subprocess.run(
        [
            ffmpeg_bin, "-y", "-nostdin",
            "-f", "concat", "-safe", "0", "-i", "concat.txt",
            "-c", "copy",
            out_mp4,
        ],
        cwd=tmp_dir,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    return out_mp4


def main():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("FAIL GEMINI_API_KEY not set.")
        sys.exit(1)

    storyboard = load_storyboard()
    narr_cfg = storyboard.get("narration", {})
    primary_model = narr_cfg.get("model", "gemini-3.8-flash-tts")
    fallback_model = narr_cfg.get("fallback_model", "gemini-3.8-flash-lite-tts")
    models = [primary_model] + ([fallback_model] if fallback_model != primary_model else [])
    voice = narr_cfg.get("voice", "Schedar")

    out_dir = os.path.join(PROJECT_ROOT, "outputs", "benchmarks")
    os.makedirs(out_dir, exist_ok=True)
    cache_path = os.path.join(out_dir, ".cache.json")
    cache = load_cache(cache_path)

    # 1. Font glyph audit (Ebrima vs Tigrinya / Oromo characters)
    font_eth = mod_asm.find_ethiopic_font(40)
    print("Stage 1/3: Font glyph audit (Ebrima)")
    for code, pack in LANGUAGE_PACKS.items():
        combined = " ".join(pack["beats"].values()) + " " + pack["end_card_proverb"]
        missing = check_font_glyphs(font_eth, combined)
        end_png = os.path.join(out_dir, f"end_card_{code}.png")
        render_language_end_card(code, pack, storyboard, end_png)
        print(f"  {code} ({pack['name']}): missing_glyphs={missing} -> saved {os.path.basename(end_png)}")

    # 2. TTS synthesis across om & ti (reusing cached am baseline from outputs/narration/)
    print("\nStage 2/3: Multi-language TTS benchmark (Gemini 3.8 TTS)")
    results = {code: {} for code in LANGUAGE_PACKS}
    quota_hit_primary = False

    for shot_id in (2, 6, 11):
        am_wav = os.path.join(PROJECT_ROOT, "outputs", "narration", f"shot_{shot_id:02d}.wav")
        am_text = LANGUAGE_PACKS["am"]["beats"][shot_id]
        am_dur = get_audio_duration(am_wav)
        results["am"][shot_id] = {
            "wav_path": f"outputs/narration/shot_{shot_id:02d}.wav",
            "model": "cached baseline",
            "duration_s": round(am_dur, 2),
            "chars_per_sec": round(len(am_text) / max(am_dur, 0.1), 2),
            "words_per_sec": round(len(am_text.split()) / max(am_dur, 0.1), 2),
        }

    for lang_code in ("om", "ti"):
        pack = LANGUAGE_PACKS[lang_code]
        lang_dir = os.path.join(out_dir, lang_code)
        os.makedirs(lang_dir, exist_ok=True)
        for shot_id in (2, 6, 11):
            text = pack["beats"][shot_id]
            wav_path = os.path.join(lang_dir, f"shot_{shot_id:02d}.wav")
            ckey = f"{lang_code}_shot_{shot_id}"
            chash = stable_hash(text, primary_model, voice, pack["style"])

            if cache.get(ckey) == chash and os.path.exists(wav_path):
                dur = get_audio_duration(wav_path)
                model_used = cache.get(f"{ckey}_model", primary_model)
                print(f"  [{lang_code}] Shot {shot_id:02d}: Cached ({dur:.2f}s, {model_used})")
            else:
                active = models[1:] if (quota_hit_primary and len(models) > 1) else models
                print(f"  [{lang_code}] Shot {shot_id:02d}: Synthesizing ({active[0]})...")
                audio, model_used, latency = synthesize_benchmark_beat(
                    api_key, active, text, voice, pack["style"], lang_code, shot_id
                )
                if model_used != primary_model:
                    quota_hit_primary = True
                with open(wav_path, "wb") as f:
                    f.write(audio)
                dur = get_audio_duration(wav_path)
                log_call({
                    "stage": "benchmark_language",
                    "provider": "gemini",
                    "language": lang_code,
                    "model": model_used,
                    "shot_id": shot_id,
                    "parameters": {"voice": voice, "style": pack["style"], "chars": len(text), "words": len(text.split())},
                    "seed": None,
                    "output_file": f"outputs/benchmarks/{lang_code}/shot_{shot_id:02d}.wav",
                    "output_bytes": len(audio),
                    "audio_duration_seconds": round(dur, 2),
                    "latency_seconds": latency,
                    "cost_estimate": "free tier",
                    "status": "success",
                })
                cache[ckey] = chash
                cache[f"{ckey}_model"] = model_used
                save_cache(cache_path, cache)
                print(f"    OK {model_used}: {dur:.2f}s audio in {latency:.2f}s ({len(audio)/1024:.1f} KB)")
                time.sleep(0.6)

            results[lang_code][shot_id] = {
                "wav_path": f"outputs/benchmarks/{lang_code}/shot_{shot_id:02d}.wav",
                "model": model_used,
                "duration_s": round(dur, 2),
                "chars_per_sec": round(len(text) / max(dur, 0.1), 2),
                "words_per_sec": round(len(text.split()) / max(dur, 0.1), 2),
            }

    # 3. Print comparison summary + write JSON report + build playable A/B reel
    report_path = os.path.join(out_dir, "benchmark_summary.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print("\nStage 3/3: Summary Table (Duration & Pacing Across Languages)")
    print(f"{'Shot':<6} {'Lang':<5} {'Dur(s)':<8} {'Chars/s':<8} {'Words/s':<8} {'Model'}")
    print("-" * 62)
    for shot_id in (2, 6, 11):
        for lang_code in ("am", "om", "ti"):
            r = results[lang_code][shot_id]
            print(f"{shot_id:02d}     {lang_code:<5} {r['duration_s']:<8.2f} {r['chars_per_sec']:<8.2f} {r['words_per_sec']:<8.2f} {r['model']}")

    ffmpeg_bin, _ = ensure_ffmpeg_in_path()
    if ffmpeg_bin:
        reel = build_comparison_reel(ffmpeg_bin, out_dir, results)
        print(f"\nOK Playable A/B comparison reel: {reel}")


if __name__ == "__main__":
    main()
