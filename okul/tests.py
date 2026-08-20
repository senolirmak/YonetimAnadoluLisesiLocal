"""okul app testleri.

Şimdilik yalnızca `okul_bilgisi_olustur` management command'ı test ediliyor —
diğer modeller/view'lar için gerçek test yok (bkz. CLAUDE.md).
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from okul.models import EgitimOgretimYili, OkulBilgi


class OkulBilgisiOlusturTestCase(TestCase):
    def _calistir(self, **kwargs):
        call_command("okul_bilgisi_olustur", stdout=StringIO(), **kwargs)

    def test_yapilandirilmamis_okulda_kayit_olusturulur(self):
        self._calistir(okul_adi="Örnek Anadolu Lisesi", egitim_yili="2025-2026")

        okul = OkulBilgi.get()
        self.assertEqual(okul.okul_adi, "Örnek Anadolu Lisesi")
        self.assertIsNotNone(okul.okul_egtyil)
        self.assertEqual(okul.okul_egtyil.egitim_yili, "2025-2026")

        yil = EgitimOgretimYili.objects.get(egitim_yili="2025-2026")
        # Varsayılan tarihler: ilk yılın 1 Eylül'ü, ikinci yılın 20 Haziran'ı.
        self.assertEqual(yil.egitim_baslangic, datetime.date(2025, 9, 1))
        self.assertEqual(yil.egitim_bitis, datetime.date(2026, 6, 20))

    def test_ozel_tarihler_kullanilir(self):
        self._calistir(
            okul_adi="Örnek Anadolu Lisesi",
            egitim_yili="2025-2026",
            baslangic="2025-09-08",
            bitis="2026-06-19",
        )
        yil = EgitimOgretimYili.objects.get(egitim_yili="2025-2026")
        self.assertEqual(yil.egitim_baslangic, datetime.date(2025, 9, 8))
        self.assertEqual(yil.egitim_bitis, datetime.date(2026, 6, 19))

    def test_zaten_yapilandirilmis_okul_degistirilmez(self):
        OkulBilgi.objects.create(pk=1, okul_adi="Mevcut Okul")

        self._calistir(okul_adi="Başka Okul", egitim_yili="2030-2031")

        okul = OkulBilgi.get()
        self.assertEqual(okul.okul_adi, "Mevcut Okul")
        self.assertFalse(EgitimOgretimYili.objects.filter(egitim_yili="2030-2031").exists())

    def test_gecersiz_egitim_yili_bicimi_hata_verir(self):
        with self.assertRaises(CommandError):
            self._calistir(okul_adi="Örnek Lise", egitim_yili="gecersiz")

    def test_ikinci_calistirmada_egitim_yili_tekrar_olusturulmaz(self):
        EgitimOgretimYili.objects.create(
            egitim_yili="2025-2026",
            egitim_baslangic=datetime.date(2025, 9, 1),
            egitim_bitis=datetime.date(2026, 6, 20),
        )
        self._calistir(okul_adi="Örnek Anadolu Lisesi", egitim_yili="2025-2026")
        self.assertEqual(EgitimOgretimYili.objects.filter(egitim_yili="2025-2026").count(), 1)
