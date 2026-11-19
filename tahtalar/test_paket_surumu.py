"""tahtalar — akal-eta-yonetim paket içeriği değişince SURUM'un artırılması."""

import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import CommandError, call_command
from django.test import SimpleTestCase

from tahtalar.services import kurulum_paketi, paket_surumu


class SurumKorumasiTestCase(SimpleTestCase):
    """Depodaki gerçek dosyaları denetler: paket değişip SURUM artmadıysa
    tahtalar değişikliği almaz — bu test main'e merge'ü durdurur."""

    def test_surum_paket_icerigiyle_uyumlu(self):
        sorun = paket_surumu.denetle()
        self.assertIsNone(sorun, sorun)


class _KopyaMixin:
    """Uygulama klasörünün geçici kopyasında çalışır (gerçek dosyalara dokunmaz)."""

    def setUp(self):
        super().setUp()
        klasor = tempfile.TemporaryDirectory()
        self.addCleanup(klasor.cleanup)
        self.klasor = Path(klasor.name) / "uygulama"
        shutil.copytree(
            kurulum_paketi.UYGULAMA_KLASORU,
            self.klasor,
            ignore=shutil.ignore_patterns("__pycache__", "kurulum.conf"),
        )
        yama = mock.patch.object(kurulum_paketi, "UYGULAMA_KLASORU", self.klasor)
        yama.start()
        self.addCleanup(yama.stop)
        self.uygulama = self.klasor / kurulum_paketi.UYGULAMA_DOSYASI
        self._surum_yaz("1.4.2")
        paket_surumu.kaydet()

    def _surum_yaz(self, surum):
        metin = self.uygulama.read_text(encoding="utf-8")
        self.uygulama.write_text(
            paket_surumu._SURUM_SATIRI.sub(f'SURUM = "{surum}"', metin), encoding="utf-8"
        )

    def _kodu_degistir(self):
        with self.uygulama.open("a", encoding="utf-8") as f:
            f.write("\n# değişiklik\n")


class PaketSurumuTestCase(_KopyaMixin, SimpleTestCase):
    def test_sonraki_surum(self):
        self.assertEqual(paket_surumu.sonraki_surum("1.2.9"), "1.2.10")
        self.assertEqual(paket_surumu.sonraki_surum("1.2.9", "kucuk"), "1.3.0")
        self.assertEqual(paket_surumu.sonraki_surum("1.2.9", "buyuk"), "2.0.0")
        for gecersiz in ("1.2", "1.2.x", "", None):
            with self.assertRaises(paket_surumu.SurumHatasi):
                paket_surumu.sonraki_surum(gecersiz)

    def test_yalniz_surum_satiri_ozeti_degistirmez(self):
        ozet = paket_surumu.icerik_ozeti()
        self._surum_yaz("9.9.9")
        self.assertEqual(paket_surumu.icerik_ozeti(), ozet)

    def test_pakete_giren_her_parca_ozeti_degistirir(self):
        ozet = paket_surumu.icerik_ozeti()
        for dosya in (
            kurulum_paketi.UYGULAMA_DOSYASI,
            "akal-eta-yonetim.service",
            "akal-eta-yonetim.conf.ornek",
            "eski-kurulumu-tasi.sh",
        ):
            with self.subTest(dosya=dosya):
                yol = self.klasor / dosya
                eski = yol.read_bytes()
                yol.write_bytes(eski + b"\n#x\n")
                self.assertNotEqual(paket_surumu.icerik_ozeti(), ozet)
                yol.write_bytes(eski)
        with mock.patch.object(kurulum_paketi, "_POSTINST", kurulum_paketi._POSTINST + "#x\n"):
            self.assertNotEqual(paket_surumu.icerik_ozeti(), ozet)
        self.assertEqual(paket_surumu.icerik_ozeti(), ozet)

    def test_denetim_durumlari(self):
        self.assertIsNone(paket_surumu.denetle())

        self._kodu_degistir()
        sorun = paket_surumu.denetle()
        self.assertIn("SURUM hâlâ 1.4.2", sorun)
        self.assertIn("Önerilen: 1.4.3", sorun)
        self.assertIn("1.5.0", sorun)

        self._surum_yaz("1.4.3")
        self.assertIn("güncellenmemiş", paket_surumu.denetle())
        paket_surumu.kaydet()
        self.assertIsNone(paket_surumu.denetle())

        self._surum_yaz("1.4.4")  # içerik aynı, sürüm boşuna artmış
        self.assertIn("içeriği değişmemiş", paket_surumu.denetle())

    def test_artir(self):
        self.assertEqual(paket_surumu.artir(), ("1.4.2", None))
        self._kodu_degistir()
        self.assertEqual(paket_surumu.artir(), ("1.4.2", "1.4.3"))
        self.assertEqual(kurulum_paketi.uygulama_surumu(), "1.4.3")
        self.assertIsNone(paket_surumu.denetle())
        self._kodu_degistir()
        self.assertEqual(paket_surumu.artir("kucuk"), ("1.4.3", "1.5.0"))
        self._kodu_degistir()
        self.assertEqual(paket_surumu.artir("buyuk"), ("1.5.0", "2.0.0"))

    def test_elle_artirilmis_surum_korunur(self):
        self._kodu_degistir()
        self._surum_yaz("1.6.0")
        self.assertEqual(paket_surumu.artir(), ("1.4.2", "1.6.0"))
        self.assertIsNone(paket_surumu.denetle())

    def test_kayit_yoksa(self):
        (self.klasor / paket_surumu.OZET_DOSYA_ADI).unlink()
        self.assertIn("--kaydet", paket_surumu.denetle())
        with self.assertRaises(paket_surumu.SurumHatasi):
            paket_surumu.artir()


class SurumArtirKomutuTestCase(_KopyaMixin, SimpleTestCase):
    def _komut(self, *arguman):
        cikti = io.StringIO()
        call_command("tahta_surum_artir", *arguman, stdout=cikti)
        return cikti.getvalue()

    def test_komut(self):
        self.assertIn("uyumlu", self._komut("--denetle"))
        self.assertIn("değişmedi", self._komut())

        self._kodu_degistir()
        with self.assertRaisesMessage(CommandError, "Önerilen: 1.4.3"):
            self._komut("--denetle")
        self.assertIn("1.4.2 → 1.5.0", self._komut("--kucuk"))
        self.assertIn("uyumlu", self._komut("--denetle"))

    def test_secenekler_birlikte_kullanilamaz(self):
        with self.assertRaises(CommandError):
            self._komut("--kucuk", "--buyuk")
