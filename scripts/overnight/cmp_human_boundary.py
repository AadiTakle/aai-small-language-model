"""Was the human curation worth it? Matched comparison on the SAME reviewed contexts:
  - v9 baseline (no boundary pairs)
  - v9 + human-curated pairs (your edits applied)
  - v9 + synthetic pairs (same contexts, un-edited gpt-5.6)
Frozen leak-recall / safety-binary / 5-way. Human vs synthetic differs only where you edited.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.scale_boundary import ADP, WORK, iters_for, judge_rows, measure_judge, render, train  # noqa: E402

OUT = REPO / "eval" / "results" / "overnight" / "cmp_human_boundary"


def main():
    reviews = read_jsonl("data/raw/human_boundary.jsonl")
    pairs = {json.loads(l)["id"]: json.loads(l)
             for l in open(REPO / "data/raw/boundary_pairs.jsonl") if l.strip()}
    v9_base = read_jsonl("data/raw/v9.jsonl")
    frozen = read_jsonl("eval/gold/frozen_eval.jsonl")

    human, synth = [], []
    for r in reviews:
        if r.get("decision") == "skip":
            continue
        orig = pairs.get(r["id"])
        if not orig:
            continue
        hp = dict(orig)
        hp["leaky_candidate"] = r.get("leaky_candidate") or orig["leaky_candidate"]
        hp["safe_rewrite"] = r.get("safe_rewrite") or orig["safe_rewrite"]
        human.append(hp)
        synth.append(orig)
    print(f"[cmp] {len(human)} curated pairs (base v9 {len(v9_base)} rows, frozen {len(frozen)})",
          file=sys.stderr, flush=True)

    results = {}

    def arm(name, pset):
        rows = v9_base + [row for p in pset for row in judge_rows(p)]
        src = WORK / f"cmp_{name}.jsonl"
        write_jsonl(src, rows)
        mlx = WORK / f"mlx_cmp_{name}"
        if not render("verdict", src, mlx):
            print(f"[cmp] {name}: render failed", file=sys.stderr)
            return None
        it = iters_for(mlx)
        adapter = ADP / f"cmp_{name}"
        print(f"[cmp] {name}: {len(rows)} rows, {it} iters -> train", file=sys.stderr, flush=True)
        if not train(mlx, adapter, it, WORK / f"cmp_{name}.log"):
            print(f"[cmp] {name}: train failed", file=sys.stderr)
            return None
        return measure_judge(adapter, frozen)

    for name, pset in [("human", human), ("synth", synth)]:
        m = arm(name, pset)
        if m:
            results[name] = m
            print(f"[cmp] {name}: recall={m['leak_recall']:.1%} safety={m['safety_binary']:.1%}",
                  file=sys.stderr, flush=True)
            OUT.with_suffix(".json").write_text(json.dumps(results, indent=2))

    print("[cmp] v9 baseline (no retrain) ...", file=sys.stderr, flush=True)
    results["v9_baseline"] = measure_judge("adapters/v9", frozen)

    lines = [f"# Human-curated vs synthetic boundary pairs on v9 (frozen n={len(frozen)}, {len(human)} pairs)",
             "", "| arm | leak recall | safety-binary |", "|---|---|---|"]
    for k in ("v9_baseline", "synth", "human"):
        m = results.get(k)
        if m:
            lines.append(f"| {k} | {m['leak_recall']:.1%} | {m['safety_binary']:.1%} |")
    md = "\n".join(lines) + "\n"
    OUT.with_suffix(".md").write_text(md)
    OUT.with_suffix(".json").write_text(json.dumps(results, indent=2))
    print(md)
    print(f"[cmp] wrote {OUT}.md/.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
