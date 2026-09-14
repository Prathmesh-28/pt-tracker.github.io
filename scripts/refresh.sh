#!/usr/bin/env bash
# One full pipeline run, with a lock and a log. The 8 AM job and the page's
# Refresh button both come through here, so two runs never overlap.
#
#   ./scripts/refresh.sh            # LinkedIn and Indeed only if the 4h cooldown allows
#   ./scripts/refresh.sh --force    # search them regardless
set -uo pipefail
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:/usr/bin:/bin"
mkdir -p data/raw/logs

LOCK=data/raw/run.lock
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "A run is already in progress (pid $holder)."
    exit 0
  fi
  rm -rf "$LOCK" && mkdir "$LOCK"   # left behind by a run that was killed
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

LOG="data/raw/logs/$(date +%Y-%m-%d-%H%M%S).log"
ln -sf "$(basename "$LOG")" data/raw/logs/latest.log
{
  echo "started $(date '+%Y-%m-%d %H:%M:%S')"
  ./scripts/run_all.sh "$@"
  status=$?
  echo "finished $(date '+%Y-%m-%d %H:%M:%S') exit $status"
} > "$LOG" 2>&1
# Keep the last 60 run logs.
ls -1t data/raw/logs/20*.log 2>/dev/null | tail -n +61 | xargs -r rm -f
exit "${status:-1}"
