"""
Stage 4: Music generation helper.
ACE-Step 1.5 runs on Kaggle/Colab GPU (<4 GB VRAM).
Prepares generation parameters from storyboard.json and checks if
outputs/music/score.wav is present.
"""

import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.utils import get_audio_duration, load_storyboard


def prepare_music_params():
    storyboard = load_storyboard()
    music = storyboard["music"]

    print("ACE-Step 1.5 Music Generation Parameters")
    print("=" * 60)
    print(f"Caption:     {music['caption']}")
    print(f"Tags:        {music['tags']}")
    print(f"Duration:    {music['duration_seconds']} seconds")
    print(f"Tempo (BPM): {music['tempo_bpm']}")
    print(f"Key:         {music['key']}")
    print(f"Style:       {music['style']}")
    print(f"Mood:        {music['mood']}")
    print(f"Instruments: {music['instruments']}")
    print("=" * 60)

    params_path = os.path.join(PROJECT_ROOT, "outputs", "music", "generation_params.json")
    os.makedirs(os.path.dirname(params_path), exist_ok=True)
    params = {
        "caption": music["caption"],
        "tags": music["tags"],
        "duration": music["duration_seconds"],
        "tempo_bpm": music["tempo_bpm"],
        "key": music["key"],
        "lyrics": "[Instrumental]",
        "num_candidates": 3,
        "seeds": [42, 123, 777],
        "note": "Run notebooks/acestep_music.ipynb on Kaggle, audition 3 seeds, save best as outputs/music/score.wav",
    }
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2, ensure_ascii=False)
    print(f"Saved parameters to: {params_path}")

    for ext in ("score.wav", "score.mp3"):
        score_path = os.path.join(PROJECT_ROOT, "outputs", "music", ext)
        if os.path.exists(score_path):
            dur = get_audio_duration(score_path)
            size_kb = os.path.getsize(score_path) / 1024
            print(f"OK   Score present: {ext} ({dur:.1f}s, {size_kb:.1f} KB)")
            return

    print("WARN No outputs/music/score.wav found yet.")
    print("     Upload notebooks/acestep_music.ipynb to Kaggle, generate 3 candidates,")
    print("     and place the chosen track at outputs/music/score.wav.")


if __name__ == "__main__":
    prepare_music_params()
