# Task 2 — rewrite eval (held-out n=60) | base=mlx-community/Qwen3-1.7B-4bit | teacher=gpt-5.6
_jury (rank 1=best): ['claude-group/claude-opus-4-8', 'openai-group/gpt-5.5']; win-rate = share of items ranked at least as good as the teacher._

| model | mean jury rank | win-rate vs teacher | leak rate | mean length (words) | hints |
|---|---|---|---|---|---|
| base | 3.242 | 7.5% | 46.7% | 14.3 | 60/60 |
| rewrite_v2 | 2.558 | 20.8% | 31.7% | 23.0 | 60/60 |
| rewrite_v3 | 2.725 | 17.5% | 25.0% | 22.1 | 60/60 |
| teacher:gpt-5.6 | 1.475 | — | 21.7% | 18.3 | 60/60 |
