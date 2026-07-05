# Mate Voice — kurulum sonrası

Mate Voice, Hermes'e LiveKit üzerinden **canlı sesli asistan** ekler: konuş, dinlesin, sesli yanıt versin.

## LiveKit — ek komut GEREKMEZ
Kurulumda sorulan **LIVEKIT_MODE** ne yaptığını belirler:
- **boş / `yeni`** (varsayılan): gateway **ilk başlatmada LiveKit'i otomatik kurar**
  (binary + key + config + systemd, 0.0.0.0) ve bağlantı değerlerini `.env`'e kendisi yazar.
- **`var`**: mevcut sunucunun bilgilerini gir: `hermes mate_voice reconfigure`
  (LiveKit URL + API key + secret sorar, `.env`'e yazar).

## Son adım
1. Gateway'i başlat / yeniden başlat:
   ```
   hermes gateway restart
   ```
2. Doğrulama — `~/.hermes/logs/gateway.log` içinde:
   `✓ mate_voice connected` ve `Gateway running with 1 platform(s)`.

## Client bağlantısı (pairing — otomatik)
Client'a (mate-mac) yalnız **tek adres** girilir; gerisi pairing ile otomatik dağıtılır:
- Sunucuda `hermes mate_voice pair-qr` → QR/link, client okutur → LiveKit URL,
  oda, client key, gateway adresi **kendiliğinden** gelir.
- Ya da client "Eşleştir" der → ekrandaki kodu herhangi bir Hermes kanalından
  `approve_pairing` ile onaylarsın.
- `X-Mate-Key`'i elle girmek yalnız gelişmiş senaryo içindir:
  `hermes mate_voice show-key` ile görülebilir.

## Sunucu sağlayıcı firewall'u (önemli)
Client dışarıdan bağlanacaksa şu portları sağlayıcının güvenlik duvarında
(OCI security list / AWS SG / Hetzner FW / ufw) **açın**:
- **7880/tcp** — LiveKit ws (sinyal)
- **7881/tcp** — LiveKit RTC/TCP fallback
- **7882/udp** — LiveKit medya (WebRTC, tek mux portu)
- **8830/tcp** — mate_voice token/pairing endpoint'i
- **8800/tcp** — Hermes gateway RPC (client oturum/araç kanalı; token korumalı)

## Ayarlar / bakım
- Bağlantı bilgilerini değiştir: `hermes mate_voice reconfigure` → gateway restart
- Girilen değerler: `LIVEKIT_URL/KEY/SECRET` (otomatik kurulumda kendisi yazar),
  `STT_HOST/PORT` (whisper), `VOX_HOST/PORT` (TTS), `MATE_VOICE_CLIENT_KEY`
  (boşsa ilk başlatmada otomatik üretilir)
- Not: TLS/domain kullanıyorsan client'a duyurulan adresi `MATE_PUBLIC_LIVEKIT_URL`
  ile sabitle; yoksa adres, client'ın sunucuya ulaştığı host'tan otomatik türetilir.
