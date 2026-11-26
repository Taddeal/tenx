"""
Stage 2: Generate character reference sheet and shot keyframes via Cloudflare Workers AI.
1. Generates outputs/references/character_sheet.png first (if not cached).
2. Generates each non-end-card shot keyframe conditioned on the character sheet
   using @cf/black-forest-labs/flux-2-klein-4b (multipart/form-data, Apache 2.0),
   with fallback to @cf/black-forest-labs/flux-1-schnell if needed.
3. Caches by content hash (prompt + style + characters + seed + ref hash) and
   logs every call (model, parameters, seed, latency, cost) to runs.jsonl.
"""

import base64
import io
import os
import sys
import time
import requests
from PIL import Image

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

from pipeline.utils import (
    inject_windows_certs,
    load_cache,
    load_storyboard,
    log_call,
    save_cache,
    stable_hash,
)

inject_windows_certs()

FLUX2_KLEIN_MODEL = "@cf/black-forest-labs/flux-2-klein-4b"
FLUX1_SCHNELL_MODEL = "@cf/black-forest-labs/flux-1-schnell"
TARGET_W = 1280
TARGET_H = 720


def decode_cf_image_response(resp):
    """Extract raw image bytes from Cloudflare Workers AI response (JSON base64 or binary)."""
    content_type = resp.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        data = resp.json()
        b64 = data.get("result", {}).get("image") or data.get("image")
        if not b64:
            raise RuntimeError(f"Missing base64 image in JSON response: {str(data)[:200]}")
        return base64.b64decode(b64)
    return resp.content


def save_normalized_png(raw_bytes, out_path, target_w=TARGET_W, target_h=TARGET_H):
    """Save image bytes as PNG, center-cropping/resizing to target 16:9 dimensions if needed."""
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    if img.size != (target_w, target_h):
        # Center crop to 16:9 preserving center subject, then resize
        src_w, src_h = img.size
        target_ratio = target_w / target_h
        src_ratio = src_w / src_h
        if src_ratio > target_ratio:
            new_w = int(src_h * target_ratio)
            left = (src_w - new_w) // 2
            img = img.crop((left, 0, left + new_w, src_h))
        elif src_ratio < target_ratio:
            new_h = int(src_w / target_ratio)
            top = (src_h - new_h) // 2
            img = img.crop((0, top, src_w, top + new_h))
        img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    img.save(out_path, format="PNG")


def call_flux2_klein(account_id, api_token, prompt, seed, width, height, ref_image_path=None):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{FLUX2_KLEIN_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "User-Agent": "HeritageShortPipeline/1.0",
    }

    data = {
        "prompt": prompt[:2048],
        "width": str(width),
        "height": str(height),
        "seed": str(seed),
    }

    if ref_image_path and os.path.exists(ref_image_path):
        # Cloudflare FLUX.2 klein requires input_image_0 <= 512x512 px
        ref_img = Image.open(ref_image_path).convert("RGB")
        ref_img.thumbnail((480, 480), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        ref_img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        files = {"input_image_0": ("ref.jpg", buf, "image/jpeg")}
        resp = requests.post(url, headers=headers, data=data, files=files, timeout=90)
    else:
        multipart_fields = {k: (None, v) for k, v in data.items()}
        resp = requests.post(url, headers=headers, files=multipart_fields, timeout=90)

    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")
    return decode_cf_image_response(resp), FLUX2_KLEIN_MODEL


def call_flux1_schnell(account_id, api_token, prompt, steps=4):
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{FLUX1_SCHNELL_MODEL}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt[:2048],
        "steps": steps,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:250]}")
    return decode_cf_image_response(resp), FLUX1_SCHNELL_MODEL


