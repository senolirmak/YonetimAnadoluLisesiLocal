"""ogrenci.services.aktiflik testleri."""

from django.test import TestCase

from ogrenci.models import OgrenciAyrilma
from ogrenci.services.aktiflik import aktifligi_guncelle, pasif_sebepleri
from okul.testing import aktif_egitim_yili_olustur, ogrenci_olustur


class AktiflikTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.ogr = ogrenci_olustur(12, "A", aktif=False)

    def test_sebep_yoksa_aktif_olur(self):
        self.assertEqual(aktifligi_guncelle(self.ogr), [])
        self.ogr.refresh_from_db()
        self.assertTrue(self.ogr.aktif)

    def test_sebeplerin_hepsi_sayilir(self):
        from okul.models import EgitimOgretimYili
        from secmelidersler.models import OgrenciTasdikname
        from senesonu.models import SeneSonuGecisi, SeneSonuOgrenciGecisi

        OgrenciAyrilma.objects.create(ogrenci=self.ogr, sebep="nakil")
        OgrenciTasdikname.objects.create(ogrenci=self.ogr, egitim_yili=self.yil)
        yeni_yil = EgitimOgretimYili.objects.create(
            egitim_yili="2026-2027",
            egitim_baslangic=self.yil.egitim_bitis,
            egitim_bitis=self.yil.egitim_bitis.replace(year=2027),
        )
        gecis = SeneSonuGecisi.objects.create(
            eski_egitim_yili=self.yil, yeni_egitim_yili=yeni_yil, uygulandi=True
        )
        SeneSonuOgrenciGecisi.objects.create(
            gecis=gecis, ogrenci=self.ogr, eski_sinif=12, eski_sube="A", durum="mezun"
        )

        self.assertEqual(
            pasif_sebepleri(self.ogr), ["okuldan ayrılma kaydı", "tasdikname kaydı", "mezuniyet"]
        )

    def test_aktif_ogrenci_sebep_varsa_pasife_alinir(self):
        self.ogr.aktif = True
        self.ogr.save()
        OgrenciAyrilma.objects.create(ogrenci=self.ogr, sebep="nakil")

        self.assertEqual(aktifligi_guncelle(self.ogr), ["okuldan ayrılma kaydı"])
        self.ogr.refresh_from_db()
        self.assertFalse(self.ogr.aktif)
