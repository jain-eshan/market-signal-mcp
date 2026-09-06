#!/usr/bin/env bash
# check_update.sh - cached, throttled version-check for market-signal-mcp.
#
# Run at /market-signal skill invocation, NOT on every MCP tool call - this is a
# once-a-day-at-most convenience check, not a critical dependency.
#
# Output (one line, or nothing):
#   UPDATE_AVAILABLE <old> <new> <compare_url>   - remote VERSION differs from local
#   (nothing)                                     - up to date, cache still fresh,
#                                                    or network/read failure (silent -
#                                                    this check must never block or
#                                                    error out the skill)
#
# Env overrides (for testing):
#   MARKET_SIGNAL_STATE_DIR          - override the ~/.config/market-signal-mcp state dir
#   MARKET_SIGNAL_REMOTE_VERSION_URL - override the remote VERSION URL
set -uo pipefail

STATE_DIR="${MARKET_SIGNAL_STATE_DIR:-$HOME/.config/market-signal-mcp}"
CACHE_FILE="$STATE_DIR/last-update-check"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION_FILE="$REPO_DIR/VERSION"
REMOTE_URL="${MARKET_SIGNAL_REMOTE_VERSION_URL:-https://raw.githubusercontent.com/jain-eshan/market-signal-mcp/main/VERSION}"
REPO_SLUG="jain-eshan/market-signal-mcp"

mkdir -p "$STATE_DIR" 2>/dev/null || exit 0

NOW=$(date +%s)
if [ -f "$CACHE_FILE" ]; then
  LAST=$(cat "$CACHE_FILE" 2>/dev/null || echo 0)
  AGE=$(( NOW - LAST ))
  if [ "$AGE" -lt 86400 ]; then
    exit 0
  fi
fi

[ -f "$VERSION_FILE" ] || exit 0
LOCAL_VERSION=$(tr -d '[:space:]' < "$VERSION_FILE")

REMOTE_VERSION=$(curl -fsSL --max-time 5 "$REMOTE_URL" 2>/dev/null | tr -d '[:space:]')

# Record the check attempt regardless of outcome - this is what makes the
# throttle work even when the network call fails.
echo "$NOW" > "$CACHE_FILE" 2>/dev/null || true

[ -z "$REMOTE_VERSION" ] && exit 0

if [ "$LOCAL_VERSION" != "$REMOTE_VERSION" ]; then
  echo "UPDATE_AVAILABLE $LOCAL_VERSION $REMOTE_VERSION https://github.com/$REPO_SLUG/compare/v$LOCAL_VERSION...v$REMOTE_VERSION"
fi
exit 0
