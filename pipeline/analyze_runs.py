"""
Utility: Summarize runs.jsonl metrics (calls, successes, errors, avg/total latency)
to help populate COSTS.md with exact measured evidence.
"""

import json
import os
from collections import defaultdict

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def summarize():
    log_path = os.path.join(PROJECT_ROOT, "runs.jsonl")
    if not os.path.exists(log_path):
        print("No runs.jsonl found.")
        return

    stats = defaultdict(lambda: {"ok": 0, "err": 0, "latencies": [], "audio_dur": 0.0})
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            key = (row.get("stage", "?"), row.get("model", "?"))
            if row.get("status") == "success":
                stats[key]["ok"] += 1
                if row.get("latency_seconds") is not None:
                    stats[key]["latencies"].append(float(row["latency_seconds"]))
                if row.get("audio_duration_seconds"):
                    stats[key]["audio_dur"] += float(row["audio_duration_seconds"])
            else:
                stats[key]["err"] += 1

    print(f"{'Stage':<16} {'Model':<28} {'OK':>4} {'Err':>4} {'Avg(s)':>8} {'Tot(s)':>8} {'Audio(s)':>9}")
    print("-" * 82)
    for (stage, model), d in sorted(stats.items()):
        lats = d["latencies"]
        avg_l = sum(lats) / len(lats) if lats else 0.0
        tot_l = sum(lats)
        print(f"{stage:<16} {model:<28} {d['ok']:>4} {d['err']:>4} {avg_l:>8.2f} {tot_l:>8.2f} {d['audio_dur']:>9.2f}")


if __name__ == "__main__":
    summarize()