def generate_with_fallback(account_id, api_token, prompt, seed, ref_path, stage_label, shot_id=None, out_path=None, ref_enabled=True):
    """Try FLUX.2 klein (with reference if enabled, seed, and seed+100 on false-positive flag), then FLUX.1 schnell."""
    attempts = []
    if ref_enabled and ref_path and os.path.exists(ref_path):
        attempts.append(("flux2-ref", lambda: call_flux2_klein(account_id, api_token, prompt, seed, TARGET_W, TARGET_H, ref_path)))
        attempts.append(("flux2-ref-altseed", lambda: call_flux2_klein(account_id, api_token, prompt, seed + 100, TARGET_W, TARGET_H, ref_path)))
    attempts.append(("flux2-txt", lambda: call_flux2_klein(account_id, api_token, prompt, seed, TARGET_W, TARGET_H, None)))
    attempts.append(("flux2-txt-altseed", lambda: call_flux2_klein(account_id, api_token, prompt, seed + 100, TARGET_W, TARGET_H, None)))
    attempts.append(("flux1-schnell", lambda: call_flux1_schnell(account_id, api_token, prompt, steps=4)))

    last_err = None
    ref_waf_blocked = False
    for mode_name, fn in attempts:
        t0 = time.time()
        try:
            raw_bytes, model_used = fn()
            latency = round(time.time() - t0, 2)
            save_normalized_png(raw_bytes, out_path, TARGET_W, TARGET_H)
            file_size = os.path.getsize(out_path)
            log_call({
                "stage": stage_label,
                "provider": "cloudflare",
                "model": model_used,
                "shot_id": shot_id,
                "parameters": {
                    "mode": mode_name,
                    "width": TARGET_W,
                    "height": TARGET_H,
                    "steps": 4,
                    "referenced_sheet": bool(mode_name.startswith("flux2-ref")),
                },
                "seed": seed,
                "prompt": prompt[:220],
                "output_file": os.path.relpath(out_path, PROJECT_ROOT).replace("\\", "/"),
                "output_bytes": file_size,
                "latency_seconds": latency,
                "cost_estimate": "free tier (Cloudflare Workers AI)",
                "status": "success",
            })
            return model_used, mode_name, latency, file_size, ref_waf_blocked
        except Exception as e:
            latency = round(time.time() - t0, 2)
            last_err = e
            if mode_name == "flux2-ref" and "HTTP 403" in str(e):
                ref_waf_blocked = True
            log_call({
                "stage": stage_label,
                "provider": "cloudflare",
                "model": FLUX2_KLEIN_MODEL if "flux2" in mode_name else FLUX1_SCHNELL_MODEL,
                "shot_id": shot_id,
                "parameters": {"mode": mode_name},
                "seed": seed,
                "latency_seconds": latency,
                "cost_estimate": "free tier",
                "status": "error",
                "error": str(e)[:250],
            })
            if "getaddrinfo" in str(e) or "NameResolutionError" in str(e):
                raise RuntimeError(f"Offline/DNS error (cannot reach Cloudflare API): {e}")
            time.sleep(1)
    raise RuntimeError(f"All Cloudflare image attempts failed: {last_err}")


