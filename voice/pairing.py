"""Tek-URL pairing — store + config paketi (mate_voice, stdlib-only).

Client tek adres girer (https://mate-token.drascom.uk) → POST /pair/request →
kısa kod ekranda → kullanıcı HERHANGİ bir Hermes kanalından `approve_pairing`
tool'u ile onaylar → client GET /pair/status ile config paketini TEK SEFER alır.
Alternatif: sunucuda `pair_qr.py` (veya `hermes mate_voice pair-qr`) tek
kullanımlık ticket + QR üretir → client GET /pair/claim?ticket=... ile onaysız
config alır (ticket'a sahip olmak yetkidir).

Depo: SQLite, speaker_store ile aynı dizin (~/.hermes/mate_voice/pairing.db) —
plugin `install --force` yeniden kurulumlarından etkilenmez. Sadece stdlib
(sqlite3/secrets/os/time) → QR CLI'ı ağır ses deps'leri olmadan da çalışır.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time

PAIR_TTL_S = 600      # kod TTL: 10 dk
TICKET_TTL_S = 600    # QR ticket TTL: 10 dk
MAX_PENDING = 50      # DB flood emniyeti: bekleyen istek tavanı

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pairings (
    pair_id     TEXT PRIMARY KEY,
    code        TEXT,               -- onay kodu (ticket satırında NULL)
    ticket      TEXT UNIQUE,        -- QR ticket (kod satırında NULL)
    device_name TEXT,
    platform    TEXT,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending|approved|denied|consumed
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pairings_code ON pairings(code);
"""


def default_db_path() -> str:
    env = os.getenv("MATE_VOICE_PAIR_DB_PATH")
    if env:
        return env
    return os.path.join(os.path.expanduser("~/.hermes/mate_voice"), "pairing.db")


