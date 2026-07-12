# Honest leak re-measure (held-out n=60) — broad vs sharpened detector
_broad = llm_leaks (fires on any operation/number mention); sharp = llm_leaks_sharp (leak only if it states the answer / takes the next step / corrects an error w/o nudging)._

| model | broad leak | sharp leak | over-flag gap |
|---|---|---|---|
| base | 48.3% | 38.3% | +10.0% |
| rewrite_v3 | 21.7% | 8.3% | +13.4% |
| rewrite_v4 | 16.7% | 6.7% | +10.0% |
| gpt-4o | 35.0% | 11.7% | +23.3% |
| gpt-4.1 | 31.7% | 10.0% | +21.7% |
| sonnet-5 | 30.0% | 6.7% | +23.3% |
| gpt-5.6 | 15.0% | 11.7% | +3.3% |
