"""yedekleme — medya yedeğinin tahta APT deposu dosyalarını (imza anahtarı ve
paket arşivi) taşıması ve geri yüklemede onları media/'ye değil asıl yerlerine
yazması."""

import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from okul.testing import kullanici_olustur
from tahtalar.services import apt_deposu, depo_anahtari
from yedekleme.services import yedek_servisi

ANAHTAR = json.dumps({"tohum": "11" * 32, "olusturma": 1767225600}).encode()
BASKA_ANAHTAR = json.dumps({"tohum": "22" * 32, "olusturma": 1767225600}).encode()


class TahtaDosyalariYedekTestCase(TestCase):
    def setUp(self):
        klasor = tempfile.TemporaryDirectory()
        self.addCleanup(klasor.cleanup)
        self.kok = Path(klasor.name)
        self.medya = self.kok / "media"
        self.medya.mkdir()
        self.anahtar = self.kok / "tahta-deposu" / "imza-anahtari.json"
        self.paketler = self.kok / "tahta-deposu" / "paketler"
        for modul, ad, deger in (
            (yedek_servisi, "BACKUP_DIR", self.kok / "backups"),
            (yedek_servisi, "MEDIA_DIR", self.medya),
            (depo_anahtari, "ANAHTAR_DOSYASI", self.anahtar),
            (apt_deposu, "ARSIV_KLASORU", self.paketler),
            (depo_anahtari, "ESKI_ANAHTAR_DOSYASI", self.kok / "tahta-apt-imza-anahtari.json"),
            (apt_deposu, "ESKI_ARSIV_KLASORU", self.kok / "tahta-paketleri"),
        ):
            yama = mock.patch.object(modul, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)

        (self.medya / "ogrenci").mkdir()
        (self.medya / "ogrenci" / "a.pdf").write_bytes(b"pdf")
        self.paketler.mkdir(parents=True)
        self.anahtar.write_bytes(ANAHTAR)
        self.anahtar.chmod(0o600)
        for surum in ("1.2.0", "1.2.1"):
            (self.paketler / f"akal-eta-yonetim_{surum}_all.deb").write_bytes(surum.encode())
        (self.paketler / ".gecici.tmp").write_bytes(b"x")

    def _yedek(self):
        return yedek_servisi.medya_yedek_olustur(etiket="test")

    def _adlar(self, yol):
        with tarfile.open(yol, "r:gz") as tf:
            return sorted(tf.getnames())

    def test_yedek_tahta_dosyalarini_icerir(self):
        adlar = self._adlar(self._yedek())
        self.assertIn("ogrenci/a.pdf", adlar)
        self.assertIn("_akalyonetim_sistem/tahta-apt-imza-anahtari.json", adlar)
        self.assertIn("_akalyonetim_sistem/tahta-paketleri/akal-eta-yonetim_1.2.0_all.deb", adlar)
        self.assertIn("_akalyonetim_sistem/tahta-paketleri/akal-eta-yonetim_1.2.1_all.deb", adlar)
        self.assertFalse(any(".gecici.tmp" in ad for ad in adlar))

    def test_eski_konumdaki_dosyalar_yedeklenir_yeni_konuma_geri_yuklenir(self):
        self.anahtar.unlink()
        eski_anahtar = self.kok / "tahta-apt-imza-anahtari.json"
        eski_anahtar.write_bytes(ANAHTAR)
        eski_arsiv = self.kok / "tahta-paketleri"
        eski_arsiv.mkdir()
        (eski_arsiv / "akal-eta-yonetim_1.1.0_all.deb").write_bytes(b"1.1.0")
        yedek = self._yedek()
        self.assertIn(
            "_akalyonetim_sistem/tahta-paketleri/akal-eta-yonetim_1.1.0_all.deb", self._adlar(yedek)
        )
        eski_anahtar.unlink()
        yedek_servisi.medya_yedek_geri_yukle(yedek.name)
        self.assertEqual(self.anahtar.read_bytes(), ANAHTAR)
        self.assertEqual((self.paketler / "akal-eta-yonetim_1.1.0_all.deb").read_bytes(), b"1.1.0")

    def test_arsiv_bilgisi_tahta_dosyalarini_ayri_sayar(self):
        bilgi = yedek_servisi.medya_arsiv_bilgisi(self._yedek())
        self.assertEqual(bilgi.dosya_sayisi, 1)
        self.assertTrue(bilgi.tahta_anahtari)
        self.assertEqual(bilgi.tahta_paket_sayisi, 2)

    def test_geri_yukleme_anahtari_media_ya_acmaz_asil_yerine_yazar(self):
        yedek = self._yedek()
        self.anahtar.unlink()
        (self.paketler / "akal-eta-yonetim_1.2.0_all.deb").unlink()
        (self.paketler / "akal-eta-yonetim_1.2.1_all.deb").write_bytes(b"mevcut")
        (self.medya / "ogrenci" / "a.pdf").unlink()

        notlar = yedek_servisi.medya_yedek_geri_yukle(yedek.name)

        self.assertEqual((self.medya / "ogrenci" / "a.pdf").read_bytes(), b"pdf")
        self.assertFalse((self.medya / "_akalyonetim_sistem").exists())
        self.assertEqual([p.name for p in self.medya.rglob("*") if "anahtar" in p.name], [])
        self.assertEqual(self.anahtar.read_bytes(), ANAHTAR)
        self.assertEqual(self.anahtar.stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.paketler / "akal-eta-yonetim_1.2.0_all.deb").read_bytes(), b"1.2.0")
        # Mevcut paket değiştirilmez.
        self.assertEqual((self.paketler / "akal-eta-yonetim_1.2.1_all.deb").read_bytes(), b"mevcut")
        self.assertIn("Tahta depo anahtarı geri yüklendi.", notlar)
        self.assertIn("1 tahta paketi arşive geri yüklendi.", notlar)

    def test_ayni_anahtar_sessizce_kalir(self):
        notlar = yedek_servisi.medya_yedek_geri_yukle(self._yedek().name)
        self.assertEqual(notlar, [])
        self.assertFalse(self.anahtar.with_name(self.anahtar.name + ".onceki").exists())

    def test_farkli_anahtar_onceki_olarak_saklanir(self):
        yedek = self._yedek()
        self.anahtar.write_bytes(BASKA_ANAHTAR)
        notlar = yedek_servisi.medya_yedek_geri_yukle(yedek.name)
        self.assertEqual(self.anahtar.read_bytes(), ANAHTAR)
        onceki = self.anahtar.with_name(self.anahtar.name + ".onceki")
        self.assertEqual(onceki.read_bytes(), BASKA_ANAHTAR)
        self.assertEqual(onceki.stat().st_mode & 0o777, 0o600)
        self.assertTrue(any(".onceki" in n for n in notlar))

    def test_bozuk_anahtar_yazilmaz(self):
        self.anahtar.write_bytes(b"{bozuk")
        yedek = self._yedek()
        self.anahtar.write_bytes(ANAHTAR)
        notlar = yedek_servisi.medya_yedek_geri_yukle(yedek.name)
        self.assertEqual(self.anahtar.read_bytes(), ANAHTAR)
        self.assertTrue(any("bozuk" in n for n in notlar))

    def test_tahta_dosyasi_olmayan_eski_yedek_anahtara_dokunmaz(self):
        self.anahtar.unlink()
        for deb in self.paketler.iterdir():
            deb.unlink()
        yedek = self._yedek()
        self.assertEqual(self._adlar(yedek), ["ogrenci", "ogrenci/a.pdf"])
        self.anahtar.write_bytes(BASKA_ANAHTAR)
        self.assertEqual(yedek_servisi.medya_yedek_geri_yukle(yedek.name), [])
        self.assertEqual(self.anahtar.read_bytes(), BASKA_ANAHTAR)

    def test_disaridan_gelen_arsivde_tehlikeli_paket_adi_yok_sayilir(self):
        yedek = self.kok / "backups" / "media_disaridan_1.tar.gz"
        yedek.parent.mkdir(exist_ok=True)
        with tarfile.open(yedek, "w:gz") as tf:
            for ad in (
                "_akalyonetim_sistem/tahta-paketleri/../../kotu.deb",
                "_akalyonetim_sistem/tahta-paketleri/baska.deb",
                "_akalyonetim_sistem/baska-dosya",
            ):
                bilgi = tarfile.TarInfo(ad)
                bilgi.size = 1
                tf.addfile(bilgi, io.BytesIO(b"x"))
        yedek_servisi.medya_yedek_geri_yukle(yedek.name)
        self.assertFalse((self.kok / "kotu.deb").exists())
        self.assertFalse((self.paketler / "baska.deb").exists())
        self.assertFalse((self.medya / "_akalyonetim_sistem").exists())

    @unittest.skipIf(os.geteuid() == 0, "root her dosyayı okur")
    def test_okunamayan_anahtar_medya_yedegini_bozmaz(self):
        self.anahtar.chmod(0o000)
        self.addCleanup(self.anahtar.chmod, 0o600)
        with self.assertLogs("yedekleme.services.yedek_servisi", "WARNING"):
            yedek = self._yedek()
        adlar = self._adlar(yedek)
        self.assertIn("ogrenci/a.pdf", adlar)
        self.assertNotIn("_akalyonetim_sistem/tahta-apt-imza-anahtari.json", adlar)

    def test_onay_sayfasi_tahta_dosyalarini_gosterir(self):
        yedek = self._yedek()
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        yanit = self.client.get(reverse("yedekleme:medya_yedek_geri_yukle_onay", args=[yedek.name]))
        self.assertContains(yanit, "APT depo anahtarı, 2 akal-eta-yonetim paketi")
