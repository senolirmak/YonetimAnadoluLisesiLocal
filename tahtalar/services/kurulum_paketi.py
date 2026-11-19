"""akal-eta-yonetim için ETAP/Pardus'a kurulabilir .deb paketi üretir.

Paket sunucuda, bellekte üretilir; dpkg-deb / fakeroot gerekmez (.deb, içinde
iki tar.gz bulunan basit bir `ar` arşividir). Sunucu adresi, kayıt anahtarı ve
varsa yerel CA sertifikası pakete gömülür; tahtada

    sudo apt install ./akal-eta-yonetim_<sürüm>_all.deb

yeterlidir. postinst, `kur.sh`'ın yaptığını yapar: eski adla (okul-ajan)
yapılmış kurulumu taşır (eski-kurulumu-tasi.sh), ayar dosyasını oluşturur (varsa
yalnızca `sunucu` ve `kayit_anahtari` satırlarını günceller), servisi
etkinleştirip yeniden başlatır.

Paket kayıt anahtarını içerir: yalnızca üst yönetici indirir ya da süreli,
imzalı bir link üretir (bkz. `indirme_tokeni_uret`).

Sunucuda APT depo anahtarı varsa (bkz. `depo_anahtari`) paket depo kaynağını
da kurar; sonraki sürümler tahtaya sunucudaki APT deposundan gelir. Depodaki
paket (`depo_paketi_olustur`) kayıt anahtarı, sunucu adresi ve CA içermez;
kurulu tahtanın ayarlarına dokunmaz.
"""

import gzip
import hashlib
import io
import re
import tarfile
import time
from pathlib import Path

from django.conf import settings
from django.core import signing

from tahtalar.services import depo_anahtari

PAKET_ADI = "akal-eta-yonetim"
ESKI_PAKET_ADI = "okul-ajan"
UYGULAMA_KLASORU = Path(__file__).resolve().parent.parent / PAKET_ADI
UYGULAMA_DOSYASI = "akal_eta_yonetim.py"
CA_DOSYASI = Path(settings.BASE_DIR) / "yerel-ca-sertifikasi.crt"

LINK_GECERLILIK_SN = 24 * 60 * 60
_IMZA_TUZU = "tahtalar.ajan_paketi"  # değişirse üretilmiş linkler geçersiz olur

# kur.sh ile aynı kurallar.
_SUNUCU_KALIBI = re.compile(r"^https?://[A-Za-z0-9._:-]+(/[A-Za-z0-9._~/-]*)?$")
_ANAHTAR_KALIBI = re.compile(r"^[A-Za-z0-9_-]+$")


class PaketHatasi(Exception):
    pass


def uygulama_surumu():
    """akal_eta_yonetim.py içindeki SURUM sabitini (dosyayı çalıştırmadan) okur."""
    metin = (UYGULAMA_KLASORU / UYGULAMA_DOSYASI).read_text(encoding="utf-8")
    eslesme = re.search(r'^SURUM = "([0-9][0-9A-Za-z.+~-]*)"$', metin, re.MULTILINE)
    if not eslesme:
        raise PaketHatasi(f"{UYGULAMA_DOSYASI} içinde SURUM bulunamadı.")
    return eslesme.group(1)


def paket_dosya_adi():
    return f"{PAKET_ADI}_{uygulama_surumu()}_all.deb"


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

UYGULAMA=akal-eta-yonetim
AYAR=/etc/$UYGULAMA/$UYGULAMA.conf
PAYLASIM=/usr/share/$UYGULAMA
# Kurulum paketinde var; APT deposundaki pakette yok (kurulu ayarlara dokunulmaz).
SUNUCU_ADRESI=
TAHTA_KAYIT_ANAHTARI=
if [ -f "$PAYLASIM/kurulum.conf" ]; then
    . "$PAYLASIM/kurulum.conf"
fi

# Eski adla (okul-ajan) yapılmış kurulumun ayarları ve sunucu kaydı taşınır.
sh "$PAYLASIM/eski-kurulumu-tasi.sh"

install -d -m 0700 /etc/$UYGULAMA
if [ ! -f "$AYAR" ]; then
    install -m 0600 "$PAYLASIM/$UYGULAMA.conf.ornek" "$AYAR"
fi
# Yeniden kurulumda yalnızca bu iki satır güncellenir; diğer ayarlar korunur.
if [ -n "$SUNUCU_ADRESI" ]; then
    sed -i "s|^[[:space:]]*sunucu[[:space:]]*=.*|sunucu = $SUNUCU_ADRESI|" "$AYAR"
fi
if [ -n "$TAHTA_KAYIT_ANAHTARI" ]; then
    sed -i "s|^[[:space:]]*kayit_anahtari[[:space:]]*=.*|kayit_anahtari = $TAHTA_KAYIT_ANAHTARI|" "$AYAR"
fi

if [ -f "$PAYLASIM/yerel-ca.crt" ]; then
    install -m 0644 "$PAYLASIM/yerel-ca.crt" /etc/$UYGULAMA/yerel-ca.crt
