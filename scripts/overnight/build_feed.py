"""Build the rewrite-curation feed (data/raw/rewrite_feed.jsonl).

For each training context, pair the gpt-5.6 teacher rewrite with rewrite_v1's rewrite (only when
--slm is passed AND the adapter exists — that step needs the GPU), score 'fuzziness'
(leak-risk + length outliers + teacher/slm disagreement), and write the feed sorted fuzziest-first
so the web UI surfaces the highest-value-to-review items at the top.

Two-phase by design (so the UI can go live before the GPU frees):
  phase 1 (CPU, now):  python scripts/overnight/build_feed.py                 # teacher-only
  phase 2 (GPU, later): python scripts/overnight/build_feed.py --slm          # add rewrite_v1 column
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from socratic_tutor import config  # noqa: E402
from socratic_tutor.io_utils import read_jsonl, write_jsonl  # noqa: E402
from overnight.split_common import clean_hint, infer_rewrite_prompt, input_dict, rewrite_leaks  # noqa: E402

CTX_KEYS = ("id", "source", "problem", "correct_solution", "final_answer", "key_step",
            "conversation_history", "candidate_message", "verdict", "reason")


def fuzzy(row: dict) -> float:
    """Higher = more uncertain/valuable to review: leak-risk >> length-outlier + disagreement."""
    s = 0.0
    for rw in (row.get("teacher_rewrite"), row.get("slm_rewrite")):
        if not rw:
            continue
        if rewrite_leaks(rw, row):
            s += 3.0
        n = len(rw.split())
        if n < 8 or n > 32:
            s += 1.0
    t, sl = row.get("teacher_rewrite") or "", row.get("slm_rewrite") or ""
    if t and sl:
        ta, sa = set(t.lower().split()), set(sl.lower().split())
        jac = len(ta & sa) / len(ta | sa) if (ta | sa) else 1.0
        s += (1.0 - jac) * 2.0
    return round(s, 3)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default="data/raw/rewrite_train.jsonl")
    ap.add_argument("--out", default="data/raw/rewrite_feed.jsonl")
    ap.add_argument("--slm", action="store_true", help="also generate rewrite_v1 outputs (needs GPU)")
    ap.add_argument("--adapter", default="adapters/rewrite_v1")
    a = ap.parse_args()

    rows = read_jsonl(a.src)
    slm = {}
    if a.slm and (REPO / a.adapter).exists():
        print(f"[feed] generating rewrite_v1 outputs for {len(rows)} contexts ...", file=sys.stderr)
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler
        model, tok = load(config.MODEL, adapter_path=a.adapter)
        sampler = make_sampler(temp=0.0)
        for i, r in enumerate(rows, 1):
            prompt = infer_rewrite_prompt(tok, input_dict(r), r.get("verdict") or "", r.get("reason") or "")
            slm[r["id"]] = clean_hint(generate(model, tok, prompt=prompt, max_tokens=128, sampler=sampler, verbose=False))
            if i % 100 == 0:
                print(f"[feed]   {i}/{len(rows)}", file=sys.stderr, flush=True)
    elif a.slm:
        print(f"[feed] WARN {a.adapter} missing — writing teacher-only feed", file=sys.stderr)

    feed = []
    for r in rows:
        item = {k: r.get(k) for k in CTX_KEYS}
        item["teacher_rewrite"] = r.get("target_rewrite") or r.get("rewritten_message") or ""
        item["slm_rewrite"] = slm.get(r["id"], "")
        item["fuzzy"] = fuzzy(item)
        feed.append(item)
    feed.sort(key=lambda x: x["fuzzy"], reverse=True)
    write_jsonl(a.out, feed)
    has_slm = sum(1 for f in feed if f["slm_rewrite"])
    print(f"[feed] wrote {len(feed)} items -> {a.out}  (slm_rewrite on {has_slm}) "
          f"fuzzy range {feed[-1]['fuzzy']}..{feed[0]['fuzzy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
