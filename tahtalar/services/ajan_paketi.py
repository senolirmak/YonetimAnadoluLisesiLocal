"""Tahta ajanı için ETAP/Pardus'a kurulabilir .deb paketi üretir.

Paket sunucuda, bellekte üretilir; dpkg-deb / fakeroot gerekmez (.deb, içinde
iki tar.gz bulunan basit bir `ar` arşividir). Sunucu adresi, kayıt anahtarı ve
varsa yerel CA sertifikası pakete gömülür; tahtada

    sudo apt install ./okul-ajan_<sürüm>_all.deb

yeterlidir. postinst, `kur.sh`'ın yaptığını yapar: /etc/okul-ajan/ajan.conf'u
oluşturur (varsa yalnızca `sunucu` ve `kayit_anahtari` satırlarını günceller),
servisi etkinleştirip yeniden başlatır. Eski `kur.sh` kurulumunun üzerine de
kurulabilir.

Paket kayıt anahtarını içerir: yalnızca üst yönetici indirir ya da süreli,
imzalı bir link üretir (bkz. `indirme_tokeni_uret`).
"""

import hashlib
import io
import re
import tarfile
import time
from pathlib import Path

from django.conf import settings
from django.core import signing

PAKET_ADI = "okul-ajan"
AJAN_KLASORU = Path(__file__).resolve().parent.parent / "ajan"
CA_DOSYASI = Path(settings.BASE_DIR) / "yerel-ca-sertifikasi.crt"

LINK_GECERLILIK_SN = 24 * 60 * 60
_IMZA_TUZU = "tahtalar.ajan_paketi"

# kur.sh ile aynı kurallar.
_SUNUCU_KALIBI = re.compile(r"^https?://[A-Za-z0-9._:-]+(/[A-Za-z0-9._~/-]*)?$")
_ANAHTAR_KALIBI = re.compile(r"^[A-Za-z0-9_-]+$")


class PaketHatasi(Exception):
    pass


def ajan_surumu():
    """okul_ajan.py içindeki SURUM sabitini (dosyayı çalıştırmadan) okur."""
    metin = (AJAN_KLASORU / "okul_ajan.py").read_text(encoding="utf-8")
    eslesme = re.search(r'^SURUM = "([0-9][0-9A-Za-z.+~-]*)"$', metin, re.MULTILINE)
    if not eslesme:
        raise PaketHatasi("okul_ajan.py içinde SURUM bulunamadı.")
    return eslesme.group(1)


def paket_dosya_adi():
    return f"{PAKET_ADI}_{ajan_surumu()}_all.deb"


def sunucu_adresini_dogrula(sunucu):
    """Adresi kur.sh ile aynı biçimde düzeltir: şema yoksa https, sondaki / atılır."""
    sunucu = (sunucu or "").strip()
    if sunucu and not sunucu.startswith(("http://", "https://")):
        if "://" in sunucu:
            raise PaketHatasi(f"Sunucu adresi http:// ya da https:// ile başlamalı: {sunucu}")
        sunucu = "https://" + sunucu
    sunucu = sunucu.rstrip("/")
    if not _SUNUCU_KALIBI.match(sunucu):
        raise PaketHatasi(f"Sunucu adresi geçersiz: {sunucu or '(boş)'}")
    return sunucu


def kayit_anahtari():
    anahtar = settings.TAHTA_KAYIT_ANAHTARI
    if not anahtar:
        raise PaketHatasi(
            "Sunucuda TAHTA_KAYIT_ANAHTARI tanımlı değil; paketle kurulan tahtalar kaydolamaz."
        )
    if not _ANAHTAR_KALIBI.match(anahtar):
        raise PaketHatasi("TAHTA_KAYIT_ANAHTARI geçersiz karakter içeriyor.")
    return anahtar


def ca_sertifikasi():
    """Kurulumcunun dağıtım için çıkardığı yerel CA'nın genel sertifikası (yoksa None)."""
    return CA_DOSYASI.read_bytes() if CA_DOSYASI.is_file() else None


# ── İndirme linki ───────────────────────────────────────────────────────


