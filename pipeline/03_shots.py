"""
Stage 3: Generate moving shots from keyframes.
- If a Wan 2.2 clip exists at outputs/shots/wan/shot_NN.mp4 (downloaded from Kaggle)
  AND matches the current keyframe hash (or is newer), copy/use it and preserve it.
- Otherwise generate smooth, upscaled Ken Burns (pan-and-zoom) motion via FFmpeg.
- Syncs shot clip duration to at least max(planned, narration_duration + 0.8s) so
  narration is never truncated in assembly.
- Logs every shot generation call to runs.jsonl.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.utils import (
    ensure_ffmpeg_in_path,
    get_audio_duration,
    get_video_duration,
    load_cache,
    load_storyboard,
    log_call,
    save_cache,
    stable_hash,
)

OUT_W = 1280
OUT_H = 720
FPS = 24


def camera_to_direction(camera_desc):
    camera = (camera_desc or "").lower()
    if "pull" in camera or "back" in camera:
        return "pull_out"
    if "pan" in camera and "left" in camera:
        return "pan_left"
    if "pan" in camera and "right" in camera:
        return "pan_right"
    if "pan" in camera and "up" in camera:
        return "pan_up"
    if "pan" in camera and "down" in camera:
        return "pan_down"
    if "orbit" in camera:
        return "pan_right"
    return "push_in"


def build_ken_burns_filter(duration_seconds, direction):
    """
    Upscale 3x before zoompan to eliminate FFmpeg's integer-rounding shimmer,
    then scale cleanly back to 1280x720.
    """
    total_frames = max(24, int(round(duration_seconds * FPS)))
    up_w = OUT_W * 3  # 3840x2160 intermediate eliminates 1px jitter

    if direction == "push_in":
        zp = f"zoompan=z='1.0+0.15*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    elif direction == "pull_out":
        zp = f"zoompan=z='1.15-0.15*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    elif direction == "pan_left":
        zp = f"zoompan=z='1.14':x='(iw-iw/zoom)*(1-on/{total_frames})':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    elif direction == "pan_right":
        zp = f"zoompan=z='1.14':x='(iw-iw/zoom)*(on/{total_frames})':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    elif direction == "pan_up":
        zp = f"zoompan=z='1.14':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-on/{total_frames})':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    elif direction == "pan_down":
        zp = f"zoompan=z='1.14':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(on/{total_frames})':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"
    else:
        zp = f"zoompan=z='1.0+0.10*on/{total_frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s={OUT_W}x{OUT_H}:fps={FPS}"

    return f"scale={up_w}:-2:flags=lanczos,{zp},setsar=1"


def effective_shot_duration(shot, narr_dir):
    planned = float(shot["duration_seconds"])
    if not shot.get("narration_amharic", "").strip():
        return planned
    narr_wav = os.path.join(narr_dir, f"shot_{shot['id']:02d}.wav")
    if os.path.exists(narr_wav):
        narr_dur = get_audio_duration(narr_wav)
        return max(planned, round(narr_dur + 0.8, 2))
    return planned


def generate_shots(force_ken_burns=False):
    ffmpeg_bin, _ = ensure_ffmpeg_in_path()
    if not ffmpeg_bin:
        print("FAIL FFmpeg not found.")
        sys.exit(1)

    storyboard = load_storyboard()
    kf_dir = os.path.join(PROJECT_ROOT, "outputs", "keyframes")
    narr_dir = os.path.join(PROJECT_ROOT, "outputs", "narration")
    shots_dir = os.path.join(PROJECT_ROOT, "outputs", "shots")
    wan_dir = os.path.join(shots_dir, "wan")
    os.makedirs(shots_dir, exist_ok=True)
    os.makedirs(wan_dir, exist_ok=True)

    cache_path = os.path.join(shots_dir, ".cache.json")
    cache = load_cache(cache_path)

    generated = 0
    cached = 0
    wan_used = 0
    failed = 0

    for shot in storyboard["shots"]:
        sid = shot["id"]
        if shot.get("is_end_card"):
            print(f"  Shot {sid:02d}: End card handled in assembly. Skipping.")
            continue

        kf_path = os.path.join(kf_dir, f"shot_{sid:02d}.png")
        wan_path = os.path.join(wan_dir, f"shot_{sid:02d}.mp4")
        out_path = os.path.join(shots_dir, f"shot_{sid:02d}.mp4")
        cache_key = f"shot_{sid}"

        if not os.path.exists(kf_path):
            print(f"  FAIL Shot {sid:02d}: Missing keyframe {kf_path}")
            failed += 1
            continue

        duration = effective_shot_duration(shot, narr_dir)
        direction = camera_to_direction(shot.get("camera", "push_in"))
        kf_mtime_size = f"{os.path.getsize(kf_path)}_{int(os.path.getmtime(kf_path))}"

        # Prefer Wan 2.2 AI clip if present in outputs/shots/wan/ and not forcing Ken Burns
        if os.path.exists(wan_path) and not force_ken_burns:
            wan_hash = stable_hash("wan2.2", kf_mtime_size, os.path.getsize(wan_path), duration)
            if cache.get(cache_key) == wan_hash and os.path.exists(out_path):
                print(f"  Shot {sid:02d}: Cached Wan 2.2 clip ({duration}s). Skipping.")
                cached += 1
                continue

            print(f"  Shot {sid:02d}: Importing Wan 2.2 clip (extending/normalizing to {duration}s)...")
            t0 = time.time()
            wan_dur = get_video_duration(wan_path)
            pad_dur = max(0.0, round(duration - wan_dur, 2))
            vf = f"scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},fps={FPS},setsar=1"
            if pad_dur > 0.05:
                vf += f",tpad=stop_mode=clone:stop_duration={pad_dur}"

            cmd = [
                ffmpeg_bin, "-y", "-i", wan_path,
                "-vf", vf, "-t", str(duration),
                "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                out_path,
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            latency = round(time.time() - t0, 2)
            if res.returncode == 0:
                cache[cache_key] = wan_hash
                save_cache(cache_path, cache)
                log_call({
                    "stage": "shots",
                    "provider": "kaggle+ffmpeg",
                    "model": "wan2.2-ti2v-5b",
                    "shot_id": sid,
                    "parameters": {"source": "wan2.2", "duration_seconds": duration},
                    "seed": shot.get("seed"),
                    "output_file": f"outputs/shots/shot_{sid:02d}.mp4",
                    "output_bytes": os.path.getsize(out_path),
                    "latency_seconds": latency,
                    "cost_estimate": "free (Kaggle GPU + local normalize)",
                    "status": "success",
                })
                print(f"    OK   Wan 2.2 clip normalized ({latency}s)")
                wan_used += 1
                continue
            else:
                print(f"    WARN Wan 2.2 normalize failed, falling back to Ken Burns: {res.stderr[-180:]}")

        # Ken Burns fallback / default
        kb_hash = stable_hash("ken_burns", kf_mtime_size, duration, direction)
        if cache.get(cache_key) == kb_hash and os.path.exists(out_path):
            print(f"  Shot {sid:02d}: Cached Ken Burns ({direction}, {duration}s). Skipping.")
            cached += 1
            continue

        print(f"  Shot {sid:02d}: Generating smooth Ken Burns ({direction}, {duration}s)...")
        vf = build_ken_burns_filter(duration, direction)
        t0 = time.time()
        cmd = [
            ffmpeg_bin, "-nostdin", "-y",
            "-loop", "1", "-framerate", str(FPS), "-t", str(duration), "-i", kf_path,
            "-vf", vf,
            "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-r", str(FPS),
            out_path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        latency = round(time.time() - t0, 2)
        if res.returncode == 0 and os.path.exists(out_path):
            file_size = os.path.getsize(out_path)
            cache[cache_key] = kb_hash
            save_cache(cache_path, cache)
            log_call({
                "stage": "shots",
                "provider": "local",
                "model": "ffmpeg-ken-burns",
                "shot_id": sid,
                "parameters": {"direction": direction, "duration_seconds": duration, "resolution": f"{OUT_W}x{OUT_H}"},
                "seed": shot.get("seed"),
                "output_file": f"outputs/shots/shot_{sid:02d}.mp4",
                "output_bytes": file_size,
                "latency_seconds": latency,
                "cost_estimate": "free (local FFmpeg)",
                "status": "success",
            })
            print(f"    OK   Generated ({latency}s, {file_size / 1024:.1f} KB)")
            generated += 1
        else:
            print(f"    FAIL FFmpeg error: {res.stderr[-250:]}")
            failed += 1

    print(f"\nShots summary: {generated} Ken Burns, {wan_used} Wan 2.2, {cached} cached, {failed} failed")
    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-ken-burns", action="store_true", help="Ignore Wan 2.2 clips and render Ken Burns")
    args = parser.parse_args()
    print("Stage 3: Generating moving shots...")
    print("=" * 60)
    generate_shots(force_ken_burns=args.force_ken_burns)
    print("=" * 60)
    print("Stage 3 complete.")
