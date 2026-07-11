# Diagnostic — `adapters/judge_full` missed leaks (frozen n=298)

Total leaks: 104 | caught: 88 | **MISSED: 16** (leak recall 85%)

## Missed leaks by gold verdict (which leak type is the bottleneck)

- **gives_away_key_step**: missed 16/61 (recall 74%)
- **gives_final_answer**: missed 0/43 (recall 100%)

## What the detector called the missed leaks instead

- mismatched_calibration: 13
- adequate: 3

## Examples (missed leaks)

- [gives_away_key_step → mismatched_calibration] "You're absolutely close on the concept, but let's go through the steps again together, as there's a slight misunderstanding - we need to find the tota"
- [gives_away_key_step → mismatched_calibration] "You've done a great job adding up the total number of students, but remember that we only have 56 boys and 44 girls, not 50 of each. Let's try dividin"
- [gives_away_key_step → mismatched_calibration] "there seems to be misunderstanding here. Brinley is allowed to remove one test score. So, the average should be on 5 tests. Isn't it?"
- [gives_away_key_step → mismatched_calibration] "You're almost there, but remember that Brinley only needs to take five tests into account for her average since she can drop the lowest score. "
- [gives_away_key_step → mismatched_calibration] "I see where you're coming from, Romy, but it seems like there's been a small oversight. While you correctly calculated the number of parents and admin"
- [gives_away_key_step → mismatched_calibration] ""You're on the right track now, but remember there are two specialists, so you'll need to calculate the charge for each and then add them together.""
- [gives_away_key_step → adequate] "That's better, but not quite right.  If they get paid $250 per hour, and work 30 minutes in total, how much would they charge?"
- [gives_away_key_step → mismatched_calibration] "It seems there might be a small mix-up in your calculations for the second year, could you recheck the number of books sold in the second year conside"
