"""Report figures (Phase 3). Each figure is guarded — a missing input skips just that figure, so
this can run early (loss + dataset + detector) and again after the scaling experiment (adds growth).

Figures -> docs/figures/:
  loss_curves.png              train/val loss vs iter (rewrite v2/v3/v4 + judge_v1)
  dataset_rewrite.png          rewrite training-set adequacy (verdict / source / length / leak-safe)
  dataset_judge.png            judge training-set verdict balance + leak/safe (if data present)
  detector_broad_vs_sharp.png  leak rate under broad vs sharpened detector (from eval_sharp.json)
  dataset_growth_vs_perf.png   perf vs boundary rows added (from boundary_scaling.json)
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

REPO = Path(__file__).resolve().parent.parent.parent
FIG = REPO / "docs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)
OVN = REPO / "eval" / "results" / "overnight"
LEAKV = {"gives_final_answer", "gives_away_key_step"}

IT_TRAIN = re.compile(r"Iter (\d+): Train loss ([\d.]+)")
IT_VAL = re.compile(r"Iter (\d+): Val loss ([\d.]+)")


def _read_jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def parse_log(path):
    """Split a training log into runs on iteration-reset; return the longest run's train/val series."""
    runs, cur, last = [], None, 10 ** 9
    for line in Path(path).read_text().splitlines():
        mt, mv = IT_TRAIN.search(line), IT_VAL.search(line)
        m = mt or mv
        if not m:
            continue
        it = int(m.group(1))
        if cur is None or it < last:
            cur = {"train": [], "val": []}
            runs.append(cur)
        last = it
        (cur["train"] if mt else cur["val"]).append((it, float(m.group(2))))
    if not runs:
        return None
    return max(runs, key=lambda r: len(r["train"]) + len(r["val"]))


def fig_loss(out):
    logs = {"rewrite_v2": "rewrite_v2.log", "rewrite_v3": "rewrite_v3.log",
            "rewrite_v4": "rewrite_v4.log", "judge_v1": "train_judge_v1.log"}
    plt.figure(figsize=(9, 5.5))
    any_ = False
    colors = plt.cm.tab10.colors
    for i, (name, fn) in enumerate(logs.items()):
        p = OVN / fn
        if not p.exists():
            continue
        run = parse_log(p)
        if not run or not run["val"]:
            continue
        c = colors[i % 10]
        xv, yv = zip(*run["val"])
        plt.plot(xv, yv, marker="o", ms=3, color=c, label=f"{name} val")
        if run["train"]:
            xt, yt = zip(*run["train"])
            plt.plot(xt, yt, ls="--", alpha=0.4, color=c)
        any_ = True
    if not any_:
        print("[graphs] loss: no data", file=sys.stderr)
        return
    plt.xlabel("iteration")
    plt.ylabel("loss")
    plt.title("Training loss (solid=val, dashed=train)")
    plt.legend(fontsize=8)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=130)
    plt.close()
    print(f"[graphs] wrote {out}", file=sys.stderr)


