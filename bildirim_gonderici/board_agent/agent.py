#!/usr/bin/env python3
"""
Pardus 23 Sınıf Tahtası Bildirim Ajanı
=======================================
Okul sunucusundan gelen HTTP POST isteklerini alır ve
masaüstü bildirimi (notify-send) olarak gösterir.

Kurulum:
  1. Bu dosyayı tahtaya kopyalayın: /opt/tahta_agent/agent.py
  2. Gizli anahtarı oluşturun:
       sudo mkdir -p /etc/tahta_agent
       echo 'GIZLI_ANAHTAR=buraya-guclu-bir-anahtar-yazin' | sudo tee /etc/tahta_agent/secrets
       sudo chmod 600 /etc/tahta_agent/secrets
       sudo chown root:root /etc/tahta_agent/secrets
  3. Django settings.py içindeki BILDIRIM_ANAHTAR ile aynı değeri kullanın.
  4. Systemd servisini kurun (aşağıdaki tahta_agent.service dosyasına bakın)

Gereksinimler:
  - Python 3.8+  (Pardus 23'te varsayılan olarak mevcut)
  - libnotify-bin paketi: sudo apt install libnotify-bin
"""

import json
import logging
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


def masaustu_uid_bul() -> str:
    """Masaüstünde aktif grafik oturumu açık olan kullanıcının UID'sini döndürür.

    Öncelik sırası:
      1. loginctl üzerinden x11/wayland oturumu olan kullanıcı
      2. /run/user/ altındaki ilk UID >= 1000 dizini
      3. MASAUSTU_UID ortam değişkeni veya sabit "1000"
    """
    # 1. loginctl ile grafik oturumunu bul
    try:
        cikti = subprocess.check_output(
            ["loginctl", "list-sessions", "--no-legend"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for satir in cikti.splitlines():
            parcalar = satir.split()
            if len(parcalar) < 2:
                continue
            session_id, uid = parcalar[0], parcalar[1]
            if not uid.isdigit() or int(uid) < 1000:
                continue
            try:
                tip = subprocess.check_output(
                    ["loginctl", "show-session", session_id, "-p", "Type", "--value"],
                    text=True,
                    stderr=subprocess.DEVNULL,
                ).strip()
                if tip in ("x11", "wayland", "mir"):
                    return uid
            except Exception:
                continue
    except Exception:
        pass

    # 2. /run/user/ altındaki aktif oturum dizinlerini tara
    try:
        adaylar = sorted(
            e.name
            for e in os.scandir("/run/user")
            if e.is_dir() and e.name.isdigit() and int(e.name) >= 1000
        )
        if adaylar:
            return adaylar[0]
    except Exception:
        pass

    # 3. Ortam değişkeni veya varsayılan
    return os.environ.get("MASAUSTU_UID", "1000")


# ── Yapılandırma ──────────────────────────────────────────────
DINLEME_PORTU  = int(os.environ.get("DINLEME_PORTU", 8765))
BILDIRIM_SURESI_MS = 15000              # Bildirimin ekranda kalma süresi (ms)
LOG_DOSYASI    = "/var/log/tahta_agent.log"

# Tahtada oturum açık olan kullanıcının UID'si
MASAUSTU_KULLANICI_UID = masaustu_uid_bul()

# Gizli anahtar — systemd EnvironmentFile=/etc/tahta_agent/secrets üzerinden gelir
GIZLI_ANAHTAR = os.environ.get("GIZLI_ANAHTAR", "")
if not GIZLI_ANAHTAR:
    print("HATA: GIZLI_ANAHTAR ortam değişkeni tanımlı değil.", file=sys.stderr)
    print("  /etc/tahta_agent/secrets dosyasını oluşturun ve", file=sys.stderr)
    print("  systemd servisine EnvironmentFile= ekleyin.", file=sys.stderr)
    sys.exit(1)
# ─────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DOSYASI),
        logging.StreamHandler(),
    ],
)


def bildirim_gonder(baslik: str, mesaj: str, sure_ms: int = BILDIRIM_SURESI_MS):
    """notify-send komutu ile masaüstü bildirimi gösterir."""
    env = os.environ.copy()
    env["DISPLAY"] = ":0"
    env["DBUS_SESSION_BUS_ADDRESS"] = (
        f"unix:path=/run/user/{MASAUSTU_KULLANICI_UID}/bus"
    )

    try:
        subprocess.Popen(
            [
                "notify-send",
                "--urgency=normal",
                f"--expire-time={sure_ms}",
                "--icon=dialog-information",
                baslik,
                mesaj,
            ],
            env=env,
        )
        logging.info("Bildirim gösterildi: %s", baslik)
    except FileNotFoundError:
        logging.error(
            "notify-send bulunamadı. Kurulum: sudo apt install libnotify-bin"
        )
    except Exception as exc:
        logging.error("notify-send hatası: %s", exc)


class BildirimHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        """Sağlık kontrolü — Django sunucusu bağlantıyı test etmek için kullanır."""
        if self.path == "/saglik":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path != "/bildirim":
            self.send_response(404)
            self.end_headers()
            return

        try:
            uzunluk = int(self.headers.get("Content-Length", 0))
            if uzunluk > 4096:
                self.send_response(413)
                self.end_headers()
                return
            veri = json.loads(self.rfile.read(uzunluk))
        except (json.JSONDecodeError, ValueError):
            self.send_response(400)
            self.end_headers()
            return

        # Gizli anahtar kontrolü
        if veri.get("anahtar") != GIZLI_ANAHTAR:
            logging.warning(
                "Geçersiz anahtar ile istek alındı: %s",
                self.client_address[0],
            )
            self.send_response(403)
            self.end_headers()
            return

        baslik = str(veri.get("baslik", "Okul Bildirimi"))[:200]
        mesaj  = str(veri.get("mesaj", ""))[:500]
        sure   = int(veri.get("sure_ms", BILDIRIM_SURESI_MS))

        bildirim_gonder(baslik, mesaj, sure)

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        """Standart HTTP loglarını gizle; kendi logging'imizi kullanıyoruz."""
        pass


def main():
    server = HTTPServer(("0.0.0.0", DINLEME_PORTU), BildirimHandler)
    logging.info("Tahta bildirim ajanı başlatıldı — port %d", DINLEME_PORTU)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Ajan durduruldu.")
        server.shutdown()


if __name__ == "__main__":
    main()
