# Shared helpers for dlo zsh scripts.
# Source from other scripts: source "${DLO_ROOT}/scripts/zsh/common.zsh"

: "${DLO_ROOT:=$(cd "${0:h}/../.." && pwd)}"

dlo_venv_python() {
  local py="${DLO_ROOT}/.venv/bin/python"
  if [[ -x "$py" ]]; then
    echo "$py"
  else
    echo "python3"
  fi
}

dlo_cli() {
  "$(dlo_venv_python)" -m dlo.cli "$@"
}

dlo_load_env() {
  local env_file="${DLO_ROOT}/.env"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$env_file"
    set +a
  fi
}
