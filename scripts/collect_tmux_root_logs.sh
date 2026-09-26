#!/usr/bin/env bash
set -euo pipefail

OUT="${1:-/tmp/tmux-root-log-audit.txt}"
SINCE="${SINCE:-14 days ago}"
USER_NAME="${SUDO_USER:-${USER:-anonymous}}"
USER_ID="$(id -u "$USER_NAME")"

{
  echo "===== audit metadata ====="
  date
  hostname
  echo "collector_user=$(id -un)"
  echo "target_user=$USER_NAME"
  echo "target_uid=$USER_ID"
  echo "since=$SINCE"
  echo

  echo "===== current tmux processes ====="
  pgrep -a tmux || true
  ps -eo pid,ppid,pgid,sid,user,stat,lstart,etime,cmd | awk 'NR==1 || /[t]mux/'
  echo

  echo "===== tmux process cgroups ====="
  for p in $(pgrep tmux || true); do
    echo "--- PID $p ---"
    cat "/proc/$p/cgroup" 2>/dev/null || true
    readlink "/proc/$p/fd/0" 2>/dev/null | sed 's/^/stdin=/' || true
  done
  echo

  echo "===== loginctl user ====="
  loginctl show-user "$USER_NAME" -p Linger -p State -p Sessions -p RuntimePath || true
  loginctl user-status "$USER_NAME" || true
  echo

  echo "===== sessions ====="
  loginctl list-sessions || true
  for s in $(loginctl list-sessions --no-legend 2>/dev/null | awk -v uid="$USER_ID" '$2 == uid {print $1}'); do
    echo "--- session $s ---"
    loginctl show-session "$s" -p Id -p User -p Name -p State -p Active -p KillProcesses -p Scope -p Service -p Type -p Remote -p RemoteHost -p Leader -p Timestamp || true
    scope="$(loginctl show-session "$s" -p Scope --value 2>/dev/null || true)"
    if [ -n "$scope" ]; then
      systemctl show "$scope" -p ActiveState -p SubState -p SendSIGHUP -p KillMode -p KillSignal -p FinalKillSignal -p TimeoutStopUSec -p CollectMode || true
      systemctl status "$scope" --no-pager || true
    fi
  done
  echo

  echo "===== logind config ====="
  systemd-analyze cat-config systemd/logind.conf || true
  echo

  echo "===== user service config ====="
  systemctl cat "user@${USER_ID}.service" || true
  systemctl status "user@${USER_ID}.service" --no-pager || true
  echo

  echo "===== journal: tmux/logind/session/kill/oom ====="
  journalctl --no-pager --since "$SINCE" \
    | grep -Ei "tmux|user-${USER_ID}|user@${USER_ID}|session-|${USER_NAME}|systemd-logind|logind|oom|out of memory|killed process|sigkill|sigterm|sighup|killed|terminated|abandoned|removed session|new session" \
    || true
  echo

  echo "===== kernel journal: oom/kill/crash ====="
  journalctl -k --no-pager --since "$SINCE" \
    | grep -Ei "oom|out of memory|killed process|memory cgroup|tmux|segfault|sigkill|hung task|invoked oom-killer" \
    || true
  echo

  echo "===== traditional logs if present ====="
  for f in /var/log/syslog /var/log/syslog.1 /var/log/kern.log /var/log/kern.log.1 /var/log/auth.log /var/log/auth.log.1; do
    [ -r "$f" ] || continue
    echo "--- $f ---"
    grep -Ei "tmux|user-${USER_ID}|session-|${USER_NAME}|systemd-logind|logind|oom|out of memory|killed process|sigkill|sigterm|sighup|killed|terminated|abandoned" "$f" || true
  done
} > "$OUT"

chmod 0644 "$OUT"
echo "Wrote $OUT"
