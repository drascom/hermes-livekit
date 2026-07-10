"""Env-driven config shim for the Mate voice plugin.

Builds a `settings` object from environment variables (plain os.getenv — no
pydantic dependency, keeps the Hermes venv install light).

SELF-CONTAINED: önce plugin'in KENDİ `.env`'ini (plugin kök dizini) os.environ'a
yükler (setdefault — mevcut env/systemd/global ~/.hermes/.env değerlerini EZMEZ,
yalnız boşları doldurur). Böylece "gerekli her şey plugin klasöründe": kurulumda
`.env.example` → `.env` (Hermes installer kopyalar), kullanıcı doldurur, plugin
okur. `.env` gitignored; `.env.example` commit'li (açıklamalı şablon).
"""

import os
import secrets
import sys
from pathlib import Path

from .instance import is_auto_room, load_instance_identity

_PLUGIN_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"  # <plugin>/.env


def _load_plugin_env() -> None:
    """Plugin kök dizinindeki `.env`'i os.environ'a yükle (setdefault). Basit
    parser (python-dotenv deps'i gerekmez): KEY=VALUE, # yorum, boş satır atla,
    çevreleyen tırnakları soy. Zaten set olan anahtarı EZMEZ."""
    env_path = _PLUGIN_ENV_PATH
    try:
        if not env_path.is_file():
            return
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            # Satır-içi yorum ayıkla (eski şablonda `DEĞER   # açıklama` vardı;
            # yorum değerin parçası sanılıyordu → çöp secret/dil değerleri).
            if not (val.startswith('"') or val.startswith("'")):
                val = val.split(" #", 1)[0].split("\t#", 1)[0].strip()
                if val == "#" or val.startswith("# "):
                    val = ""
            val = val.strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass  # fail-open: .env okunamazsa global env / default'lara düş


_load_plugin_env()


def _persist_client_key(key: str) -> bool:
    """`MATE_VOICE_CLIENT_KEY=<key>` satırını plugin .env'e yaz/güncelle. Fail-open."""
    path = _PLUGIN_ENV_PATH
    line = f"MATE_VOICE_CLIENT_KEY={key}"
    try:
        if path.is_file():
            lines = path.read_text(encoding="utf-8").splitlines()
            out, replaced = [], False
            for ln in lines:
                if ln.strip().split("=", 1)[0].strip() == "MATE_VOICE_CLIENT_KEY":
                    out.append(line)
                    replaced = True
                else:
                    out.append(ln)
            if not replaced:
                out.append(line)
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
        else:
            path.write_text(line + "\n", encoding="utf-8")
        return True
    except Exception:
        return False  # izin yoksa çökme — banner yine de gösterilir


def _print_key_banner(key: str, persisted: bool) -> None:
    saved = "Plugin .env'e kaydedildi." if persisted else "UYARI: .env'e YAZILAMADI (izin?) — elle ekleyin."
    box = (
        "\n"
        "╔═══════════════════════════════════════════════════════════════╗\n"
        "║  🔑 MATE_VOICE_CLIENT_KEY üretildi (ilk kurulum)              ║\n"
        "╠═══════════════════════════════════════════════════════════════╣\n"
        f"║  {key}\n"
        "║  Bu değeri client (mate-mac) ayarlarına 'X-Mate-Key' / Client\n"
        f"║  Key olarak girin. {saved}\n"
        "╚═══════════════════════════════════════════════════════════════╝\n"
    )
    try:
        import logging
        logging.getLogger("hermes_livekit.config").warning(
            "MATE_VOICE_CLIENT_KEY üretildi: %s (%s)", key,
            "persisted" if persisted else "persist FAILED")
    except Exception:
        pass
    print(box, file=sys.stderr, flush=True)
    _print_key_qr(key)


def _print_key_qr(key: str) -> None:
    """Key'i terminal ASCII QR olarak bas. qrcode yoksa kurmayı dene; olmazsa atla
    (fail-open — düz-metin banner zaten gösterildi, asla çökme)."""
    try:
        import importlib.util
        if importlib.util.find_spec("qrcode") is None:
            try:
                from ._deps import _pip_install
                _pip_install(["qrcode"])
                importlib.invalidate_caches()
            except Exception:
                pass
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(key)
        qr.make(fit=True)
        print("  (mate-mac ile kamera/QR taransın):", file=sys.stderr, flush=True)
        qr.print_ascii(out=sys.stderr)
    except Exception:
        pass  # QR atlandı; metin key yine de görünür


