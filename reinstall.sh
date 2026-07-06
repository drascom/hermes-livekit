#!/usr/bin/env bash
# hermes_livekit (Hermes LiveKit / LiveKit) plugin'ini SIFIRDAN kurar:
#   1) Plugin'i kaldır            (hermes plugins remove)
#   2) ~/.hermes/.env'den LiveKit ile ilgili satırları temizle (önce yedek alır)
#   3) Plugin'i GitHub main'den yeniden kur  (hermes plugins install)
#
# Kurulumdan sonra yapılandırma:
#   hermes setup                 # "Hermes LiveKit" → LiveKit modu / STT / VOX / oda
#   hermes gateway restart
#   hermes hermes_livekit pair-qr    # client eşleştir
#
# NOT: `curl ... | bash` altında script'in kendisi stdin'dedir; interaktif
# hermes promptu bunu "cevap" sanıp otomatik geçerdi. Bu yüzden interaktif
# hermes komutlarının stdin'ini gerçek terminale (/dev/tty) yönlendiririz —
# SADECE o komuta (tüm shell'e DEĞİL; yoksa bash script'i terminalden okumaya
# çalışıp bozulur). Terminal yoksa /dev/null → promptlar temiz atlanır.
set -euo pipefail

ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
TTYIN=/dev/tty; [ -e /dev/tty ] || TTYIN=/dev/null
REPO="drascom/hermes-livekit"
PLUGIN="hermes_livekit"

# .env'den silinecek hermes_livekit (LiveKit + STT/VOX) anahtarları.
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
hermes plugins remove "$PLUGIN" < "$TTYIN" || echo "   (kurulu değil — atlanıyor)"

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
hermes plugins install "$REPO" < "$TTYIN"

echo
echo "✓ Bitti. Sıradaki adımlar:"
echo "   hermes setup                 # Hermes LiveKit → LiveKit modu / STT / VOX / oda"
echo "   hermes gateway restart"
echo "   hermes hermes_livekit pair-qr    # client eşleştir"
