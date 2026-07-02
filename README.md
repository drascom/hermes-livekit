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
