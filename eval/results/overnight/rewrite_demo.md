# Honest leak re-measure (held-out n=60) — broad vs sharpened detector
_broad = llm_leaks (fires on any operation/number mention); sharp = llm_leaks_sharp (leak only if it states the answer / takes the next step / corrects an error w/o nudging)._

| model | broad leak | sharp leak | over-flag gap |
|---|---|---|---|
| base | 46.7% | 36.7% | +10.0% |
| rewrite_v4 | 16.7% | 6.7% | +10.0% |
| opus-4.8 | 20.0% | 10.0% | +10.0% |
| gpt-5.5 | 21.7% | 6.7% | +15.0% |
