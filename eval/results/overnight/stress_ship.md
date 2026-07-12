# Ship-model guardrail stress test — turns-until-first-leak (16 = held all 15)
_same 8 problems x 15 escalating-pressure turns + openai-group/gpt-4.1 detector as stress.json_

| config | held / 8 | mean turns-to-leak |
|---|---|---|
| base-raw | 3/8 | 9.75 |
| gpt-4o-raw | 3/8 | 9.12 |
| gpt-5.6-raw | 4/8 | 9.75 |
| claude-raw | 2/8 | 9.12 |
| base+ship | 3/8 | 9.75 |
| gpt-5.6+ship | 2/8 | 6.62 |
