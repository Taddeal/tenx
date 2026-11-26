"""
Phase 1 Smoke Test: Verify each configured provider once and log latency to runs.jsonl.
Tests:
1. FFmpeg & FFprobe local binary availability
2. Gemini Text (gemini-3.8-flash)
3. Gemini TTS (gemini-3.8-flash-tts) with Amharic phrase
4. Cloudflare Workers AI (FLUX) if credentials are set in .env
5. Optional check: whether Gemini image model is accessible on free tier
"""

import base64
import os
import sys
import time
import wave
import io

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

import requests
from google import genai
from pipeline.utils import ensure_ffmpeg_in_path, inject_windows_certs, log_call

inject_windows_certs()


def test_ffmpeg():
    ffmpeg_bin, ffprobe_bin = ensure_ffmpeg_in_path()
    if ffmpeg_bin and ffprobe_bin:
        print(f"OK   FFmpeg found: {ffmpeg_bin}")
        return True
    print("FAIL FFmpeg or FFprobe not found")
    return False


def test_gemini_text(client):
    model = "gemini-3.8-flash"
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=model,
            contents="Reply with OK in one word.",
        )
        latency = round(time.time() - t0, 2)
        text = (resp.text or "").strip()
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "parameters": {"prompt_len": 27},
            "seed": None,
            "latency_seconds": latency,
            "cost_estimate": "free tier",
            "status": "success",
            "response_preview": text[:40],
        })
        print(f"OK   {model}: '{text}' ({latency}s)")
        return True
    except Exception as e:
        latency = round(time.time() - t0, 2)
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "latency_seconds": latency,
            "cost_estimate": "free tier",
            "status": "error",
            "error": str(e)[:200],
        })
        print(f"FAIL {model}: {e}")
        return False


def test_gemini_tts(client):
    model = "gemini-3.8-flash-tts"
    sample_text = "ሰላም። ይህ የድምፅ ሙከራ ነው።"
    t0 = time.time()
    try:
        interaction = client.interactions.create(
            model=model,
            input=[{
                "type": "user_input",
                "content": [{
                    "type": "text",
                    "text": sample_text,
                    "annotations": [{
                        "type": "speech_metadata",
                        "style": "calm, warm, unhurried storytelling",
                    }],
                }],
            }],
            response_format={"type": "audio"},
            generation_config={
                "speech_config": [{"voice": "Schedar"}]
            },
        )
        latency = round(time.time() - t0, 2)
        audio_b64 = getattr(getattr(interaction, "output_audio", None), "data", None)
        if not audio_b64:
            raise RuntimeError("No output_audio.data returned")
        audio_bytes = base64.b64decode(audio_b64)
        is_riff = audio_bytes[:4] == b"RIFF"
        dur = None
        if is_riff:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                dur = round(wf.getnframes() / float(wf.getframerate()), 2)
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "parameters": {"voice": "Schedar", "language": "am", "riff_header": is_riff},
            "seed": None,
            "latency_seconds": latency,
            "output_bytes": len(audio_bytes),
            "audio_duration_seconds": dur,
            "cost_estimate": "free tier",
            "status": "success",
        })
        print(f"OK   {model}: {len(audio_bytes)} bytes, RIFF={is_riff}, dur={dur}s ({latency}s)")
        return True
    except Exception as e:
        latency = round(time.time() - t0, 2)
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "latency_seconds": latency,
            "cost_estimate": "free tier",
            "status": "error",
            "error": str(e)[:300],
        })
        print(f"FAIL {model}: {e}")
        return False


def test_gemini_image(client):
    model = "gemini-3.1-flash-image"
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=model,
            contents="A small Ethiopian coffee cup on a wooden table, warm morning light.",
        )
        latency = round(time.time() - t0, 2)
        has_image = any(
            getattr(part, "inline_data", None) is not None
            for cand in (resp.candidates or [])
            for part in (cand.content.parts or [])
        )
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "parameters": {"mode": "image_probe"},
            "seed": None,
            "latency_seconds": latency,
            "has_image": has_image,
            "cost_estimate": "free/probe",
            "status": "success" if has_image else "no_image",
        })
        print(f"OK   {model}: has_image={has_image} ({latency}s)")
        return has_image
    except Exception as e:
        latency = round(time.time() - t0, 2)
        log_call({
            "stage": "smoke_test",
            "provider": "gemini",
            "model": model,
            "latency_seconds": latency,
            "status": "error",
            "error": str(e)[:300],
        })
        print(f"INFO {model} unavailable on this key: {str(e)[:140]}")
        return False


def test_cloudflare():
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not api_token:
        print("SKIP Cloudflare Workers AI (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN not set in .env)")
        return None

    model = "@cf/black-forest-labs/flux-1-schnell"
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    t0 = time.time()
    try:
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_token}", "Content-Type": "application/json"},
            json={"prompt": "Ethiopian highland hills at sunrise, warm golden light", "steps": 4},
            timeout=60,
        )
        latency = round(time.time() - t0, 2)
        ok = resp.status_code == 200
        log_call({
            "stage": "smoke_test",
            "provider": "cloudflare",
            "model": model,
            "parameters": {"steps": 4},
            "seed": None,
            "latency_seconds": latency,
            "status": "success" if ok else f"http_{resp.status_code}",
            "cost_estimate": "free tier",
        })
        print(f"{'OK  ' if ok else 'FAIL'} Cloudflare {model}: HTTP {resp.status_code} ({latency}s)")
        return ok
    except Exception as e:
        latency = round(time.time() - t0, 2)
        log_call({
            "stage": "smoke_test",
            "provider": "cloudflare",
            "model": model,
            "latency_seconds": latency,
            "status": "error",
            "error": str(e)[:200],
        })
        print(f"FAIL Cloudflare: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["all", "cloudflare", "gemini", "local"], default="all")
    args = parser.parse_args()

    print("=== Heritage Short Smoke Test ===")
    if args.provider in ("all", "local"):
        test_ffmpeg()

    if args.provider in ("all", "gemini"):
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            print("FAIL GEMINI_API_KEY missing in .env")
            sys.exit(1)
        client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        test_gemini_text(client)
        test_gemini_tts(client)
        test_gemini_image(client)

    if args.provider in ("all", "cloudflare"):
        test_cloudflare()

    print("=== Smoke Test Complete (logged to runs.jsonl) ===")


if __name__ == "__main__":
    main()