elif [ ! -f /etc/$UYGULAMA/yerel-ca.crt ]; then
    # CA yoksa sistemin güvendiği sertifikalar kullanılır.
    sed -i "s|^[[:space:]]*ca_dosyasi[[:space:]]*=.*|ca_dosyasi =|" "$AYAR"
fi

# APT deposu: sonraki sürümler okul sunucusundan gelir. Adres ve CA ayar
# dosyasından alınır. Okul sunucusuna vekil sunucu (proxy) olmadan gidilir;
# APT dosyaları _apt kullanıcısıyla indirdiği için CA okunabilir bir yere kopyalanır.
# Kurulu sürüm 1000 öncelikle sabitlenir (pin): tahtadaki genel "apt upgrade" /
# "dist-upgrade" (Güncelle komutu) bu paketi yükseltmez. Paket yalnızca
# uygulamanın sağlık kontrollü kendini güncellemesiyle (tam sürüm belirterek)
# ya da elle .deb ile kurulur; çalışmazsa eski sürüme dönülür. Her kurulumda
# (geri dönüş dahil) pin kurulan sürüme güncellenir.
ANAHTARLIK=/usr/share/keyrings/$UYGULAMA.gpg
LISTE=/etc/apt/sources.list.d/$UYGULAMA.list
APT_AYAR=/etc/apt/apt.conf.d/50$UYGULAMA
APT_CA=/etc/apt/$UYGULAMA-ca.crt
APT_ONCELIK=/etc/apt/preferences.d/$UYGULAMA
ayar_degeri() {
    sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$AYAR" | head -n 1 | tr -d '[:space:]'
}
SUNUCU=$(ayar_degeri sunucu)
SUNUCU=${SUNUCU%/}
if [ -f "$ANAHTARLIK" ] && printf '%s\\n' "$SUNUCU" | grep -Eqx 'https?://[A-Za-z0-9._:-]+(/[A-Za-z0-9._~/-]*)?'; then
    SUNUCU_HOST=$(printf '%s\\n' "$SUNUCU" | sed -e 's|^[a-z]*://||' -e 's|[:/].*$||')
    printf 'deb [signed-by=%s] %s/tahtalar/apt/ ./\\n' "$ANAHTARLIK" "$SUNUCU" > "$LISTE.tmp"
    {
        echo "// $UYGULAMA paketi üretir; elle değiştirmeyin."
        echo "Acquire::http::Proxy::$SUNUCU_HOST \\"DIRECT\\";"
        echo "Acquire::https::Proxy::$SUNUCU_HOST \\"DIRECT\\";"
    } > "$APT_AYAR.tmp"
    CA=$(ayar_degeri ca_dosyasi)
    if [ "${SUNUCU%%://*}" = https ] && [ -n "$CA" ] && [ -f "$CA" ]; then
        install -m 0644 "$CA" "$APT_CA"
        echo "Acquire::https::$SUNUCU_HOST::CaInfo \\"$APT_CA\\";" >> "$APT_AYAR.tmp"
    else
        rm -f "$APT_CA"
    fi
    KURULU=$(dpkg-query -W -f='${Version}' $UYGULAMA)
    printf 'Package: %s\\nPin: version %s\\nPin-Priority: 1000\\n' "$UYGULAMA" "$KURULU" > "$APT_ONCELIK.tmp"
    chmod 0644 "$LISTE.tmp" "$APT_AYAR.tmp" "$APT_ONCELIK.tmp"
    mv "$LISTE.tmp" "$LISTE"
    mv "$APT_AYAR.tmp" "$APT_AYAR"
    mv "$APT_ONCELIK.tmp" "$APT_ONCELIK"
else
    rm -f "$LISTE" "$APT_AYAR" "$APT_CA" "$APT_ONCELIK"
fi

# kur.sh kurulumunun servis dosyası paketinkini gölgeler; kaldırılır.
rm -f /etc/systemd/system/$UYGULAMA.service

if [ -d /run/systemd/system ]; then
    systemctl daemon-reload
    systemctl enable $UYGULAMA.service >/dev/null 2>&1 || true
    systemctl restart $UYGULAMA.service
fi
echo "$UYGULAMA çalışıyor. Günlük: sudo journalctl -u $UYGULAMA -n 20 -f"
exit 0
"""

_PRERM = """#!/bin/sh
set -e
if [ "$1" = "remove" ] && [ -d /run/systemd/system ]; then
    systemctl disable --now akal-eta-yonetim.service >/dev/null 2>&1 || true
fi
exit 0
"""

_POSTRM = """#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    rm -f /etc/apt/sources.list.d/akal-eta-yonetim.list \
        /etc/apt/apt.conf.d/50akal-eta-yonetim /etc/apt/akal-eta-yonetim-ca.crt \
        /etc/apt/preferences.d/akal-eta-yonetim
