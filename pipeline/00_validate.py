"""
Stage 0: Validate storyboard.json against schema/storyboard.schema.json.
Ensures the contract between all pipeline stages is valid before generation.
"""

import json
import os
import sys
from jsonschema import validate, ValidationError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from pipeline.utils import load_storyboard


def validate_storyboard():
    schema_path = os.path.join(PROJECT_ROOT, "schema", "storyboard.schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)

    storyboard = load_storyboard()

    try:
        validate(instance=storyboard, schema=schema)
        print("OK   storyboard.json is valid against the schema.")
    except ValidationError as e:
        print(f"FAIL Validation error: {e.message}")
        print(f"     Path: {' -> '.join(str(p) for p in e.absolute_path)}")
        sys.exit(1)

    shots = storyboard["shots"]
    total_duration = sum(s["duration_seconds"] for s in shots)
    target_min, target_max = storyboard["meta"]["duration_target_seconds"]

    print(f"INFO Total planned shot duration: {total_duration}s (target: {target_min}-{target_max}s)")

    if total_duration < target_min:
        print(f"WARN Total duration ({total_duration}s) is below target minimum ({target_min}s)")
    elif total_duration > target_max:
        print(f"WARN Total duration ({total_duration}s) is above target maximum ({target_max}s)")

    ids = [s["id"] for s in shots]
    expected = list(range(1, len(shots) + 1))
    if ids != expected:
        print(f"FAIL Shot IDs must be sequential 1..{len(shots)}, got {ids}")
        sys.exit(1)

    char_ids = {c["id"] for c in storyboard["characters"]}
    for shot in shots:
        for char in shot.get("characters_in_shot", []):
            if char not in char_ids:
                print(f"FAIL Shot {shot['id']} references unknown character '{char}'")
                sys.exit(1)

    narration_shots = [s for s in shots if s["narration_amharic"].strip()]
    print(f"INFO Shots with narration: {len(narration_shots)} / {len(shots)}")
    print(f"INFO Total shots: {len(shots)}")
    print(f"INFO Narration voice: {storyboard.get('narration', {}).get('voice', 'default')}")
    print(f"INFO Music style: {storyboard['music']['style']}")

    return storyboard


if __name__ == "__main__":
    validate_storyboard()
    print("OK   All checks passed.")