_CLIENT_KEY_CHECKED = False


def _ensure_client_key() -> None:
    """Key boşsa üret + persist + banner. İdempotent + modül-seviyesi tek-sefer guard."""
    global _CLIENT_KEY_CHECKED
    if _CLIENT_KEY_CHECKED:
        return
    _CLIENT_KEY_CHECKED = True
    if (os.getenv("MATE_VOICE_CLIENT_KEY") or "").strip():
        return  # zaten dolu → no-op, banner yok
    key = secrets.token_hex(24)
    os.environ["MATE_VOICE_CLIENT_KEY"] = key
    # GLOBAL ~/.hermes/.env'e yaz (plugin .env DEĞİL): `hermes plugins install
    # --force` plugin dizinini sıfırlar → plugin .env'deki key kaybolur → yeniden
    # üretilir → bağlı client'lar kopar. Global .env install --force'tan etkilenmez.
    # Fail-open: Hermes util import edilemezse (test / Hermes yok) eski davranış.
    persisted = False
    try:
        from hermes_cli.config import save_env_value
        save_env_value("MATE_VOICE_CLIENT_KEY", key)
        persisted = True
    except Exception:
        persisted = _persist_client_key(key)  # fallback: plugin .env
    _print_key_banner(key, persisted)


_ensure_client_key()


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except (TypeError, ValueError):
        return default


