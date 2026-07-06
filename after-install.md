# Hermes LiveKit installed

Hermes LiveKit adds a live voice channel to Hermes through LiveKit.

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
   hermes hermes_livekit pair-qr
   ```

Scan the QR code or open the link in the Mate client. The client receives the
LiveKit URL, room, client key, and gateway address automatically.

## LiveKit setup

During setup, choose one of these:

- **New LiveKit server**: Hermes LiveKit installs and configures LiveKit on the
  first gateway start.
- **Existing LiveKit server**: enter your LiveKit URL, API key, and API secret.

To change these values later:

```bash
hermes hermes_livekit reconfigure
hermes gateway restart
```

## Required services

Hermes LiveKit also needs your STT and TTS services:

- `STT_HOST` / `STT_PORT` for Whisper STT
- `VOX_HOST` / `VOX_PORT` for VOX TTS

You can set them during `hermes setup gateway` or later with
`hermes hermes_livekit reconfigure`.

## Firewall ports

If clients connect from outside the server, open these ports:

- `7880/tcp` for LiveKit signaling
- `7881/tcp` for LiveKit TCP fallback
- `7882/udp` for LiveKit media
- `8830/tcp` for Hermes LiveKit pairing and tokens
- `8800/tcp` for the Hermes gateway

## Useful commands

```bash
hermes hermes_livekit pair-qr       # pair a client
hermes hermes_livekit show-key      # show the client key
hermes hermes_livekit reconfigure   # change settings
hermes gateway restart          # restart after changes
```

## Uninstall

`hermes plugins remove hermes_livekit` removes only the plugin code. The LiveKit
server (its systemd service, binary, config, and data) is separate and keeps
running. To remove everything in one step:

```bash
curl -fsSL https://raw.githubusercontent.com/drascom/hermes-livekit/main/uninstall.sh | bash
```

This removes the plugin, the `livekit-server` service and
`~/.hermes/mate_voice/livekit`, and the LiveKit/STT/VOX keys in `~/.hermes/.env`
(backed up first); it also offers to delete the pairing and speaker databases.