fi
if [ "$1" = "purge" ]; then
    rm -rf /etc/akal-eta-yonetim /var/lib/akal-eta-yonetim
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
        # Eski adlı paket kuruluysa apt onu kaldırır; ayarları postinst taşır.
        f"Conflicts: {ESKI_PAKET_ADI}\n"
        f"Replaces: {ESKI_PAKET_ADI}\n"
        "Section: admin\n"
        "Priority: optional\n"
        f"Installed-Size: {kurulu_boyut_kb}\n"
        "Description: akal-eta-yonetim - etkilesimli tahta yonetimi\n"
        " Etkilesimli tahtanin durumunu okul sunucusuna bildirir ve\n"
        " kapat / yeniden baslat / guncelle komutlarini uygular.\n"
        " MEB Ahenk dosyalarina yazmaz.\n"
    )


def _tar_gz(dosyalar, zaman):
    """dosyalar: [(yol, içerik bytes | None=klasör, mod)] → tar.gz bytes (root:root)."""
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w", format=tarfile.GNU_FORMAT) as tar:
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
    # gzip başlığındaki zaman da sabitlenir: aynı girdi aynı baytları verir.
    return gzip.compress(tampon.getvalue(), compresslevel=9, mtime=zaman)


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
    """Kurulum paketi: verilen sunucu adresi ve sunucudaki kayıt anahtarıyla .deb → bytes."""
    sunucu = sunucu_adresini_dogrula(sunucu)
    anahtar = kayit_anahtari()
    kurulum_conf = (
        f"# {PAKET_ADI} paketi tarafından üretildi; postinst okur.\n"
        f"SUNUCU_ADRESI='{sunucu}'\n"
        f"TAHTA_KAYIT_ANAHTARI='{anahtar}'\n"
    ).encode("utf-8")
    ca = ca_sertifikasi() if sunucu.startswith("https://") else None
    return _deb(kurulum_conf, ca, int(time.time()))


def depo_paketi_olustur():
    """APT deposundaki paket: kayıt anahtarı, sunucu adresi ve CA içermez; aynı
    sürüm her zaman aynı baytları verir (Packages dosyasındaki özet tutar)."""
    if depo_anahtari.acik_anahtarlik() is None:
        raise PaketHatasi("APT depo anahtarı yok.")
    return _deb(None, None, depo_anahtari.SABIT_ZAMAN)


def control_alanlari(paket):
    """.deb içindeki control dosyasının metni (Packages dosyası için)."""
    uyeler, i = {}, 8
    while i < len(paket):
        baslik = paket[i : i + 60]
        ad = baslik[:16].decode("ascii").strip().rstrip("/")
        boyut = int(baslik[48:58].decode("ascii").strip())
        uyeler[ad] = paket[i + 60 : i + 60 + boyut]
        i += 60 + boyut + (boyut % 2)
    with tarfile.open(fileobj=io.BytesIO(uyeler["control.tar.gz"]), mode="r:gz") as tar:
        return tar.extractfile("./control").read().decode("utf-8")


def _deb(kurulum_conf, ca, zaman):
    surum = uygulama_surumu()
    paylasim = f"./usr/share/{PAKET_ADI}"
    veri = [
        ("./opt/", None, 0o755),
        (f"./opt/{PAKET_ADI}/", None, 0o755),
        (
            f"./opt/{PAKET_ADI}/{UYGULAMA_DOSYASI}",
            (UYGULAMA_KLASORU / UYGULAMA_DOSYASI).read_bytes(),
            0o755,
        ),
        ("./lib/", None, 0o755),
        ("./lib/systemd/", None, 0o755),
        ("./lib/systemd/system/", None, 0o755),
        (
            f"./lib/systemd/system/{PAKET_ADI}.service",
            (UYGULAMA_KLASORU / f"{PAKET_ADI}.service").read_bytes(),
            0o644,
        ),
        ("./usr/", None, 0o755),
        ("./usr/share/", None, 0o755),
        (f"{paylasim}/", None, 0o755),
        (
            f"{paylasim}/{PAKET_ADI}.conf.ornek",
            (UYGULAMA_KLASORU / f"{PAKET_ADI}.conf.ornek").read_bytes(),
            0o644,
        ),
        (
            f"{paylasim}/eski-kurulumu-tasi.sh",
            (UYGULAMA_KLASORU / "eski-kurulumu-tasi.sh").read_bytes(),
            0o755,
        ),
    ]
    if kurulum_conf is not None:
        # Kayıt anahtarını içerir: yalnızca root okur.
        veri.append((f"{paylasim}/kurulum.conf", kurulum_conf, 0o600))
    if ca:
        veri.append((f"{paylasim}/yerel-ca.crt", ca, 0o644))
    anahtarlik = depo_anahtari.acik_anahtarlik()
    if anahtarlik:
        veri += [
            ("./usr/share/keyrings/", None, 0o755),
            (f"./usr/share/keyrings/{PAKET_ADI}.gpg", anahtarlik, 0o644),
        ]

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
