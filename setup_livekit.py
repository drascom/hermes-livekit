"""Opsiyonel yerel LiveKit sunucu kurulumu — Hermes LiveKit setup CLI.

`hermes plugins install drascom/hermes-livekit` yapan birinin LiveKit'i ayrıca kurması
gerekmesin diye: binary indir + key/secret üret + minimal config + systemd
unit + plugin .env güncelle. Idempotent: mevcut kurulum/değer varsa ÜZERİNE
YAZMAZ (--force ile ezilir).

Kullanım (sunucuda):
    python3 ~/.hermes/plugins/hermes_livekit/setup_livekit.py [seçenekler]

Argümansız (veya --wizard ile) çalıştırılınca İNTERAKTİF SİHİRBAZ açılır:
"Mevcut bir LiveKit sunucun var mı, yoksa yeni kurayım mı?" — "yeni kur" ise
URL/key/secret OTOMATİK üretilip .env'e yazılır (hiç sorulmaz); "mevcut var"
ise ancak o zaman URL/key/secret sorulur.

Seçenekler:
    --bind {all,loopback,mesh,public}  Dinleme kapsamı (default: all = 0.0.0.0)
    --ip <addr>                    mesh için mesh IP (örn. NetBird 100.x adresi)
    --prefix <dir>                 Kurulum dizini (default: ~/.hermes/mate_voice/livekit)
    --livekit-version <vX.Y.Z>     Sürüm sabitle (default: GitHub latest)
    --no-systemd                   systemd unit yazma/etkinleştirme
    --force                        Mevcut binary/config/env değerlerini ez
    --dry-run                      Hiçbir şey yazma; yapılacakları göster

TLS/TURN otomatikleştirilmez — public erişim için README'deki nota bakın.
Mesh-only (NetBird/Tailscale) kurulumda TLS gerekmez (ws:// yeterli).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PLUGIN_DIR, ".env")
DEFAULT_PREFIX = os.path.expanduser("~/.hermes/mate_voice/livekit")
UNIT_PATH = "/etc/systemd/system/livekit-server.service"
GH_LATEST = "https://api.github.com/repos/livekit/livekit/releases/latest"
GH_TAG = "https://api.github.com/repos/livekit/livekit/releases/tags/{tag}"

PORT_WS = 7880
PORT_TCP = 7881
PORT_UDP_MUX = 7882   # tek UDP mux portu — 50000-50200 aralığı yerine
                      # (firewall'da TEK udp portu açmak yeter)


# ---------------------------------------------------------------- helpers

def log(msg: str) -> None:
    print(msg)


def _http_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "mate-voice-setup",
                                               "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def resolve_release(version: str | None) -> tuple[str, list[dict]]:
    """(tag, assets) döndür. version None → latest."""
    url = GH_TAG.format(tag=version) if version else GH_LATEST
    data = _http_json(url)
    return data["tag_name"], data.get("assets") or []


def pick_asset(tag: str, assets: list[dict]) -> dict | None:
    """OS/arch'a uyan tar.gz asset'i seç (linux amd64/arm64/armv7 + varsa darwin)."""
    goos = {"Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    mach = platform.machine().lower()
    goarch = {"x86_64": "amd64", "amd64": "amd64",
              "aarch64": "arm64", "arm64": "arm64",
              "armv7l": "armv7"}.get(mach)
    if not goos or not goarch:
        return None
    want = f"livekit_{tag.lstrip('v')}_{goos}_{goarch}.tar.gz"
    for a in assets:
        if a.get("name") == want:
            return a
    return None


def download_binary(asset: dict, prefix: str, dry: bool) -> str:
    """tar.gz indir, livekit-server'ı prefix'e çıkar. Yol döndürür."""
    dest = os.path.join(prefix, "livekit-server")
    if dry:
        log(f"[dry-run] indirilecek: {asset['browser_download_url']} -> {dest}")
        return dest
    os.makedirs(prefix, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        tgz = os.path.join(td, asset["name"])
        log(f"→ indiriliyor: {asset['browser_download_url']}")
        urllib.request.urlretrieve(asset["browser_download_url"], tgz)
        with tarfile.open(tgz, "r:gz") as tf:
            member = next((m for m in tf.getmembers()
                           if os.path.basename(m.name) == "livekit-server"), None)
            if member is None:
                raise RuntimeError("arşivde livekit-server bulunamadı")
            member.name = os.path.basename(member.name)
            tf.extract(member, td)
            shutil.move(os.path.join(td, "livekit-server"), dest)
    os.chmod(dest, os.stat(dest).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log(f"✓ binary: {dest}")
    return dest


def gen_keypair() -> tuple[str, str]:
    """LiveKit uyumlu API key/secret (crypto-random)."""
    return "API" + secrets.token_urlsafe(12), secrets.token_urlsafe(32)


def render_config(bind: str, ip: str, key: str, secret: str) -> str:
    if bind == "loopback":
        bind_lines = "bind_addresses:\n  - 127.0.0.1\n"
    elif bind == "mesh":
        bind_lines = f"bind_addresses:\n  - 127.0.0.1\n  - {ip}\n"
    else:  # all (varsayılan) / public — tüm arayüzler
        bind_lines = "bind_addresses:\n  - 0.0.0.0\n"
    # external-IP (STUN) keşfi: 0.0.0.0'a bağlanan ("all"/"public") kurulumlar NAT
    # arkasında olabilir (Oracle Cloud gibi 1:1 NAT) → public IP'yi ICE adayı olarak
    # yayınlamak ŞART; yoksa uzak client sinyalde bağlanır ama medya (UDP) kurulamaz →
    # ~10sn'de bir "removing participant without connection" reconnect döngüsü.
    # STUN LAN'da da zararsız (aynı IP'yi bulur/ICE yereli seçer). Sadece loopback/mesh
    # (dış erişim yok) modlarında kapalı tutulur.
    ext = "false" if bind in ("loopback", "mesh") else "true"
    return (
        "# hermes_livekit setup_livekit.py tarafından üretildi\n"
        f"port: {PORT_WS}\n"
        f"{bind_lines}"
        "rtc:\n"
        f"  tcp_port: {PORT_TCP}\n"
        f"  udp_port: {PORT_UDP_MUX}\n"
        f"  use_external_ip: {ext}\n"
        "keys:\n"
        f"  {key}: {secret}\n"
    )


def render_unit(prefix: str, user: str) -> str:
    return (
        "[Unit]\n"
        "Description=LiveKit Server (Hermes LiveKit)\n"
        "After=network-online.target\n"
        "Wants=network-online.target\n\n"
        "[Service]\n"
        f"User={user}\n"
        f"ExecStart={prefix}/livekit-server --config {prefix}/livekit.yaml\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "LimitNOFILE=65535\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def read_env() -> dict[str, str]:
    vals: dict[str, str] = {}
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip()
                # satır-içi yorumu değere katma (`DEĞER  # açıklama`)
                if not (v.startswith('"') or v.startswith("'")):
                    v = v.split(" #", 1)[0].split("\t#", 1)[0].strip()
                vals[k.strip()] = v.strip('"').strip("'")
    except OSError:
        pass
    return vals


def update_env(updates: dict[str, str], force: bool, dry: bool) -> list[str]:
    """Plugin .env'e anahtarları yaz. Dolu değer varsa force olmadan DOKUNMAZ.
    Yazılan anahtar listesini döndürür."""
    current = read_env()
    todo = {k: v for k, v in updates.items() if force or not current.get(k)}
    if not todo:
        return []
    if dry:
        for k in todo:
            log(f"[dry-run] .env <- {k}={'***' if 'SECRET' in k else todo[k]}")
        return list(todo)
    lines: list[str] = []
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        pass
    seen = set()
    for i, line in enumerate(lines):
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in todo:
            lines[i] = f"{m.group(1)}={todo[m.group(1)]}"
            seen.add(m.group(1))
    for k, v in todo.items():
        if k not in seen:
            lines.append(f"{k}={v}")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    log(f"✓ .env güncellendi: {', '.join(todo)}")
    return list(todo)


def _sudo_prefix() -> list[str]:
    """Root değilsek sudo; tty yoksa `-n` (parola sorusuna ASILI KALMASIN —
    NOPASSWD yoksa hemen düşer, degrade yolu devreye girer)."""
    if os.geteuid() == 0:
        return []
    if sys.stdin.isatty():
        return ["sudo"]
    return ["sudo", "-n"]


def _sudo_write(path: str, content: str) -> bool:
    """Root gerektiren dosyayı yaz (root değilsek sudo tee)."""
    try:
        if os.geteuid() == 0:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        p = subprocess.run(_sudo_prefix() + ["tee", path], input=content.encode(),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=60)
        return p.returncode == 0
    except Exception as e:
        log(f"! unit yazılamadı ({e}) — elle kurun (içerik aşağıda basıldı)")
        return False


def _systemctl(*args: str) -> int:
    cmd = _sudo_prefix() + ["systemctl"] + list(args)
    try:
        return subprocess.run(cmd, check=False, timeout=120,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode
    except Exception:
        return 1


def _unit_active() -> bool:
    try:
        return subprocess.run(["systemctl", "is-active", "--quiet", "livekit-server"],
                              check=False, timeout=15).returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------- wizard

MESH_IFACES = ("wt0", "netbird0", "tailscale0")


def detect_mesh_ip() -> str:
    """Mesh (NetBird/Tailscale) arayüz IPv4'ünü bulmayı dene; yoksa ''."""
    for dev in MESH_IFACES:
        for cmd in (["ip", "-4", "-o", "addr", "show", dev],
                    ["ifconfig", dev]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True,
                                     timeout=5).stdout
            except Exception:
                continue
            m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
            if m:
                return m.group(1)
    return ""


