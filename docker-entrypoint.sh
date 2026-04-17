#!/bin/sh
# Entrypoint for the ohmo gateway container.
# Generates gateway.json from env vars if OHMO_TELEGRAM_TOKEN is set,
# then hands off to the CMD (ohmo gateway run).
set -e

WORKSPACE="${OHMO_WORKSPACE:-/data/ohmo}"
CONFIG_FILE="$WORKSPACE/gateway.json"

mkdir -p "$WORKSPACE/skills"

# Seed bundled skills into the workspace on every startup.
# Stored at /app/bundled-skills/ (outside the /data/ohmo volume) so they
# are never hidden by the volume mount overlay.
# -n (no-clobber) means user-placed skills in the volume are never overwritten.
if [ -d /app/bundled-skills ] && [ "$(ls -A /app/bundled-skills 2>/dev/null)" ]; then
    cp -rn /app/bundled-skills/. "$WORKSPACE/skills/"
    echo "[entrypoint] seeded skills: $(ls /app/bundled-skills | tr '\n' ' ')"
fi

# Generate gateway.json whenever OHMO_TELEGRAM_TOKEN is supplied.
# This lets ACA secrets drive the entire config without a volume mount.
# If you prefer to mount a pre-built gateway.json, just don't set
# OHMO_TELEGRAM_TOKEN and the existing file is used as-is.
if [ -n "$OHMO_TELEGRAM_TOKEN" ]; then
    PROVIDER="${OHMO_PROVIDER_PROFILE:-azure-openai}"
    PERMISSION="${OHMO_PERMISSION_MODE:-full_auto}"

    # Build enabled_channels list
    ENABLED_CHANNELS='"telegram"'
    CHANNEL_CONFIGS='"telegram": {
      "allow_from": ["*"],
      "token": "'"$OHMO_TELEGRAM_TOKEN"'",
      "reply_to_message": true
    }'

    if [ -n "$WEBUI_PORT" ]; then
        ENABLED_CHANNELS="$ENABLED_CHANNELS, \"webui\""
        CORS_LIST="[]"
        if [ -n "$WEBUI_CORS_ORIGINS" ]; then
            # Convert comma-separated string to JSON array
            CORS_LIST=$(echo "$WEBUI_CORS_ORIGINS" | awk -F',' '{
                printf "[";
                for(i=1;i<=NF;i++) {
                    gsub(/^ +| +$/, "", $i);
                    printf "\"" $i "\"";
                    if(i<NF) printf ",";
                }
                printf "]"
            }')
        fi
        CHANNEL_CONFIGS="$CHANNEL_CONFIGS,
    \"webui\": {
      \"port\": $WEBUI_PORT,
      \"allow_from\": [\"*\"],
      \"cors_origins\": $CORS_LIST
    }"
    fi

    cat > "$CONFIG_FILE" <<EOF
{
  "provider_profile": "$PROVIDER",
  "enabled_channels": [$ENABLED_CHANNELS],
  "session_routing": "chat-thread",
  "send_progress": true,
  "send_tool_hints": true,
  "permission_mode": "$PERMISSION",
  "sandbox_enabled": false,
  "allow_remote_admin_commands": false,
  "allowed_remote_admin_commands": [],
  "log_level": "${OHMO_LOG_LEVEL:-INFO}",
  "channel_configs": {
    $CHANNEL_CONFIGS
  }
}
EOF
    echo "[entrypoint] wrote $CONFIG_FILE (profile=$PROVIDER permission=$PERMISSION)"
elif [ ! -f "$CONFIG_FILE" ]; then
    echo "[entrypoint] OHMO_TELEGRAM_TOKEN not set and $CONFIG_FILE not found — gateway will start with defaults (no channels enabled)"
fi

exec "$@"
