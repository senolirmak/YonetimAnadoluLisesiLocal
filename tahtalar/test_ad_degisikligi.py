"""tahtalar — okul-ajan → akal-eta-yonetim ad değişikliği: eski kurulumun
taşınması (sahte kök dizinde; gerçek sisteme ve systemctl'e dokunulmaz),
eski ayar dosyasının okunması ve paketin eski paketin yerini alması."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from tahtalar.services import kurulum_paketi
from tahtalar.tests import _ajan_modulu

BETIK = kurulum_paketi.UYGULAMA_KLASORU / "eski-kurulumu-tasi.sh"
ESKI_AYAR = """[ajan]
sunucu = https://192.168.1.70
kayit_anahtari = eski-anahtar
ca_dosyasi = /etc/okul-ajan/yerel-ca.crt
aralik = 30
"""


@unittest.skipUnless(shutil.which("sh"), "sh yok")
class EskiKurulumuTasimaTestCase(SimpleTestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.kok = Path(self.klasor.name)

    def _yaz(self, yol, icerik):
        dosya = self.kok / yol
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_text(icerik)
        return dosya

    def _eski_kurulum(self):
        self._yaz("opt/okul-ajan/okul_ajan.py", "eski kod")
        self._yaz("etc/okul-ajan/ajan.conf", ESKI_AYAR)
        self._yaz("etc/okul-ajan/yerel-ca.crt", "CA")
        self._yaz("var/lib/okul-ajan/token", "tahta-tokeni")
        self._yaz("etc/systemd/system/okul-ajan.service", "[Unit]")

    def _calistir(self):
        sonuc = subprocess.run(["sh", str(BETIK), str(self.kok)], capture_output=True, text=True)
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)
        return sonuc.stdout

    def test_eski_kurulum_tasinir(self):
        self._eski_kurulum()
        cikti = self._calistir()
        self.assertIn("taşınıyor", cikti)

        ayar = (self.kok / "etc/akal-eta-yonetim/akal-eta-yonetim.conf").read_text()
        self.assertTrue(ayar.startswith("[akal-eta-yonetim]\n"))
        self.assertIn("kayit_anahtari = eski-anahtar", ayar)
        self.assertIn("aralik = 30", ayar)
        self.assertIn("ca_dosyasi = /etc/akal-eta-yonetim/yerel-ca.crt", ayar)
        self.assertEqual((self.kok / "etc/akal-eta-yonetim/yerel-ca.crt").read_text(), "CA")
        token = self.kok / "var/lib/akal-eta-yonetim/token"
        self.assertEqual(token.read_text(), "tahta-tokeni")
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.kok / "etc/akal-eta-yonetim/akal-eta-yonetim.conf").stat().st_mode & 0o777, 0o600)

        for eski in ("opt/okul-ajan", "etc/okul-ajan", "var/lib/okul-ajan",
                     "etc/systemd/system/okul-ajan.service"):
            self.assertFalse((self.kok / eski).exists(), eski)

    def test_eski_kurulum_yoksa_hicbir_sey_yapmaz(self):
        self._yaz("etc/akal-eta-yonetim/akal-eta-yonetim.conf", "[akal-eta-yonetim]\n")
        self.assertEqual(self._calistir(), "")
        self.assertEqual(
            sorted(str(p.relative_to(self.kok)) for p in self.kok.rglob("*") if p.is_file()),
            ["etc/akal-eta-yonetim/akal-eta-yonetim.conf"],
        )

    def test_yeni_ayar_ve_token_varsa_ezilmez(self):
        self._eski_kurulum()
        self._yaz("etc/akal-eta-yonetim/akal-eta-yonetim.conf", "[akal-eta-yonetim]\nyeni = 1\n")
        self._yaz("var/lib/akal-eta-yonetim/token", "yeni-token")
        self._calistir()
        self.assertIn("yeni = 1", (self.kok / "etc/akal-eta-yonetim/akal-eta-yonetim.conf").read_text())
        self.assertEqual((self.kok / "var/lib/akal-eta-yonetim/token").read_text(), "yeni-token")
        self.assertFalse((self.kok / "etc/okul-ajan").exists())

    def test_tekrar_calistirmak_guvenli(self):
        self._eski_kurulum()
        self._calistir()
        self.assertEqual(self._calistir(), "")
        self.assertEqual((self.kok / "var/lib/akal-eta-yonetim/token").read_text(), "tahta-tokeni")


class AyarDosyasiTestCase(SimpleTestCase):
    def setUp(self):
        self.uygulama = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.yol = Path(self.klasor.name) / "ayar.conf"

    def test_yeni_ve_eski_bolum_adi_okunur(self):
        for bolum in ("akal-eta-yonetim", "ajan"):
            with self.subTest(bolum=bolum):
                self.yol.write_text(f"[{bolum}]\nsunucu = https://okul.test/\nkayit_anahtari = a\n")
                ayarlar = self.uygulama.ayarlari_oku(str(self.yol))
                self.assertEqual(ayarlar["sunucu"], "https://okul.test")

    def test_bolum_yoksa_anlasilir_hata(self):
        self.yol.write_text("[baska]\nsunucu = x\n")
        with self.assertRaisesMessage(SystemExit, "[akal-eta-yonetim]"):
            self.uygulama.ayarlari_oku(str(self.yol))

    def test_varsayilan_yollar(self):
        self.assertEqual(self.uygulama.GUNCELLEME_BIRIMI, "akal-eta-yonetim-guncelleme")
        self.assertTrue(self.uygulama.AYAR_DOSYASI.endswith("/etc/akal-eta-yonetim/akal-eta-yonetim.conf"))


@override_settings(TAHTA_KAYIT_ANAHTARI="anahtar")
class PaketEskiPaketTestCase(SimpleTestCase):
    def test_eski_paketin_yerini_alir_ve_tasima_betigini_icerir(self):
        from tahtalar.test_paket import _ar_uyeleri, _tar

        uyeler = _ar_uyeleri(kurulum_paketi.paket_olustur("http://okul.test"))
        control = _tar(uyeler["control.tar.gz"]).extractfile("./control").read().decode()
        self.assertIn("Conflicts: okul-ajan\n", control)
        self.assertIn("Replaces: okul-ajan\n", control)
        postinst = _tar(uyeler["control.tar.gz"]).extractfile("./postinst").read().decode()
        self.assertIn('sh "$PAYLASIM/eski-kurulumu-tasi.sh"', postinst)
        betik = _tar(uyeler["data.tar.gz"]).getmember("./usr/share/akal-eta-yonetim/eski-kurulumu-tasi.sh")
        self.assertEqual(betik.mode, 0o755)
