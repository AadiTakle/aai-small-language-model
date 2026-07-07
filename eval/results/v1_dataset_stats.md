# Dataset stats

- total examples: **200**
- gate pass: **194/200** (97.0%)
- duplicate ids: **0**
- shards: v1.jsonl=200
- verdict distribution: adequate=52, gives_away_key_step=32, gives_final_answer=32, mismatched_calibration=52, vague_unhelpful=32
- band distribution: 3-5=50, 6-8=50, 9-12=50, K-2=50
- slice distribution: calibration_adversarial=40, core=160

## Gate failure reasons
- 6x: rewrite leaks final answer
