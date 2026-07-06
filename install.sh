#!/usr/bin/env bash
# Install the hermes_livekit (Hermes LiveKit) plugin FROM SCRATCH
# (removes any existing install first, so it doubles as a clean reinstall):
#   1) Remove the plugin           (hermes plugins remove)
#   2) Strip LiveKit-related keys from ~/.hermes/.env (backed up first)
#   3) Reinstall the plugin from GitHub main  (hermes plugins install)
#
# Configure after installing:
#   hermes setup gateway             # "Hermes LiveKit" -> LiveKit mode / STT / VOX / room
#   hermes gateway restart
#   hermes hermes_livekit pair-qr    # pair a client
#
# NOTE: Under `curl ... | bash` the script itself is on stdin, so an interactive
# hermes prompt would read the script's own lines as "answers" and auto-skip.
# We therefore redirect stdin to the real terminal (/dev/tty) ONLY for the
# interactive hermes commands (not the whole shell — that would make bash read
# the rest of the script from the terminal and break it). No terminal -> /dev/null
# so prompts are cleanly skipped.
set -euo pipefail

ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
TTYIN=/dev/tty; [ -e /dev/tty ] || TTYIN=/dev/null
REPO="drascom/hermes-livekit"
PLUGIN="hermes_livekit"

# hermes_livekit (LiveKit + STT/VOX) keys to remove from .env.
KEYS=(
  LIVEKIT_MODE
  LIVEKIT_URL
  LIVEKIT_API_KEY
  LIVEKIT_API_SECRET
  MATE_LIVEKIT_ROOM
  MATE_PUBLIC_LIVEKIT_URL
  STT_HOST
  STT_PORT
  VOX_HOST
  VOX_PORT
)

echo "==> 1) Removing plugin: $PLUGIN"
hermes plugins remove "$PLUGIN" < "$TTYIN" || echo "   (not installed - skipping)"

echo "==> 2) Cleaning .env: $ENV_FILE"
if [ -f "$ENV_FILE" ]; then
  backup="$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$ENV_FILE" "$backup"
  echo "   backup: $backup"
  for key in "${KEYS[@]}"; do
    sed -i "/^[[:space:]]*${key}=/d" "$ENV_FILE"
  done
  echo "   removed keys: ${KEYS[*]}"
else
  echo "   .env not found - skipping"
fi

echo "==> 3) Reinstalling plugin: $REPO"
hermes plugins install "$REPO" < "$TTYIN"

echo
echo "✓ Done. Next steps:"
echo "   hermes setup gateway             # Hermes LiveKit -> LiveKit mode / STT / VOX / room"
echo "   hermes gateway restart"
echo "   hermes hermes_livekit pair-qr    # pair a client"
