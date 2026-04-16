from __future__ import annotations

import os
import subprocess
from typing import Mapping, Sequence


class CommandError(RuntimeError):
    pass


def run(
    args: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    capture_output: bool = True,
) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    completed = subprocess.run(
        list(args),
        check=False,
        cwd=cwd,
        env=merged_env,
        text=True,
        capture_output=capture_output,
    )
    if completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        message = stderr or stdout or f"command failed: {' '.join(args)}"
        raise CommandError(message)
    return (completed.stdout or "").strip()
