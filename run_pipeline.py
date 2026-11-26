"""
Main pipeline runner — runs all stages in sequence.
Usage:
  python run_pipeline.py                 # Run full film pipeline (stages 0-5)
  python run_pipeline.py --radio-cut     # Phase 1: validate + TTS + radio cut only
  python run_pipeline.py --stage N       # Run only stage N (0-5)
  python run_pipeline.py --from N        # Resume from stage N (0-5)
"""

import argparse
import os
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

STAGES = [
    ("00_validate.py",  "Validate storyboard"),
    ("01_narration.py", "Generate narration (Gemini 3.8 Flash TTS)"),
    ("02_keyframes.py", "Generate reference sheet & keyframes (Cloudflare FLUX)"),
    ("03_shots.py",     "Generate moving shots (Wan 2.2 / Ken Burns)"),
    ("04_music.py",     "Prepare / check music score (ACE-Step 1.5)"),
    ("05_assemble.py",  "Final assembly (FFmpeg 16:9 + 9:16)"),
]


def run_script(script_name, label):
    script = os.path.join(PROJECT_ROOT, "pipeline", script_name)
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    t0 = time.time()
    result = subprocess.run([sys.executable, script], cwd=PROJECT_ROOT, timeout=600)
    elapsed = time.time() - t0
    if result.returncode != 0:
        print(f"\nFAIL {label} exited with code {result.returncode} after {elapsed:.1f}s")
        return False
    print(f"  OK  {label} finished in {elapsed:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(description="Heritage Short Film Pipeline")
    parser.add_argument("--stage", type=int, help="Run only this stage (0-5)")
    parser.add_argument("--from", dest="from_stage", type=int, default=0, help="Start from stage (0-5)")
    parser.add_argument("--skip-music", action="store_true", help="Skip music prompt helper stage")
    parser.add_argument("--radio-cut", action="store_true", help="Run Phase 1 only: validate + narration + radio_cut.mp4")
    args = parser.parse_args()

    print("Heritage Short Film Pipeline")
    print(f"  Project: {PROJECT_ROOT}")
    print(f"  Started: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    t_total = time.time()

    if args.radio_cut:
        for script, label in [
            ("00_validate.py", "Stage 0: Validate storyboard"),
            ("01_narration.py", "Stage 1: Generate narration"),
            ("01b_radio_cut.py", "Stage 1b: Build Radio Cut"),
        ]:
            if not run_script(script, label):
                sys.exit(1)
    elif args.stage is not None:
        if 0 <= args.stage < len(STAGES):
            script, name = STAGES[args.stage]
            if not run_script(script, f"Stage {args.stage}: {name}"):
                sys.exit(1)
        else:
            print(f"FAIL Invalid stage {args.stage}; expected 0-{len(STAGES)-1}")
            sys.exit(1)
    else:
        for i, (script, name) in enumerate(STAGES):
            if i < args.from_stage:
                print(f"  SKIP Stage {i}: {name}")
                continue
            if args.skip_music and i == 4:
                print("  SKIP Stage 4: Music helper (--skip-music)")
                continue
            if not run_script(script, f"Stage {i}: {name}"):
                print(f"\nResume after fixing with: python run_pipeline.py --from {i}")
                sys.exit(1)

    total_elapsed = time.time() - t_total
    print(f"\n{'=' * 60}")
    print(f"Pipeline complete in {total_elapsed:.1f}s")
    print(f"  Outputs: {os.path.join(PROJECT_ROOT, 'outputs', 'final')}")
    print(f"  Logs:    {os.path.join(PROJECT_ROOT, 'runs.jsonl')}")


if __name__ == "__main__":
    main()
