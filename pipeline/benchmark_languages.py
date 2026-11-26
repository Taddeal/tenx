"""
Raising the Ceiling: Multi-Language Ethiopian TTS & Standalone Film Dubbing Benchmark.

Builds separate full 60-90s films in Afaan Oromo (om) and Tigrinya (ti) alongside
the primary Amharic (am) pipeline, without altering storyboard.json or outputs/final/.
Running `python run_pipeline.py` continues to generate Amharic-only films.

Features:
  1. Font glyph coverage check (Ebrima on Ethiopic/Tigrinya ቐ-series & Latin Qubee)
  2. Gemini 3.8 TTS synthesis across all 10 narrated shots per language with 3 RPM
     rate-limit wait vs 10 RPD quota fallback distinction
  3. Separate 16:9 and 9:16 dubbed exports via pipeline/05_assemble.py assemble_film():
       outputs/benchmarks/om/final/film_om_{16x9,9x16}.mp4
       outputs/benchmarks/ti/final/film_ti_{16x9,9x16}.mp4
"""

import argparse
import copy
import importlib
import json
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from pipeline.utils import (
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

LANGUAGE_PACKS = {
    "am": {
        "name": "Amharic",
        "script": "Ethiopic (Ge'ez)",
        "style": "warm, clear, natural Ethiopian storytelling",
        "end_card_proverb": "አዛውንቶችን አክብር፤ እውነትን ግን አትካድ።",
        "end_card_title": "የእውነት ፈተና",
        "beats": {
            1: "አዲሱ ገና ልጅ እያለ፣ አባቱ በየቀኑ ሁለት ቃሎችን ይነግረው ነበር።",
            2: "አዲሱ ልጄ፣ አዛውንቶችን አክብር፤ ሁልጊዜም ለእውነት ቁም።",
            3: "ዓመታት አለፉ። አዲሱ አደገ፤ የአባቱን ምክር ግን አልረሳም።",
            4: "አንድ ቀን በቤተሰብ ስብሰባ ላይ ገንዘብ ጠፋ።",
            5: "ንጹሕ ሰው ተከሰሰ። አዲሱ ግን እውነቱን ያውቅ ነበር።",
            6: "የወሰደው የአንድ ሽማግሌ ልጅ ነበር። ሽማግሌውም አዲሱን፣ እባክህ ዝም በል አሉት።",
            7: "አዲሱ ተጨነቀ። ሽማግሌውን ያክብር ወይስ እውነቱን ይናገር?",
            9: "አዲሱ ተነስቶ፣ አከብርዎታለሁ አለ። ግን ንጹሕ ሰው ሲበደል ዝም አልልም።",
            10: "እውነቱ ወጣ፤ ንጹሑም ሰው ነፃ ሆነ።",
            11: "አዲሱ ተረዳ፤ ማክበር ማለት ስህተትን መደበቅ አይደለም።",
        },
    },
    "om": {
        "name": "Afaan Oromo",
        "script": "Qubee (Latin + glottal/ejectives)",
        "style": "warm, clear, natural Afaan Oromo Ethiopian storytelling",
        "end_card_proverb": "Manguddoota kabaji; dhugaa garuu hin ganin.",
        "end_card_title": "Qormaata Dhugaa",
        "beats": {
            1: "Yeroo Addisuun ijoollee turetti, abbaan isaa guyyaa hundumaa jechoota lama itti hima ture.",
            2: "Ilma koo Addisu, manguddoota kabaji; yeroo hundas dhugaadhaaf dhaabbadhu.",
            3: "Waggoonni darban. Addisuun guddate; gorsa abbaa isaa garuu hin irraanfanne.",
            4: "Gaaf tokko walga'ii maatii irratti maallaqni bade.",
            5: "Namni qulqulluun tokko himatame. Addisuun garuu dhugaa isaa beeka ture.",
            6: "Kan fudhate ilma jaarsaa ture. Jaarsichis Addisuudhaan, maaloo cal jedhi jedheen.",
            7: "Addisuun yaaddoo keessa gale. Jaarsa kabaju moo dhugaa dubbatu?",
            9: "Addisuun tasgabbiidhaan ka'ee, isin nan kabaja jedhe. Garuu namni qulqulluun yoo miidhamu hin callisu.",
            10: "Dhugaan bahe; namni qulqulluun sunis bilisa ta'e.",
            11: "Addisuun ni hubate; kabajuun dogoggora dhoksuu miti.",
        },
    },
    "ti": {
        "name": "Tigrinya",
        "script": "Ethiopic (incl. Tigrinya ቐ-series)",
        "style": "warm, clear, natural Tigrinya Ethiopian storytelling",
        "end_card_proverb": "ንዓበይቲ ኣኽብር፤ ንሓቂ ግን ኣይትኽሓድ።",
        "end_card_title": "ፈተና ሓቂ",
        "beats": {
            1: "ኣዲሱ ገና ቆልዓ እንከሎ፣ ኣቦኡ መዓልታዊ ክልተ ቃላት ይነግሮ ነበረ።",
            2: "ወደይ ኣዲሱ፣ ንዓበይቲ ኣኽብር፤ ኩሉ ግዜ ድማ ንሓቂ ደው በል።",
            3: "ዓመታት ሓለፉ። ኣዲሱ ዓበየ፤ ምኽሪ ኣቦኡ ግን ኣይረስዐን።",
            4: "ሓደ መዓልቲ ኣብ ኣኼባ ስድራቤት ገንዘብ ጠፍአ።",
            5: "ንጹህ ሰብ ተኸሰሰ። ኣዲሱ ግን እቲ ሓቂ ይፈልጦ ነበረ።",
            6: "ዝወሰዶ ወዲ ሓደ ዓቢ ሰብኣይ ነበረ። እቲ ዓቢ ሰብኣይ ድማ ንኣዲሱ፣ በጃኻ ስቕ በል በሎ።",
            7: "ኣዲሱ ተጨነቐ። ነቲ ዓቢ ሰብኣይ የኽብር ዋላ እቲ ሓቂ ይዛረብ?",
            9: "ኣዲሱ ብህድኣት ተሲኡ፣ የኽብረኩም እየ በለ። ግን ንጹህ ሰብ ክብደል ከሎ ስቕ ኣይብልን።",
            10: "እቲ ሓቂ ወጸ፤ እቲ ንጹህ ሰብውን ነጻ ኮነ።",
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


def build_localized_storyboard(base_sb, lang_code, pack):
    """Create an in-memory storyboard variant without modifying storyboard.json on disk."""
    sb = copy.deepcopy(base_sb)
    sb["meta"]["title_amharic"] = pack["end_card_title"]
    sb["meta"]["language"] = lang_code
    sb["end_card"]["text_amharic"] = pack["end_card_proverb"]
    for shot in sb["shots"]:
        sid = shot["id"]
        if sid in pack["beats"]:
            shot["narration_amharic"] = pack["beats"][sid]
    return sb


def synthesize_with_rpm_awareness(api_key, models, text, voice, style, lang_code, shot_id):
    """Wait out 3 RPM throttles on flash-tts before falling back to flash-lite-tts."""
    last_err = None
    for model in models:
        for attempt in (1, 2):
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
                    "parameters": {"voice": voice, "style": style, "attempt": attempt},
                    "seed": None,
                    "latency_seconds": latency,
                    "cost_estimate": "free tier",
                    "status": "error",
                    "error": err_str[:280],
                })
                if "getaddrinfo" in err_str:
                    raise
                if "per minute" in err_str.lower() and attempt == 1:
                    print(f"    WAIT {model} hit 3 RPM limit; sleeping 48s before retry...")
                    time.sleep(48)
                    continue
                if "429" in err_str or "too_many_requests" in err_str:
                    break
                if attempt == 1:
                    time.sleep(3)
    raise RuntimeError(f"TTS failed for {lang_code} shot {shot_id}: {last_err}")


def main():
    parser = argparse.ArgumentParser(description="Multi-language Ethiopian film generator & benchmark")
    parser.add_argument("--langs", nargs="+", default=["om", "ti"], choices=["om", "ti"], help="Target languages")
    parser.add_argument("--beats-only", action="store_true", help="Only synthesize Beats 2, 6, 11 without full film export")
    args = parser.parse_args()

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

    shot_ids = (2, 6, 11) if args.beats_only else tuple(s["id"] for s in storyboard["shots"] if s["id"] in LANGUAGE_PACKS["om"]["beats"])

    # 1. Font glyph check
    font_eth = mod_asm.find_ethiopic_font(40)
    print("Stage 1/3: Font glyph audit (Ebrima)")
    for code in ("am", *args.langs):
        pack = LANGUAGE_PACKS[code]
        combined = " ".join(pack["beats"].values()) + " " + pack["end_card_proverb"]
        missing = check_font_glyphs(font_eth, combined)
        print(f"  {code} ({pack['name']}): missing_glyphs={missing}")

    # 2. Synthesize narration tracks per language
    print(f"\nStage 2/3: Synthesizing {len(shot_ids)} shots per language ({', '.join(args.langs)})")
    results = {"am": {}}
    for sid in shot_ids:
        am_wav = os.path.join(PROJECT_ROOT, "outputs", "narration", f"shot_{sid:02d}.wav")
        am_text = LANGUAGE_PACKS["am"]["beats"][sid]
        am_dur = get_audio_duration(am_wav)
        results["am"][sid] = {
            "wav_path": f"outputs/narration/shot_{sid:02d}.wav",
            "model": "cached baseline",
            "duration_s": round(am_dur, 2),
            "chars_per_sec": round(len(am_text) / max(am_dur, 0.1), 2),
            "words_per_sec": round(len(am_text.split()) / max(am_dur, 0.1), 2),
        }

    daily_exhausted_primary = False
    for lang_code in args.langs:
        pack = LANGUAGE_PACKS[lang_code]
        lang_dir = os.path.join(out_dir, lang_code)
        os.makedirs(lang_dir, exist_ok=True)
        results[lang_code] = {}

        for sid in shot_ids:
            text = pack["beats"][sid]
            wav_path = os.path.join(lang_dir, f"shot_{sid:02d}.wav")
            ckey = f"{lang_code}_shot_{sid}"
            chash = stable_hash(text, primary_model, voice, pack["style"])

            if cache.get(ckey) == chash and os.path.exists(wav_path):
                dur = get_audio_duration(wav_path)
                model_used = cache.get(f"{ckey}_model", primary_model)
                print(f"  [{lang_code}] Shot {sid:02d}: Cached ({dur:.2f}s, {model_used})")
            else:
                active = models[1:] if (daily_exhausted_primary and len(models) > 1) else models
                print(f"  [{lang_code}] Shot {sid:02d}: Synthesizing ({active[0]})...")
                audio, model_used, latency = synthesize_with_rpm_awareness(
                    api_key, active, text, voice, pack["style"], lang_code, sid
                )
                if model_used != primary_model:
                    daily_exhausted_primary = True
                with open(wav_path, "wb") as f:
                    f.write(audio)
                dur = get_audio_duration(wav_path)
                log_call({
                    "stage": "benchmark_language",
                    "provider": "gemini",
                    "language": lang_code,
                    "model": model_used,
                    "shot_id": sid,
                    "parameters": {"voice": voice, "style": pack["style"], "chars": len(text), "words": len(text.split())},
                    "seed": None,
                    "output_file": f"outputs/benchmarks/{lang_code}/shot_{sid:02d}.wav",
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
                time.sleep(21 if model_used == primary_model else 1.0)

            results[lang_code][sid] = {
                "wav_path": f"outputs/benchmarks/{lang_code}/shot_{sid:02d}.wav",
                "model": model_used,
                "duration_s": round(dur, 2),
                "chars_per_sec": round(len(text) / max(dur, 0.1), 2),
                "words_per_sec": round(len(text.split()) / max(dur, 0.1), 2),
            }

    # 3. Assemble standalone full films for each language unless --beats-only
    film_outputs = {
        "am": {
            "16x9": "outputs/final/film_16x9.mp4",
            "9x16": "outputs/final/film_9x16.mp4",
        }
    }
    if not args.beats_only:
        print("\nStage 3/3: Assembling separate standalone films per language...")
        for lang_code in args.langs:
            pack = LANGUAGE_PACKS[lang_code]
            sb_lang = build_localized_storyboard(storyboard, lang_code, pack)
            lang_narr_dir = os.path.join(out_dir, lang_code)
            lang_final_dir = os.path.join(lang_narr_dir, "final")
            os.makedirs(lang_final_dir, exist_ok=True)
            print(f"\n  --- Building standalone {pack['name']} ({lang_code}) 16:9 + 9:16 ---")
            mod_asm.assemble_film(
                storyboard=sb_lang,
                narr_dir=lang_narr_dir,
                final_dir=lang_final_dir,
                filename_prefix=f"film_{lang_code}",
                log_stage="benchmark_language_film",
                log_extra={"language": lang_code},
            )
            film_outputs[lang_code] = {
                "16x9": f"outputs/benchmarks/{lang_code}/final/film_{lang_code}_16x9.mp4",
                "9x16": f"outputs/benchmarks/{lang_code}/final/film_{lang_code}_9x16.mp4",
            }

    report_path = os.path.join(out_dir, "benchmark_summary.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"shots": results, "films": film_outputs}, f, indent=2, ensure_ascii=False)

    print("\nSummary (Per-Language Totals):")
    for lang_code in ("am", *args.langs):
        tot_speech = sum(v["duration_s"] for v in results[lang_code].values())
        print(f"  {lang_code:<4} speech={tot_speech:.2f}s -> {film_outputs.get(lang_code, {})}")


if __name__ == "__main__":
    main()
