"""kurulumcu.servis_kullanicisi.tahta_deposunu_hazirla — tahta APT deposu
klasörünün servis kullanıcısına ait hazırlanması ve anahtarın üretilmesi.

kurulumcu bir Django app'i olmadığından testi burada (deponun app'inde). sudo
komutları çalıştırılmaz, kaydedilir; "test -e" gerçek dosya sistemine sorulur.
"""

import tempfile
from pathlib import Path
from unittest import TestCase, mock

from kurulumcu import servis_kullanicisi

AYAR = ["--settings=config.settings.production"]


class TahtaDeposunuHazirlaTestCase(TestCase):
    def setUp(self):
        klasor = tempfile.TemporaryDirectory()
        self.addCleanup(klasor.cleanup)
        self.proje = Path(klasor.name)
        self.venv = self.proje / "venv"
        self.depo = self.proje / "tahta-deposu"
        self.komutlar = []
        self.uyarilar = []

        def calistir(komut, *, sudo=False, **kw):
            self.assertTrue(sudo, komut)
            self.komutlar.append(komut)

        def basarili_mi(komut, *, sudo=False, **kw):
            self.assertEqual(komut[:2], ["test", "-e"])
            return Path(komut[2]).exists()

        y = servis_kullanicisi.y
        for ad, yeni in (
            ("calistir", calistir),
            ("basarili_mi", basarili_mi),
            ("basari", lambda m: None),
            ("uyari", self.uyarilar.append),
        ):
            yama = mock.patch.object(y, ad, side_effect=yeni)
            yama.start()
            self.addCleanup(yama.stop)

    def _calistir(self):
        servis_kullanicisi.tahta_deposunu_hazirla(self.proje, self.venv, AYAR)

    def _ilk(self, ad):
        return next(k for k in self.komutlar if k[0] == ad)

    def test_ilk_kurulum(self):
        self._calistir()
        self.assertEqual(
            self.komutlar[0],
            ["install", "-d", "-o", "akalsite", "-g", "akalsite", "-m", "700", str(self.depo)],
        )
        self.assertEqual(
            self.komutlar[1],
            ["install", "-d", "-o", "akalsite", "-g", "akalsite", "-m", "755", str(self.depo / "paketler")],
        )
        self.assertIn(["chown", "-R", "akalsite:akalsite", str(self.depo)], self.komutlar)
        self.assertIn(["chmod", "700", str(self.depo)], self.komutlar)
        # Anahtar servis kullanıcısıyla, proje dizininde, production ayarıyla üretilir; en son.
        self.assertEqual(
            self.komutlar[-1],
            [
                "-u", "akalsite", "env", "-C", str(self.proje),
                str(self.venv / "bin" / "python"), "manage.py", "tahta_apt_anahtari_olustur",
                *AYAR,
            ],
        )
        self.assertFalse(any(k[0] in ("mv", "rm", "cp") for k in self.komutlar))

    def test_ilk_surumden_kalan_dosyalar_tasinir(self):
        (self.proje / "tahta-apt-imza-anahtari.json").write_text("{}")
        eski = self.proje / "tahta-paketleri"
        eski.mkdir()
        (eski / "akal-eta-yonetim_1.2.0_all.deb").write_bytes(b"x")
        (eski / "baska-dosya").write_bytes(b"x")
        self._calistir()
        self.assertIn(
            ["mv", str(self.proje / "tahta-apt-imza-anahtari.json"), str(self.depo / "imza-anahtari.json")],
            self.komutlar,
        )
        self.assertIn(
            [
                "cp", "-n", str(eski / "akal-eta-yonetim_1.2.0_all.deb"),
                str(self.depo / "paketler" / "akal-eta-yonetim_1.2.0_all.deb"),
            ],
            self.komutlar,
        )
        self.assertFalse(any("baska-dosya" in " ".join(k) for k in self.komutlar))
        self.assertIn(["rm", "-rf", str(eski)], self.komutlar)
        # Taşıma sahiplik düzeltmesinden önce yapılır.
        self.assertLess(self.komutlar.index(self._ilk("mv")), self.komutlar.index(self._ilk("chown")))

    def test_iki_konumda_da_anahtar_varsa_yenisi_korunur_uyarilir(self):
        (self.proje / "tahta-apt-imza-anahtari.json").write_text("{}")
        self.depo.mkdir()
        (self.depo / "imza-anahtari.json").write_text("{}")
        self._calistir()
        self.assertFalse(any(k[0] == "mv" for k in self.komutlar))
        self.assertEqual(len(self.uyarilar), 1)
        self.assertIn(["chmod", "600", str(self.depo / "imza-anahtari.json")], self.komutlar)

    def test_tekrar_calistirma_anahtari_ezmez(self):
        self.depo.mkdir()
        (self.depo / "imza-anahtari.json").write_text("{}")
        self._calistir()
        komut = self.komutlar[-1]
        self.assertIn("tahta_apt_anahtari_olustur", komut)
        self.assertNotIn("--zorla", komut)
