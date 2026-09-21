#!/usr/bin/env bash
# Run a command inside the project environment.
#
# The source tree lives on the Windows filesystem (/mnt/c/...) so it stays
# visible to Explorer and to a single git worktree, but the virtualenv lives on
# the WSL-native filesystem because package installs over the 9p mount are slow.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-$HOME/.venvs/socb}"
cd "$(dirname "$0")/.."
exec uv run "$@"
