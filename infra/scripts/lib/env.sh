#!/usr/bin/env bash
# Shared lab environment loader. Runtime VMs keep secrets in /etc; local host
# workflows can keep using the ignored repo-local .env.

# Retry a network-dependent command a few times with a short backoff. Some
# hosting environments (nested virtualization behind a NAT network) see
# intermittent TLS-handshake resets/timeouts to external hosts (GitHub,
# apt/package mirrors); a bare retry clears most of them without masking a
# real, persistent failure (which still surfaces after the retry budget).
retry() {
  local attempt=1 max=5 delay=5
  until "$@"; do
    if [ "$attempt" -ge "$max" ]; then
      echo "retry: giving up after $attempt attempts: $*" >&2
      return 1
    fi
    echo "retry: attempt $attempt/$max failed, retrying in ${delay}s: $*" >&2
    sleep "$delay"
    attempt=$((attempt + 1))
  done
}

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
