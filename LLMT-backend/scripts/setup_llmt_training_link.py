"""Create the llmt_training import link used by local development.

The source directory is named ``LLMT-training`` for repository readability,
but Python imports use ``llmt_training``. This script creates or repairs a
repo-root symlink so subprocesses can import the training package.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    source = repo_root / "LLMT-training"
    target = repo_root / "llmt_training"

    if not source.is_dir():
        print(f"LLMT-training not found: {source}", file=sys.stderr)
        return 1

    if target.is_symlink():
        current = target.resolve()
        if current == source.resolve():
            print(f"llmt_training already points to {source}")
            return 0
        target.unlink()
    elif target.exists():
        print(f"Refusing to replace existing non-symlink path: {target}", file=sys.stderr)
        return 1

    try:
        target.symlink_to(source, target_is_directory=True)
        print(f"Created symlink: {target} -> {source}")
    except OSError as exc:
        if os.name != "nt":
            print(f"Failed to create symlink: {exc}", file=sys.stderr)
            return 1

        # Windows fallback for users without symlink privileges.
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        print(f"Symlink failed; copied package directory instead: {target}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
