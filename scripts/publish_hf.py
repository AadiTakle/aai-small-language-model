"""Publish the ship models + dataset to HF Hub. Auth via the cached `hf auth login` token (or HF_TOKEN
env). Idempotent — safe to re-run (exist_ok + re-upload). Prints the resulting URLs."""

import sys

from huggingface_hub import HfApi

REPOS = [
    ("atakle/socratic-tutor-judge-v9-1.7b", "data/hf/judge-v9", "model"),
    ("atakle/socratic-tutor-rewriter-v4-1.7b", "data/hf/rewriter-v4", "model"),
    ("atakle/socratic-tutor-data", "data/hf/dataset", "dataset"),
]


def main():
    api = HfApi()
    try:
        who = api.whoami()
        print(f"[publish] authenticated as: {who.get('name')}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[publish] NOT AUTHENTICATED ({type(e).__name__}). Run `hf auth login` first.",
              file=sys.stderr)
        return 3
    for repo, path, rtype in REPOS:
        api.create_repo(repo, repo_type=rtype, exist_ok=True, private=False)
        print(f"[publish] uploading {repo} ({rtype}) from {path} ...", flush=True)
        api.upload_folder(folder_path=path, repo_id=repo, repo_type=rtype,
                          commit_message="Publish Socratic Tutor guardrail (SLM training project)")
        pfx = "datasets/" if rtype == "dataset" else ""
        print(f"[publish]   -> https://huggingface.co/{pfx}{repo}", flush=True)
    print("[publish] ALL DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
