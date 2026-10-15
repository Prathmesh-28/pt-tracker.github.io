#!/usr/bin/env bash
# Both Japan lists, refreshed from every source and synced to the team site: every day at
# 8:00 in the morning India time (IST), whatever time zone this Mac is set to, and whenever
# someone presses Refresh on the team site.
#
#   Japan/daily.sh install     # schedule it on this Mac
#   Japan/daily.sh status      # is it scheduled, and how did the last run go
#   Japan/daily.sh now         # run it now, in the background (same lock and log)
#   Japan/daily.sh uninstall
#   Japan/daily.sh             # run it now, here
#
# launchd calls `daily.sh --if-due` every minute. It runs the refresh at the first call at or
# after 8:00 IST each day (8:00 when the Mac is awake, else as soon as it wakes or starts up),
# and whenever the site's Refresh button has queued one. To have the Mac awake at 8, once:
#   sudo pmset repeat wakeorpoweron MTWRFSU 07:58:00
#
# Order: Prathmesh's company boards and sync first (most of his list), then his case competitions
# from Unstop (CaseCompetitions/) and his India roles with pay (India/, from the India tracker's
# data/latest.json) and their syncs, then Madhura's searches and sync, then Prathmesh's LinkedIn and
# Indeed searches (one set a day in turn) and a second sync. Searches keep their cooldowns (LinkedIn 4 hours, Madhura's part-time searches 1 hour),
# so pressing Refresh often re-reads the company boards without getting the searches blocked.
# A step that fails is logged and skipped; the sync never mass-closes jobs because a source
# was down. Progress goes to the site as it happens (Japan/team/refresh_queue.py).
set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
PY="$ROOT/.venv/bin/python"
export PATH="$ROOT/.venv/bin:/usr/bin:/bin:/usr/sbin:/sbin"
LABEL=com.pttracker.japan
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOGS="$ROOT/Japan/private/logs"
STAMP="$ROOT/Japan/private/last_daily_run"
LOCK="$ROOT/Japan/private/daily.lock"
ist() { TZ=Asia/Kolkata date "+$1"; }
mkdir -p "$LOGS"

TRIGGER=schedule
case "${1:-}" in
  install)
    [ -x "$PY" ] || { echo "No .venv here; create it first."; exit 1; }
    if [ -d "$LOCK" ] && kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null; then
      echo "A refresh is running; reinstalling now would stop it. Try again when it finishes."; exit 1
    fi
    mkdir -p "$(dirname "$PLIST")"
    cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$ROOT/Japan/daily.sh</string><string>--if-due</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StartInterval</key><integer>60</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOGS/launchd.log</string>
  <key>StandardErrorPath</key><string>$LOGS/launchd.log</string>
  <key>LowPriorityIO</key><true/>
</dict>
</plist>
PLIST
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$PLIST"
    echo "Scheduled: both Japan lists refresh every day at 08:00 IST, and within a minute of a Refresh on the site."
    exit 0 ;;
  uninstall)
    launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "Removed the daily Japan refresh."
    exit 0 ;;
  status)
    if launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
      echo "$LABEL: scheduled, daily at 08:00 IST and on the site's Refresh button (now $(ist '%H:%M') IST)"
    else
      echo "$LABEL: not installed (Japan/daily.sh install)"
    fi
    echo "Last 8:00 run: $(cat "$STAMP" 2>/dev/null || echo never) (IST date)"
    if [ -L "$LOGS/latest.log" ]; then
      echo; grep -E "^(started|finished|== |!! |done:|[0-9,]+ (part-time|roles in Japan)|NOT closing|Prathmesh: )" "$LOGS/latest.log" || true
    fi
    exit 0 ;;
  now)
    nohup "$0" > /dev/null 2>&1 &
    echo "Started. Follow it: tail -f Japan/private/logs/latest.log"
    exit 0 ;;
  --if-due)
    if [[ "$(ist %H%M)" > "0759" ]] && [ "$(cat "$STAMP" 2>/dev/null)" != "$(ist %F)" ]; then
      TRIGGER=schedule                                    # 8:00 IST, first time today
    elif "$PY" Japan/team/refresh_queue.py waiting 2>/dev/null; then
      TRIGGER=button                                      # someone pressed Refresh
    else
      exit 0
    fi ;;
  "") ;;
  *) sed -n '2,22p' "$0"; exit 1 ;;
esac

# One run at a time; a lock left by a run that was killed is cleared.
if ! mkdir "$LOCK" 2>/dev/null; then
  holder=$(cat "$LOCK/pid" 2>/dev/null || true)
  if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
    echo "A Japan refresh is already running (pid $holder)."
    exit 0
  fi
  rm -rf "$LOCK" && mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT
[ "${1:-}" = "--if-due" ] && [ "$TRIGGER" = schedule ] && ist %F > "$STAMP"   # once a day, even if a step fails

LOG="$LOGS/$(ist %Y-%m-%d-%H%M).log"
ln -sf "$(basename "$LOG")" "$LOGS/latest.log"
RID=$("$PY" Japan/team/refresh_queue.py start "$TRIGGER" 2>>"$LOG" | tail -1)
report() { [ -z "$RID" ] || "$PY" Japan/team/refresh_queue.py "$1" "$RID" "${@:2}" || true; }
failed=""   # a plain string: the bash 3.2 that macOS ships fails on empty arrays under set -u
STEPS=10 n=0
step() {
  local name="$1"; shift
  n=$((n + 1))
  echo; echo "== $name ($(ist %H:%M:%S) IST)"
  report step "Step $n of $STEPS: $name"
  "$@"
  local rc=$?
  if [ $rc -ne 0 ]; then echo "!! $name failed (exit $rc); carrying on"; failed="${failed:+$failed; }$name"; fi
  case "$name" in *sync*) report synced ;; esac
}
{
  echo "started $(ist '%Y-%m-%d %H:%M:%S') IST by the $TRIGGER${RID:+ (refresh $RID)}"
  step "Prathmesh: company boards" "$PY" Japan/fetch_japan.py
  step "Prathmesh: sync to the team site" "$PY" Japan/team/sync_jobs.py
  step "Competitions: Unstop and the watchlist" "$PY" CaseCompetitions/fetch_competitions.py
  step "Competitions: sync to the team site" "$PY" Japan/team/sync_jobs.py --competitions
  step "India: pay and company type for the India roles" "$PY" India/fetch_india.py
  step "India: sync to the team site" "$PY" Japan/team/sync_jobs.py --india
  if [ -f madhura/find_jobs.py ]; then
    step "Madhura: Indeed part-time, Guidable, LinkedIn, Indeed, Daijob" "$PY" madhura/find_jobs.py --search
    step "Madhura: sync to the team site" "$PY" Japan/team/sync_jobs.py --candidate madhura
  else
    STEPS=8
  fi
  step "Prathmesh: LinkedIn and Indeed (today's set)" "$PY" Japan/fetch_japan.py --reclassify --rotate
  step "Prathmesh: sync to the team site" "$PY" Japan/team/sync_jobs.py
  echo
  report finish "$([ -z "$failed" ] && echo done || echo failed)"
  echo "finished $(ist '%Y-%m-%d %H:%M:%S') IST${failed:+; failed: $failed}"
} >> "$LOG" 2>&1
# Keep the last 60 logs.
ls -1t "$LOGS"/20*.log 2>/dev/null | tail -n +61 | xargs -r rm -f
[ -z "$failed" ]
