"""
Shared utilities for the Heritage Short pipeline:
- Windows SSL truststore injection for requests/urllib3
- Logging to runs.jsonl
- Content hashing for deterministic caching
- FFmpeg / FFprobe discovery on Windows (handles fresh WinGet installs)
- Audio / video duration inspection
"""

import hashlib
import json
import os
import shutil
import subprocess
import time
import wave
import contextlib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def inject_windows_certs():
    """Use OS native certificate store (fixes Windows SSL errors in requests)."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass


def ensure_ffmpeg_in_path():
    """Ensure ffmpeg and ffprobe are on PATH, checking Windows User PATH / WinGet if needed."""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return shutil.which("ffmpeg"), shutil.which("ffprobe")

    candidate_dirs = []
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                user_path, _ = winreg.QueryValueEx(key, "Path")
                for p in user_path.split(";"):
                    if p and os.path.isdir(p):
                        candidate_dirs.append(p)
        except Exception:
            pass

        local_app = os.environ.get("LOCALAPPDATA", "")
        winget_pkg = os.path.join(local_app, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_pkg):
            for entry in os.listdir(winget_pkg):
                if "ffmpeg" in entry.lower():
                    pkg_dir = os.path.join(winget_pkg, entry)
                    for root, _, files in os.walk(pkg_dir):
                        if "ffmpeg.exe" in files:
                            candidate_dirs.append(root)
                            break

        for fallback in [r"C:\ffmpeg\bin", r"C:\ProgramData\chocolatey\bin"]:
            if os.path.isdir(fallback):
                candidate_dirs.append(fallback)

    for d in candidate_dirs:
        if d not in os.environ.get("PATH", ""):
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")

    return shutil.which("ffmpeg"), shutil.which("ffprobe")


def log_call(entry):
    """Append a structured JSON log line to runs.jsonl."""
    log_path = os.path.join(PROJECT_ROOT, "runs.jsonl")
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        **entry,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def stable_hash(*parts):
    """Return a 16-char SHA256 hex digest over arbitrary JSON-serializable parts."""
    serialized = json.dumps(parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


def load_storyboard():
    path = os.path.join(PROJECT_ROOT, "storyboard.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cache(cache_path):
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache_path, cache):
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def get_audio_duration(audio_path):
    """Return duration in seconds of a WAV/audio file."""
    try:
        with contextlib.closing(wave.open(audio_path, "rb")) as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        pass
    _, ffprobe = ensure_ffmpeg_in_path()
    if ffprobe:
        try:
            res = subprocess.run(
                [
                    ffprobe, "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    audio_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            return float(res.stdout.strip())
        except Exception:
            pass
    return 0.0


def get_video_duration(video_path):
    """Return duration in seconds of a video file."""
    _, ffprobe = ensure_ffmpeg_in_path()
    if not ffprobe:
        return 0.0
    try:
        res = subprocess.run(
            [
                ffprobe, "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, timeout=15,
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0
