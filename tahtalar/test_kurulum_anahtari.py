"""kurulumcu.env_dosyasi.eksikse_ekle — TAHTA_KAYIT_ANAHTARI'nın kurulumda üretilmesi.

kurulumcu bir Django app'i olmadığından testi burada (anahtarı kullanan app'te).
Yalnızca geçici dosyayla çalışır; sudo kullanılmaz.
"""

import tempfile
from pathlib import Path
from unittest import TestCase

from kurulumcu import env_dosyasi


class EksikseEkleTestCase(TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.env = Path(self.klasor.name) / ".env"
        self.env.write_text("SECRET_KEY=x\nDEBUG=False\n")

    def tearDown(self):
        self.klasor.cleanup()

    def _anahtar(self):
        return env_dosyasi.oku(self.env).get("TAHTA_KAYIT_ANAHTARI")

    def test_yoksa_ekler_diger_satirlari_korur(self):
        self.assertTrue(env_dosyasi.eksikse_ekle(self.env, "TAHTA_KAYIT_ANAHTARI", lambda: "a1"))
        self.assertEqual(
            self.env.read_text(), "SECRET_KEY=x\nDEBUG=False\nTAHTA_KAYIT_ANAHTARI=a1\n"
        )
        self.assertEqual(self.env.stat().st_mode & 0o777, 0o600)

    def test_tekrar_calistirmada_degismez(self):
        env_dosyasi.eksikse_ekle(self.env, "TAHTA_KAYIT_ANAHTARI", lambda: "ilk")
        self.assertFalse(env_dosyasi.eksikse_ekle(self.env, "TAHTA_KAYIT_ANAHTARI", lambda: "yeni"))
        self.assertEqual(self._anahtar(), "ilk")
        self.assertEqual(self.env.read_text().count("TAHTA_KAYIT_ANAHTARI"), 1)

    def test_bos_deger_doldurulur_yorum_satiri_sayilmaz(self):
        self.env.write_text("# TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>\nTAHTA_KAYIT_ANAHTARI=\n")
        self.assertTrue(env_dosyasi.eksikse_ekle(self.env, "TAHTA_KAYIT_ANAHTARI", lambda: "b2"))
        self.assertEqual(self._anahtar(), "b2")
        self.assertIn("# TAHTA_KAYIT_ANAHTARI=<KAYIT_ANAHTARI>", self.env.read_text())

    def test_env_yoksa_bir_sey_yapmaz(self):
        self.env.unlink()
        self.assertFalse(env_dosyasi.eksikse_ekle(self.env, "TAHTA_KAYIT_ANAHTARI", lambda: "c"))
        self.assertFalse(self.env.exists())
