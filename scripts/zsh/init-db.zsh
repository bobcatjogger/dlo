#!/usr/bin/env zsh
# Initialize the local SQLite database (or whatever CODEZ_DATABASE_URL points to).

set -euo pipefail

CODEZ_ROOT="$(cd "${0:h}/../.." && pwd)"
# shellcheck source=scripts/zsh/common.zsh
source "${CODEZ_ROOT}/scripts/zsh/common.zsh"
codez_load_env

echo "Initializing database..."
codez_cli init-db
echo "Done."
