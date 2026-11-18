#!/bin/sh
# Okul tahta ajanını bu tahtaya kurar. Tahtada root olarak çalıştırın:
#   sudo sh kur.sh                      # ayarları yandaki kurulum.conf'tan okur
#   sudo sh kur.sh /yol/kurulum.conf    # ayar dosyası başka bir yerdeyse
# Dosyalar bu betikle aynı klasörde olmalı: okul_ajan.py, okul-ajan.service,
# ajan.conf.ornek, kurulum.conf (ve varsa yerel-ca.crt).
#
# kurulum.conf (USB'de, bkz. kurulum.conf.ornek):
#   SUNUCU_ADRESI=https://<SUNUCU_ADRESI>
#   TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>
set -eu
# Türkçe yerel ayarda [A-Za-z] aralığı bazı harfleri (örn. "i") kaçırır;
# karakter denetimleri dilden bağımsız olsun.
export LC_ALL=C

KAYNAK=$(cd "$(dirname "$0")" && pwd)
KURULUM_DOSYASI=${1:-"$KAYNAK/kurulum.conf"}
AYAR=/etc/okul-ajan/ajan.conf

if [ "$(id -u)" -ne 0 ]; then
    echo "Root olarak çalıştırın: sudo sh $0" >&2
    exit 1
fi

# kurulum.conf'tan ANAHTAR=değer satırını okur. Dosya çalıştırılmaz (source
# edilmez); Windows satır sonu (\r), boşluklar ve tırnaklar temizlenir.
deger_oku() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$KURULUM_DOSYASI" \
        | tail -n 1 | tr -d '\r' | sed 's/[[:space:]]*$//; s/^["'\'']//; s/["'\'']$//'
}

SUNUCU=""
ANAHTAR=""
if [ -f "$KURULUM_DOSYASI" ]; then
    SUNUCU=$(deger_oku SUNUCU_ADRESI)
    ANAHTAR=$(deger_oku TAHTA_KAYIT_ANAHTARI)
    echo "Ayarlar okundu: $KURULUM_DOSYASI"
elif [ $# -gt 0 ]; then
    echo "Ayar dosyası bulunamadı: $KURULUM_DOSYASI" >&2
    exit 1
else
    echo "Uyarı: $KURULUM_DOSYASI yok; ayarları $AYAR içine elle girmeniz gerekecek." >&2
fi

if [ -n "$SUNUCU" ]; then
    # Adres şemasız yazıldıysa https varsayılır; sondaki / atılır.
    case "$SUNUCU" in
        http://* | https://*) ;;
        *) SUNUCU="https://$SUNUCU" ;;
    esac
    SUNUCU=${SUNUCU%/}
    if ! printf '%s' "$SUNUCU" | grep -Eq '^https?://[A-Za-z0-9._:-]+(/[A-Za-z0-9._~/-]*)?$'; then
        echo "SUNUCU_ADRESI geçersiz: $SUNUCU" >&2
        exit 1
    fi
fi
if [ -n "$ANAHTAR" ] && ! printf '%s' "$ANAHTAR" | grep -Eq '^[A-Za-z0-9_-]+$'; then
    # Sunucuda secrets.token_urlsafe ile üretilen anahtar yalnızca bu karakterleri içerir.
    echo "TAHTA_KAYIT_ANAHTARI geçersiz karakter içeriyor." >&2
    exit 1
fi

install -d -m 0755 /opt/okul-ajan
install -m 0755 "$KAYNAK/okul_ajan.py" /opt/okul-ajan/okul_ajan.py

install -d -m 0700 /etc/okul-ajan
if [ ! -f "$AYAR" ]; then
    install -m 0600 "$KAYNAK/ajan.conf.ornek" "$AYAR"
    echo "$AYAR oluşturuldu."
fi
# Değerler verildiyse (yeniden kurulumda da) ayar dosyasına yazılır; diğer
# ayarlar (ca_dosyasi, aralik) olduğu gibi kalır.
if [ -n "$SUNUCU" ]; then
    sed -i "s|^[[:space:]]*sunucu[[:space:]]*=.*|sunucu = $SUNUCU|" "$AYAR"
fi
if [ -n "$ANAHTAR" ]; then
    sed -i "s|^[[:space:]]*kayit_anahtari[[:space:]]*=.*|kayit_anahtari = $ANAHTAR|" "$AYAR"
fi

if [ -f "$KAYNAK/yerel-ca.crt" ]; then
    install -m 0644 "$KAYNAK/yerel-ca.crt" /etc/okul-ajan/yerel-ca.crt
fi

install -m 0644 "$KAYNAK/okul-ajan.service" /etc/systemd/system/okul-ajan.service
systemctl daemon-reload

if grep -q '<KAYIT_ANAHTARI>\|<SUNUCU_ADRESI>' "$AYAR"; then
    echo "Eksik ayar var. $AYAR dosyasını düzenledikten sonra: systemctl enable --now okul-ajan"
else
    systemctl enable --now okul-ajan
    systemctl restart okul-ajan
    echo "okul-ajan çalışıyor. Günlük: sudo journalctl -u okul-ajan -n 20 -f"
fi
