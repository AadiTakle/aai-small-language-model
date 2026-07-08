
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

# Gap loop v2 start 2026-07-08 10:02 (parallel API; cumulative-anchor; halt via STOP file; add+prune moves)
Anchor (v4) frozen means: {"verdict": 1.534, "schema": 2.0, "grounded": 1.427, "rewrite_safety": 1.449, "consistency": 1.417}

## Iter 1 — MOVE=add focus=**consistency** — generated 80 examples

# Gap loop v2 start 2026-07-08 11:00 (parallel API; cumulative-anchor; halt via STOP file; add+prune moves)
Anchor (v4) frozen means: {"verdict": 1.534, "schema": 2.0, "grounded": 1.427, "rewrite_safety": 1.436, "consistency": 1.447}

## Iter 1 — MOVE=add focus=**grounded** — generated 80 examples
candidate means: {"verdict": 1.369, "schema": 1.981, "grounded": 1.553, "rewrite_safety": 1.474, "consistency": 1.398}
vs anchor: {"verdict": -0.165, "schema": -0.019, "grounded": 0.126, "rewrite_safety": 0.038, "consistency": -0.049}
focus grounded vs-anchor +0.126 [-0.010,+0.262] (sig=False); regressions_vs_anchor=['verdict -0.165[-0.291,-0.039]']
**REVERT** (dry=1) reason=no-sig-improve

## Iter 2 — MOVE=prune — dropped 34/150 judged-mislabeled rows (kept 1300)

# Gap loop v2 start 2026-07-08 11:49 (parallel API; cumulative-anchor; halt via STOP file; add+prune moves)
scoring anchor v4 (11:49:50) ...
Anchor (v4) frozen means: {"verdict": 1.534, "schema": 2.0, "grounded": 1.437, "rewrite_safety": 1.462, "consistency": 1.447}

## Iter 1 — MOVE=add focus=**grounded** — generated 80 examples
training adapters/loop1 (11:58:41) — ~500 iters, watch mlx output ...

# Gap loop v2 start 2026-07-08 12:02 (parallel API; cumulative-anchor; halt via STOP file; add+prune moves)
scoring anchor v4 (12:02:08) ...
Anchor (v4) frozen means: {"verdict": 1.523, "schema": 2.0, "grounded": 1.477, "rewrite_safety": 1.431, "consistency": 1.451}

## Iter 1 — MOVE=add focus=**rewrite_safety** — generated 80 examples
training adapters/loop1 (12:25:25) — ~500 iters, watch mlx output ...
scoring adapters/loop1 (12:55:27) ...
candidate means: {"verdict": 1.51, "schema": 1.987, "grounded": 1.513, "rewrite_safety": 0.986, "consistency": 1.428}
vs anchor: {"verdict": -0.013, "schema": -0.013, "grounded": 0.036, "rewrite_safety": -0.445, "consistency": -0.023}
focus rewrite_safety vs-anchor -0.409 [-0.570,-0.249] (sig=False); regressions_vs_anchor=['rewrite_safety -0.409[-0.570,-0.249]']
**REVERT** (dry=1) reason=no-sig-improve

## Iter 2 — MOVE=prune — dropped 35/150 judged-mislabeled rows (kept 1299)
training adapters/loop2 (13:17:56) — ~500 iters, watch mlx output ...
scoring adapters/loop2 (13:47:40) ...
candidate means: {"verdict": 1.454, "schema": 1.98, "grounded": 1.405, "rewrite_safety": 1.46, "consistency": 1.399}
vs anchor: {"verdict": -0.069, "schema": -0.02, "grounded": -0.072, "rewrite_safety": 0.029, "consistency": -0.052}
focus rewrite_safety vs-anchor +0.048 [-0.122,+0.207] (sig=False); regressions_vs_anchor=none
**REVERT** (dry=2) reason=no-sig-improve

# Loop done. Best: adapters/v4 | data: data/raw/v4.jsonl
Final best frozen means: {"verdict": 1.523, "schema": 2.0, "grounded": 1.477, "rewrite_safety": 1.431, "consistency": 1.451}

## Impact ranking (accepted moves, by focus gain vs anchor)
