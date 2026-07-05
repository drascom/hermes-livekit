# hermes-livekit

LiveKit voice platform adapter for **Hermes Agent** — the **Mate/Candan** voice stack as a
single `BasePlatformAdapter` plugin: RMS endpointing, smart-turn v3 EOU, barge-in, wake-word
gate, live transcript, speaker-ID, and an ack'd RPC handshake with clients.

## Kurulum

```bash
hermes plugins install drascom/hermes-livekit
```

Güncelleme (git tabanlı):

```bash
hermes plugins update mate_voice
```

Plugin ayrıca periyodik olarak yeni sürümü kontrol eder ve sesli olarak haber verir;
onay verdiğinde kendini `hermes plugins update` ile günceller.

## Yapılandırma

`.env.example`'ı kopyalayıp `.env` yapın ve doldurun (LiveKit URL/secret, STT/TTS host'ları,
oda, token sunucusu). Örnek host'lar generic'tir — kendi altyapınızla değiştirin.

## LiveKit sunucusunu plugin ile kurma (opsiyonel)

Elinizde çalışan bir LiveKit yoksa plugin'in setup script'i her şeyi kurar:
binary indirir (GitHub releases, linux amd64/arm64/armv7), crypto-random API
key/secret üretir, minimal `livekit.yaml` yazar, systemd unit'i kurup başlatır
ve plugin `.env`'ini günceller (`LIVEKIT_URL/API_KEY/API_SECRET`) — pairing
config paketi böylece otomatik doğru değerleri dağıtır.

```bash
# mesh (NetBird/Tailscale) kurulumu — önerilen; TLS gerekmez
python3 ~/.hermes/plugins/mate_voice/setup_livekit.py --bind mesh --ip 100.x.y.z

# sadece localhost
python3 ~/.hermes/plugins/mate_voice/setup_livekit.py

# önce ne yapacağını gör
python3 ~/.hermes/plugins/mate_voice/setup_livekit.py --dry-run
```

Seçenekler: `--bind {loopback,mesh,public}`, `--ip`, `--prefix` (default
`~/.hermes/mate_voice/livekit`), `--livekit-version vX.Y.Z`, `--no-systemd`,
`--force`, `--dry-run`. **Idempotent:** mevcut binary/config/env değerlerine
sormadan dokunmaz; `--force` ile ezilir. macOS'ta systemd yerine elle başlatma
komutu basılır (binary için `brew install livekit`).

**TLS/TURN notu:** `--bind public` seçerseniz tarayıcı/uzak client'lar için
domain + sertifika (wss) ve NAT arkasında TURN şarttır — bunu script
otomatikleştirmez; Caddy/nginx reverse proxy kurun. Mesh-only kurulumda
(NetBird/Tailscale) TLS gerekmez, `ws://` yeterlidir.

## Bağımlı / ilişkili repolar

Bu plugin tek başına çalışmaz; şu bileşenlere bağlıdır (aynı Mate/Candan sistemi):

- **STT / TTS servisleri** → [`drascom/mate-media`](https://github.com/drascom/mate-media)
  *(planlanan)* — whisper (Wyoming STT) + vox (TTS). Plugin `STT_HOST`/`VOX_HOST` ile bunlara bağlanır.
- **İstemciler** → [`drascom/mate-clients`](https://github.com/drascom/mate-clients)
  *(planlanan)* — mate-mac (+ ilerde mate-ios, mate-android, mate-satellite). LiveKit odasına
  bağlanıp bu plugin'le RPC handshake (`mate.hello` / `mate.set_awake`) yapar.
- **LiveKit sunucusu** — ayrı LiveKit server kurulumu gerekir (agent `LIVEKIT_URL` ile bağlanır).

## Lisans

Özel — Mate/Candan asistan sistemi.
