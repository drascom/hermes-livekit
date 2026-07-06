# Mate Voice installed

Mate Voice adds a live voice channel to Hermes through LiveKit.

## What to do next

1. Restart the Hermes gateway:

   ```bash
   hermes gateway restart
   ```

2. Open the gateway setup screen if you want to review or change settings:

   ```bash
   hermes setup gateway
   ```

3. Pair your Mate client:

   ```bash
   hermes mate_voice pair-qr
   ```

Scan the QR code or open the link in the Mate client. The client receives the
LiveKit URL, room, client key, and gateway address automatically.

## LiveKit setup

During setup, choose one of these:

- **New LiveKit server**: Mate Voice installs and configures LiveKit on the
  first gateway start.
- **Existing LiveKit server**: enter your LiveKit URL, API key, and API secret.

To change these values later:

```bash
hermes mate_voice reconfigure
hermes gateway restart
```

## Required services

Mate Voice also needs your STT and TTS services:

- `STT_HOST` / `STT_PORT` for Whisper STT
- `VOX_HOST` / `VOX_PORT` for VOX TTS

You can set them during `hermes setup gateway` or later with
`hermes mate_voice reconfigure`.

## Firewall ports

If clients connect from outside the server, open these ports:

- `7880/tcp` for LiveKit signaling
- `7881/tcp` for LiveKit TCP fallback
- `7882/udp` for LiveKit media
- `8830/tcp` for Mate Voice pairing and tokens
- `8800/tcp` for the Hermes gateway

## Useful commands

```bash
hermes mate_voice pair-qr       # pair a client
hermes mate_voice show-key      # show the client key
hermes mate_voice reconfigure   # change settings
hermes gateway restart          # restart after changes
```
