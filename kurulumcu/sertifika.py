"""MEB (Millî Eğitim Bakanlığı) ağ geçidi/proxy kök sertifikasının sisteme kurulumu.

Okul ağları genelde MEB'in kendi HTTPS trafiğini denetleyen ("SSL inceleme")
bir ağ geçidi/proxy'sinden geçer; bu proxy dış sunuculara (ör.
qr-etap.eba.gov.tr — bkz. ebagiris app'i, EBA karekod ile giriş) giden TLS
bağlantılarında kendi kök sertifikasıyla imzalanmış bir sertifika sunar. Bu
kök sertifika sistemin güvenilir CA deposuna eklenmedikçe, o ağdaki bir
sunucudan yapılan sertifika doğrulaması (ör. `websockets.connect("wss://...")`)
"certificate verify failed" ile başarısız olur.
"""

from __future__ import annotations

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
