"""
Stage 1b (Phase 1 Checkpoint): Assemble the Radio Cut.
Builds an audio-first prototype (outputs/final/radio_cut.mp4):
- Black screen with shot label, Amharic narration text, and English subtitle
- Gemini TTS narration per shot + gentle low ambient placeholder tone
- Prints exact timing comparison (planned shot duration vs measured TTS duration)
"""

import os
import subprocess
import sys
import time
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.utils import (
    ensure_ffmpeg_in_path,
    get_audio_duration,
    get_video_duration,
    load_storyboard,
    log_call,
)


def find_ethiopic_font(size):
    candidates = [
        r"C:\Windows\Fonts\ebrima.ttf",
        r"C:\Windows\Fonts\nyala.ttf",
        "/usr/share/fonts/truetype/abyssinica/AbyssinicaSIL-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def find_latin_font(size):
    candidates = [
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap_text(text, max_chars=48):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def render_radio_card(shot, out_png, end_card_cfg=None):
    w, h = 1280, 720
    img = Image.new("RGB", (w, h), (16, 14, 12))
    draw = ImageDraw.Draw(img)

    font_meta = find_latin_font(22)
    font_am = find_ethiopic_font(34)
    font_en = find_latin_font(26)

    if shot.get("is_end_card") and end_card_cfg:
        am_text = end_card_cfg.get("text_amharic", "")
        en_text = end_card_cfg.get("text_english", "")
        ai_text = end_card_cfg.get("ai_disclosure", "This film was made with AI")
        draw.multiline_text((w // 2, h // 2 - 70), am_text, font=font_am, fill=(245, 225, 190), anchor="mm", align="center")
        draw.multiline_text((w // 2, h // 2 + 10), en_text, font=font_en, fill=(215, 215, 215), anchor="mm", align="center")
        draw.text((w // 2, h // 2 + 95), ai_text, font=font_meta, fill=(140, 140, 140), anchor="mm")
    else:
        header = f"RADIO CUT  |  Shot {shot['id']:02d}: {shot['scene']}  ({shot['shot_type']})"
        draw.text((60, 48), header, font=font_meta, fill=(180, 150, 105))

        am_wrapped = wrap_text(shot["narration_amharic"], 42)
        en_wrapped = wrap_text(shot["narration_english"], 54)
        draw.multiline_text((w // 2, h // 2 - 40), am_wrapped, font=font_am, fill=(245, 240, 230), anchor="mm", align="center", spacing=10)
        draw.multiline_text((w // 2, h - 130), en_wrapped, font=font_en, fill=(195, 195, 195), anchor="mm", align="center", spacing=8)

    img.save(out_png)


def build_radio_cut():
    ffmpeg_bin, _ = ensure_ffmpeg_in_path()
    if not ffmpeg_bin:
        print("FAIL FFmpeg not found.")
        sys.exit(1)

    storyboard = load_storyboard()
    narr_dir = os.path.join(PROJECT_ROOT, "outputs", "narration")
    final_dir = os.path.join(PROJECT_ROOT, "outputs", "final")
    tmp_dir = os.path.join(final_dir, "_radio_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    t0 = time.time()
    total_planned = 0.0
    total_effective = 0.0
    clip_names = []

    print("\nTiming Analysis (Planned vs Measured TTS):")
    print(f"{'Shot':<6} {'Scene':<20} {'Planned':>8} {'TTS Dur':>8} {'Effective':>10}")
    print("-" * 58)

    for shot in storyboard["shots"]:
        sid = shot["id"]
        planned = float(shot["duration_seconds"])
        narr_wav = os.path.join(narr_dir, f"shot_{sid:02d}.wav")

        if shot.get("is_end_card"):
            narr_dur = 0.0
            effective = float(storyboard.get("end_card", {}).get("duration_seconds", planned))
        elif not shot["narration_amharic"].strip():
            narr_dur = 0.0
            effective = planned
        elif os.path.exists(narr_wav):
            narr_dur = get_audio_duration(narr_wav)
            effective = max(planned, round(narr_dur + 0.8, 2))
        else:
            print(f"FAIL Missing narration WAV for shot {sid}: {narr_wav}")
            sys.exit(1)

        total_planned += planned
        total_effective += effective
        print(f"{sid:<6} {shot['scene'][:19]:<20} {planned:>7.1f}s {narr_dur:>7.2f}s {effective:>9.2f}s")

        card_png = os.path.join(tmp_dir, f"card_{sid:02d}.png")
        render_radio_card(shot, card_png, storyboard.get("end_card"))

        clip_name = f"radio_{sid:02d}.mp4"
        clip_path = os.path.join(tmp_dir, clip_name)

        if os.path.exists(narr_wav) and not shot.get("is_end_card"):
            # Delay voice by 0.25s, pad tail cleanly and trim to exact duration
            cmd = [
                ffmpeg_bin, "-nostdin", "-y",
                "-loop", "1", "-framerate", "24", "-t", str(effective), "-i", f"card_{sid:02d}.png",
                "-i", os.path.abspath(narr_wav),
                "-filter_complex",
                f"[1:a]adelay=250|250,apad,atrim=0:{effective},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[a]",
                "-map", "0:v", "-map", "[a]",
                "-shortest",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                clip_name,
            ]
        else:
            cmd = [
                ffmpeg_bin, "-nostdin", "-y",
                "-loop", "1", "-framerate", "24", "-t", str(effective), "-i", f"card_{sid:02d}.png",
                "-f", "lavfi", "-t", str(effective), "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                clip_name,
            ]

        res = subprocess.run(cmd, cwd=tmp_dir, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            print(f"FAIL Shot {sid} radio render error: {res.stderr[-300:]}")
            sys.exit(1)
        clip_names.append(clip_name)

    print("-" * 58)
    print(f"{'TOTAL':<27} {total_planned:>7.1f}s {'':>8} {total_effective:>9.2f}s")

    concat_txt = os.path.join(tmp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for cn in clip_names:
            f.write(f"file '{cn}'\n")

    raw_radio = os.path.join(tmp_dir, "radio_raw.mp4")
    res = subprocess.run(
        [
            ffmpeg_bin, "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", "concat.txt",
            "-c", "copy", "radio_raw.mp4",
        ],
        cwd=tmp_dir, capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        print(f"FAIL Concat failed: {res.stderr[-300:]}")
        sys.exit(1)

    # Mix subtle warm placeholder pad (soft sine A-minor chord at -28dB) + normalize
    out_radio = os.path.join(final_dir, "radio_cut.mp4")
    res = subprocess.run(
        [
            ffmpeg_bin, "-nostdin", "-y",
            "-i", raw_radio,
            "-f", "lavfi", "-i", f"aevalsrc=0.015*(sin(2*PI*220*t)+0.6*sin(2*PI*261.63*t)+0.5*sin(2*PI*329.63*t)):s=48000:d={total_effective}",
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:weights=1 0.25,loudnorm=I=-16:TP=-1:LRA=11[aout]",
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", "aac",
            "-movflags", "+faststart",
            out_radio,
        ],
        cwd=tmp_dir, capture_output=True, text=True, timeout=120,
    )
    if res.returncode != 0:
        print(f"FAIL Final radio mix failed: {res.stderr[-300:]}")
        sys.exit(1)

    latency = round(time.time() - t0, 2)
    final_dur = get_video_duration(out_radio)
    log_call({
        "stage": "radio_cut",
        "provider": "local",
        "model": "ffmpeg",
        "parameters": {"total_effective_seconds": round(total_effective, 2)},
        "seed": None,
        "output_file": "outputs/final/radio_cut.mp4",
        "duration_seconds": round(final_dur, 2),
        "latency_seconds": latency,
        "cost_estimate": "free (local FFmpeg)",
        "status": "success",
    })
    print(f"\nOK   Radio cut ready: {out_radio} ({final_dur:.1f}s, built in {latency}s)")


if __name__ == "__main__":
    print("Stage 1b: Building Radio Cut prototype...")
    build_radio_cut()
