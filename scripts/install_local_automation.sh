#!/bin/zsh
set -eu

SCRIPT_DIR="${0:A:h}"
PROJECT_ROOT="${SCRIPT_DIR:h}"
TEMPLATE="$PROJECT_ROOT/launch_agents/com.invdata.dashboard.daily.plist"
LAUNCH_AGENT="$HOME/Library/LaunchAgents/com.invdata.dashboard.daily.plist"
LOG_DIR="$HOME/Library/Logs/InvDataDashboard"

mkdir -p "${LAUNCH_AGENT:h}" "$LOG_DIR"
sed \
  -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
  -e "s|__LOG_DIR__|$LOG_DIR|g" \
  "$TEMPLATE" > "$LAUNCH_AGENT"

plutil -lint "$LAUNCH_AGENT"
launchctl bootout "gui/$(id -u)" "$LAUNCH_AGENT" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$LAUNCH_AGENT"
launchctl enable "gui/$(id -u)/com.invdata.dashboard.daily"

echo "Installed: $LAUNCH_AGENT"
echo "Logs: $LOG_DIR"
