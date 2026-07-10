# v6 self-consistency leak-recall sweep (no retraining)

n=298 | k=5 @ temp=0.7 | adapter=adapters/v6 | thinking=False

vote>=m/k: predict LEAK if at least m of k samples say leak (m=1 = OR = max recall).

| setting | leak P | leak R | leak F1 | safety-binary | 5-way |
|---|---|---|---|---|---|
| greedy (baseline = v6) | 84.9% | 59.6% | 70.1% | 82.2% | 61.7% |
| vote>=1/5 | 60.8% | 76.0% | 67.5% | 74.5% | 56.7% |
| vote>=2/5 | 72.7% | 61.5% | 66.7% | 78.5% | 58.1% |
| vote>=3/5 | 82.6% | 54.8% | 65.9% | 80.2% | 58.4% |
| vote>=4/5 | 84.3% | 41.3% | 55.5% | 76.8% | 55.0% |
| vote>=5/5 | 90.0% | 26.0% | 40.3% | 73.2% | 52.3% |
