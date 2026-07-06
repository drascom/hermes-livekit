#!/usr/bin/env bash
# Hermes LiveKit (hermes_livekit) eklentisini + LiveKit sunucusunu KOMPLE kaldırır.
#
# NEDEN AYRI SCRIPT: `hermes plugins remove` yalnız plugin KODUNU siler
# (~/.hermes/plugins/hermes_livekit). LiveKit sunucusu ayrı bir systemd servisi
# + binary + config + veri olduğu için plugin remove ile KALKMAZ. Hermes
# çekirdeğinde uninstall-hook yok, bu yüzden teardown'u bu script yapar.
#
# Kaldırdıkları:
#   1) plugin kodu           (hermes plugins remove hermes_livekit)
#   2) LiveKit systemd servisi + binary + config  (~/.hermes/mate_voice/livekit)
#   3) .env'deki LiveKit + STT/VOX anahtarları     (önce yedek alır)
#   4) (opsiyonel, sorar) eşleşme + ses-kimlik verisi (pairing.db / speakers.db)
set -euo pipefail

ENV_FILE="${HERMES_HOME:-$HOME/.hermes}/.env"
DATA_DIR="${HERMES_HOME:-$HOME/.hermes}/mate_voice"     # veri dizini (rename'de korunur)
LK_DIR="$DATA_DIR/livekit"
UNIT=/etc/systemd/system/livekit-server.service
PLUGIN="hermes_livekit"
TTYIN=/dev/tty; [ -e /dev/tty ] || TTYIN=/dev/null

echo "==> 1) Plugin kaldırılıyor: $PLUGIN"
hermes plugins remove "$PLUGIN" < "$TTYIN" || echo "   (kurulu değil — atlanıyor)"

echo "==> 2) LiveKit servisi + dosyaları kaldırılıyor"
if systemctl list-unit-files 2>/dev/null | grep -q "^livekit-server.service"; then
  sudo systemctl disable --now livekit-server 2>/dev/null || true
  sudo rm -f "$UNIT"
  sudo systemctl daemon-reload
  echo "   servis durduruldu + kaldırıldı"
else
  echo "   livekit-server servisi yok — atlanıyor"
fi
rm -rf "$LK_DIR" && echo "   $LK_DIR silindi" || true

echo "==> 3) .env temizleniyor: $ENV_FILE"
if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "$ENV_FILE.bak.$(date +%Y%m%d_%H%M%S)"
  for key in LIVEKIT_MODE LIVEKIT_URL LIVEKIT_API_KEY LIVEKIT_API_SECRET \
             MATE_LIVEKIT_ROOM MATE_PUBLIC_LIVEKIT_URL MATE_PUBLIC_TOKEN_URL \
             MATE_VOICE_CLIENT_KEY STT_HOST STT_PORT VOX_HOST VOX_PORT; do
    sed -i "/^[[:space:]]*${key}=/d" "$ENV_FILE"
  done
  echo "   LiveKit + STT/VOX anahtarları silindi (yedek alındı)"
fi

echo "==> 4) Eşleşme + ses-kimlik verisi (pairing.db / speakers.db) de silinsin mi?"
read -r -p "   Sil? [e/H]: " ans < "$TTYIN" || ans=""
case "$ans" in
  e|E|y|Y) rm -f "$DATA_DIR/pairing.db" "$DATA_DIR/speakers.db"; echo "   veri silindi" ;;
  *) echo "   veri korundu ($DATA_DIR)" ;;
esac

echo
echo "✓ Hermes LiveKit tamamen kaldırıldı."
echo "  Gateway'i tazelemek istersen: hermes gateway restart"
