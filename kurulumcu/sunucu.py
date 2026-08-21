"""Sunucu (üretim) modu: Gunicorn systemd servisi ve Nginx reverse proxy kurulumu."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from pathlib import Path

from . import yardimci as y


def gunicorn_servisi_kur(proje_dizin: Path, venv: Path, servis_adi: str, kullanici: str, grup: str) -> str:
    servis = f"{servis_adi}.service"
    y.bilgi(f"Gunicorn systemd servisi yazılıyor: {servis}")

    icerik = f"""[Unit]
Description={servis_adi} Django
After=network.target

[Service]
User={kullanici}
Group={grup}
# Soket ve olası gelecekteki dosya yazımları grup üyesine (nginx) rwx, diğerlerine
# hiç erişim bırakmasın diye: varsayılan izinden 0007 çıkarılır (rwxrwx--- kalır).
UMask=0007
WorkingDirectory={proje_dizin}
EnvironmentFile={proje_dizin}/.env

# systemd her başlatmada /run/{servis_adi}/ dizinini otomatik oluşturur.
# /run tmpfs olduğundan reboot sonrası dizin kaybolur — RuntimeDirectory bunu çözer.
# 0750: yalnızca {kullanici} ve {grup} (nginx) girebilir, diğerleri giremez.
RuntimeDirectory={servis_adi}
RuntimeDirectoryMode=0750

ExecStart={venv}/bin/gunicorn \\
    --workers 3 \\
    --timeout 120 \\
    --bind unix:/run/{servis_adi}/gunicorn.sock \\
    config.wsgi:application
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""
    y.calistir(["tee", f"/etc/systemd/system/{servis}"], sudo=True, sessiz=True, girdi=icerik)

    y.calistir(["systemctl", "daemon-reload"], sudo=True)
    y.calistir(["systemctl", "enable", servis], sudo=True, sessiz=True)
    y.calistir(["systemctl", "restart", servis], sudo=True)
    time.sleep(2)
    if not y.basarili_mi(["systemctl", "is-active", "--quiet", servis]):
        y.hata(f"Servis başlatılamadı! Loglar: sudo journalctl -u {servis} -n 30")
    y.basari(f"Gunicorn servisi çalışıyor: {servis}")
    return servis


def _varsayilan_siteyi_devre_disi_birak() -> None:
    """Nginx paketiyle birlikte gelen varsayılan site tanımını devre dışı bırakır.

    Bizim conf.d dosyamız `default_server` bayrağını almadıkça, dağıtımın kendi
    varsayılan sitesi (Debian/Ubuntu'da sites-enabled/default, resmi nginx.org
    RPM paketinde conf.d/default.conf) `listen 80 default_server;` ile önceliği
    elinde tutmaya devam eder — bu durumda server_name eşleşmeyen/bare-IP
    istekler (örn. `saglik_kontrolu()`'nun kendi 127.0.0.1 isteği) sessizce
    nginx'in "Welcome to nginx" sayfasına düşer, bizim uygulamamıza değil.
    Dosya yoksa mv sessizce başarısız olur (kontrol=False) — tekrar çalıştırmak
    güvenlidir.
    """
    for yol in ("/etc/nginx/sites-enabled/default", "/etc/nginx/conf.d/default.conf"):
        y.calistir(["mv", yol, f"{yol}.devre-disi"], sudo=True, sessiz=True, kontrol=False)


def nginx_yapilandir(proje_dizin: Path, servis_adi: str, allowed_hosts: str) -> None:
    server_name = allowed_hosts.replace(",", " ").strip() or "_"
    dosya = f"/etc/nginx/conf.d/{servis_adi}.conf"
    y.bilgi(f"Nginx yapılandırması yazılıyor: {dosya}")

    _varsayilan_siteyi_devre_disi_birak()

    icerik = f"""server {{
    listen 80 default_server;
    server_name {server_name};

    client_max_body_size 20M;

    location /static/ {{
        alias {proje_dizin}/staticfiles/;
    }}

    location /media/ {{
        alias {proje_dizin}/media/;
    }}

    location / {{
        proxy_pass http://unix:/run/{servis_adi}/gunicorn.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }}
}}
"""
    y.calistir(["tee", dosya], sudo=True, sessiz=True, girdi=icerik)

    if not y.basarili_mi(["nginx", "-t"], sudo=True):
        y.hata("Nginx yapılandırma testi başarısız. 'sudo nginx -t' ile inceleyin.")
    y.calistir(["systemctl", "enable", "nginx"], sudo=True, sessiz=True)
    y.calistir(["systemctl", "restart", "nginx"], sudo=True)
    y.basari("Nginx yapılandırıldı ve yeniden başlatıldı.")


def saglik_kontrolu(servis: str) -> None:
    y.bilgi("Sağlık kontrolü yapılıyor...")
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1/", timeout=5) as yanit:
            if yanit.status < 500:
                y.basari(f"Site ayağa kalktı: http://127.0.0.1/ üzerinden {yanit.status} yanıtı alınıyor.")
                return
    except urllib.error.HTTPError as hata_nesnesi:
        if hata_nesnesi.code < 500:
            y.basari(f"Site ayağa kalktı: http://127.0.0.1/ üzerinden {hata_nesnesi.code} yanıtı alınıyor.")
            return
    except Exception:
        pass
    y.uyari(f"Site henüz yanıt vermiyor. Kontrol: 'sudo journalctl -u {servis} -f' ve 'sudo journalctl -u nginx -f'")