def generate_keyframes():
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()

    if not account_id or not api_token:
        print("FAIL CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_API_TOKEN not set in .env")
        print("     1. Open https://dash.cloudflare.com -> AI -> Workers AI -> Use REST API")
        print("     2. Copy Account ID & create a Workers AI API Token")
        print("     3. Paste both into .env and re-run.")
        sys.exit(1)

    storyboard = load_storyboard()
    style_cfg = storyboard["style"]
    style_block = style_cfg["block"]

    ref_dir = os.path.join(PROJECT_ROOT, "outputs", "references")
    kf_dir = os.path.join(PROJECT_ROOT, "outputs", "keyframes")
    os.makedirs(ref_dir, exist_ok=True)
    os.makedirs(kf_dir, exist_ok=True)

    ref_cache_path = os.path.join(ref_dir, ".cache.json")
    ref_cache = load_cache(ref_cache_path)

    # Step 1: Character & style reference sheet
    ref_prompt = style_cfg.get("reference_sheet_prompt") or (
        "Character sheet showing: "
        + "; ".join(f"{c['name']}: {c['description']}" for c in storyboard["characters"])
        + f". Style: {style_block}"
    )
    ref_seed = int(style_cfg.get("reference_seed", 2026))
    ref_hash = stable_hash(ref_prompt, style_block, ref_seed)
    ref_path = os.path.join(ref_dir, "character_sheet.png")

    if ref_cache.get("character_sheet") == ref_hash and os.path.exists(ref_path):
        print("  Reference Sheet: Cached (unchanged). Skipping.")
    else:
        print("  Reference Sheet: Generating character & style reference sheet...")
        model_used, mode_name, latency, size, _ = generate_with_fallback(
            account_id, api_token, ref_prompt, ref_seed, None,
            stage_label="reference_sheet", shot_id=None, out_path=ref_path,
        )
        ref_cache["character_sheet"] = ref_hash
        save_cache(ref_cache_path, ref_cache)
        print(f"    OK   {model_used} ({mode_name}) in {latency}s ({size / 1024:.1f} KB)")
        time.sleep(1.5)

    # Step 2: Keyframes per shot
    kf_cache_path = os.path.join(kf_dir, ".cache.json")
    kf_cache = load_cache(kf_cache_path)
    char_map = {c["id"]: c for c in storyboard["characters"]}

    generated = 0
    cached = 0
    failed = 0
    # Default to text-to-image (flux2-txt) for scene keyframes: FLUX.2 klein's input_image_0
    # treats the multi-character lineup sheet as a spatial edit canvas and bleeds extra figures into shots.
    ref_enabled = os.environ.get("CF_ENABLE_IMAGE_REF", "0") == "1"

    for shot in storyboard["shots"]:
        sid = shot["id"]
        if shot.get("is_end_card"):
            print(f"  Shot {sid:02d}: End card rendered in assembly. Skipping keyframe.")
            continue

        chars_in_shot = shot.get("characters_in_shot", [])
        ref_shot_id = shot.get("reference_shot_id")
        ref_shot_path = os.path.join(kf_dir, f"shot_{int(ref_shot_id):02d}.png") if ref_shot_id else None
        use_golden_ref = bool(ref_shot_path and os.path.exists(ref_shot_path))

        full_prompt = shot["image_prompt"]
        if use_golden_ref:
            full_prompt += ". Style: " + style_block
            use_ref = ref_shot_path
            with open(ref_shot_path, "rb") as rf:
                import hashlib
                ref_token = f"shot_{int(ref_shot_id):02d}_" + hashlib.sha256(rf.read()).hexdigest()[:12]
            shot_ref_enabled = True
        else:
            char_descs = [
                f"{char_map[cid]['name']} ({char_map[cid]['description']})"
                for cid in chars_in_shot if cid in char_map
            ]
            if char_descs:
                full_prompt += ". Characters matching reference sheet: " + "; ".join(char_descs)
            full_prompt += f". Style: {style_block}"
            use_ref = ref_path if (chars_in_shot and ref_enabled) else None
            ref_token = ref_hash if use_ref else "txt_mode"
            shot_ref_enabled = ref_enabled

        seed = int(shot.get("seed", 1000 + sid))
        p_hash = stable_hash(full_prompt, seed, ref_token)
        out_path = os.path.join(kf_dir, f"shot_{sid:02d}.png")
        cache_key = f"shot_{sid}"

        if kf_cache.get(cache_key) == p_hash and os.path.exists(out_path):
            print(f"  Shot {sid:02d}: Cached (unchanged). Skipping.")
            cached += 1
            continue

        print(f"  Shot {sid:02d}: Generating keyframe (seed={seed}, ref={bool(use_ref and shot_ref_enabled)})...")
        try:
            model_used, mode_name, latency, size, ref_waf_blocked = generate_with_fallback(
                account_id, api_token, full_prompt, seed, use_ref,
                stage_label="keyframes", shot_id=sid, out_path=out_path, ref_enabled=shot_ref_enabled,
            )
            if ref_waf_blocked and not use_golden_ref:
                ref_enabled = False
            kf_cache[cache_key] = p_hash
            save_cache(kf_cache_path, kf_cache)
            print(f"    OK   {model_used} ({mode_name}) in {latency}s ({size / 1024:.1f} KB)")
            generated += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"    FAIL Shot {sid:02d}: {e}")
            failed += 1

    print(f"\nKeyframes summary: {generated} generated, {cached} cached, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    print("Stage 2: Generating reference sheet & keyframes (Cloudflare FLUX)...")
    print("=" * 60)
    generate_keyframes()
    print("=" * 60)
    print("Stage 2 complete.")
