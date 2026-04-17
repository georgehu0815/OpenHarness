#!/bin/sh
# tui-aca.sh — Launch the ohmo TUI inside the running ACA container.
# Usage:
#   ./tui-aca.sh              # fresh session
#   ./tui-aca.sh --continue   # resume latest session
#   ./tui-aca.sh --resume <id># resume session by id

set -e

RG="rg-copilot-usi-demo"
ACA_APP="brain-copilot-usi-demo-app"

# -- resolve the live replica -------------------------------------------
echo "Resolving replica..."
REPLICA=$(az containerapp replica list \
  --name "$ACA_APP" \
  --resource-group "$RG" \
  --query "[0].name" \
  --output tsv 2>/dev/null)

if [ -z "$REPLICA" ]; then
  echo "Error: no running replica found for $ACA_APP in $RG" >&2
  echo "  Check: az containerapp show --name $ACA_APP --resource-group $RG --query properties.runningStatus -o tsv" >&2
  exit 1
fi
echo "Replica: $REPLICA"

# -- capture local terminal dimensions before exec ---------------------
COLS=$(tput cols 2>/dev/null || echo 220)
ROWS=$(tput lines 2>/dev/null || echo 50)

# -- build the ohmo command from script args ---------------------------
OHMO_CMD="ohmo --workspace /data/ohmo --cwd /app"
case "${1:-}" in
  --continue)
    OHMO_CMD="$OHMO_CMD --continue"
    ;;
  --resume)
    if [ -z "${2:-}" ]; then
      echo "Error: --resume requires a session id" >&2; exit 1
    fi
    OHMO_CMD="$OHMO_CMD --resume $2"
    ;;
  "")
    ;;
  *)
    echo "Usage: $0 [--continue | --resume <session-id>]" >&2; exit 1
    ;;
esac

echo "Connecting (this may take a few seconds)..."
echo ""

# -- connect via expect (allocates its own PTY; no heredoc to az exec) --
# Shell variable expansion happens here in the heredoc — Tcl sees literals.
# expect waits for the shell prompt (#), sets terminal env, then launches TUI.
# interact hands the terminal to the user for the full TUI session.
if command -v expect >/dev/null 2>&1; then
  expect <<EXPECT_SCRIPT
log_user 1
set timeout 60
spawn az containerapp exec --name "$ACA_APP" --resource-group "$RG" --replica "$REPLICA" --command /bin/sh
expect "# "
send "export TERM=xterm-256color COLUMNS=$COLS LINES=$ROWS\r"
expect "# "
send "$OHMO_CMD\r"
interact
EXPECT_SCRIPT
else
  # Fallback: exec directly and print the startup command for the user to paste
  echo ">>> expect not found. After connecting, run:"
  echo "    export TERM=xterm-256color COLUMNS=$COLS LINES=$ROWS && $OHMO_CMD"
  echo ""
  exec az containerapp exec \
    --name "$ACA_APP" \
    --resource-group "$RG" \
    --replica "$REPLICA" \
    --command /bin/sh
fi

# ohmo --workspace /data/ohmo --cwd /app --resume b3f50e04e98b