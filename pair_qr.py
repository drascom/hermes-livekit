"""Tek-URL pairing — QR ticket CLI.

Sunucu terminalinde çalıştır: yeni TEK KULLANIMLIK ticket üretir, claim
linkini + terminal QR'ını basar. Client QR'ı okuyup GET /pair/claim?ticket=...
ile config paketini onaysız alır (ticket'a sahip olmak yetkidir; TTL 10 dk).

Kullanım (sunucuda):
    hermes mate_voice pair-qr                            # Hermes CLI üzerinden
    python3 ~/.hermes/plugins/mate_voice/pair_qr.py      # standalone (hafif, ses deps'siz)
    (cd ~/.hermes/plugins && python3 -m mate_voice.pair_qr)  # paket importu
"""

from __future__ import annotations

import sys


def _import_pairing():
    """Paket ya da standalone çalıştırmada voice.pairing'i getir (ağır ses
    deps'lerini yüklemeden — voice/__init__ boş, plugin __init__'e girilmez)."""
    if __package__:
        from .voice.pairing import PairingStore, public_base_url  # type: ignore
        return PairingStore, public_base_url
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from voice.pairing import PairingStore, public_base_url  # type: ignore
    return PairingStore, public_base_url


def _print_qr(data: str) -> None:
    """Terminal ASCII QR (qrcode kütüphanesi; yoksa kurmayı dene; olmazsa atla —
    link zaten metin olarak basıldı)."""
    try:
        import importlib.util
        if importlib.util.find_spec("qrcode") is None:
            try:
                import subprocess
                subprocess.run([sys.executable, "-m", "pip", "install", "-q", "qrcode"],
                               check=False, timeout=60)
                importlib.invalidate_caches()
            except Exception:
                pass
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        qr.make(fit=True)
        qr.print_ascii(out=sys.stdout)
    except Exception:
        print("(QR basılamadı — linki elle girin)")


def main() -> int:
    PairingStore, public_base_url = _import_pairing()
    ticket = PairingStore().create_ticket()
    url = f"{public_base_url()}/pair/claim?ticket={ticket}"
    print("\n🔗 Mate pairing ticket üretildi (TEK kullanımlık, 10 dk geçerli)")
    print(f"   {url}\n")
    _print_qr(url)
    print("Client'ta 'QR ile eşleş' seçin ya da linki tek-URL alanına yapıştırın.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
