# Rubric reframe — safety-axis metrics on the frozen set (re-scored, no model runs)

LEAK = {gives_final_answer, gives_away_key_step}; SAFE = {adequate, mismatched_calibration, vague_unhelpful}. **3-way** collapses the fuzzy quality axis into SAFE; **safety binary** + **leak F1** are the objective safety numbers (leak = positive class).

| model | n | 5-way acc (old) | 3-way acc | safety binary | leak P | leak R | leak F1 |
|---|---|---|---|---|---|---|---|
| base | 298 | 25.2% | 65.1% | 66.1% | 55.2% | 15.4% | 24.1% |
| v2 | 298 | 36.2% | 74.2% | 75.5% | 86.0% | 35.6% | 50.3% |
| v3 | 298 | 42.3% | 67.1% | 67.8% | 75.0% | 14.4% | 24.2% |
| v4 | 298 | 50.3% | 75.8% | 77.2% | 86.0% | 41.3% | 55.8% |
| v5 | 298 | 55.4% | 76.5% | 79.2% | 77.5% | 59.6% | 67.4% |
| v6 | 298 | 61.7% | 79.2% | 82.2% | 84.9% | 59.6% | 70.1% |
| v7 | 298 | 56.4% | 76.5% | 79.2% | 73.5% | 72.1% | 72.8% |
| v8 | 298 | 50.3% | 70.8% | 74.8% | 64.7% | 63.5% | 64.1% |
| gpt4o | 298 | 52.3% | 76.2% | 77.5% | 91.1% | 39.4% | 55.0% |
| claude | 298 | 59.4% | 76.8% | 78.5% | 74.5% | 76.0% | 75.2% |
