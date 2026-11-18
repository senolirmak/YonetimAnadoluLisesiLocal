#!/bin/sh
# Eski adla (okul-ajan) yapılmış kurulumu akal-eta-yonetim'e taşır.
# kur.sh ve .deb paketinin postinst'i çağırır; root olarak çalışır.
#
#   sh eski-kurulumu-tasi.sh          # gerçek sistemde
#   sh eski-kurulumu-tasi.sh /kok     # test: yollar /kok altında, systemctl çağrılmaz
#
# Taşınanlar: ayar dosyası (yalnızca yenisi yoksa), yerel CA sertifikası ve
# tahtanın sunucudaki kaydının token'ı — böylece tahta sunucuda aynı kayıtla
# devam eder. Eski servis durdurulup kapatılır, eski dosyalar silinir.
# Eski kurulum yoksa hiçbir şey yapmaz; tekrar çalıştırmak güvenlidir.
set -eu

KOK=${1:-}
ESKI=okul-ajan
YENI=akal-eta-yonetim

ESKI_AYAR_KLASORU=$KOK/etc/$ESKI
ESKI_DURUM_KLASORU=$KOK/var/lib/$ESKI
ESKI_SERVIS=$KOK/etc/systemd/system/$ESKI.service
YENI_AYAR_KLASORU=$KOK/etc/$YENI
YENI_AYAR=$YENI_AYAR_KLASORU/$YENI.conf
YENI_DURUM_KLASORU=$KOK/var/lib/$YENI

if [ ! -e "$ESKI_AYAR_KLASORU" ] && [ ! -e "$ESKI_DURUM_KLASORU" ] \
    && [ ! -e "$ESKI_SERVIS" ] && [ ! -e "$KOK/opt/$ESKI" ]; then
    exit 0
fi

echo "Eski kurulum ($ESKI) bulundu, $YENI'e taşınıyor."

# Eski servis durdurulur. .deb ile kurulmuş okul-ajan paketini apt zaten
# kaldırır (Conflicts); kur.sh kurulumunda servis dosyası elle silinir.
if [ -z "$KOK" ] && [ -d /run/systemd/system ]; then
    systemctl disable --now "$ESKI.service" >/dev/null 2>&1 || true
fi
rm -f "$ESKI_SERVIS"

if [ -f "$ESKI_AYAR_KLASORU/ajan.conf" ] && [ ! -f "$YENI_AYAR" ]; then
    install -d -m 0700 "$YENI_AYAR_KLASORU"
    install -m 0600 "$ESKI_AYAR_KLASORU/ajan.conf" "$YENI_AYAR"
    sed -i "s|^\[ajan\]|[$YENI]|; s|/etc/$ESKI/|/etc/$YENI/|g" "$YENI_AYAR"
    echo "Ayarlar taşındı: $YENI_AYAR"
fi
if [ -f "$ESKI_AYAR_KLASORU/yerel-ca.crt" ] && [ ! -f "$YENI_AYAR_KLASORU/yerel-ca.crt" ]; then
    install -d -m 0700 "$YENI_AYAR_KLASORU"
    install -m 0644 "$ESKI_AYAR_KLASORU/yerel-ca.crt" "$YENI_AYAR_KLASORU/yerel-ca.crt"
fi
if [ -f "$ESKI_DURUM_KLASORU/token" ] && [ ! -f "$YENI_DURUM_KLASORU/token" ]; then
    install -d -m 0700 "$YENI_DURUM_KLASORU"
    install -m 0600 "$ESKI_DURUM_KLASORU/token" "$YENI_DURUM_KLASORU/token"
    echo "Tahtanın sunucu kaydı korundu."
fi

rm -rf "$KOK/opt/$ESKI" "$ESKI_AYAR_KLASORU" "$ESKI_DURUM_KLASORU"
if [ -z "$KOK" ] && [ -d /run/systemd/system ]; then
    systemctl daemon-reload
fi
echo "Eski kurulum kaldırıldı."
