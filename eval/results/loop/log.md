
# Gap-closing loop start 2026-07-08 02:14 (local SFT; accept=paired-sig + no-regression; stop=2 dry)
Baseline (v4) frozen means: {"verdict": 1.534, "schema": 2.0, "grounded": 1.408, "rewrite_safety": 1.41, "consistency": 1.369}

## Iter 1 — focus **consistency** (means {"rewrite_safety": 1.41, "grounded": 1.408, "consistency": 1.369})
generated 80 targeted examples for consistency
candidate means: {"verdict": 1.447, "schema": 2.0, "grounded": 1.612, "rewrite_safety": 1.021, "consistency": 1.398}
focus consistency paired diff +0.029 [-0.136,+0.194] (sig=False); regressions=['rewrite_safety -0.385[-0.641,-0.115]']
**REVERT** (dry=1) reason=no-sig-improve

## Iter 2 — focus **consistency** (means {"rewrite_safety": 1.41, "grounded": 1.408, "consistency": 1.369})
generated 80 targeted examples for consistency
candidate means: {"verdict": 1.466, "schema": 1.981, "grounded": 1.592, "rewrite_safety": 1.322, "consistency": 1.553}
focus consistency paired diff +0.184 [+0.058,+0.311] (sig=True); regressions=none
**ACCEPT** -> new best adapters/loop2

## Iter 3 — focus **rewrite_safety** (means {"rewrite_safety": 1.322, "grounded": 1.592, "consistency": 1.553})
generated 80 targeted examples for rewrite_safety
candidate means: {"verdict": 1.427, "schema": 1.981, "grounded": 1.534, "rewrite_safety": 1.614, "consistency": 1.544}
focus rewrite_safety paired diff +0.287 [+0.050,+0.525] (sig=True); regressions=none
**ACCEPT** -> new best adapters/loop3

## Iter 4 — focus **grounded** (means {"rewrite_safety": 1.614, "grounded": 1.534, "consistency": 1.544})
generated 80 targeted examples for grounded
candidate means: {"verdict": 1.524, "schema": 2.0, "grounded": 1.476, "rewrite_safety": 1.7, "consistency": 1.301}
focus grounded paired diff -0.058 [-0.233,+0.117] (sig=False); regressions=['consistency -0.243[-0.427,-0.058]']
**REVERT** (dry=1) reason=no-sig-improve

## Iter 5 — focus **grounded** (means {"rewrite_safety": 1.614, "grounded": 1.534, "consistency": 1.544})
generated 80 targeted examples for grounded
candidate means: {"verdict": 1.34, "schema": 1.99, "grounded": 1.388, "rewrite_safety": 1.468, "consistency": 1.408}
focus grounded paired diff -0.146 [-0.301,+0.019] (sig=False); regressions=none
**REVERT** (dry=2) reason=no-sig-improve

# Loop done. Best adapter: adapters/loop3 | data: eval/results/loop/iter3_data.jsonl
Final frozen means: {"verdict": 1.427, "schema": 1.981, "grounded": 1.534, "rewrite_safety": 1.614, "consistency": 1.544}
