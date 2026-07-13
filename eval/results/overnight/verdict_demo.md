# Task 1 — verdict eval (frozen n=298) | base=mlx-community/Qwen3-1.7B-4bit

| model | 5-way acc | safety-binary | leak recall | leak precision | leak F1 | parse |
|---|---|---|---|---|---|---|
| base | 26.8% | 68.5% | 51.0% | 55.2% | 53.0% | 100% |
| v9 | 64.1% | 77.5% | 90.4% | 62.3% | 73.7% | 100% |
| opus-4.8 | 67.4% | 87.2% | 82.7% | 81.1% | 81.9% | 100% |
| gpt-5.5 | 71.5% | 88.9% | 74.0% | 92.8% | 82.4% | 100% |
