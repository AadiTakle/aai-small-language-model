# Task 1 — verdict dataset balancing (label-safe resample)

Source: `data/raw/v9b.jsonl` (1432 raw). Excluded: 5 frozen-eval ids, 186 gate-fails, 52 malformed/ends-on-tutor artifacts -> **1189 clean pool**.

Balance: hard-equal verdict at **999/verdict** (cap) -> **1189 rows**. Secondary axes flattened by round-robin over band x topic x len x turns x nnum cells.

Clean per-verdict (pre-balance): {'adequate': 375, 'gives_final_answer': 145, 'gives_away_key_step': 283, 'mismatched_calibration': 231, 'vague_unhelpful': 155}

## BEFORE (clean pool marginals)
- **verdict**: adequate=375, gives_away_key_step=283, gives_final_answer=145, mismatched_calibration=231, vague_unhelpful=155
- **band**: 3-5=168, 6-8=186, 9-12=188, ?=449, K-2=198
- **topic**: algebra=156, arithmetic=449, fraction=146, geometry=54, money=102, percent=86, ratio_rate=117, time_measure=79
- **len**: long(>35w)=186, med(15-35w)=727, short(<15w)=276
- **turns**: t2-3=291, t4+=405, t<=1=493
- **nnum**: nums3-4=563, nums5+=128, nums<=2=498

## AFTER (balanced set marginals)
- **verdict**: adequate=375, gives_away_key_step=283, gives_final_answer=145, mismatched_calibration=231, vague_unhelpful=155
- **band**: 3-5=168, 6-8=186, 9-12=188, ?=449, K-2=198
- **topic**: algebra=156, arithmetic=449, fraction=146, geometry=54, money=102, percent=86, ratio_rate=117, time_measure=79
- **len**: long(>35w)=186, med(15-35w)=727, short(<15w)=276
- **turns**: t2-3=291, t4+=405, t<=1=493
- **nnum**: nums3-4=563, nums5+=128, nums<=2=498

## Coverage gaps (band/topic cells with <3 rows): ['6-8/time_measure', '9-12/time_measure']

_No row content was edited; balancing is pure resampling, so every gold verdict stays valid._
