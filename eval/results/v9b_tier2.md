# v9 (Tier-2 minimal-pair augmentation) vs v6 — frozen set

n=298 | added 102 training rows

| metric | v6 | v9 | Δ |
|---|---|---|---|
| leak recall | 59.6% | 51.0% | -8.7% |
| leak precision | 84.9% | 75.7% | -9.2% |
| leak F1 | 70.1% | 60.9% | -9.1% |
| safety-binary | 82.2% | 77.2% | -5.0% |
| 5-way | 61.7% | 54.4% | -7.4% |
| canary FP (corrective-safe, n=40) | 12.5% | 12.5% | +0.0% |

**Verdict: REVERT (v6 stays)** — leak recall not up, safety-binary regressed, canary ok.
