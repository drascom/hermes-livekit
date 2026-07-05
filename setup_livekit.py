"""Opsiyonel yerel LiveKit sunucu kurulumu — mate_voice setup CLI.

`hermes plugins install mate_voice` yapan birinin LiveKit'i ayrıca kurması
gerekmesin diye: binary indir + key/secret üret + minimal config + systemd
unit + plugin .env güncelle. Idempotent: mevcut kurulum/değer varsa ÜZERİNE
YAZMAZ (--force ile ezilir).

Kullanım (sunucuda):
    python3 ~/.hermes/plugins/mate_voice/setup_livekit.py [seçenekler]

Seçenekler:
    --bind {loopback,mesh,public}  Dinleme kapsamı (default: loopback)
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
UDP_START = 50000
UDP_END = 50200


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
    else:  # public
        bind_lines = "bind_addresses:\n  - 0.0.0.0\n"
    ext = "true" if bind == "public" else "false"
    return (
        "# mate_voice setup_livekit.py tarafından üretildi\n"
        f"port: {PORT_WS}\n"
        f"{bind_lines}"
        "rtc:\n"
        f"  tcp_port: {PORT_TCP}\n"
        f"  port_range_start: {UDP_START}\n"
        f"  port_range_end: {UDP_END}\n"
        f"  use_external_ip: {ext}\n"
        "keys:\n"
        f"  {key}: {secret}\n"
    )


def render_unit(prefix: str, user: str) -> str:
    return (
        "[Unit]\n"
        "Description=LiveKit Server (mate_voice)\n"
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
                vals[k.strip()] = v.strip().strip('"').strip("'")
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


def _sudo_write(path: str, content: str) -> bool:
    """Root gerektiren dosyayı yaz (root değilsek sudo tee)."""
    try:
        if os.geteuid() == 0:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        p = subprocess.run(["sudo", "tee", path], input=content.encode(),
                           stdout=subprocess.DEVNULL, timeout=60)
        return p.returncode == 0
    except Exception as e:
        log(f"! unit yazılamadı ({e}) — elle kurun (içerik aşağıda basıldı)")
        return False


def _systemctl(*args: str) -> None:
    cmd = (["systemctl"] if os.geteuid() == 0 else ["sudo", "systemctl"]) + list(args)
    subprocess.run(cmd, check=False, timeout=120)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", choices=["loopback", "mesh", "public"], default="loopback")
    ap.add_argument("--ip", default="", help="mesh bind için IP (örn. 100.x NetBird)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--livekit-version", default=None, help="örn. v1.13.3 (default: latest)")
    ap.add_argument("--no-systemd", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.bind == "mesh" and not a.ip:
        ap.error("--bind mesh için --ip <mesh-adresi> gerekli")

    prefix = os.path.abspath(os.path.expanduser(a.prefix))
    cfg_path = os.path.join(prefix, "livekit.yaml")
    bin_path = os.path.join(prefix, "livekit-server")
    is_linux = platform.system() == "Linux"
    dry = a.dry_run

    log(f"mate_voice LiveKit kurulumu — bind={a.bind} prefix={prefix}"
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
    cfg = render_config(a.bind, a.ip, key, secret)
    if os.path.exists(cfg_path) and not a.force:
        pass  # yukarıda bildirildi
    elif dry:
        log(f"[dry-run] config yazılacak: {cfg_path}\n--- livekit.yaml ---\n{cfg}---")
    else:
        os.makedirs(prefix, exist_ok=True)
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(cfg)
        os.chmod(cfg_path, 0o600)  # secret içerir
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

    # 5) Plugin .env — pairing build_config() doğru değerleri dağıtsın
    url_ip = {"loopback": "127.0.0.1", "mesh": a.ip}.get(a.bind, a.ip or "127.0.0.1")
    update_env({"LIVEKIT_URL": f"ws://{url_ip}:{PORT_WS}",
                "LIVEKIT_API_KEY": key,
                "LIVEKIT_API_SECRET": secret}, a.force, dry)

    log("\nBitti." + (" (dry-run — hiçbir şey yazılmadı)" if dry else
        " Hermes'i yeniden başlatın; pairing config paketi yeni LiveKit değerlerini dağıtır."))
    if a.bind == "public":
        log("NOT: public bind seçtiniz — tarayıcı/uzak client için TLS (wss) ve gerekirse "
            "TURN şarttır. Domain + reverse proxy (Caddy/nginx) kurun; bkz. README.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
