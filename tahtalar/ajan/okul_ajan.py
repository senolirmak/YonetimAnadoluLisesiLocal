#!/usr/bin/python3
"""Okul tahta ajanı.

Etkileşimli tahtada systemd servisi olarak çalışır (bkz. okul-ajan.service).
Yalnızca Python'un standart kütüphanesini kullanır; tahtaya pip ile bir şey
kurulmaz.

Her ARALIK saniyede bir okul sunucusuna (akalyonetim) tahtanın durumunu
gönderir ve bekleyen komutları (kapat / yeniden başlat / güncelle) alır.

Güncelleme, ajanın kısıtlı servisinin dışında ayrı bir systemd birimi
(okul-ajan-guncelleme) olarak çalışır; ajan yalnızca başlatır ve sonucunu
izler. Güncelleme sürerken kapat / yeniden başlat komutları reddedilir.

MEB Ahenk ile ilişkisi: /etc/ahenk altına HİÇBİR ŞEY yazmaz. Ahenk servisinin
çalışıp çalışmadığını ve tahtanın MEB'e kayıtlı olup olmadığını yalnızca
okur. Servis dosyası da /etc/ahenk'i bu ajan için salt okunur yapar.

Ayar dosyası: /etc/okul-ajan/ajan.conf
"""

import configparser
import json
import logging
import os
import pwd
import socket
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SURUM = "1.0.0"

AYAR_DOSYASI = os.environ.get("OKUL_AJAN_AYAR", "/etc/okul-ajan/ajan.conf")
DURUM_KLASORU = os.environ.get("STATE_DIRECTORY", "/var/lib/okul-ajan")
AHENK_KLASORU = "/etc/ahenk"
AHENK_SERVISI = "ahenk.service"

GUNCELLEME_BIRIMI = "okul-ajan-guncelleme"

# Güncelleme betiği. $1: sonucun yazılacağı dosya. Yarıda kalmış bir kurulum
# önce tamamlanır; yapılandırma dosyalarının mevcut hâli korunur (confold) —
# /etc/ahenk dahil hiçbir ayar dosyası değiştirilmez. "upgrade" paket
# kaldırmaz; yalnızca kurulu paketleri günceller.
GUNCELLEME_BETIGI = r"""
set -u
export DEBIAN_FRONTEND=noninteractive
APT="apt-get -q -o DPkg::Lock::Timeout=900 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"
dpkg --configure -a && $APT update && $APT -y upgrade
kod=$?
if [ "$kod" -eq 0 ]; then d=basarili; else d=basarisiz; fi
echo "$d $(date +%s) $kod" > "$1.tmp" && mv "$1.tmp" "$1"
exit "$kod"
"""

KOMUTLAR = {
    "kapat": ["systemctl", "poweroff", "--no-block"],
    "yeniden_baslat": ["systemctl", "reboot", "--no-block"],
}

log = logging.getLogger("okul-ajan")


# ── Ayarlar ──────────────────────────────────────────────────────────────


def ayarlari_oku(yol=AYAR_DOSYASI):
    parser = configparser.ConfigParser()
    if not parser.read(yol, encoding="utf-8"):
        raise SystemExit(f"Ayar dosyası okunamadı: {yol}")
    bolum = parser["ajan"]
    sunucu = bolum.get("sunucu", "").strip().rstrip("/")
    if not sunucu:
        raise SystemExit("Ayar dosyasında 'sunucu' boş.")
    return {
        "sunucu": sunucu,
        "kayit_anahtari": bolum.get("kayit_anahtari", "").strip(),
        "ca_dosyasi": bolum.get("ca_dosyasi", "").strip(),
        "aralik": max(15, bolum.getint("aralik", fallback=60)),
    }


def _token_yolu():
    return os.path.join(DURUM_KLASORU, "token")


def token_oku():
    try:
        with open(_token_yolu(), encoding="utf-8") as f:
            return f.read().strip() or None
    except OSError:
        return None


def token_yaz(token):
    os.makedirs(DURUM_KLASORU, exist_ok=True)
    yol = _token_yolu()
    fd = os.open(yol, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)


def token_sil():
    try:
        os.remove(_token_yolu())
    except OSError:
        pass


# ── Tahtanın durumu ──────────────────────────────────────────────────────


