# Dataset stats

- total examples: **700**
- gate pass: **675/700** (96.4%)
- duplicate ids: **0**
- shards: all.jsonl=700
- verdict distribution: adequate=167, gives_away_key_step=142, gives_final_answer=112, mismatched_calibration=167, vague_unhelpful=112
- band distribution: 3-5=179, 6-8=174, 9-12=174, K-2=173
- slice distribution: calibration_adversarial=90, core=610

## Gate failure reasons
- 25x: rewrite leaks final answer
