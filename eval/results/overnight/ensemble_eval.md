# Ensemble-union verdict eval (frozen n=298) — recall-first

| model | leak recall | leak precision | leak F1 | safety-binary | false-pos | missed-leaks |
|---|---|---|---|---|---|---|
| judge_full | 84.6% | 62.0% | 71.5% | 76.5% | 54 | 16 |
| v6 | 59.6% | 84.9% | 70.1% | 82.2% | 11 | 42 |
| UNION(judge_full|v6) | 85.6% | 62.2% | 72.1% | 76.8% | 54 | 15 |
