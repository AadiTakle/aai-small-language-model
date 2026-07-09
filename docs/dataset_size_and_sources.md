# Optimal dataset size + best clean sources

## Optimal size: ~1,000–1,500 clean, balanced, correctly-labeled examples. Quality ≫ quantity.

**Our own evidence says size is not the binding constraint:**
- **v4 (1,334 rows) already ties Claude on verdict + schema** — the constrained classify+format behavior saturates early; the base→v2→v3→v4 gains came from *better/more-real* data, not raw volume.
- The gap loop **adding ~80 examples/iteration did nothing** (and adding imitation rewrites *hurt*). **Re-labeling** the same-size set (v5) is what fixed leak recall (2%→35%). So label *correctness* + *coverage* + *balance* move the needle; row count doesn't.
- The corrected eval is only ~299 items yet gives tight enough CIs to rank models. The task is narrow.

**Recommendation:** target **~1,200–1,500** examples, **~250 per verdict** (balanced — see `docs/dataset_balancing.md`), every label consensus-verified. Below ~500 underfits the fuzzy `adequate/mismatched/vague` boundary; above ~3,000 is diminishing returns for SFT — spend that marginal effort on **DPO** (rewrite safety) and **eval hardening** instead. The generative half (rewrite quality) is capacity/method-bound, not SFT-volume-bound.

## Best sources for clean, genuinely-helpful labeled data (ranked)

| # | source | why | effort |
|---|---|---|---|
| 1 | **Unused MRBench** (~1,100 of 1,596 responses) | already human-annotated on 8 pedagogical dims → maps to our verdicts + is reliable; same distribution we're tuned on | low (mapping + judge-verify) |
| 2 | **Bridge** (700 snippets, **novice + expert** response pairs) | real elementary tutoring; expert responses = clean `adequate`; **novice≺expert pairs are ready-made DPO data** for rewrite safety — we've only touched Bridge via MRBench | low–med |
| 3 | **MathDial unused** (~2,700 of 2,861) | real teacher-move-tagged dialogues; large; middle-school | med (teacher-move → verdict mapping + judge relabel) |
| 4 | **Petukhova & Kochmar (2025)** 11-intent re-annotation of MathDial | finer pedagogical intents → cleaner mapping to our quality axis | med |
| 5 | **Synthetic via the gateway** (gpt-5.5 / cross-model) | fill *rare* classes real data lacks — `gives_away_key_step`, confirmation cases — then jury-filter | low, but weaker evidence (label as such) |
| 6 | PRM800K / MR-GSM8K (step-level correctness) | grounding the *solution* / error-localization, not tutor-message verdicts directly | low priority |

## The labeling caveat that ties it together
The MRBench authors found that an LLM judge (Prometheus2) **correlates poorly (often negatively) with humans on the fine-grained pedagogical dims** — i.e. naive LLM-as-judge is unreliable exactly on our fuzzy quality axis. This is why our pipeline is the right shape: a **calibrated, validated** jury (κ 0.69 cross-family, 98% self-consistent, human-anchored) + a **reliable binary safety axis** + **human spot-checks**. Any new source must be labeled through that pipeline, not a single naive judge. Encouragingly, the **BEA-2025 four tracks** (mistake identification / location / guidance / actionability) map cleanly onto our verdict taxonomy (we already do this via `map_verdict` on MRBench's dims), so MRBench/Bridge/BEA-labeled data can be mapped programmatically + jury-verified.

## Concrete next-data plan (v6+)
Augment the balanced set's minorities (`vague`, `gives_away`, `mismatched`) up to ~250 each from **unused MRBench first, then Bridge** (relabel via the jury + spot-check) → a fully-even ~1,250-row set, no downsampling. Mine **Bridge novice/expert pairs** separately as the DPO dataset for rewrite safety.

Sources: [MathDial](https://www.researchgate.net/publication/376393909_MathDial) · [MRBench / Unifying AI Tutor Evaluation](https://arxiv.org/html/2412.09416v1) · [BEA 2025 Shared Task](https://arxiv.org/html/2505.18549) · [Pedagogically Aligned LLM Tutors for Mistake Remediation](https://arxiv.org/html/2606.21502v1) · [MathTutorBench](https://arxiv.org/pdf/2502.18940) · [ConvoLearn](https://arxiv.org/html/2601.08950v1)
