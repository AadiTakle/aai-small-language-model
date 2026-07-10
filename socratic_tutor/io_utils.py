"""JSONL read/write and dataset splitting."""

import json
from pathlib import Path


def read_jsonl(path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def split_rows(rows: list, train: float = 0.8, valid: float = 0.1):
    """Split a (pre-shuffled) list into train/valid/test by ratio.

    valid/test each get at least 1 row when the input has >= 3 rows, so MLX always
    has a non-empty valid.jsonl for --steps-per-eval.
    """
    n = len(rows)
    if n == 0:
        return [], [], []
    n_train = int(n * train)
    n_valid = int(n * valid)
    if n >= 3:
        n_valid = max(1, n_valid)
        n_train = min(n_train, n - n_valid - 1)  # leave >=1 for test
    train_rows = rows[:n_train]
    valid_rows = rows[n_train : n_train + n_valid]
    test_rows = rows[n_train + n_valid :]
    return train_rows, valid_rows, test_rows
