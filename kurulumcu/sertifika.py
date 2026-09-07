"""Sertifika kurulumu: (1) MEB ağ geçidi kök sertifikasının sisteme GÜVENİLEN
CA olarak eklenmesi, (2) sunucunun kendi HTTPS'i için yerel bir sertifika
otoritesi (CA) ve onunla imzalı bir sunucu sertifikası üretimi.

── (1) MEB kök sertifikası ─────────────────────────────────────────────
Okul ağları genelde MEB'in kendi HTTPS trafiğini denetleyen ("SSL inceleme")
bir ağ geçidi/proxy'sinden geçer; bu proxy dış sunuculara (ör.
qr-etap.eba.gov.tr — bkz. ebagiris app'i, EBA karekod ile giriş) giden TLS
bağlantılarında kendi kök sertifikasıyla imzalanmış bir sertifika sunar. Bu
kök sertifika sistemin güvenilir CA deposuna eklenmedikçe, o ağdaki bir
sunucudan yapılan sertifika doğrulaması (ör. `websockets.connect("wss://...")`)
"certificate verify failed" ile başarısız olur.

── (2) Sunucunun kendi HTTPS'i (yerel CA) ──────────────────────────────
Sunucu okul ağı içinde, dışarıya kapalı çalışıyor ve genel bir alan adı
(public domain) yok — bu yüzden Let's Encrypt gibi genel sertifika
otoriteleri (HTTP-01 de DNS-01 de) kullanılamaz: ikisi de doğrulama için
ya sunucunun dışarıdan erişilebilir olmasını ya da genel DNS üzerinde kontrol
sahibi olunan bir alan adını gerektirir. Tek gerçekçi yol, kendi (kendinden
imzalı) sertifika otoritemizi (`yerel_ca_olustur`) bir kez oluşturup onunla
sunucu için bir sertifika imzalamak (`sunucu_sertifikasi_olustur`). Bu CA'nın
ÖZEL ANAHTARI asla dağıtılmaz; yalnızca genel sertifikası
(`ca_sertifikasini_disari_kopyala`) okuldaki istemci bilgisayarların
"Güvenilen Kök Sertifika Yetkilileri" deposuna elle/GPO ile eklenir — bu
yapılmadan tarayıcılar siteyi "güvenli değil" olarak işaretlemeye devam eder
(yine de "Devam et" ile girilebilir, sert bir engel değildir).
"""

from __future__ import annotations

import ipaddress
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import yardimci as y

MEB_SERTIFIKA_URL = "https://sertifika.meb.gov.tr/MEB_SERTIFIKASI.cer"
HEDEF_DOSYA = Path("/usr/local/share/ca-certificates/meb-sertifikasi.crt")


def _der_mi(veri: bytes) -> bool:
    """DER (binary) mi PEM (metin, '-----BEGIN CERTIFICATE-----') mi olduğunu
    ayırt eder — `.cer` uzantısı ikisi için de kullanılabildiğinden, indirilen
    içeriğin baytlarına bakılır (MEB'in kendi sitesinde "binary sistemde"
    olarak belirtilmesi DER olduğuna işaret eder, ama ileride PEM'e
    dönüştürülse bile bu fonksiyon doğru davranmaya devam eder)."""
    return not veri.lstrip().startswith(b"-----BEGIN")


