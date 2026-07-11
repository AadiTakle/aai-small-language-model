# Task 2 — rewrite eval (held-out n=60) | base=mlx-community/Qwen3-1.7B-4bit | teacher=gpt-5.6
_jury (rank 1=best): ['claude-group/claude-opus-4-8', 'openai-group/gpt-5.5']; win-rate = share of items ranked at least as good as the teacher._

| model | mean jury rank | win-rate vs teacher | leak rate | mean length (words) | hints |
|---|---|---|---|---|---|
| base | 2.617 | 5.8% | 10.0% | 14.3 | 60/60 |
| rewrite_v1 | 2.125 | 18.3% | 0.0% | 20.3 | 60/60 |
| teacher:gpt-5.6 | 1.258 | — | 1.7% | 18.0 | 60/60 |
