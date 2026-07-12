#!/usr/bin/env bash
# Overnight honest-eval chain: Phase 2 (benchmarks) -> 3a (graphs) -> 4a (boundary synth) ->
# 4b (scaling) -> 3b (graphs w/ growth). Phase 1 (eval_sharp) already ran separately.
# set +e: a failed phase is logged but the chain continues (report-critical phases run first).
set +e
cd "/Users/atakle/Desktop/Intership Files/Alpha AI Engineering 2026/aai-small-language-model" || exit 1
PY=.venv/bin/python
LOG=eval/results/overnight/honest_eval.log
ts() { date +%H:%M:%S; }
echo "[chain] $(ts) START (phases 2 -> 3a -> 4a -> 4b -> 3b)" | tee -a "$LOG"

echo "[chain] $(ts) PHASE 2: traditional benchmarks (fuse v6 + GSM8K/MMLU base+fused)" | tee -a "$LOG"
$PY scripts/overnight/bench_run.py >> "$LOG" 2>&1
echo "[chain] $(ts) phase2(benchmarks) exit $?" | tee -a "$LOG"

echo "[chain] $(ts) PHASE 3a: graphs (loss + dataset + detector)" | tee -a "$LOG"
$PY scripts/overnight/make_graphs.py >> "$LOG" 2>&1
echo "[chain] $(ts) phase3a(graphs) exit $?" | tee -a "$LOG"

echo "[chain] $(ts) PHASE 4a: boundary minimal-pair synthesis" | tee -a "$LOG"
$PY scripts/overnight/gen_boundary.py >> "$LOG" 2>&1
echo "[chain] $(ts) phase4a(boundary-synth) exit $?" | tee -a "$LOG"

echo "[chain] $(ts) PHASE 4b: dataset-growth scaling (rewrite + judge)" | tee -a "$LOG"
$PY scripts/overnight/scale_boundary.py >> "$LOG" 2>&1
echo "[chain] $(ts) phase4b(scaling) exit $?" | tee -a "$LOG"

echo "[chain] $(ts) PHASE 3b: graphs (add dataset-growth-vs-perf)" | tee -a "$LOG"
$PY scripts/overnight/make_graphs.py >> "$LOG" 2>&1
echo "[chain] $(ts) phase3b(graphs) exit $?" | tee -a "$LOG"

echo "[chain] $(ts) DONE" | tee -a "$LOG"