def _dosya_oku(yol):
    try:
        with open(yol, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def makine_kimligi():
    return _dosya_oku("/etc/machine-id").strip()


def isletim_sistemi():
    for satir in _dosya_oku("/etc/os-release").splitlines():
        if satir.startswith("PRETTY_NAME="):
            return satir.split("=", 1)[1].strip().strip('"')
    return ""


def acik_kalma_suresi():
    try:
        return int(float(_dosya_oku("/proc/uptime").split()[0]))
    except (IndexError, ValueError):
        return None


def mac_adresleri(klasor="/sys/class/net"):
    """Fiziksel ağ arayüzlerinin MAC adresleri (sunucu MEB Lider envanteriyle eşleştirir)."""
    macler = []
    try:
        arayuzler = sorted(os.listdir(klasor))
    except OSError:
        return macler
    for arayuz in arayuzler:
        if arayuz == "lo":
            continue
        mac = _dosya_oku(os.path.join(klasor, arayuz, "address")).strip().lower()
        if mac and mac != "00:00:00:00:00:00" and mac not in macler:
            macler.append(mac)
    return macler


def ip_adresi(sunucu):
    """Sunucuya giden trafiğin çıktığı yerel IP. UDP 'connect' paket göndermez."""
    host = urllib.parse.urlsplit(sunucu).hostname or ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((host, 9))
            return s.getsockname()[0]
    except OSError:
        return ""


def ahenk_servis_durumu():
    """'calisiyor' | 'durmus' | 'yok' | 'bilinmiyor' — yalnızca okur."""
    try:
        cikti = subprocess.run(
            ["systemctl", "show", AHENK_SERVISI, "--property=LoadState,ActiveState"],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "bilinmiyor"
    ozellik = dict(s.split("=", 1) for s in cikti.splitlines() if "=" in s)
    if ozellik.get("LoadState") == "not-found":
        return "yok"
    durum = ozellik.get("ActiveState")
    if durum in ("active", "reloading"):
        return "calisiyor"
    if durum:
        return "durmus"
    return "bilinmiyor"


def _dogru_mu(deger):
    return str(deger).strip().lower() in ("1", "true", "evet", "yes")


def meb_kayit_durumu(klasor=AHENK_KLASORU):
    """True / False / None (bilinmiyor). Ahenk dosyalarını yalnızca okur.

    Önce Ahenk'in veritabanındaki 'registration' tablosuna, olmazsa
    ahenk.conf'taki [CONNECTION] uid değerine bakar.
    """
    db = os.path.join(klasor, "ahenk.db")
    if os.path.exists(db):
        try:
            # mode=ro: dosya salt okunur açılır, hiçbir şey yazılmaz.
            baglanti = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            try:
                satirlar = baglanti.execute("SELECT registered FROM registration").fetchall()
            finally:
                baglanti.close()
            return any(_dogru_mu(s[0]) for s in satirlar)
        except sqlite3.Error as hata:
            log.debug("ahenk.db okunamadı: %s", hata)

    conf = configparser.ConfigParser(interpolation=None)
    try:
        okundu = conf.read(os.path.join(klasor, "ahenk.conf"), encoding="utf-8")
    except configparser.Error:
        okundu = []
    if okundu and conf.has_section("CONNECTION"):
        return bool(conf.get("CONNECTION", "uid", fallback="").strip())
    return None


def _loginctl(*arguman):
    try:
        return subprocess.run(
            ["loginctl", *arguman], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _hesap_bilgisi(kullanici):
    """(gerçek ad, EBA özeti) — /etc/passwd GECOS alanından.

    ETAP'ın EBA karekod girişi (eta-qr-login) yerel hesabı GECOS'a
    "<Ad Soyad>,,,,<md5(eba_id)>" yazarak açar. EBA özeti, sunucunun öğretmeni
    EBA hesabı bağlı Personel kaydıyla eşleştirmesi içindir; yerel hesaplarda
    (örn. etapadmin) boş döner.
    """
    try:
        gecos = pwd.getpwnam(kullanici).pw_gecos
    except (KeyError, AttributeError):
        return "", ""
    ad = gecos.split(",")[0].strip()
    ozet = ""
    if ",,,," in gecos:
        son = gecos.rsplit(",", 1)[-1].strip().lower()
        if len(son) == 32 and all(c in "0123456789abcdef" for c in son):
            ozet = son
    return ad, ozet


def oturumlar():
    """Tahtada şu an açık kullanıcı oturumları. Geçmiş tutulmaz; her turda o
    anki liste gönderilir. Giriş ekranı (greeter) ve sistem oturumları hariç."""
    liste = []
    for satir in _loginctl("list-sessions", "--no-legend").splitlines()[:20]:
        parca = satir.split()
        if not parca:
            continue
        cikti = _loginctl(
            "show-session",
            parca[0],
            "-p",
            "Name",
            "-p",
            "Active",
            "-p",
            "Class",
            "-p",
            "Type",
            "-p",
            "State",
            "-p",
            "TimestampMonotonic",
        )
        ozellik = dict(s.split("=", 1) for s in cikti.splitlines() if "=" in s)
        kullanici = ozellik.get("Name", "")
        if not kullanici or ozellik.get("Class") != "user" or ozellik.get("State") == "closing":
            continue
        baslangic = None
        try:
            # systemd'nin monotonik saati Python'unkiyle aynıdır (CLOCK_MONOTONIC).
            gecen = time.monotonic() - int(ozellik.get("TimestampMonotonic", "")) / 1e6
            baslangic = int(time.time() - gecen)
        except ValueError:
            pass
        ad, eba_ozeti = _hesap_bilgisi(kullanici)
        liste.append(
            {
                "kullanici": kullanici,
                "ad": ad,
                "eba_ozeti": eba_ozeti,
                "aktif": ozellik.get("Active") == "yes",
                "tur": ozellik.get("Type", ""),
                "baslangic": baslangic,
            }
        )
    liste.sort(key=lambda o: not o["aktif"])
    return liste[:10]


def _guncelleme_dosyasi():
    return os.path.join(DURUM_KLASORU, "guncelleme")


def guncelleme_suruyor():
    try:
        sonuc = subprocess.run(
            ["systemctl", "is-active", GUNCELLEME_BIRIMI],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return sonuc.stdout.strip() in ("active", "activating")


def guncelleme_durumu():
    """{'durum': suruyor|basarili|basarisiz|yarida_kaldi, 'zaman': epoch} ya da None."""
    parcalar = _dosya_oku(_guncelleme_dosyasi()).split()
    if len(parcalar) < 2 or not parcalar[1].isdigit():
        return None
    durum, zaman = parcalar[0], int(parcalar[1])
    if durum == "suruyor" and not guncelleme_suruyor():
        # Birim bitmiş ama sonuç yazılmamış: tahta güncelleme sırasında kapanmış.
        durum = "yarida_kaldi"
    return {"durum": durum, "zaman": zaman}


def guncellemeyi_baslat():
    if guncelleme_suruyor():
        return "basarisiz", "Güncelleme zaten sürüyor."
    os.makedirs(DURUM_KLASORU, exist_ok=True)
    yol = _guncelleme_dosyasi()
    with open(yol, "w", encoding="utf-8") as f:
        f.write(f"suruyor {int(time.time())}\n")
    # systemd-run: ajanın sandbox'ı dışında, kendi birimi olarak çalışır;
    # ajan yeniden başlasa da güncelleme sürer. Günlük: journalctl -u okul-ajan-guncelleme
    arguman = [
        "systemd-run",
        f"--unit={GUNCELLEME_BIRIMI}",
        "--description=Okul tahta güncellemesi",
        "--collect",
        "--property=Nice=10",
        "/bin/sh",
        "-c",
        GUNCELLEME_BETIGI,
        "okul-guncelleme",
        yol,
    ]
    try:
        sonuc = subprocess.run(arguman, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as hata:
        os.remove(yol)
        return "basarisiz", str(hata)[:255]
    if sonuc.returncode != 0:
        os.remove(yol)
        return "basarisiz", (sonuc.stderr.strip() or f"çıkış kodu {sonuc.returncode}")[:255]
    return "tamamlandi", "Güncelleme başlatıldı."


def durum_bilgisi(ayarlar):
    return {
        "makine_kimligi": makine_kimligi(),
        "hostname": socket.gethostname(),
        "ip_adresi": ip_adresi(ayarlar["sunucu"]),
        "mac_adresleri": mac_adresleri(),
        "isletim_sistemi": isletim_sistemi(),
        "ajan_surumu": SURUM,
        "acik_kalma_suresi": acik_kalma_suresi(),
        "ahenk_servisi": ahenk_servis_durumu(),
        "meb_kayitli": meb_kayit_durumu(),
        "guncelleme": guncelleme_durumu(),
        "oturumlar": oturumlar(),
    }


# ── Sunucu ile konuşma ───────────────────────────────────────────────────


class SunucuHatasi(Exception):
    def __init__(self, kod, mesaj):
        super().__init__(f"HTTP {kod}: {mesaj}")
        self.kod = kod


def _ssl_baglami(ayarlar):
    if not ayarlar["sunucu"].startswith("https://"):
        return None
    if ayarlar["ca_dosyasi"]:
        return ssl.create_default_context(cafile=ayarlar["ca_dosyasi"])
    return ssl.create_default_context()


def istek(ayarlar, yol, veri, token=None):
    govde = json.dumps(veri).encode("utf-8")
    basliklar = {"Content-Type": "application/json", "User-Agent": f"okul-ajan/{SURUM}"}
    if token:
        basliklar["Authorization"] = f"Token {token}"
    req = urllib.request.Request(
        ayarlar["sunucu"] + yol, data=govde, headers=basliklar, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=20, context=_ssl_baglami(ayarlar)) as yanit:
            return json.loads(yanit.read().decode("utf-8"))
    except urllib.error.HTTPError as hata:
        try:
            mesaj = json.loads(hata.read().decode("utf-8")).get("hata", "")
        except (ValueError, AttributeError):
            mesaj = hata.reason
        raise SunucuHatasi(hata.code, mesaj) from None


def kaydol(ayarlar):
    if not ayarlar["kayit_anahtari"]:
        raise SystemExit("Ayar dosyasında 'kayit_anahtari' boş; tahta kaydolamaz.")
    veri = durum_bilgisi(ayarlar)
    veri["kayit_anahtari"] = ayarlar["kayit_anahtari"]
    yanit = istek(ayarlar, "/tahtalar/api/kayit/", veri)
    token_yaz(yanit["token"])
    log.info("Sunucuya kaydolundu: %s", yanit.get("tahta"))
    return yanit["token"]


def komutu_uygula(komut):
    """Döner: (durum, mesaj). Kapatma/yeniden başlatma --no-block ile kuyruğa
    alınır; böylece sonucu sunucuya bildirmeye vakit kalır."""
    if komut == "guncelle":
        return guncellemeyi_baslat()
    arguman = KOMUTLAR.get(komut)
    if arguman is None:
        return "basarisiz", f"Bilinmeyen komut: {komut}"
    if guncelleme_suruyor():
        # Güncelleme ortasında kapanan tahtanın paketleri bozulabilir.
        return "basarisiz", "Güncelleme sürüyor; bitince tekrar deneyin."
    try:
        sonuc = subprocess.run(arguman, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as hata:
        return "basarisiz", str(hata)[:255]
    if sonuc.returncode != 0:
        return "basarisiz", (sonuc.stderr.strip() or f"çıkış kodu {sonuc.returncode}")[:255]
    return "tamamlandi", ""


def tur(ayarlar, token, sonuclar):
    """Bir tur: durumu gönder, gelen komutları uygula. Döner: bildirilemeyen sonuçlar."""
    veri = durum_bilgisi(ayarlar)
    veri["sonuclar"] = sonuclar
    yanit = istek(ayarlar, "/tahtalar/api/durum/", veri, token)
    bekleyen = []
    for komut in yanit.get("komutlar", []):
        log.info("Komut alındı: %s (#%s)", komut.get("komut"), komut.get("id"))
        durum, mesaj = komutu_uygula(komut.get("komut"))
        sonuc = {"id": komut.get("id"), "durum": durum, "mesaj": mesaj}
        # Kapanmadan önce sonucu hemen bildir; olmazsa bir sonraki turda gider.
        try:
            veri["sonuclar"] = [sonuc]
            istek(ayarlar, "/tahtalar/api/durum/", veri, token)
        except (OSError, SunucuHatasi, ValueError):
            bekleyen.append(sonuc)
    return bekleyen


def calis():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
    ayarlar = ayarlari_oku()
    log.info("okul-ajan %s başladı, sunucu: %s", SURUM, ayarlar["sunucu"])
    token = token_oku()
    sonuclar = []
    while True:
        try:
            if token is None:
                token = kaydol(ayarlar)
            sonuclar = tur(ayarlar, token, sonuclar)
        except SunucuHatasi as hata:
            log.warning("%s", hata)
            if hata.kod == 401:
                # Token geçersiz (tahta silinmiş olabilir): yeniden kaydol.
                token_sil()
                token = None
        except (OSError, ValueError, KeyError) as hata:
            log.warning("Sunucuya ulaşılamadı: %s", hata)
        time.sleep(ayarlar["aralik"])


if __name__ == "__main__":
    calis()