def meb_sertifikasini_kur(force: bool = False) -> bool:
    """MEB kök sertifikasını indirir, DER ise PEM'e çevirir ve `update-ca-
    certificates` ile sistemin güvenilir CA deposuna ekler.

    `force=False` (varsayılan) iken hedef dosya zaten varsa hiçbir şey
    yapmadan atlar — tekrar çalıştırmak güvenlidir. İndirme/dönüştürme
    başarısız olursa kurulumu DURDURMAZ, yalnızca uyarıp elle kurulum
    komutlarını gösterir: bu adım MEB ağı dışında (ör. bu sihirbazın
    geliştirme/test edildiği ortamda) başarısız olabilir ama kalan kurulumu
    engellememelidir — EBA karekod özelliği zaten isteğe bağlıdır."""
    if not force and HEDEF_DOSYA.is_file():
        y.uyari(f"MEB kök sertifikası zaten kurulu ({HEDEF_DOSYA}), atlanıyor.")
        return True

    if not y.komut_var_mi("openssl"):
        y.uyari("'openssl' bulunamadı, MEB sertifikası kurulumu atlanıyor.")
        return False

    y.bilgi(f"MEB kök sertifikası indiriliyor: {MEB_SERTIFIKA_URL}")
    try:
        with urllib.request.urlopen(MEB_SERTIFIKA_URL, timeout=15) as yanit:
            ham = yanit.read()
    except Exception as e:  # noqa: BLE001
        y.uyari(
            f"MEB sertifikası indirilemedi ({e}); atlanıyor. MEB proxy'si TLS "
            "denetimi yapan bir okul ağındaysanız EBA karekod özelliği bu "
            f"olmadan çalışmayabilir. Elle kurmak için:\n"
            f"    curl -o meb.cer {MEB_SERTIFIKA_URL}\n"
            f"    openssl x509 -inform DER -in meb.cer -out /tmp/meb.crt\n"
            f"    sudo cp /tmp/meb.crt {HEDEF_DOSYA}\n"
            "    sudo update-ca-certificates"
        )
        return False

    if not ham:
        y.uyari("MEB sertifikası boş döndü, atlanıyor.")
        return False

    with tempfile.TemporaryDirectory() as tmp_ad:
        tmp = Path(tmp_ad)
        if _der_mi(ham):
            ham_dosya = tmp / "meb_sertifikasi.cer"
            ham_dosya.write_bytes(ham)
            pem_dosya = tmp / "meb_sertifikasi.pem"
            sonuc = subprocess.run(
                ["openssl", "x509", "-inform", "DER", "-in", str(ham_dosya), "-out", str(pem_dosya)],
                capture_output=True,
                text=True,
            )
            if sonuc.returncode != 0:
                y.uyari(f"Sertifika DER'den PEM'e çevrilemedi: {sonuc.stderr.strip()}")
                return False
            pem_icerik = pem_dosya.read_text()
        else:
            pem_icerik = ham.decode("utf-8", errors="replace")

    y.calistir(["tee", str(HEDEF_DOSYA)], sudo=True, sessiz=True, girdi=pem_icerik)
    y.calistir(["update-ca-certificates"], sudo=True, sessiz=True)
    y.basari(f"MEB kök sertifikası kuruldu: {HEDEF_DOSYA}")
    return True


# ── Yerel CA + sunucu sertifikası (sunucunun kendi HTTPS'i) ───────────────

CA_DIZIN = Path("/etc/ssl/akalyonetim-ca")
CA_ANAHTAR = CA_DIZIN / "ca.key"
CA_SERTIFIKA = CA_DIZIN / "ca.crt"
CA_GECERLILIK_GUN = 3650  # 10 yıl — yalnızca kendi altyapımızda güvenilen bir kök, rotasyonu biz yönetiyoruz

SUNUCU_SSL_DIZIN = Path("/etc/nginx/ssl")
SUNUCU_ANAHTAR = SUNUCU_SSL_DIZIN / "akalyonetim.key"
SUNUCU_SERTIFIKA = SUNUCU_SSL_DIZIN / "akalyonetim.crt"
SUNUCU_GECERLILIK_GUN = 825  # tarayıcıların genel CA'lar için kabul ettiği üst sınıra yakın, makul bir varsayılan

CA_DAGITIM_DOSYA_ADI = "yerel-ca-sertifikasi.crt"


def _ip_mi(deger: str) -> bool:
    try:
        ipaddress.ip_address(deger)
        return True
    except ValueError:
        return False


def yerel_ca_olustur(force: bool = False) -> bool:
    """Kendinden imzalı, yalnızca bu kurulum için kullanılacak bir kök
    sertifika otoritesi (CA) anahtarı/sertifikası üretir.

    `force=False` (varsayılan) iken CA zaten varsa atlar — CA'yı yeniden
    üretmek, ondan daha önce imzalanmış TÜM sunucu sertifikalarını (ve
    istemcilere dağıtılmış eski CA sertifikasını) geçersiz kılar; bu yüzden
    `force=True` yalnızca bilinçli bir CA yenileme/dönüşü olarak kullanılmalı."""
    if not force and CA_SERTIFIKA.is_file():
        y.uyari(f"Yerel CA zaten var ({CA_SERTIFIKA}), atlanıyor.")
        return True

    if not y.komut_var_mi("openssl"):
        y.hata("'openssl' bulunamadı, yerel CA oluşturulamıyor.")

    y.bilgi("Yerel sertifika otoritesi (CA) oluşturuluyor...")
    y.calistir(["mkdir", "-p", str(CA_DIZIN)], sudo=True)
    y.calistir(["chmod", "700", str(CA_DIZIN)], sudo=True)

    y.calistir(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:4096", "-sha256", "-nodes",
            "-days", str(CA_GECERLILIK_GUN),
            "-keyout", str(CA_ANAHTAR),
            "-out", str(CA_SERTIFIKA),
            "-subj", "/CN=Okul Yonetim Sistemi Yerel CA",
        ],
        sudo=True,
        sessiz=True,
    )
    y.calistir(["chmod", "600", str(CA_ANAHTAR)], sudo=True)
    y.calistir(["chmod", "644", str(CA_SERTIFIKA)], sudo=True)
    y.basari(f"Yerel CA oluşturuldu: {CA_SERTIFIKA} ({CA_GECERLILIK_GUN // 365} yıl geçerli).")
    return True


