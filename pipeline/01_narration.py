"""
Stage 1: Generate narration audio for each shot using Gemini 3.8 TTS.
- Uses Gemini Interactions REST API (v1beta) with strict per-request timeout
  and OS truststore certificates so stalled connections fail fast.
- Automatically falls back to gemini-3.8-flash-lite-tts on 429 quota exhaustion
  (since gemini-3.8-flash-tts free tier is capped at 10 RPD).
- Caches by content hash (text + voice + style + primary model) so existing
  valid clips are preserved across runs.
"""

import base64
import os
import sys
import time
import requests

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

inject_windows_certs()

INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


def extract_audio_b64(payload):
    """Extract base64 audio from Gemini Interactions REST JSON response."""
    # Check both outputs[] (new REST shape) and steps[] (documented REST shape)
    for step in reversed(payload.get("outputs", []) or payload.get("steps", [])):
        if isinstance(step, dict):
            if step.get("type") == "audio" and step.get("data"):
                return step["data"]
            for item in reversed(step.get("content", [])):
                if isinstance(item, dict) and item.get("type") == "audio" and item.get("data"):
                    return item["data"]
    return None


def call_tts_rest(api_key, model, text, voice, style, timeout_s=35):
    resp = requests.post(
        INTERACTIONS_URL,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "input": [{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": text,
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": style,
                    }],
                }],
            }],
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [{"voice": voice}],
            },
        },
        timeout=(10, timeout_s),
    )
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:280]}")
    data = resp.json()
    b64 = extract_audio_b64(data)
    if not b64:
        raise RuntimeError(f"No audio payload in response keys={list(data.keys())}")
    return base64.b64decode(b64)


def synthesize_with_fallback(api_key, models, text, voice, style, shot_id):
    """Try primary model then fallback model on 429/503/timeout."""
    last_err = None
    for model in models:
        for attempt in (1, 2):
            t0 = time.time()
            try:
                audio_bytes = call_tts_rest(api_key, model, text, voice, style, timeout_s=35)
                latency = round(time.time() - t0, 2)
                return audio_bytes, model, latency, attempt
            except Exception as e:
                latency = round(time.time() - t0, 2)
                last_err = e
                err_str = str(e)
                log_call({
                    "stage": "narration",
                    "provider": "gemini",
                    "model": model,
                    "shot_id": shot_id,
                    "parameters": {"voice": voice, "style": style, "attempt": attempt},
                    "seed": None,
                    "latency_seconds": latency,
                    "cost_estimate": "free tier",
                    "status": "error",
                    "error": err_str[:280],
                })
                # Don't waste another attempt on 429 daily quota exhaustion; switch to fallback model immediately
                if "429" in err_str or "too_many_requests" in err_str or "getaddrinfo" in err_str:
                    print(f"    WARN {model} blocked ({err_str[:80]}...); switching fallback if available.")
                    break
                if attempt < 2:
                    print(f"    WARN {model} attempt {attempt} failed ({err_str[:80]}); retrying in 3s...")
                    time.sleep(3)
    raise RuntimeError(f"All TTS models failed for shot {shot_id}: {last_err}")


def generate_narration():
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("FAIL GEMINI_API_KEY not set. Check .env file.")
        sys.exit(1)

    storyboard = load_storyboard()
    narr_cfg = storyboard.get("narration", {})
    primary_model = narr_cfg.get("model", "gemini-3.8-flash-tts")
    fallback_model = narr_cfg.get("fallback_model", "gemini-3.8-flash-lite-tts")
    voice = narr_cfg.get("voice", "Schedar")
    style = narr_cfg.get("style", "calm, warm, unhurried Ethiopian storytelling")

    models = [primary_model]
    if fallback_model and fallback_model != primary_model:
        models.append(fallback_model)

    output_dir = os.path.join(PROJECT_ROOT, "outputs", "narration")
    os.makedirs(output_dir, exist_ok=True)
    cache_path = os.path.join(output_dir, ".cache.json")
    cache = load_cache(cache_path)

    generated = 0
    cached = 0
    failed = 0
    quota_exhausted_primary = False

    for shot in storyboard["shots"]:
        shot_id = shot["id"]
        narration = shot["narration_amharic"].strip()

        output_file = os.path.join(output_dir, f"shot_{shot_id:02d}.wav")
        cache_key = f"shot_{shot_id}"

        if not narration:
            if os.path.exists(output_file):
                os.remove(output_file)
            if cache_key in cache:
                cache.pop(cache_key, None)
                save_cache(cache_path, cache)
            print(f"  Shot {shot_id:02d}: No narration (silent/end card). Skipping.")
            continue

        # Check cache
        content_key = stable_hash(narration, primary_model, voice, style)

        if cache.get(cache_key) == content_key and os.path.exists(output_file):
            dur = get_audio_duration(output_file)
            print(f"  Shot {shot_id:02d}: Cached ({dur:.2f}s). Skipping.")
            cached += 1
            continue

        active_models = models[1:] if (quota_exhausted_primary and len(models) > 1) else models
        print(f"  Shot {shot_id:02d}: Generating narration ({active_models[0]}, {voice})...")
        try:
            audio_bytes, model_used, latency, attempt = synthesize_with_fallback(
                api_key, active_models, narration, voice, style, shot_id
            )
            if model_used != primary_model:
                quota_exhausted_primary = True

            with open(output_file, "wb") as f:
                f.write(audio_bytes)

            file_size = os.path.getsize(output_file)
            dur = get_audio_duration(output_file)

            log_call({
                "stage": "narration",
                "provider": "gemini",
                "model": model_used,
                "shot_id": shot_id,
                "parameters": {"voice": voice, "style": style, "input_chars": len(narration), "attempt": attempt},
                "seed": None,
                "input_text": narration,
                "output_file": f"outputs/narration/shot_{shot_id:02d}.wav",
                "output_bytes": file_size,
                "audio_duration_seconds": round(dur, 2),
                "latency_seconds": latency,
                "cost_estimate": "free tier",
                "status": "success",
            })

            cache[cache_key] = content_key
            save_cache(cache_path, cache)
            print(f"    OK   {model_used}: {dur:.2f}s audio in {latency:.2f}s ({file_size / 1024:.1f} KB)")
            generated += 1
            time.sleep(0.6)
        except Exception as e:
            print(f"    FAIL {e}")
            failed += 1

    print(f"\nNarration summary: {generated} generated, {cached} cached, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    print("Stage 1: Generating Amharic narration with Gemini 3.8 TTS...")
    print("=" * 60)
    generate_narration()
    print("=" * 60)
    print("Stage 1 complete.")
