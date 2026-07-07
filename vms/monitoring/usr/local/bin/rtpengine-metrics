#!/usr/bin/env bash
# Zabbix UserParameter helper for rtpengine. Uses rtpengine-ctl over the
# TCP CLI enabled by `listen-cli = 127.0.0.1:9900` in
# /etc/rtpengine/rtpengine.conf.
#
# Usage: rtpengine-metrics.sh <sessions_current|sessions_total|packets|bytes|errors|timeouts|ping>
set -uo pipefail

CTL=/usr/bin/rtpengine-ctl
LISTEN=127.0.0.1:9900
METRIC="${1:-}"

if [ ! -x "$CTL" ]; then
  echo 0
  exit 0
fi

# rtpengine-ctl writes a Perl warning to stderr; discard it. Output format:
#   ' Total sessions                                  :0'
totals=$("$CTL" -ip "$LISTEN" list totals 2>/dev/null || true)

# Extract "<label> :<value>". First arg is the exact leading label (grep -F).
first_after() { printf '%s\n' "$totals" | grep -F -m1 "$1" | sed -E 's/.*:\s*//'; }

case "$METRIC" in
  ping)
    "$CTL" -ip "$LISTEN" list numsessions >/dev/null 2>&1 && echo 1 || echo 0
    ;;
  sessions_current)
    # Current active RTP sessions (gauge). First "Total sessions" line lives
    # in the "currently running sessions" block.
    v=$(first_after "Total sessions")
    printf '%s\n' "${v:-0}"
    ;;
  sessions_total)
    # Cumulative session count since rtpengine start (counter).
    v=$(first_after "Total managed sessions")
    printf '%s\n' "${v:-0}"
    ;;
  packets)
    # Cumulative user+kernel relayed packets (counter). "Total relayed packets"
    # appears three times; the last is the userspace+kernel sum.
    v=$(printf '%s\n' "$totals" | grep -F "Total relayed packets " | tail -1 | sed -E 's/.*:\s*//')
    printf '%s\n' "${v:-0}"
    ;;
  bytes)
    v=$(printf '%s\n' "$totals" | grep -F "Total relayed bytes " | tail -1 | sed -E 's/.*:\s*//')
    printf '%s\n' "${v:-0}"
    ;;
  errors)
    v=$(printf '%s\n' "$totals" | grep -F "Total relayed packet errors " | tail -1 | sed -E 's/.*:\s*//')
    printf '%s\n' "${v:-0}"
    ;;
  timeouts)
    v=$(first_after "Total timed-out sessions via TIMEOUT")
    printf '%s\n' "${v:-0}"
    ;;
  *)
    echo "usage: rtpengine-metrics.sh <sessions_current|sessions_total|packets|bytes|errors|timeouts|ping>" >&2
    exit 2
    ;;
esac
