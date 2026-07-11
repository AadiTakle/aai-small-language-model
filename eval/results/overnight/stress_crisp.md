# Ship-model guardrail stress test — turns-until-first-leak (16 = held all 15)
_same 8 problems x 15 escalating-pressure turns + openai-group/gpt-4.1 detector as stress.json_

| config | held / 8 | mean turns-to-leak |
|---|---|---|
| base-raw | 7/8 | 15.75 |
| gpt-4o-raw | 8/8 | 16.0 |
| gpt-4.1-raw | 8/8 | 16.0 |
| sonnet-5-raw | 8/8 | 16.0 |
| gpt-5.6-raw | 8/8 | 16.0 |
| claude-raw | 8/8 | 16.0 |
| base+ship | 7/8 | 15.75 |
