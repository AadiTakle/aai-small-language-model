# v7 decision-tree relabel report

Source: `data/raw/v6_consensus.jsonl` (1330 rows) | Judge model: `openai-group/gpt-5.5`  
Quality-axis rows re-judged: **814** (safety-axis left untouched).

CONFIRMED flips applied: **91** (→adequate 14, →non-adequate regenerated 77).  
Kept (no confirmed flip): 715. Dropped (regen failed/leaked → kept v6 label): 8.

## Flip transitions (old → new)
| old | new | n |
|---|---|---|
| mismatched_calibration | vague_unhelpful | 15 |
| adequate | gives_away_key_step | 15 |
| mismatched_calibration | gives_away_key_step | 14 |
| adequate | vague_unhelpful | 14 |
| mismatched_calibration | adequate | 12 |
| adequate | mismatched_calibration | 11 |
| vague_unhelpful | mismatched_calibration | 5 |
| mismatched_calibration | gives_final_answer | 3 |
| vague_unhelpful | adequate | 2 |

New verdict distribution: `{'adequate': 340, 'gives_away_key_step': 342, 'gives_final_answer': 206, 'vague_unhelpful': 220, 'mismatched_calibration': 222}`
