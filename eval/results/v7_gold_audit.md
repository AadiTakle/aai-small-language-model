# v7 vs frozen-gold audit — independent blind jury

Jury: claude-group/claude-opus-4-8, openai-group/gpt-4o (blind: decision-tree prompt, no gold, no identities; neither produced v7's gpt-5.5 labels).

Valid v6!=v7 disagreements: **77**; jury confident (both agree): **31**.

| subset | n | jury=v7 | jury=sft_v6 | jury=frozen_gold |
|---|---|---|---|---|
| all confident disagreements | 31 | 9 | 18 | 23 |
| v7-LOST (gold==v6) | 19 | 2 | 16 | 16 |
| v7-WON (gold==v7) | 5 | 5 | 0 | 5 |

**On v7-LOST items the jury backs v7 (gold poor) in 2, backs gold (v7 wrong) in 16.**

## Clearest 'gold looks poor' cases (v7-lost, jury unanimously sided with v7)

- `frozen-mrb-1180-90f-GPT4` — gold=`adequate` · v7=`mismatched_calibration` · jury=`mismatched_calibration`
    problem: Jam has three boxes full of pencils and 2 loose pencils which give a total of 26 pencils. If her sister, Meg, has 46 pencils, how many boxes do Jam and Meg need
    candidate: You've done a great job with calculations, but there seems to be a misunderstanding about the number of pencils each box can hold. Let's work on this together.

- `frozen-mrb-1380-46d-Expert` — gold=`gives_away_key_step` · v7=`adequate` · jury=`adequate`
    problem: Brinley is in Mr. Bert's math class. Mr. Bert gives six tests each semester. He allows the Students to remove the lowest score from the average each semester. I
    candidate: there seems to be misunderstanding here. Brinley is allowed to remove one test score. So, the average should be on 5 tests. Isn't it?
