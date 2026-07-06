#!/usr/bin/env bash
# mate_voice (Mate Voice / LiveKit) plugin'ini SIFIRDAN kurar:
#   1) Plugin'i kaldır            (hermes plugins remove)
#   2) ~/.hermes/.env'den LiveKit ile ilgili satırları temizle (önce yedek alır)
#   3) Plugin'i GitHub main'den yeniden kur  (hermes plugins install)
#
# Kurulumdan sonra yapılandırma:
#   hermes setup                 # "Mate Voice (LiveKit)" → LiveKit modu / STT / VOX / oda
#   hermes gateway restart
#   hermes mate_voice pair-qr    # client eşleştir
set -euo pipefail

ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
REPO="drascom/hermes-livekit"
PLUGIN="mate_voice"

# .env'den silinecek mate_voice (LiveKit + STT/VOX) anahtarları.
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

echo "==> 1) Plugin kaldırılıyor: $PLUGIN"
hermes plugins remove "$PLUGIN" || echo "   (kurulu değil — atlanıyor)"

echo "==> 2) .env temizleniyor: $ENV_FILE"
if [ -f "$ENV_FILE" ]; then
  backup="$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
  cp "$ENV_FILE" "$backup"
  echo "   yedek: $backup"
  for key in "${KEYS[@]}"; do
    sed -i "/^[[:space:]]*${key}=/d" "$ENV_FILE"
  done
  echo "   silinen anahtarlar: ${KEYS[*]}"
else
  echo "   .env bulunamadı — atlanıyor"
fi

echo "==> 3) Plugin yeniden kuruluyor: $REPO"
hermes plugins install "$REPO"

echo
echo "✓ Bitti. Sıradaki adımlar:"
echo "   hermes setup                 # Mate Voice → LiveKit modu / STT / VOX / oda"
echo "   hermes gateway restart"
echo "   hermes mate_voice pair-qr    # client eşleştir"
