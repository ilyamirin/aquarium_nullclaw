#!/bin/sh
set -eu

ROOT_DIR=$(
  CDPATH='' cd -- "$(dirname "$0")/.."
  pwd
)

cd "$ROOT_DIR"

FILE_COUNT=$(git ls-files --cached --others --exclude-standard | wc -l | tr -d ' ')

if [ "$FILE_COUNT" -eq 0 ]; then
  exec pre-commit run --all-files
fi

# We intentionally lint tracked and untracked non-ignored files so the
# baseline also works before the first commit exists.
# shellcheck disable=SC2046
exec pre-commit run --files $(git ls-files --cached --others --exclude-standard)
