"""
Stage 5: Final assembly — combines all outputs into the finished 16:9 and 9:16 films.
- Syncs each shot duration with actual narration length (never cuts off speech!)
- Generates crisp Amharic + English end card using Pillow + Ethiopic font (Ebrima/Nyala)
- Concatenates shots cleanly using relative paths (safe on Windows)
- Ducks original ACE-Step score under voice via sidechaincompress
- Normalizes loudness to -14 LUFS / -1 dB true peak
- Burns in readable English subtitles in safe area for both 16:9 and 9:16
- Logs assembly summary to runs.jsonl
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

W_16_9, H_16_9 = 1280, 720
W_9_16, H_9_16 = 720, 1280
FPS = 24


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
        r"C:\Windows\Fonts\georgia.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def create_end_card_image(storyboard, out_png, width=W_16_9, height=H_16_9):
    """Render an elegant end card with Amharic proverb, English translation, and AI disclosure."""
    ec = storyboard.get("end_card", {})
    text_am = ec.get("text_amharic", "አዛውንቶችን አክብር፣ እውነትን ግን አትክድ።")
    text_en = ec.get("text_english", "Respect your elders, but never deny the truth.")
    ai_text = ec.get("ai_disclosure", "This film was made with AI")
    title = f"{storyboard['meta']['title_amharic']}  —  {storyboard['meta']['title']}"

    img = Image.new("RGB", (width, height), (30, 20, 14))
    draw = ImageDraw.Draw(img)

    # Subtle traditional double border
    pad = 28
    draw.rectangle([pad, pad, width - pad, height - pad], outline=(168, 128, 72), width=2)
    draw.rectangle([pad + 8, pad + 8, width - pad - 8, height - pad - 8], outline=(110, 82, 46), width=1)

    font_am = find_ethiopic_font(44 if width > height else 34)
    font_en = find_latin_font(28 if width > height else 23)
    font_title = find_ethiopic_font(22 if width > height else 18)
    font_ai = find_latin_font(20 if width > height else 18)

    cx, cy = width // 2, height // 2
    draw.text((cx, cy - 115), title, font=font_title, fill=(195, 160, 105), anchor="mm")
    draw.text((cx, cy - 30), text_am, font=font_am, fill=(250, 240, 225), anchor="mm")
    draw.text((cx, cy + 40), f'"{text_en}"', font=font_en, fill=(220, 210, 195), anchor="mm")
    draw.text((cx, height - 78), ai_text, font=font_ai, fill=(165, 155, 145), anchor="mm")

    img.save(out_png, format="PNG")
    return out_png


def fmt_srt_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds % 1) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap_subtitle(text, max_chars=40):
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
    # Cap to 2 balanced lines if possible
    if len(lines) > 2:
        half = len(words) // 2
        return " ".join(words[:half]) + "\n" + " ".join(words[half:])
    return "\n".join(lines)


def generate_srt(timeline, srt_path, max_chars=40):
    lines = []
    idx = 1
    for item in timeline:
        en = item["narration_english"].strip()
        if not en or item["is_end_card"]:
            continue
        start = item["start"] + 0.25
        # Keep subtitle on screen through speech + brief readability tail, capped inside shot
        speech_end = start + max(item["narr_dur"], 1.8) + 0.35
        end = min(speech_end, item["start"] + item["duration"] - 0.1)
        lines.append(str(idx))
        lines.append(f"{fmt_srt_time(start)} --> {fmt_srt_time(end)}")
        lines.append(wrap_subtitle(en, max_chars=max_chars))
        lines.append("")
        idx += 1

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return idx - 1


def assemble_film(
    storyboard=None,
    narr_dir=None,
    final_dir=None,
    filename_prefix="film",
    log_stage="assembly",
    log_extra=None,
):
    ffmpeg_bin, _ = ensure_ffmpeg_in_path()
    if not ffmpeg_bin:
        print("FAIL FFmpeg not found.")
        sys.exit(1)

    t0 = time.time()
    if storyboard is None:
        storyboard = load_storyboard()

    shots_dir = os.path.join(PROJECT_ROOT, "outputs", "shots")
    if narr_dir is None:
        narr_dir = os.path.join(PROJECT_ROOT, "outputs", "narration")
    music_dir = os.path.join(PROJECT_ROOT, "outputs", "music")
    if final_dir is None:
        final_dir = os.path.join(PROJECT_ROOT, "outputs", "final")
    tmp_dir = os.path.join(final_dir, "_build_tmp")
    os.makedirs(tmp_dir, exist_ok=True)

    score_path = os.path.join(music_dir, "score.wav")
    if not os.path.exists(score_path):
        # Also check .mp3
        mp3_score = os.path.join(music_dir, "score.mp3")
        if os.path.exists(mp3_score):
            score_path = mp3_score

    has_score = os.path.exists(score_path)
    if not has_score:
        print("WARN No outputs/music/score.wav found — assembling narration without music score.")

    # Build timeline & per-shot sync-locked mixed clips
    timeline = []
    cursor = 0.0
    mixed_names = []

    def append_end_card_clip(sid_label, planned_dur):
        nonlocal cursor
        ec_dur = float(storyboard.get("end_card", {}).get("duration_seconds", planned_dur))
        ec_img = os.path.join(tmp_dir, "end_card_16x9.png")
        create_end_card_image(storyboard, ec_img, W_16_9, H_16_9)

        ec_clip_name = f"mixed_{sid_label}.mp4"
        cmd = [
            ffmpeg_bin, "-nostdin", "-y",
            "-loop", "1", "-framerate", str(FPS), "-t", str(ec_dur), "-i", "end_card_16x9.png",
            "-f", "lavfi", "-t", str(ec_dur), "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
            "-vf", f"fade=t=in:st=0:d=0.6,fade=t=out:st={max(0.5, ec_dur - 0.8)}:d=0.8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac",
            ec_clip_name,
        ]
        res = subprocess.run(cmd, cwd=tmp_dir, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            print(f"FAIL End card clip failed: {res.stderr[-250:]}")
            sys.exit(1)

        timeline.append({
            "id": sid_label, "start": cursor, "duration": ec_dur,
            "narr_dur": 0.0, "narration_english": "", "is_end_card": True,
        })
        cursor += ec_dur
        mixed_names.append(ec_clip_name)

    has_explicit_end_card = False
    for shot in storyboard["shots"]:
        sid = shot["id"]
        is_ec = bool(shot.get("is_end_card"))
        planned = float(shot["duration_seconds"])
        narr_wav = os.path.join(narr_dir, f"shot_{sid:02d}.wav")

        if is_ec:
            has_explicit_end_card = True
            append_end_card_clip(f"{sid:02d}", planned)
            continue

        video_path = os.path.join(shots_dir, f"shot_{sid:02d}.mp4")
        if not os.path.exists(video_path):
            print(f"FAIL Missing shot video: {video_path}. Run stage 3 first.")
            sys.exit(1)

        has_narr = bool(shot.get("narration_amharic", "").strip()) and os.path.exists(narr_wav)
        narr_dur = get_audio_duration(narr_wav) if has_narr else 0.0
        eff_dur = max(planned, round(narr_dur + 0.8, 2))
        vid_dur = get_video_duration(video_path)
        pad_dur = max(0.0, round(eff_dur - vid_dur, 2))

        vf_parts = [f"scale={W_16_9}:{H_16_9}:force_original_aspect_ratio=decrease,pad={W_16_9}:{H_16_9}:-1:-1:color=black,fps={FPS},setsar=1"]
        if pad_dur > 0.05:
            vf_parts.append(f"tpad=stop_mode=clone:stop_duration={pad_dur}")
        if shot.get("transition") == "fade_to_black":
            vf_parts.append(f"fade=t=out:st={max(0.5, eff_dur - 0.7)}:d=0.7")
        vf = ",".join(vf_parts)

        mixed_name = f"mixed_{sid:02d}.mp4"
        if has_narr and narr_dur > 0:
            # 0.25s lead-in, pad silence and trim to exact eff_dur
            cmd = [
                ffmpeg_bin, "-nostdin", "-y",
                "-i", os.path.abspath(video_path),
                "-i", os.path.abspath(narr_wav),
                "-filter_complex",
                f"[0:v]{vf}[v];"
                f"[1:a]adelay=250|250,apad,atrim=0:{eff_dur},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono[a]",
                "-map", "[v]", "-map", "[a]",
                "-t", str(eff_dur),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-c:a", "aac",
                mixed_name,
            ]
        else:
            cmd = [
                ffmpeg_bin, "-nostdin", "-y",
                "-i", os.path.abspath(video_path),
                "-f", "lavfi", "-t", str(eff_dur), "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
                "-filter_complex", f"[0:v]{vf}[v]",
                "-map", "[v]", "-map", "1:a",
                "-t", str(eff_dur),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-c:a", "aac",
                mixed_name,
            ]

        res = subprocess.run(cmd, cwd=tmp_dir, capture_output=True, text=True, timeout=120)
        if res.returncode != 0:
            print(f"FAIL Shot {sid:02d} mix failed: {res.stderr[-250:]}")
            sys.exit(1)

        timeline.append({
            "id": sid, "start": cursor, "duration": eff_dur,
            "narr_dur": narr_dur, "narration_english": shot["narration_english"],
            "is_end_card": False,
        })
        cursor += eff_dur
        mixed_names.append(mixed_name)

    if not has_explicit_end_card and storyboard.get("end_card"):
        append_end_card_clip("endcard", 5.0)

    total_duration = cursor
    print(f"  Timeline built: {len(mixed_names)} clips, {total_duration:.2f}s total")

    # Subtitles (16:9 and tighter 9:16 wrap)
    srt_16_9 = os.path.join(tmp_dir, "subtitles_16x9.srt")
    srt_9_16 = os.path.join(tmp_dir, "subtitles_9x16.srt")
    n_subs = generate_srt(timeline, srt_16_9, max_chars=42)
    generate_srt(timeline, srt_9_16, max_chars=34)
    # Also save copy in final_dir for inspection
    generate_srt(timeline, os.path.join(final_dir, "subtitles.srt"), max_chars=42)
    print(f"  Generated {n_subs} synchronized English subtitles")

    # Concatenate clips using relative paths
    concat_txt = os.path.join(tmp_dir, "concat_list.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for name in mixed_names:
            f.write(f"file '{name}'\n")

    res = subprocess.run(
        [ffmpeg_bin, "-nostdin", "-y", "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", "concat_raw.mp4"],
        cwd=tmp_dir, capture_output=True, text=True, timeout=180,
    )
    if res.returncode != 0:
        print(f"FAIL Concat failed: {res.stderr[-250:]}")
        sys.exit(1)

    # Mix score with sidechain ducking + normalize to -14 LUFS
    master_av = "master_av.mp4"
    if has_score:
        print("  Mixing score with sidechain ducking and -14 LUFS loudness normalization...")
        fade_out_start = max(1.0, total_duration - 2.5)
        fc = (
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,loudnorm=I=-16:TP=-1.5[voice];"
            f"[1:a]aloop=loop=-1:size=2e+09,atrim=0:{total_duration},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=mono,"
            f"volume=0.28,afade=t=in:st=0:d=1.2,afade=t=out:st={fade_out_start}:d=2.4[music];"
            f"[music][voice]sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500[ducked_music];"
            f"[voice][ducked_music]amix=inputs=2:duration=first:normalize=0,"
            f"loudnorm=I=-14:TP=-1:LRA=11[aout]"
        )
        res = subprocess.run(
            [
                ffmpeg_bin, "-nostdin", "-y",
                "-i", "concat_raw.mp4",
                "-i", os.path.abspath(score_path),
                "-filter_complex", fc,
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac",
                master_av,
            ],
            cwd=tmp_dir, capture_output=True, text=True, timeout=300,
        )
        if res.returncode != 0:
            print(f"FAIL Audio duck/mix failed: {res.stderr[-300:]}")
            sys.exit(1)
    else:
        print("  Normalizing narration loudness to -14 LUFS...")
        res = subprocess.run(
            [
                ffmpeg_bin, "-nostdin", "-y", "-i", "concat_raw.mp4",
                "-af", "loudnorm=I=-14:TP=-1:LRA=11",
                "-c:v", "copy", "-c:a", "aac",
                master_av,
            ],
            cwd=tmp_dir, capture_output=True, text=True, timeout=300,
        )
        if res.returncode != 0:
            print(f"FAIL Loudnorm failed: {res.stderr[-250:]}")
            sys.exit(1)

    # Export 16:9 with burned-in subtitles (relative subtitle path avoids Windows C: drive escaping bugs)
    out_16_9 = os.path.join(final_dir, f"{filename_prefix}_16x9.mp4")
    print("  Exporting 16:9 MP4 with burned-in subtitles...")
    res = subprocess.run(
        [
            ffmpeg_bin, "-nostdin", "-y", "-i", master_av,
            "-vf", "subtitles=subtitles_16x9.srt:force_style='FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BackColour=&H64000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=28'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart",
            os.path.abspath(out_16_9),
        ],
        cwd=tmp_dir, capture_output=True, text=True, timeout=300,
    )
    if res.returncode != 0:
        print(f"FAIL 16:9 export failed: {res.stderr[-300:]}")
        sys.exit(1)

    # Export 9:16 vertical: crop center 9:16 from 16:9 body, replace end card with clean vertical end card!
    # Generating dedicated 9:16 end card so text never crops off edges
    ec_9_16_png = os.path.join(tmp_dir, "end_card_9x16.png")
    create_end_card_image(storyboard, ec_9_16_png, W_9_16, H_9_16)
    ec_start = timeline[-1]["start"] if timeline[-1]["is_end_card"] else total_duration

    out_9_16 = os.path.join(final_dir, f"{filename_prefix}_9x16.mp4")
    print("  Exporting 9:16 vertical MP4 with safe-area subtitles & fitted vertical end card...")
    ec_dur = timeline[-1]["duration"]
    vf_9_16 = (
        f"[0:v]trim=0:{ec_start},setpts=PTS-STARTPTS,"
        f"crop=ih*9/16:ih,scale={W_9_16}:{H_9_16}:flags=lanczos,setsar=1,"
        f"subtitles=subtitles_9x16.srt:force_style='FontName=Arial,FontSize=9,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=1.5,Shadow=1,MarginL=20,MarginR=20,MarginV=42'[body];"
        f"[1:v]scale={W_9_16}:{H_9_16},setsar=1,fade=t=in:st=0:d=0.6,fade=t=out:st={max(0.5, ec_dur - 0.8)}:d=0.8[ec];"
        f"[body][ec]concat=n=2:v=1:a=0[vout]"
    )
    res = subprocess.run(
        [
            ffmpeg_bin, "-nostdin", "-y",
            "-i", master_av,
            "-loop", "1", "-framerate", str(FPS), "-t", str(ec_dur), "-i", "end_card_9x16.png",
            "-filter_complex", vf_9_16,
            "-map", "[vout]", "-map", "0:a",
            "-t", str(total_duration),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "copy", "-movflags", "+faststart",
            os.path.abspath(out_9_16),
        ],
        cwd=tmp_dir, capture_output=True, text=True, timeout=300,
    )
    if res.returncode != 0:
        print(f"FAIL 9:16 export failed: {res.stderr[-300:]}")
        sys.exit(1)

    latency = round(time.time() - t0, 2)
    dur_16 = get_video_duration(out_16_9)
    dur_9 = get_video_duration(out_9_16)

    rel_dir = os.path.relpath(final_dir, PROJECT_ROOT).replace("\\", "/")
    log_payload = {
        "stage": log_stage,
        "provider": "local",
        "model": "ffmpeg",
        "parameters": {
            "has_score": has_score,
            "num_shots": len(storyboard["shots"]),
            "loudnorm": "-14 LUFS / -1 TP",
            "ducking": "threshold=0.02,ratio=6,attack=300,release=1500" if has_score else "none",
        },
        "seed": None,
        "output_16x9": f"{rel_dir}/{filename_prefix}_16x9.mp4",
        "output_9x16": f"{rel_dir}/{filename_prefix}_9x16.mp4",
        "duration_16x9": round(dur_16, 2),
        "duration_9x16": round(dur_9, 2),
        "latency_seconds": latency,
        "cost_estimate": "free (local FFmpeg)",
        "status": "success",
    }
    if log_extra:
        log_payload.update(log_extra)
    log_call(log_payload)

    print("=" * 60)
    print("OK   Assembly complete!")
    print(f"     16:9 -> {out_16_9} ({dur_16:.1f}s, {os.path.getsize(out_16_9)/1024/1024:.2f} MB)")
    print(f"     9:16 -> {out_9_16} ({dur_9:.1f}s, {os.path.getsize(out_9_16)/1024/1024:.2f} MB)")


if __name__ == "__main__":
    print("Stage 5: Assembling final 16:9 and 9:16 films...")
    print("=" * 60)
    assemble_film()
