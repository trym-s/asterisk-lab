#!/usr/bin/env bash
# Smoke-check the Asterisk lab on this host. Non-zero exit on first failure;
# prints a one-line pass/fail per check. Run via `make verify` or directly.
# Some checks need sudo (asterisk CLI, file owner inspection) — invoke with
# sudo or run as a user with passwordless sudo.
set -u
set -o pipefail

SUDO=$([ "$(id -u)" -eq 0 ] && echo "" || echo "sudo")

pass=0
fail=0

check() {
  local name="$1" pattern="$2" cmd="$3"
  printf '  %-42s ' "$name"
  local out
  if ! out=$(eval "$cmd" 2>&1); then
    echo "FAIL"
    echo "      cmd:    $cmd"
    echo "      error:  $(echo "$out" | head -1)"
    fail=$((fail + 1))
    return
  fi
  if [[ "$out" =~ $pattern ]]; then
    echo "OK"
    pass=$((pass + 1))
  else
    echo "FAIL"
    echo "      cmd:    $cmd"
    echo "      want:   $pattern"
    echo "      got:    $(echo "$out" | head -1)"
    fail=$((fail + 1))
  fi
}

echo "== asterisk =="
check "asterisk.service active"       "active"            "$SUDO systemctl is-active asterisk"
check "asterisk version 22.x"          "Asterisk 22"        "$SUDO asterisk -rx 'core show version'"
check "pjsip endpoint 1001 present"   "1001"               "$SUDO asterisk -rx 'pjsip show endpoints' | grep -E '^ Endpoint: +1001'"
check "dialplan extension 600 present" "MixMonitor"         "$SUDO asterisk -rx 'dialplan show 600@from-softphones'"
check "monitor dir writable by asterisk" "asterisk asterisk" "stat -c '%U %G' /var/spool/asterisk/monitor"

echo
echo "== transcriber =="
check "transcriber.service active"     "active"            "$SUDO systemctl is-active transcriber"
check "venv python runnable"           "Python 3"          "/opt/transcriber/venv/bin/python --version"
check "openai-whisper installed"       "openai-whisper"    "/opt/transcriber/venv/bin/pip show openai-whisper"
check "whisper base model cached"      "base.pt"           "ls /var/lib/asterisk/.cache/whisper/"
check "watcher.py present"             "watcher.py"        "ls /opt/transcriber/watcher.py"

echo
total=$((pass + fail))
if [ "$fail" -eq 0 ]; then
  echo "$pass/$total OK"
  exit 0
else
  echo "$fail/$total FAILED"
  exit 1
fi
