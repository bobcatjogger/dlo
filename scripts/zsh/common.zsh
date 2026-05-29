# Shared helpers for codez zsh scripts.
# Source from other scripts: source "${CODEZ_ROOT}/scripts/zsh/common.zsh"

: "${CODEZ_ROOT:=$(cd "${0:h}/../.." && pwd)}"

codez_venv_python() {
  local py="${CODEZ_ROOT}/.venv/bin/python"
  if [[ -x "$py" ]]; then
    echo "$py"
  else
    echo "python3"
  fi
}

codez_cli() {
  "$(codez_venv_python)" -m codez.cli "$@"
}

codez_load_env() {
  local env_file="${CODEZ_ROOT}/.env"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$env_file"
    set +a
  fi
}