def _b(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _s(name: str, default: str) -> str:
    return os.getenv(name) or default


class _Settings:
    """Mirror of the subset of brain.config.Settings the voice modules touch."""

    def __init__(self) -> None:
        # --- STT (Wyoming whisper) ---
        self.stt_host = _s("STT_HOST", "localhost")
        self.stt_port = _i("STT_PORT", 10300)
        self.stt_language = _s("STT_LANGUAGE", "")
        self.stt_default_engine = _s("STT_DEFAULT_ENGINE", "whisper")
        # Optional alt engine (nemotron) host:port — same Wyoming protocol.
        self.stt_engines = {
            "whisper": (self.stt_host, self.stt_port),
            "nemotron": (_s("STT_NEMOTRON_HOST", self.stt_host), _i("STT_NEMOTRON_PORT", 10301)),
        }

        # --- TTS (vox bridge / piper) ---
        self.tts_engine = _s("TTS_ENGINE", "vox")
        self.tts_host = _s("TTS_HOST", "localhost")
        self.tts_port = _i("TTS_PORT", 10200)
        self.vox_host = _s("VOX_HOST", "localhost")
        self.vox_port = _i("VOX_PORT", 8808)
        self.vox_api_key = _s("VOX_API_KEY", "")

        # --- Speaker-ID (CAM++ sherpa-onnx) ---
        self.speaker_id_enabled = _b("SPEAKER_ID_ENABLED", False)
        self.speaker_model_path = _s("SPEAKER_MODEL_PATH", "")
        self.speaker_model_id = _s("SPEAKER_MODEL_ID", "campplus_zh_en_advanced_v1")
        self.speaker_threshold = _f("SPEAKER_THRESHOLD", 0.45)
        self.speaker_margin = _f("SPEAKER_MARGIN", 0.05)
        self.speaker_min_seconds = _f("SPEAKER_MIN_SECONDS", 1.0)
        self.speaker_enroll_min_seconds = _f("SPEAKER_ENROLL_MIN_SECONDS", 4.0)
        # Oto-onboarding: bağlantıda ilk BİLİNMEYEN ses duyulunca bir kez
        # "seni tanımıyorum, adın ne?" diye sorup enroll ak. Ret → sessiz guest.
        self.onboarding_enabled = _b("ONBOARDING_ENABLED", True)
        # On-demand video kare yakalama (vision). Açıkken video track'ler subscribe
        # edilip `mate.capture_frame` ile tek kare çekilebilir; Pillow auto-install.
        self.video_capture_enabled = _b("MATE_VOICE_VIDEO_CAPTURE_ENABLED", True)
        self.barge_in_speaker_gate = _b("BARGE_IN_SPEAKER_GATE", True)
        self.barge_in_speaker_min_seconds = _f("BARGE_IN_SPEAKER_MIN_SECONDS", 0.6)
        self.barge_in_speaker_threshold = _f("BARGE_IN_SPEAKER_THRESHOLD", self.speaker_threshold)

        # --- Smart-turn v3 EOU ---
        self.turn_detector_enabled = _b("TURN_DETECTOR_ENABLED", True)
        self.turn_detector_repo = _s("TURN_DETECTOR_REPO", "pipecat-ai/smart-turn-v3")
        self.turn_detector_file = _s("TURN_DETECTOR_FILE", "smart-turn-v3.2-cpu.onnx")
        # Threshold 0.5→0.65: cümle-ortası duraksamayı "tamam" sayıp kullanıcıyı
        # KESMESİN (p 0.5-0.65 arası artık "devam"). min_endpointing 1.6→2.2:
        # EOU kontrolünden önce daha uzun sessizlik bekle → akıcı cümle bölünmesin.
        self.turn_detector_threshold = _f("TURN_DETECTOR_THRESHOLD", 0.65)
        self.turn_min_endpointing_delay = _f("TURN_MIN_ENDPOINTING_DELAY", 2.2)
        self.turn_max_endpointing_delay = _f("TURN_MAX_ENDPOINTING_DELAY", 6.0)
        self.turn_recheck_interval = _f("TURN_RECHECK_INTERVAL", 0.4)

        # --- LiveKit ---
        # Every plugin installation owns a stable generated room. The legacy
        # default `mate-hermes-test` migrates to auto; a different explicit
        # MATE_LIVEKIT_ROOM remains an operator override. Never inherit the
        # brain's LIVEKIT_ROOM: two gateways would otherwise collide.
        self.livekit_url = _s("LIVEKIT_URL", "ws://127.0.0.1:7880")
        self.livekit_api_key = _s("LIVEKIT_API_KEY", "devkey")
        self.livekit_api_secret = _s("LIVEKIT_API_SECRET", "")
        configured_room = _s("MATE_LIVEKIT_ROOM", "auto")
        instance = load_instance_identity(configured_room)
        self.instance_id = instance.instance_id
        self.livekit_room = instance.room
        self.instance_state_path = str(instance.state_path)
        self.livekit_token_ttl_seconds = _i("LIVEKIT_TOKEN_TTL_SECONDS", 3600)
        # Public LiveKit URL handed to CLIENTS via the token endpoint (clients
        # can't reach the agent's internal ws://127.0.0.1:7880). Falls back to
        # livekit_url if unset.
        self.public_livekit_url = _s("MATE_PUBLIC_LIVEKIT_URL", "") or self.livekit_url

        # --- Token endpoint (clients fetch room-scoped join tokens; secret stays
        #     on the server). Disabled if client_key is empty. ---
        self.token_port = _i("MATE_VOICE_TOKEN_PORT", 8830)
        self.token_bind = _s("MATE_VOICE_TOKEN_BIND", "0.0.0.0")
        self.client_key = _s("MATE_VOICE_CLIENT_KEY", "")
        # TTL for client tokens minted by the endpoint.
        self.client_token_ttl_seconds = _i("MATE_VOICE_CLIENT_TOKEN_TTL", 3600)

        # --- Onboarding (sihirbaz): açık /mate/demo-token rotası (key'siz, kısa
        #     ömürlü). onboarding_room boşsa ana odaya düşülür (agent zaten orada)
        #     → iki-oda (S3) gelene kadar demo işlevsel kalır. ---
        onboarding_room = _s("MATE_ONBOARDING_ROOM", "")
        self.onboarding_room = (
            self.livekit_room if is_auto_room(onboarding_room) else onboarding_room
        )
        self.demo_token_ttl_seconds = _i("MATE_VOICE_DEMO_TOKEN_TTL", 600)
        # Açık demo rotası güvenlik kapısı: varsayılan AÇIK; kapatmak için "0".
        self.demo_token_enabled = _b("MATE_VOICE_DEMO_TOKEN_ENABLED", True)

    def resolve_stt_engine(self, engine):
        """(name, host, port). Unknown/missing → default (whisper)."""
        name = engine or self.stt_default_engine
        if name not in self.stt_engines:
            name = self.stt_default_engine
        if name == self.stt_default_engine:
            return name, self.stt_host, self.stt_port
        host, port = self.stt_engines[name]
        return name, host, port


settings = _Settings()