def fig_dataset_rewrite(out):
    for fn in ["data/raw/rewrite_train_v4.jsonl", "data/raw/rewrite_train_v3.jsonl"]:
        p = REPO / fn
        if p.exists():
            break
    else:
        print("[graphs] rewrite dataset: none found", file=sys.stderr)
        return
    rows = _read_jsonl(p)
    tkey = "target_rewrite" if rows and "target_rewrite" in rows[0] else "rewritten_message"
    verd = Counter(r.get("verdict") for r in rows)
    src = Counter((r.get("source") or "?").split("-")[0] for r in rows)
    lens = [len((r.get(tkey) or "").split()) for r in rows if r.get(tkey)]
    leak = sum(1 for r in rows if r.get("verdict") in LEAKV)
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))
    ax[0, 0].bar(list(verd), list(verd.values()), color="#68a")
    ax[0, 0].set_title("verdict distribution")
    ax[0, 0].tick_params(axis="x", rotation=25, labelsize=8)
    ax[0, 1].bar(list(src), list(src.values()), color="#8a6")
    ax[0, 1].set_title("source mix")
    ax[0, 1].tick_params(axis="x", rotation=25, labelsize=8)
    if lens:
        med = sorted(lens)[len(lens) // 2]
        ax[1, 0].hist(lens, bins=20, color="#a68")
        ax[1, 0].axvline(med, color="k", ls="--", label=f"median {med}w")
        ax[1, 0].set_title("target hint length (words)")
        ax[1, 0].legend(fontsize=8)
    ax[1, 1].bar(["leak-verdict", "safe/other"], [leak, len(rows) - leak], color=["#d55", "#5a5"])
    ax[1, 1].set_title("leak vs safe context balance")
    fig.suptitle(f"Rewrite training-set adequacy ({p.name}, n={len(rows)})")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close()
    print(f"[graphs] wrote {out}", file=sys.stderr)


def fig_dataset_judge(out):
    for fn in ["data/raw/v9b.jsonl", "data/raw/v9.jsonl", "data/raw/v6_consensus.jsonl"]:
        p = REPO / fn
        if p.exists():
            break
    else:
        print("[graphs] judge dataset: none", file=sys.stderr)
        return
    rows = _read_jsonl(p)
    verd = Counter(r.get("verdict") for r in rows if r.get("verdict"))
    if not verd:
        print("[graphs] judge dataset: no verdict field", file=sys.stderr)
        return
    leak = sum(n for v, n in verd.items() if v in LEAKV)
    fig, ax = plt.subplots(1, 2, figsize=(11, 4.5))
    ax[0].bar(list(verd), list(verd.values()), color="#68a")
    ax[0].set_title("judge verdict distribution")
    ax[0].tick_params(axis="x", rotation=25, labelsize=8)
    ax[1].bar(["leak", "safe/other"], [leak, len(rows) - leak], color=["#d55", "#5a5"])
    ax[1].set_title("leak vs safe balance")
    fig.suptitle(f"Judge training-set adequacy (n={len(rows)})")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close()
    print(f"[graphs] wrote {out}", file=sys.stderr)


def fig_detector(out):
    p = OVN / "eval_sharp.json"
    if not p.exists():
        print("[graphs] detector: no eval_sharp.json", file=sys.stderr)
        return
    import numpy as np
    rows = json.loads(p.read_text())["rows"]
    names = [r["model"] for r in rows]
    broad = [r["broad"] * 100 for r in rows]
    sharp = [r["sharp"] * 100 for r in rows]
    x = np.arange(len(names))
    w = 0.38
    plt.figure(figsize=(10, 5))
    plt.bar(x - w / 2, broad, w, label="broad (over-flags)", color="#e88")
    plt.bar(x + w / 2, sharp, w, label="sharp (honest)", color="#48c")
    plt.xticks(x, names, rotation=25, fontsize=9)
    plt.ylabel("key-step leak rate (%)")
    plt.title("Rewrite leak rate: broad vs sharpened detector (held-out 60)")
    plt.legend()
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out, dpi=130)
    plt.close()
    print(f"[graphs] wrote {out}", file=sys.stderr)


def fig_growth(out):
    p = OVN / "boundary_scaling.json"
    if not p.exists():
        print("[graphs] growth: no boundary_scaling.json (phase 4 pending)", file=sys.stderr)
        return
    data = json.loads(p.read_text())
    fig, ax = plt.subplots(1, 2, figsize=(13, 5))
    if data.get("rewrite"):
        r = sorted(data["rewrite"], key=lambda d: d["added"])
        xs = [d["added"] for d in r]
        ax[0].plot(xs, [d["sharp_leak"] * 100 for d in r], marker="o", color="#48c", label="sharp leak %")
        a2 = ax[0].twinx()
        a2.plot(xs, [d.get("jury_rank", 0) for d in r], marker="s", color="#a63", label="jury rank")
        a2.set_ylabel("jury rank (lower=better)")
        ax[0].set_title("rewrite: perf vs boundary rows added")
        ax[0].set_xlabel("boundary rows added")
        ax[0].set_ylabel("sharp leak %")
        ax[0].grid(alpha=0.3)
        ax[0].legend(loc="upper left", fontsize=8)
    if data.get("judge"):
        j = sorted(data["judge"], key=lambda d: d["added"])
        xs = [d["added"] for d in j]
        ax[1].plot(xs, [d["leak_recall"] * 100 for d in j], marker="o", color="#4a4", label="leak recall %")
        ax[1].plot(xs, [d.get("safety", 0) * 100 for d in j], marker="s", color="#a44", label="safety-binary %")
        ax[1].set_title("judge: perf vs boundary rows added")
        ax[1].set_xlabel("boundary rows added")
        ax[1].set_ylabel("%")
        ax[1].grid(alpha=0.3)
        ax[1].legend(fontsize=8)
    fig.suptitle("Dataset growth vs performance (boundary leak/safe minimal-pairs)")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close()
    print(f"[graphs] wrote {out}", file=sys.stderr)


def main():
    fig_loss(FIG / "loss_curves.png")
    fig_dataset_rewrite(FIG / "dataset_rewrite.png")
    fig_dataset_judge(FIG / "dataset_judge.png")
    fig_detector(FIG / "detector_broad_vs_sharp.png")
    fig_growth(FIG / "dataset_growth_vs_perf.png")
    print("[graphs] done", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
