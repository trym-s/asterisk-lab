#!/usr/bin/env bash
# Shared lab environment loader. Runtime VMs keep secrets in /etc; local host
# workflows can keep using the ignored repo-local .env.

load_lab_env() {
  local repo_root="$1"
  local env_file="${ASTERISK_LAB_ENV:-}"

  if [ -z "$env_file" ]; then
    if [ -f /etc/asterisk-lab/env ]; then
      env_file=/etc/asterisk-lab/env
    else
      env_file="$repo_root/.env"
    fi
  fi

  LAB_ENV_FILE="$env_file"
  export LAB_ENV_FILE

  if [ -f "$env_file" ]; then
    set -a
    # shellcheck source=/dev/null
    . "$env_file"
    set +a
  fi
}
