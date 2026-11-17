#!/bin/sh
# Okul tahta ajanını bu tahtaya kurar. Tahtada root olarak çalıştırın:
#   sudo sh kur.sh
# Dosyalar bu betikle aynı klasörde olmalı: okul_ajan.py, okul-ajan.service,
# ajan.conf.ornek (ve varsa yerel-ca.crt).
set -eu

KAYNAK=$(cd "$(dirname "$0")" && pwd)

if [ "$(id -u)" -ne 0 ]; then
    echo "Root olarak çalıştırın: sudo sh $0" >&2
    exit 1
fi

install -d -m 0755 /opt/okul-ajan
install -m 0755 "$KAYNAK/okul_ajan.py" /opt/okul-ajan/okul_ajan.py

install -d -m 0700 /etc/okul-ajan
if [ ! -f /etc/okul-ajan/ajan.conf ]; then
    install -m 0600 "$KAYNAK/ajan.conf.ornek" /etc/okul-ajan/ajan.conf
    echo "/etc/okul-ajan/ajan.conf oluşturuldu — sunucu ve kayit_anahtari değerlerini girin."
fi
if [ -f "$KAYNAK/yerel-ca.crt" ]; then
    install -m 0644 "$KAYNAK/yerel-ca.crt" /etc/okul-ajan/yerel-ca.crt
fi

install -m 0644 "$KAYNAK/okul-ajan.service" /etc/systemd/system/okul-ajan.service
systemctl daemon-reload

if grep -q '<KAYIT_ANAHTARI>\|<SUNUCU_ADRESI>' /etc/okul-ajan/ajan.conf; then
    echo "Ayar dosyasını düzenledikten sonra: systemctl enable --now okul-ajan"
else
    systemctl enable --now okul-ajan
    systemctl restart okul-ajan
    echo "okul-ajan çalışıyor. Günlük: journalctl -u okul-ajan -f"
fi
