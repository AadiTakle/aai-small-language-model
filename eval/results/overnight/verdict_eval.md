# Task 1 — verdict eval (frozen n=298) | base=mlx-community/Qwen3-1.7B-4bit

| model | 5-way acc | safety-binary | leak recall | leak precision | leak F1 | parse |
|---|---|---|---|---|---|---|
| base | 26.8% | 68.5% | 51.0% | 55.2% | 53.0% | 100% |
| judge_v1 | 50.3% | 75.5% | 67.3% | 64.2% | 65.7% | 100% |
| v6 | 61.7% | 82.2% | 59.6% | 84.9% | 70.1% | 100% |
| opus-4.8 | 68.5% | 87.9% | 84.6% | 81.5% | 83.0% | 100% |
| gpt-5.6 | 70.8% | 90.6% | 77.9% | 94.2% | 85.3% | 100% |
