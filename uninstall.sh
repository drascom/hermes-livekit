#!/usr/bin/env bash
# COMPLETELY remove the Hermes LiveKit (hermes_livekit) plugin AND the LiveKit server.
#
# WHY A SEPARATE SCRIPT: `hermes plugins remove` deletes only the plugin CODE
# (~/.hermes/plugins/hermes_livekit). The LiveKit server is a separate systemd
# service + binary + config + data, so it does NOT come down with plugin remove.
# Hermes core has no uninstall hook, so this script performs the teardown.
#
# What it removes:
#   1) plugin code           (hermes plugins remove hermes_livekit)
#   2) LiveKit systemd service + binary + config  (~/.hermes/mate_voice/livekit)
#   3) LiveKit + STT/VOX keys in .env             (backed up first)
#   4) (optional, prompts) pairing + speaker-ID data (pairing.db / speakers.db)
set -euo pipefail

ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
CONFIG_YAML="${HERMES_HOME:-$HOME/.hermes}/config.yaml"
DATA_DIR="${HERMES_HOME:-$HOME/.hermes}/mate_voice"     # data dir (kept across the rename)
LK_DIR="$DATA_DIR/livekit"
UNIT=/etc/systemd/system/livekit-server.service
PLUGIN="hermes_livekit"
TTYIN=/dev/tty; [ -e /dev/tty ] || TTYIN=/dev/null

echo "==> 1) Removing plugin: $PLUGIN"
hermes plugins remove "$PLUGIN" < "$TTYIN" || echo "   (not installed - skipping)"

# `hermes plugins remove` deletes the code but leaves the name in
# config.yaml `plugins.enabled` -> the gateway then tries to load a plugin whose
# dir is gone (ModuleNotFoundError). Strip the enabled entry so removal is clean.
if [ -f "$CONFIG_YAML" ] && grep -qE "^[[:space:]]*-[[:space:]]*${PLUGIN}[[:space:]]*\$" "$CONFIG_YAML"; then
  cp "$CONFIG_YAML" "$CONFIG_YAML.bak.$(date +%Y%m%d_%H%M%S)"
  sed -i "/^[[:space:]]*-[[:space:]]*${PLUGIN}[[:space:]]*\$/d" "$CONFIG_YAML"
  echo "   removed '$PLUGIN' from config.yaml plugins.enabled"
fi

echo "==> 2) Removing LiveKit service + files"
if systemctl list-unit-files 2>/dev/null | grep -q "^livekit-server.service"; then
  sudo systemctl disable --now livekit-server 2>/dev/null || true
  sudo rm -f "$UNIT"
  sudo systemctl daemon-reload
  echo "   service stopped + removed"
else
  echo "   livekit-server service not present - skipping"
fi
rm -rf "$LK_DIR" && echo "   deleted $LK_DIR" || true

echo "==> 3) Cleaning .env: $ENV_FILE"
if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
  for key in LIVEKIT_MODE LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET \
             MATE_LIVEKIT_ROOM MATE_PUBLIC_LIVEKIT_URL MATE_PUBLIC_TOKEN_URL \
             MATE_VOICE_CLIENT_KEY STT_HOST STT_PORT VOX_HOST VOX_PORT; do
    sed -i "/^[[:space:]]*${key}=/d" "$ENV_FILE"
  done
  echo "   removed LiveKit + STT/VOX keys (backed up)"
fi

echo "==> 4) Also delete pairing + speaker-ID data (pairing.db / speakers.db)?"
read -r -p "   Delete? [y/N]: " ans < "$TTYIN" || ans=""
case "$ans" in
  y|Y) rm -f "$DATA_DIR/pairing.db" "$DATA_DIR/speakers.db"; echo "   data deleted" ;;
  *) echo "   data kept ($DATA_DIR)" ;;
esac

echo
echo "✓ Hermes LiveKit completely removed."
echo "  To refresh the gateway: hermes gateway restart"
