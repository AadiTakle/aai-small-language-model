# Future fixes — prioritized (synthesis)

Ranked by expected impact-per-effort, grounded in the corrected+consensus-gold re-score
(`docs/model_holes.md`) and the analyses in `docs/{dataset_balancing,rubric_evaluation,dataset_size_and_sources}.md`.

## P0 — do next
1. **DPO for rewrite safety.** SFT plateaued rewrite-safety at ~1.0 for *every* model incl. frontier — it's the one thing nobody solves, and it's method-bound, not volume-bound. **Done (2026-07-09): mined 230 pairs from already-validated MRBench rows** (`scripts/mine_dpo_pairs.py` → `data/dpo/bridge_mathdial_pairs.jsonl`; 22 tight bridge_novice + 63 bridge_other + 145 mathdial) by reusing each row's existing `candidate_message`/`rewritten_message` as a zero-new-generation chosen/rejected pair. Unrendered/tokenizer-agnostic schema — prompt rendering deferred to whatever base model the Colab DPO run uses. Runs on Colab/CUDA (MLX has no DPO). Highest-leverage single move.
2. **Retrain v6 to close the leak hole.** `data/raw/v6_consensus.jsonl` already lifts `gives_away` 229→313. **Done (2026-07-09): all 216 `needs_regen` rows regenerated** via `scripts/regen_v6.py` + 8 parallel Claude-subagent batches, leak-gated via `_heuristic_safe`. 199/216 passed the gate cleanly; the other 17 were manually re-verified against full conversation history and rescued (see `eval/gold/review/regen-v6/rescued.json`) — all 17 were heuristic false positives: the flagged number was either already stated by the student themselves (safe to cite back) or the new content was asked as a question rather than stated as fact. **Finding**: the same recheck found 46 *other*, pre-existing non-adequate rows elsewhere in `v6_consensus.jsonl` (untouched this session) that also fail `_heuristic_safe` for the same reason — the heuristic has no notion of "already known to the student" or "asked vs. stated." Not fixed (out of scope for this pass); worth a dedicated sweep later, but low urgency since `_heuristic_safe` is only a fallback — the real judge model resolves this correctly when available (`rubric.py`'s docstring already flags the heuristic as tier-{0,2}-only). Next: train v6 locally and re-score.

## P1 — high value
3. **Two-axis reporting + rubric split.** Stop reporting one blended accuracy. Report **(a) binary safety** (leak vs. not — objective, ~100% jury agreement) and **(b) quality** (adequate/mismatched/vague — ~45% inter-judge disagreement) *separately*. The mismatched↔adequate confusion (14% recall) is partly irreducible ambiguity; don't let it mask the safety story. Do **not** adopt the decision-tree prompt (ablation negative for a 1.7B).
4. **Report rewrite-safety jointly with grounding.** Safety alone rewards vagueness (base "wins" by being unhelpful; `docs/model_holes.md`). Add a combined **safe-AND-grounded** score so a useless-but-safe rewrite can't score well.
5. **Contrastive mismatched data.** Mine adequate-vs-mismatched *minimal pairs* (same problem, hint pitched right vs. wrong) from MRBench/MathDial to sharpen the fuzziest boundary.

## P2 — eval hardening (the eval must stay ahead of the model)
6. **Grow the adversarial calibration slice** n=2 → 30–40 paired items (robustness CI is currently uninformative).
7. **Re-measure consistency** (k was skipped to save gateway budget) — at least k=3 on a subset, to re-confirm 98% self-consistency on the corrected gold.
8. **Blind judge-vs-human κ** on a fresh 40-item sample (current κ=0.69 predates the consensus relabel).

## P3 — data expansion (only after P0–P1)
9. Augment minorities to ~250 each from **unused MRBench first, then Bridge**, jury-verified → even ~1,250-row set (`docs/dataset_size_and_sources.md`). Size is *not* the binding constraint — correctness/coverage/balance are.
10. **If mismatched/leak reasoning proves capacity-bound**, try **Qwen3-4B-4bit** as a base (still local-trainable) and compare — only after data + DPO are exhausted.

## Human-in-the-loop backlog (needs your ruling, not code)
- **Gold NO_CONSENSUS (14)** + **your 15 protected hand-labels the jury contested** — review lists in `eval/gold/review/consensus/frozen_{flagged,human_overrides}.*`.
- **Training NO_CONSENSUS (45)** — `eval/gold/review/consensus/train_flagged.jsonl`.
- These are where the jury genuinely split; a human ruling is worth more than another model vote.
