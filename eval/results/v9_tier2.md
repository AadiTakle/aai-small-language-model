# v9 (Tier-2 minimal-pair augmentation) vs v6 — frozen set

n=298 | added 38 training rows

| metric | v6 | v9 | Δ |
|---|---|---|---|
| leak recall | 59.6% | 89.4% | +29.8% |
| leak precision | 84.9% | 62.0% | -22.9% |
| leak F1 | 70.1% | 73.2% | +3.2% |
| safety-binary | 82.2% | 77.2% | -5.0% |
| 5-way | 61.7% | 63.8% | +2.0% |
| canary FP (corrective-safe, n=40) | 12.5% | 60.0% | +47.5% |

**Verdict: REVERT (v6 stays)** — leak recall up, safety-binary regressed, canary regressed.
