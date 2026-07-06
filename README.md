# Hermes LiveKit for Hermes (LiveKit voice plugin)

Hermes LiveKit is a Hermes plugin that adds a live voice channel through LiveKit.
You speak to a Mate client, Hermes listens, and the reply is spoken back.

## Install

```bash
hermes plugins install drascom/hermes-livekit
hermes gateway restart
```

To update later:

```bash
hermes plugins update hermes_livekit
hermes gateway restart
```

## Setup

Run the Hermes gateway setup flow:

```bash
hermes setup gateway
```

Choose **Hermes LiveKit** and enter:

- Whether Hermes LiveKit should install a new LiveKit server or use an existing one
- `STT_HOST` and `STT_PORT` for Whisper STT
- `VOX_HOST` and `VOX_PORT` for VOX TTS

If you choose a new LiveKit server, Hermes LiveKit installs and configures it on
the first gateway start.

If you already have LiveKit, enter the LiveKit URL, API key, and API secret.

## Pair a client

After the gateway is running:

```bash
hermes hermes_livekit pair-qr
```

Scan the QR code or open the link in the Mate client. Pairing sends the client
everything it needs: LiveKit URL, room, client key, and gateway address.

## Change settings

```bash
hermes hermes_livekit reconfigure
hermes gateway restart
```

Useful commands:

```bash
hermes hermes_livekit pair-qr       # pair a client
hermes hermes_livekit show-key      # show the client key
hermes hermes_livekit check-update  # check for plugin updates
```

## Firewall

If clients connect from outside the server, open:

- `7880/tcp` for LiveKit signaling
- `7881/tcp` for LiveKit TCP fallback
- `7882/udp` for LiveKit media
- `8830/tcp` for Hermes LiveKit pairing and tokens
- `8800/tcp` for the Hermes gateway

## Related components

Hermes LiveKit expects separate STT and TTS services:

- Whisper STT, configured with `STT_HOST` and `STT_PORT`
- VOX TTS, configured with `VOX_HOST` and `VOX_PORT`
