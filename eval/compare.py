"""Compare Hookline's picks with the independent reference picks in eval/reference_picks_*.json.

    python eval/compare.py                      # tool picks from the app's database (data/hookline.db)
    python eval/compare.py --snapshot           # tool picks from eval/run_promos.json (python -m app.seed export)
    python eval/compare.py --out eval/comparison.md

The reference set was written by a separate editor pass over the same scripts (see eval/README.md). It is
one opinion, not ground truth: agreement is a signal to read the disagreements, not a score to maximize.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.db import Database  # noqa: E402


def tc(value: str) -> float:
    minutes, seconds = value.split(":")
    return int(minutes) * 60 + float(seconds)


def union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def length(intervals) -> float:
    return sum(b - a for a, b in intervals)


def intersection(a, b) -> float:
    return sum(max(0.0, min(e1, e2) - max(s1, s2)) for s1, e1 in a for s2, e2 in b)


def iou(a, b) -> float:
    a, b = union(a), union(b)
    inter = intersection(a, b)
    total = length(a) + length(b) - inter
    return inter / total if total else 0.0


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(x: list[float], y: list[float]) -> float:
    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


def load_reference() -> dict[int, dict]:
    episodes = {}
    for path in sorted((ROOT / "eval").glob("reference_picks_*.json")):
        for ep in json.loads(path.read_text(encoding="utf-8"))["episodes"]:
            episodes[int(ep["episode"])] = ep
    return episodes


def load_tool(from_snapshot: bool, data_dir: Path) -> dict[int, dict]:
    tool = {}
    if from_snapshot:
        for rec in json.loads(config.RUN_SNAPSHOT_FILE.read_text(encoding="utf-8")):
            number = int(rec["episode_label"].split()[-1])
            promo = rec["promo"]
            tool[number] = {
                "title": promo["title"],
                "segments": json.loads(promo["segments_json"]),
                "composite": promo["composite"],
                "scores": {k: v["score"] for k, v in json.loads(promo["scores_json"]).items()},
                "flags": json.loads(promo["flags_json"]),
                "hook": promo["hook"],
                "cliffhanger": promo["cliffhanger"],
            }
        return tool
    db = Database(data_dir / "hookline.db")
    for row in db.list_promos():
        if row["episode_number"] is None:
            continue
        tool[int(row["episode_number"])] = {
            "title": row["title"],
            "segments": json.loads(row["segments_json"]),
            "composite": row["composite"],
            "scores": {k: v["score"] for k, v in json.loads(row["scores_json"]).items()},
            "flags": json.loads(row["flags_json"]),
            "hook": row["hook"],
            "cliffhanger": row["cliffhanger"],
        }
    return tool


def seg_text(segments, key_start="start", key_end="end") -> str:
    return " + ".join(f"{s[key_start]}-{s[key_end]}" for s in segments)


def compare(reference: dict[int, dict], tool: dict[int, dict]) -> str:
    rows = []
    for number in sorted(set(reference) & set(tool)):
        ref, mine = reference[number], tool[number]
        t = [(s["start_sec"], s["end_sec"]) for s in mine["segments"]]
        best = [(tc(s["start"]), tc(s["end"])) for s in ref["best"]["segments"]]
        runner = [(tc(s["start"]), tc(s["end"])) for s in (ref.get("runner_up") or {}).get("segments", [])]
        overlap_best = iou(t, best)
        overlap_runner = iou(t, runner) if runner else 0.0
        same_open = abs(t[0][0] - best[0][0]) <= 3.0
        same_cut = abs(t[-1][1] - best[-1][1]) <= 3.0
        if overlap_best >= 0.5:
            verdict = "agree"
        elif overlap_best > 0 or same_cut:
            verdict = "partial"
        elif overlap_runner > 0:
            verdict = "matches runner-up"
        else:
            verdict = "different"
        rows.append(
            {
                "episode": number,
                "verdict": verdict,
                "iou": overlap_best,
                "same_open": same_open,
                "same_cut": same_cut,
                "tool": mine,
                "ref": ref,
            }
        )
    if not rows:
        return "No overlapping episodes between the tool's picks and the reference set.\n"

    verdicts = Counter(r["verdict"] for r in rows)
    composite = [r["tool"]["composite"] for r in rows]
    ref_score = [float(r["ref"]["best"]["score"]) for r in rows]
    rho = spearman(composite, ref_score)
    top_tool = {r["episode"] for r in sorted(rows, key=lambda r: -r["tool"]["composite"])[:10]}
    top_ref = {r["episode"] for r in sorted(rows, key=lambda r: (-float(r["ref"]["best"]["score"]), r["episode"]))[:10]}
    flag_counts = Counter(f["code"] for r in rows for f in r["tool"]["flags"] if f["code"] != "hook_timing")
    multi_tool = sum(len(r["tool"]["segments"]) > 1 for r in rows)
    multi_ref = sum(len(r["ref"]["best"]["segments"]) > 1 for r in rows)
    mean_dur_tool = sum(sum(s["duration_sec"] for s in r["tool"]["segments"]) for r in rows) / len(rows)
    mean_dur_ref = sum(float(r["ref"]["best"]["duration_sec"]) for r in rows) / len(rows)

    out = [
        "# Tool vs reference picks",
        "",
        f"Episodes compared: {len(rows)}",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Same moment (IoU >= 0.5) | {verdicts['agree']} |",
        f"| Partial overlap / same final cut | {verdicts['partial']} |",
        f"| Tool picked the reference runner-up | {verdicts['matches runner-up']} |",
        f"| Completely different moment | {verdicts['different']} |",
        f"| Mean IoU with reference best | {sum(r['iou'] for r in rows) / len(rows):.2f} |",
        f"| Same opening (+-3s) / same final cut (+-3s) | {sum(r['same_open'] for r in rows)} / "
        f"{sum(r['same_cut'] for r in rows)} |",
        f"| Rank correlation, tool composite vs reference score (Spearman) | {rho:.2f} |",
        f"| Top-10 overlap | {len(top_tool & top_ref)} of 10 |",
        f"| Multi-segment promos, tool / reference | {multi_tool} / {multi_ref} |",
        f"| Mean duration, tool / reference | {mean_dur_tool:.1f}s / {mean_dur_ref:.1f}s |",
        "",
        "Tool flags (excluding hook timing): "
        + (", ".join(f"{code} x{n}" for code, n in flag_counts.most_common()) or "none"),
        "",
        "| Ep | Verdict | IoU | Tool cut | Reference cut | Tool composite | Ref score |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        out.append(
            f"| {r['episode']} | {r['verdict']} | {r['iou']:.2f} | {seg_text(r['tool']['segments'])} | "
            f"{seg_text(r['ref']['best']['segments'])} | {r['tool']['composite']:.2f} | {r['ref']['best']['score']} |"
        )
    out += ["", "## Biggest disagreements", ""]
    for r in sorted(rows, key=lambda r: r["iou"])[:10]:
        out += [
            f"**Episode {r['episode']}** ({r['verdict']}, IoU {r['iou']:.2f})",
            f"- Tool: {seg_text(r['tool']['segments'])}: \"{r['tool']['title']}\". Hook: {r['tool']['hook']} "
            f"Cliffhanger: {r['tool']['cliffhanger']}",
            f"- Reference: {seg_text(r['ref']['best']['segments'])}. Hook: {r['ref']['best']['hook']} "
            f"Cliffhanger: {r['ref']['best']['cliffhanger']}",
            "",
        ]
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", action="store_true", help="read tool picks from eval/run_promos.json")
    parser.add_argument("--data-dir", type=Path, default=config.DEFAULT_DATA_DIR)
    parser.add_argument("--out", type=Path, help="write the report here instead of stdout")
    args = parser.parse_args()
    report = compare(load_reference(), load_tool(args.snapshot, args.data_dir))
    if args.out:
        args.out.write_text(report, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