def sunucu_sertifikasi_olustur(sanlar: list[str], force: bool = False) -> bool:
    """`sanlar` (hostname ve/veya IP karışık liste — ör. ALLOWED_HOSTS) için
    yerel CA ile imzalı bir sunucu sertifikası üretir. `yerel_ca_olustur()`
    daha önce çalıştırılmış olmalı.

    `force=False` (varsayılan) iken sertifika zaten varsa atlar."""
    if not force and SUNUCU_SERTIFIKA.is_file():
        y.uyari(f"Sunucu sertifikası zaten var ({SUNUCU_SERTIFIKA}), atlanıyor.")
        return True

    if not (y.basarili_mi(["test", "-f", str(CA_ANAHTAR)], sudo=True)
            and y.basarili_mi(["test", "-f", str(CA_SERTIFIKA)], sudo=True)):
        y.hata(f"Yerel CA bulunamadı ({CA_DIZIN}) — önce yerel_ca_olustur() çalıştırılmalı.")

    if not sanlar:
        y.hata("Sunucu sertifikası için en az bir hostname/IP (SAN) gerekli.")

    y.bilgi(f"Sunucu sertifikası oluşturuluyor (SAN: {', '.join(sanlar)})...")
    y.calistir(["mkdir", "-p", str(SUNUCU_SSL_DIZIN)], sudo=True)

    san_uzantisi = "subjectAltName=" + ",".join(
        f"IP:{s}" if _ip_mi(s) else f"DNS:{s}" for s in sanlar
    )

    with tempfile.TemporaryDirectory() as tmp_ad:
        tmp = Path(tmp_ad)
        csr_dosya = tmp / "sunucu.csr"
        ext_dosya = tmp / "sunucu_ext.cnf"
        ext_dosya.write_text(san_uzantisi + "\n")

        # Anahtar doğrudan hedef (root sahipli) dizine yazılır; CSR geçici bir
        # dosyaya — openssl `sudo` altında (root olarak) çalıştığından, kendi
        # kullanıcımızın sahip olduğu tmp dizinine de sorunsuz yazabilir.
        y.calistir(
            [
                "openssl", "req", "-newkey", "rsa:2048", "-nodes",
                "-keyout", str(SUNUCU_ANAHTAR),
                "-out", str(csr_dosya),
                "-subj", f"/CN={sanlar[0]}",
                "-addext", san_uzantisi,
            ],
            sudo=True,
            sessiz=True,
        )
        y.calistir(
            [
                "openssl", "x509", "-req",
                "-in", str(csr_dosya),
                "-CA", str(CA_SERTIFIKA),
                "-CAkey", str(CA_ANAHTAR),
                "-CAcreateserial",
                "-out", str(SUNUCU_SERTIFIKA),
                "-days", str(SUNUCU_GECERLILIK_GUN),
                "-sha256",
                "-extfile", str(ext_dosya),
            ],
            sudo=True,
            sessiz=True,
        )

    y.calistir(["chmod", "600", str(SUNUCU_ANAHTAR)], sudo=True)
    y.calistir(["chmod", "644", str(SUNUCU_SERTIFIKA)], sudo=True)
    y.basari(f"Sunucu sertifikası oluşturuldu: {SUNUCU_SERTIFIKA}")
    return True


def ca_sertifikasini_disari_kopyala(proje_dizin: Path) -> Path:
    """Yerel CA'nın GENEL sertifikasını (özel anahtarı DEĞİL), okuldaki
    istemci bilgisayarlara dağıtılmak üzere proje dizinine, kurulumu
    çalıştıran kullanıcının da okuyabileceği bir kopya olarak çıkarır."""
    hedef = proje_dizin / CA_DAGITIM_DOSYA_ADI
    y.calistir(["cp", str(CA_SERTIFIKA), str(hedef)], sudo=True)
    y.calistir(["chmod", "644", str(hedef)], sudo=True)
    y.basari(f"Yerel CA sertifikası dağıtım için kopyalandı: {hedef}")
    return hedef