def primary_ip() -> str:
    """Makinenin birincil (default-route) IPv4'ü; bulunamazsa ''."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 53))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return ""


def run_wizard(a) -> int | None:
    """İnteraktif ilk kurulum. Dönüş: int = bitti (exit code);
    None = 'yeni kur' seçildi, a.bind/a.ip dolduruldu, normal akış devam etsin."""
    import getpass

    print("Hermes LiveKit — LiveKit sihirbazı")
    print("Hermes LiveKit'in bir LiveKit sunucusuna ihtiyacı var.\n")
    ans = input("Mevcut bir LiveKit sunucun var mı, yoksa yeni kurayım mı?\n"
                "  [Y]eni kur (öneri, otomatik)  /  [m]evcut var: ").strip().lower()

    if ans in ("m", "mevcut", "e", "evet", "var"):
        # Yalnız bu durumda URL/key/secret sorulur.
        url = input("LiveKit URL (örn. ws://127.0.0.1:7880 veya wss://...): ").strip()
        key = input("LiveKit API key: ").strip()
        secret = getpass.getpass("LiveKit API secret: ").strip()
        vals = {k: v for k, v in (("LIVEKIT_URL", url),
                                  ("LIVEKIT_API_KEY", key),
                                  ("LIVEKIT_API_SECRET", secret)) if v}
        if not vals:
            log("Hiç değer girilmedi — çıkılıyor. (Sonra tekrar: setup_livekit.py)")
            return 1
        update_env(vals, force=True, dry=a.dry_run)
        log("\nBitti. Gateway'i yeniden başlat: hermes gateway restart")
        return 0

    # Yeni kurulum — bind kapsamı. Varsayılan: tüm arayüzler (0.0.0.0) — çoğu
    # kullanıcı mesh/domain'siz düz IP ile bağlanır; client'lara URL sunucuya
    # ulaştıkları adresten türetilir (pairing Host header'ı).
    print("\nDinleme kapsamı:")
    print("  1) hepsi    — 0.0.0.0, tüm arayüzler (öneri; düz IP/LAN kurulumu)")
    print("  2) loopback — sadece bu makine (127.0.0.1)")
    print("  3) mesh     — NetBird/Tailscale mesh IP'sinden")
    print("  4) public   — 0.0.0.0 + external-IP keşfi (NAT arkası; TLS/TURN gerekir)")
    sel = input("Seçim [1]: ").strip()
    bind = {"1": "all", "2": "loopback", "3": "mesh", "4": "public"}.get(sel, "all")
    ip = ""
    if bind == "mesh":
        mesh_ip = detect_mesh_ip() or primary_ip()
        ip = input(f"Mesh IP [{mesh_ip or 'gerekli'}]: ").strip() or mesh_ip
        if not ip:
            log("mesh için IP gerekli — çıkılıyor.")
            return 1
    a.bind, a.ip = bind, ip
    return None  # normal kurulum akışına devam


# ---------------------------------------------------------------- install core

def run_install(a) -> int:
    """Argümanları (argparse namespace) alıp kurulumu uygular. İnteraktif DEĞİL."""
    if a.bind == "mesh" and not a.ip:
        log("HATA: --bind mesh için --ip <mesh-adresi> gerekli")
        return 2

    prefix = os.path.abspath(os.path.expanduser(a.prefix))
    cfg_path = os.path.join(prefix, "livekit.yaml")
    bin_path = os.path.join(prefix, "livekit-server")
    is_linux = platform.system() == "Linux"
    dry = a.dry_run

    log(f"Hermes LiveKit kurulumu — bind={a.bind} prefix={prefix}"
        + (" [DRY-RUN]" if dry else ""))

    # 1) Binary
    if os.path.exists(bin_path) and not a.force:
        log(f"= binary mevcut, atlandı: {bin_path} (--force ile yenile)")
    else:
        tag, assets = resolve_release(a.livekit_version)
        asset = pick_asset(tag, assets)
        if asset:
            log(f"→ sürüm: {tag}")
            download_binary(asset, prefix, dry)
        elif platform.system() == "Darwin":
            log(f"! {tag} sürümünde darwin asset yok — macOS'ta: brew install livekit"
                "\n  (config/env yine de üretilir; ExecStart yolunu brew binary'sine çevirin)")
        else:
            log(f"! {tag} için {platform.system()}/{platform.machine()} asset'i yok — elle kurun")
            return 1

    # 2) Key/secret — mevcut config'den koru (idempotent)
    key = secret = ""
    if os.path.exists(cfg_path) and not a.force:
        txt = open(cfg_path, encoding="utf-8").read()
        m = re.search(r"^\s{2}(\S+):\s*(\S+)\s*$", txt.split("keys:", 1)[-1], re.M)
        if m:
            key, secret = m.group(1), m.group(2)
            log(f"= config mevcut, key korundu: {cfg_path} (--force ile yenile)")
    if not key:
        env = read_env()
        if not a.force and env.get("LIVEKIT_API_KEY") and env.get("LIVEKIT_API_SECRET"):
            key, secret = env["LIVEKIT_API_KEY"], env["LIVEKIT_API_SECRET"]
            log("= key/secret .env'den alındı")
        else:
            key, secret = gen_keypair()
            log(f"✓ yeni API key üretildi: {key}")

    # 3) Config
    config_written = False  # YENİ config (yeni key) yazıldı mı → aşağıda restart tetikler
    cfg = render_config(a.bind, a.ip, key, secret)
    if os.path.exists(cfg_path) and not a.force:
        pass  # yukarıda bildirildi (key korundu)
    elif dry:
        log(f"[dry-run] config yazılacak: {cfg_path}\n--- livekit.yaml ---\n{cfg}---")
    else:
        os.makedirs(prefix, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg)
        os.chmod(cfg_path, 0o600)  # secret içerir
        config_written = True
        log(f"✓ config: {cfg_path}")

    # 4) systemd (yalnız linux)
    if a.no_systemd:
        log("= systemd atlandı (--no-systemd)")
    elif not is_linux:
        log("= systemd yok (linux değil) — macOS'ta elle başlatın:\n"
            f"  {bin_path if os.path.exists(bin_path) else 'livekit-server'} --config {cfg_path}")
    else:
        unit = render_unit(prefix, os.environ.get("SUDO_USER") or os.environ.get("USER") or "root")
        if os.path.exists(UNIT_PATH) and not a.force:
            log(f"= unit mevcut, atlandı: {UNIT_PATH} (--force ile yenile)")
            if not dry and not _unit_active():
                # unit var ama servis çalışmıyor (yarım kalmış kurulum) → başlat.
                _systemctl("daemon-reload")
                _systemctl("enable", "--now", "livekit-server")
        elif dry:
            log(f"[dry-run] unit yazılacak: {UNIT_PATH}\n--- unit ---\n{unit}---")
            log("[dry-run] systemctl daemon-reload && enable --now livekit-server")
        else:
            if _sudo_write(UNIT_PATH, unit):
                _systemctl("daemon-reload")
                _systemctl("enable", "--now", "livekit-server")
                log(f"✓ systemd: {UNIT_PATH} (enable --now)")
            else:
                print(unit)
        if not dry and not _unit_active():
            log("! livekit-server servisi AKTİF DEĞİL — sudo yok/başarısız olabilir.\n"
                "  Elle: sudo systemctl daemon-reload && "
                "sudo systemctl enable --now livekit-server\n"
                f"  (unit: {UNIT_PATH} — yoksa yukarıda basılan içeriği oraya yazın)")
        # YENİ config (yeni key) yazıldıysa çalışan server'ı RESTART et: `enable --now`
        # zaten aktif serviste no-op olur → eski key bellekte kalıp agent 401 alırdı.
        elif config_written and not dry:
            _systemctl("restart", "livekit-server")
            log("↻ livekit-server restart (yeni config/key yüklendi)")

    # 5) Plugin .env — agent'ın bağlandığı URL. "all"/"public"te agent yerelden
    # bağlanır (127.0.0.1); CLIENT URL'i pairing'de Host header'dan türetilir.
    url_ip = {"loopback": "127.0.0.1", "mesh": a.ip,
              "all": "127.0.0.1", "public": "127.0.0.1"}.get(a.bind, "127.0.0.1")
    update_env({"LIVEKIT_URL": f"ws://{url_ip}:{PORT_WS}",
                "LIVEKIT_API_KEY": key,
                "LIVEKIT_API_SECRET": secret}, a.force, dry)

    log("\nBitti." + (" (dry-run — hiçbir şey yazılmadı)" if dry else
        " Hermes'i yeniden başlatın; pairing config paketi yeni LiveKit değerlerini dağıtır."))
    if a.bind == "public":
        log("NOT: public bind seçtiniz — tarayıcı/uzak client için TLS (wss) ve gerekirse "
            "TURN şarttır. Domain + reverse proxy (Caddy/nginx) kurun; bkz. README.")
    return 0


# ---------------------------------------------------------------- auto (adapter)

def run_auto(log_fn=None) -> dict | None:
    """NON-INTERACTIVE otomatik kurulum — adapter ilk başlatmada çağırır
    (LIVEKIT_MODE=yeni + LIVEKIT_API_SECRET boş). Hiçbir şey sormaz.
    Bind DEFAULT: 0.0.0.0 (tüm arayüzler) — çoğu kullanıcı mesh/domain'siz düz
    IP kullanır; client'a URL pairing Host header'ından türetilir (mesh/loopback
    yalnız interaktif sihirbazda seçenek). LIVEKIT_BIND env'i ile ezilebilir
    (all|loopback|mesh|public). Başarıda .env'e yazılan LIVEKIT_URL/KEY/SECRET
    dict'ini döndürür; başarısızlıkta None (çağıran anlaşılır log basar)."""
    global log
    if log_fn is not None:
        log = log_fn  # setup loglarını adapter logger'ına akıt
    bind = (os.getenv("LIVEKIT_BIND") or "all").strip().lower()
    if bind not in ("all", "loopback", "mesh", "public"):
        bind = "all"
    ip = ""
    if bind == "mesh":
        ip = (os.getenv("LIVEKIT_MESH_IP") or "").strip() or detect_mesh_ip() or primary_ip()
        if not ip:
            log("! mesh IP bulunamadı → bind=all (0.0.0.0) ile devam")
            bind = "all"
    a = argparse.Namespace(bind=bind, ip=ip, prefix=DEFAULT_PREFIX,
                           livekit_version=None, no_systemd=False,
                           force=False, dry_run=False)
    try:
        rc = run_install(a)
    except Exception as e:
        log(f"! otomatik LiveKit kurulumu istisnayla düştü: {e!r}")
        return None
    if rc != 0:
        return None
    env = read_env()
    vals = {k: env.get(k, "") for k in
            ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET")}
    if not all(vals.values()):
        log("! kurulum bitti ama .env'de LIVEKIT_* eksik kaldı")
        return None
    return vals


# ---------------------------------------------------------------- main (CLI)

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", choices=["all", "loopback", "mesh", "public"], default="all")
    ap.add_argument("--ip", default="", help="mesh bind için IP (örn. 100.x NetBird)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--livekit-version", default=None, help="örn. v1.13.3 (default: latest)")
    ap.add_argument("--no-systemd", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--wizard", action="store_true",
                    help="interaktif sihirbaz (argümansız çalıştırınca da açılır)")
    a = ap.parse_args()

    if a.wizard or (len(sys.argv) == 1 and sys.stdin.isatty()):
        rc = run_wizard(a)
        if rc is not None:
            return rc

    return run_install(a)


if __name__ == "__main__":
    raise SystemExit(main())