def indirme_tokeni_uret(sunucu):
    return signing.dumps({"sunucu": sunucu}, salt=_IMZA_TUZU, compress=True)


def indirme_tokenini_coz(token):
    """Geçerliyse sunucu adresini, süresi dolmuş/bozuksa None döndürür."""
    try:
        veri = signing.loads(token, salt=_IMZA_TUZU, max_age=LINK_GECERLILIK_SN)
    except signing.BadSignature:  # SignatureExpired da bunun alt sınıfı
        return None
    return veri.get("sunucu") if isinstance(veri, dict) else None


# ── Paket içeriği ───────────────────────────────────────────────────────

_POSTINST = """#!/bin/sh
set -e
[ "$1" = "configure" ] || exit 0

AYAR=/etc/okul-ajan/ajan.conf
PAYLASIM=/usr/share/okul-ajan
. "$PAYLASIM/kurulum.conf"

install -d -m 0700 /etc/okul-ajan
if [ ! -f "$AYAR" ]; then
    install -m 0600 "$PAYLASIM/ajan.conf.ornek" "$AYAR"
fi
# Yeniden kurulumda yalnızca bu iki satır güncellenir; diğer ayarlar korunur.
sed -i "s|^[[:space:]]*sunucu[[:space:]]*=.*|sunucu = $SUNUCU_ADRESI|" "$AYAR"
sed -i "s|^[[:space:]]*kayit_anahtari[[:space:]]*=.*|kayit_anahtari = $TAHTA_KAYIT_ANAHTARI|" "$AYAR"

if [ -f "$PAYLASIM/yerel-ca.crt" ]; then
    install -m 0644 "$PAYLASIM/yerel-ca.crt" /etc/okul-ajan/yerel-ca.crt
elif [ ! -f /etc/okul-ajan/yerel-ca.crt ]; then
    # CA yoksa sistemin güvendiği sertifikalar kullanılır.
    sed -i "s|^[[:space:]]*ca_dosyasi[[:space:]]*=.*|ca_dosyasi =|" "$AYAR"
fi

# Eski kur.sh kurulumunun servis dosyası paketinkini gölgeler; kaldırılır.
rm -f /etc/systemd/system/okul-ajan.service

if [ -d /run/systemd/system ]; then
    systemctl daemon-reload
    systemctl enable okul-ajan.service >/dev/null 2>&1 || true
    systemctl restart okul-ajan.service
fi
echo "okul-ajan çalışıyor. Günlük: sudo journalctl -u okul-ajan -n 20 -f"
exit 0
"""

_PRERM = """#!/bin/sh
set -e
if [ "$1" = "remove" ] && [ -d /run/systemd/system ]; then
    systemctl disable --now okul-ajan.service >/dev/null 2>&1 || true
fi
exit 0
"""

_POSTRM = """#!/bin/sh
set -e
if [ "$1" = "purge" ]; then
    rm -rf /etc/okul-ajan /var/lib/okul-ajan
fi
if [ -d /run/systemd/system ]; then
    systemctl daemon-reload >/dev/null 2>&1 || true
fi
exit 0
"""


def _control(surum, kurulu_boyut_kb):
    return (
        f"Package: {PAKET_ADI}\n"
        f"Version: {surum}\n"
        "Architecture: all\n"
        "Maintainer: Okul Yonetim Sistemi <root@localhost>\n"
        "Depends: python3, systemd\n"
        "Section: admin\n"
        "Priority: optional\n"
        f"Installed-Size: {kurulu_boyut_kb}\n"
        "Description: Okul tahta ajani\n"
        " Etkilesimli tahtanin durumunu okul sunucusuna bildirir ve\n"
        " kapat / yeniden baslat / guncelle komutlarini uygular.\n"
        " MEB Ahenk dosyalarina yazmaz.\n"
    )


