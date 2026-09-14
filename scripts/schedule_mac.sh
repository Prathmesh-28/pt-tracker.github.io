#!/usr/bin/env bash
# Run the tracker on this Mac: a full refresh every morning, and the site kept
# up at http://127.0.0.1:8765 whenever you are logged in.
#
#   ./scripts/schedule_mac.sh install [HH:MM]   # default 08:00, local time
#   ./scripts/schedule_mac.sh status
#   ./scripts/schedule_mac.sh run               # start a refresh now
#   ./scripts/schedule_mac.sh uninstall
#
# Asleep at that time: launchd runs the refresh when the Mac wakes.
# Shut down: that morning is skipped, and the next refresh catches up.
# The project must live outside ~/Downloads, ~/Documents and ~/Desktop:
# macOS does not let background jobs read those folders.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
DOMAIN="gui/$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"
DAILY="com.pttracker.daily"
SERVER="com.pttracker.server"

plist() {  # label, program arguments as <string> elements, extra keys
  cat > "$AGENTS/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array>$2</array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>StandardOutPath</key><string>$ROOT/data/raw/logs/$1.log</string>
  <key>StandardErrorPath</key><string>$ROOT/data/raw/logs/$1.log</string>
  $3
</dict>
</plist>
PLIST
  launchctl bootout "$DOMAIN/$1" 2>/dev/null || true
  launchctl bootstrap "$DOMAIN" "$AGENTS/$1.plist"
}

case "${1:-}" in
  install)
    case "$ROOT" in "$HOME/Downloads"*|"$HOME/Documents"*|"$HOME/Desktop"*)
      echo "Move the project out of $ROOT first; macOS blocks background jobs there."; exit 1;;
    esac
    [ -x "$ROOT/.venv/bin/python" ] || {
      echo "No .venv. Run: python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
    TIME="${2:-08:00}"
    HOUR=$((10#${TIME%%:*})); MINUTE=$((10#${TIME##*:}))
    mkdir -p "$ROOT/data/raw/logs" "$AGENTS"

    plist "$DAILY" "<string>$ROOT/scripts/refresh.sh</string>" \
      "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>$HOUR</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>LowPriorityIO</key><true/>"
    plist "$SERVER" "<string>$ROOT/.venv/bin/python</string><string>$ROOT/scripts/serve.py</string>" \
      "<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>"

    printf "Refresh scheduled daily at %02d:%02d.\nSite: http://127.0.0.1:8765\n" "$HOUR" "$MINUTE"
    ;;
  status)
    for label in "$DAILY" "$SERVER"; do
      if launchctl print "$DOMAIN/$label" >/dev/null 2>&1; then
        state=$(launchctl print "$DOMAIN/$label" | awk -F'= ' '/^\tstate/{print $2; exit}')
        echo "$label: loaded (${state:-idle})"
      else
        echo "$label: not installed"
      fi
    done
    if [ -L data/raw/logs/latest.log ]; then
      echo; echo "Last run:"; grep -E "^(started|finished)" data/raw/logs/latest.log || true
    fi
    ;;
  run)
    launchctl kickstart "$DOMAIN/$DAILY" && echo "Refresh started. Follow it: tail -f data/raw/logs/latest.log"
    ;;
  uninstall)
    for label in "$DAILY" "$SERVER"; do
      launchctl bootout "$DOMAIN/$label" 2>/dev/null || true
      rm -f "$AGENTS/$label.plist"
    done
    echo "Removed the daily refresh and the local site."
    ;;
  *)
    sed -n '2,14p' "$0"; exit 1
    ;;
esac
