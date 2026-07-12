# Task 2 — rewrite eval (held-out n=60) | base=mlx-community/Qwen3-1.7B-4bit | teacher=gpt-5.6
_jury (rank 1=best): ['claude-group/claude-opus-4-8', 'openai-group/gpt-5.5']; win-rate = share of items ranked at least as good as the teacher._

| model | mean jury rank | win-rate vs teacher | leak rate | mean length (words) | hints |
|---|---|---|---|---|---|
| base | 3.283 | 4.2% | 48.3% | 14.3 | 60/60 |
| rewrite_v3 | 2.717 | 15.8% | 23.3% | 22.1 | 60/60 |
| rewrite_v4 | 2.658 | 13.3% | 16.7% | 23.8 | 60/60 |
| teacher:gpt-5.6 | 1.342 | — | 20.0% | 18.1 | 60/60 |