def _tar_gz(dosyalar, zaman):
    """dosyalar: [(yol, içerik bytes | None=klasör, mod)] → tar.gz bytes (root:root)."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:gz", format=tarfile.GNU_FORMAT) as tar:
        for yol, icerik, mod in dosyalar:
            bilgi = tarfile.TarInfo(yol)
            bilgi.mode = mod
            bilgi.mtime = zaman
            bilgi.uid = bilgi.gid = 0
            bilgi.uname = bilgi.gname = "root"
            if icerik is None:
                bilgi.type = tarfile.DIRTYPE
                tar.addfile(bilgi)
            else:
                bilgi.size = len(icerik)
                tar.addfile(bilgi, io.BytesIO(icerik))
    return tampon.getvalue()


def _ar(uyeler, zaman):
    """uyeler: [(ad, içerik bytes)] → ar arşivi (Debian .deb biçimi)."""
    cikti = io.BytesIO()
    cikti.write(b"!<arch>\n")
    for ad, icerik in uyeler:
        baslik = (
            f"{ad:<16}{zaman:<12}{0:<6}{0:<6}{'100644':<8}{len(icerik):<10}`\n"
        ).encode("ascii")
        cikti.write(baslik)
        cikti.write(icerik)
        if len(icerik) % 2:
            cikti.write(b"\n")
    return cikti.getvalue()


def paket_olustur(sunucu):
    """Verilen sunucu adresi ve sunucudaki kayıt anahtarıyla .deb üretir → bytes."""
    sunucu = sunucu_adresini_dogrula(sunucu)
    anahtar = kayit_anahtari()
    surum = ajan_surumu()
    zaman = int(time.time())

    kurulum_conf = (
        "# okul-ajan paketi tarafından üretildi; postinst okur.\n"
        f"SUNUCU_ADRESI='{sunucu}'\n"
        f"TAHTA_KAYIT_ANAHTARI='{anahtar}'\n"
    ).encode("utf-8")

    veri = [
        ("./opt/", None, 0o755),
        ("./opt/okul-ajan/", None, 0o755),
        ("./opt/okul-ajan/okul_ajan.py", (AJAN_KLASORU / "okul_ajan.py").read_bytes(), 0o755),
        ("./lib/", None, 0o755),
        ("./lib/systemd/", None, 0o755),
        ("./lib/systemd/system/", None, 0o755),
        (
            "./lib/systemd/system/okul-ajan.service",
            (AJAN_KLASORU / "okul-ajan.service").read_bytes(),
            0o644,
        ),
        ("./usr/", None, 0o755),
        ("./usr/share/", None, 0o755),
        ("./usr/share/okul-ajan/", None, 0o755),
        ("./usr/share/okul-ajan/ajan.conf.ornek", (AJAN_KLASORU / "ajan.conf.ornek").read_bytes(), 0o644),
        # Kayıt anahtarını içerir: yalnızca root okur.
        ("./usr/share/okul-ajan/kurulum.conf", kurulum_conf, 0o600),
    ]
    ca = ca_sertifikasi() if sunucu.startswith("https://") else None
    if ca:
        veri.append(("./usr/share/okul-ajan/yerel-ca.crt", ca, 0o644))

    dosyalar = [(yol, icerik) for yol, icerik, _ in veri if icerik is not None]
    md5sums = "".join(
        f"{hashlib.md5(icerik, usedforsecurity=False).hexdigest()}  {yol[2:]}\n" for yol, icerik in dosyalar
    ).encode("utf-8")
    kurulu_boyut_kb = max(1, sum(len(i) for _, i in dosyalar) // 1024)

    kontrol = [
        ("./", None, 0o755),
        ("./control", _control(surum, kurulu_boyut_kb).encode("utf-8"), 0o644),
        ("./md5sums", md5sums, 0o644),
        ("./postinst", _POSTINST.encode("utf-8"), 0o755),
        ("./prerm", _PRERM.encode("utf-8"), 0o755),
        ("./postrm", _POSTRM.encode("utf-8"), 0o755),
    ]
    return _ar(
        [
            ("debian-binary", b"2.0\n"),
            ("control.tar.gz", _tar_gz(kontrol, zaman)),
            ("data.tar.gz", _tar_gz([("./", None, 0o755)] + veri, zaman)),
        ],
        zaman,
    )
