#!/usr/bin/env zsh
# Initialize the local SQLite database (or whatever DLO_DATABASE_URL points to).

set -euo pipefail

DLO_ROOT="$(cd "${0:h}/../.." && pwd)"
# shellcheck source=scripts/zsh/common.zsh
source "${DLO_ROOT}/scripts/zsh/common.zsh"
dlo_load_env

echo "Initializing database..."
dlo_cli init-db
echo "Done."