def plugin_env(key: str, default: str = "") -> str:
    """os.environ → <plugin>/.env → default (hafif; voice.config'i import ETMEZ —
    config modülü yoksa bile QR CLI çalışsın, client-key üretim yan etkisi olmasın)."""
    val = (os.getenv(key) or "").strip()
    if val:
        return val
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    try:
        with open(env_path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                if k.strip() == key:
                    return v.strip().strip('"').strip("'") or default
    except OSError:
        pass
    return default


def _primary_ip() -> str:
    """Makinenin birincil (default-route) IPv4'ü; bulunamazsa ''."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 53))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return ""


def public_base_url(request_host: str = "") -> str:
    """Token/pairing endpoint'inin client'a duyurulan adresi. Açık env yoksa
    isteğin geldiği host'tan türetilir (kullanıcı hangi adresle ulaştıysa o);
    CLI bağlamında (pair-qr, istek yok) makinenin birincil IP'sine düşülür."""
    explicit = plugin_env("MATE_PUBLIC_TOKEN_URL")
    if explicit:
        return explicit.rstrip("/")
    port = plugin_env("MATE_VOICE_TOKEN_PORT", "8830")
    host = request_host or _primary_ip() or "127.0.0.1"
    return f"http://{host}:{port}"


def read_gateway_token() -> str:
    """gateway_token'ı DOSYADAN oku (koda gömülmez). Yoksa boş string (fail-open)."""
    path = os.path.expanduser(
        plugin_env("MATE_GATEWAY_TOKEN_FILE", "~/.hermes/mate_gateway_token"))
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


_LOCAL_HOSTS = {"", "127.0.0.1", "localhost", "0.0.0.0", "::1"}


def _url_host(url: str) -> str:
    m = re.match(r"[a-z+]+://\[?([^\]/:]+)", (url or "").strip())
    return m.group(1) if m else ""


def _url_port(url: str, default: int) -> int:
    m = re.match(r"[a-z+]+://[^/:]+:(\d+)", (url or "").strip())
    return int(m.group(1)) if m else default


def client_livekit_url(settings, request_host: str = "") -> str:
    """Client'a duyurulacak LiveKit URL'i. Öncelik:
    1) MATE_PUBLIC_LIVEKIT_URL (açık ayar — domain/TLS kurulumları)
    2) LIVEKIT_URL'in host'u gerçek bir adresse (mesh/LAN IP) → o
    3) İsteğin geldiği Host header'ı — kullanıcı sunucuya hangi adresle
       ulaşıyorsa LiveKit de aynı host + LiveKit portu (düz-IP kurulumu;
       LIVEKIT_URL loopback/0.0.0.0 iken tek doğru kaynak budur)."""
    explicit = plugin_env("MATE_PUBLIC_LIVEKIT_URL")
    if explicit:
        return explicit
    url = getattr(settings, "livekit_url", "") or ""
    if _url_host(url) not in _LOCAL_HOSTS:
        return url
    if request_host:
        return f"ws://{request_host}:{_url_port(url, 7880)}"
    return getattr(settings, "public_livekit_url", "") or url


def client_gateway_url(request_host: str = "") -> str:
    """Client'a duyurulacak Hermes gateway ws URL'i: MATE_GATEWAY_URL açıkça
    set edilmişse o; değilse isteğin Host header'ından türetilir (:8800)."""
    explicit = plugin_env("MATE_GATEWAY_URL")
    if explicit:
        return explicit
    if request_host:
        return f"ws://{request_host}:8800"
    return "ws://127.0.0.1:8800"


def build_config(settings, room: str, request_host: str = "") -> dict:
    """Client'a verilecek config paketi — değerler sunucudaki GERÇEK config'ten.
    request_host: pairing isteğinin Host header'ı (portsuz) — livekit/gateway
    URL'leri açık env yoksa bundan türetilir (IP-only, mesh, domain hepsi doğru)."""
    return {
        "livekit_url": client_livekit_url(settings, request_host),
        "room": room,
        "token_endpoint": public_base_url(request_host),
        "client_key": settings.client_key,
        "gateway_url": client_gateway_url(request_host),
        "gateway_token": read_gateway_token(),
    }


class PairingStore:
    """Senkron SQLite deposu. HTTP handler'lar da tool handler'lar da (ayrı süreç
    olsa bile) aynı dosya üstünden çalışır; tüm durum geçişleri tek-UPDATE ile
    atomiktir (tek-sefer tüketim yarışsızdır)."""

    def __init__(self, path: str | None = None):
        self.path = path or default_db_path()
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- yaşam döngüsü ----

    def sweep(self, conn: sqlite3.Connection | None = None) -> None:
        """Süresi geçen pending satırları sil (expired = satır yok davranışı)."""
        own = conn is None
        c = conn or self._connect()
        try:
            c.execute("DELETE FROM pairings WHERE expires_at < ? AND status = 'pending'",
                      (time.time(),))
            if own:
                c.commit()
        finally:
            if own:
                c.close()

    # ---- kod akışı ----

    def create_request(self, device_name: str, platform: str) -> dict | None:
        """Yeni pairing isteği. None → kapasite dolu (429 ver)."""
        now = time.time()
        conn = self._connect()
        try:
            self.sweep(conn)
            (pending,) = conn.execute(
                "SELECT COUNT(*) FROM pairings WHERE status = 'pending'").fetchone()
            if pending >= MAX_PENDING:
                return None
            pair_id = secrets.token_hex(16)
            # Bekleyenler arasında benzersiz 4-6 haneli kod (çakışırsa yeniden çek).
            for _ in range(20):
                code = f"{secrets.randbelow(9000) + 1000}"
                row = conn.execute(
                    "SELECT 1 FROM pairings WHERE code = ? AND status = 'pending'",
                    (code,)).fetchone()
                if row is None:
                    break
            conn.execute(
                "INSERT INTO pairings (pair_id, code, device_name, platform, status,"
                " created_at, expires_at) VALUES (?,?,?,?, 'pending', ?, ?)",
                (pair_id, code, device_name[:64], platform[:32], now, now + PAIR_TTL_S))
            conn.commit()
            return {"pair_id": pair_id, "code": code, "expires_in": PAIR_TTL_S}
        finally:
            conn.close()

    def poll_status(self, pair_id: str) -> str:
        """'pending'|'approved'|'denied'|'expired'. 'approved' TEK SEFER döner —
        aynı UPDATE ile 'consumed'a çekilir; ikinci sorgu 'expired' görür."""
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT status, expires_at FROM pairings WHERE pair_id = ? AND code IS NOT NULL",
                (pair_id,)).fetchone()
            if row is None:
                return "expired"
            if row["status"] == "pending":
                return "pending" if row["expires_at"] >= now else "expired"
            if row["status"] == "denied":
                return "denied"
            if row["status"] == "approved":
                cur = conn.execute(
                    "UPDATE pairings SET status = 'consumed'"
                    " WHERE pair_id = ? AND status = 'approved'", (pair_id,))
                conn.commit()
                return "approved" if cur.rowcount == 1 else "expired"
            return "expired"  # consumed / bilinmeyen
        finally:
            conn.close()

    def _resolve(self, code: str, new_status: str) -> dict | None:
        """Bekleyen (süresi geçmemiş) kodu approve/deny et; cihaz bilgisini döndür."""
        code = (code or "").strip()
        if not code.isdigit() or not (4 <= len(code) <= 6):
            return None
        now = time.time()
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT pair_id, device_name, platform FROM pairings"
                " WHERE code = ? AND status = 'pending' AND expires_at >= ?",
                (code, now)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE pairings SET status = ? WHERE pair_id = ?",
                         (new_status, row["pair_id"]))
            conn.commit()
            return {"pair_id": row["pair_id"], "device_name": row["device_name"],
                    "platform": row["platform"]}
        finally:
            conn.close()

    def approve(self, code: str) -> dict | None:
        return self._resolve(code, "approved")

    def deny(self, code: str) -> dict | None:
        return self._resolve(code, "denied")

    # ---- QR ticket akışı ----

    def create_ticket(self, ttl_s: int = TICKET_TTL_S) -> str:
        """Tek kullanımlık crypto-random ticket (32 bayt = 64 hex)."""
        ticket = secrets.token_hex(32)
        now = time.time()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO pairings (pair_id, ticket, device_name, platform, status,"
                " created_at, expires_at) VALUES (?,?, 'qr', 'qr', 'pending', ?, ?)",
                (secrets.token_hex(16), ticket, now, now + ttl_s))
            conn.commit()
            return ticket
        finally:
            conn.close()

    def claim_ticket(self, ticket: str) -> bool:
        """Ticket'ı atomik tüket. True = geçerli + ilk kullanım."""
        ticket = (ticket or "").strip()
        if len(ticket) < 32:
            return False
        conn = self._connect()
        try:
            cur = conn.execute(
                "UPDATE pairings SET status = 'consumed'"
                " WHERE ticket = ? AND status = 'pending' AND expires_at >= ?",
                (ticket, time.time()))
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()
