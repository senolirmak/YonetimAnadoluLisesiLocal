"""secmelidersler app testleri.

Şimdilik yalnızca `varsayilan_ders_verilerini_yukle` management command'ı test
ediliyor — komut, projeyle birlikte gelen gerçek fixture dosyasını
(`fixtures/varsayilan_ders_verileri.json`) kullanır; bu yüzden testler hem
komutun mantığını hem de fixture'ın bozulmadığını (geçerli JSON, beklenen
anahtarlar) birlikte doğrular.
"""

import datetime
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from okul.models import Brans, EgitimOgretimYili, OkulBilgi
from secmelidersler.models import (
    OrtakDers,
    OrtakDersHavuzu,
    SecmeliDers,
    SecmeliDersGrubu,
    SecmeliDersHavuzu,
)


class VarsayilanDersVerileriniYukleTestCase(TestCase):
    def _calistir(self, **kwargs):
        call_command("varsayilan_ders_verilerini_yukle", stdout=StringIO(), **kwargs)

    def test_sadece_havuz_egitim_yili_gerektirmez(self):
        self._calistir(sadece_havuz=True)

        self.assertGreater(Brans.objects.count(), 0)
        self.assertGreater(OrtakDersHavuzu.objects.count(), 0)
        self.assertGreater(SecmeliDersHavuzu.objects.count(), 0)
        # --sadece-havuz ile yıl bazlı tablolara hiç dokunulmamalı. (secmelidersler
        # migrations'ından 0011_rehberlik_verisi, egitim_yili=None ile 4 taban
        # OrtakDers kaydı ekliyor — bunlar zaten migrate'te oluşur, komutun eseri
        # değildir; bu yüzden yalnızca yıl bazlı (egitim_yili dolu) kayıtları sayıyoruz.)
        self.assertEqual(OrtakDers.objects.filter(egitim_yili__isnull=False).count(), 0)
        self.assertEqual(SecmeliDersGrubu.objects.filter(egitim_yili__isnull=False).count(), 0)

    def test_havuz_kayitlarinin_branslari_dolu(self):
        self._calistir(sadece_havuz=True)
        ilk = OrtakDersHavuzu.objects.first()
        self.assertIsNotNone(ilk)
        self.assertGreater(ilk.branslar.count(), 0)

    def test_aktif_egitim_yili_yoksa_ve_arguman_verilmezse_hata_verir(self):
        with self.assertRaises(CommandError):
            self._calistir()

    def test_egitim_yili_argumaniyla_yil_bazli_tablolar_yuklenir(self):
        EgitimOgretimYili.objects.create(
            egitim_yili="2025-2026",
            egitim_baslangic=datetime.date(2025, 9, 1),
            egitim_bitis=datetime.date(2026, 6, 20),
        )

        self._calistir(egitim_yili="2025-2026")

        yil = EgitimOgretimYili.objects.get(egitim_yili="2025-2026")
        self.assertGreater(OrtakDers.objects.filter(egitim_yili=yil).count(), 0)
        self.assertGreater(SecmeliDersGrubu.objects.filter(egitim_yili=yil).count(), 0)
        # Her grubun en az bir dersi olmalı (boş grup fixture'da varsa bile
        # genel olarak grupların çoğunda ders bulunur).
        self.assertGreater(SecmeliDers.objects.filter(grup__egitim_yili=yil).count(), 0)

    def test_olmayan_egitim_yili_hata_verir(self):
        with self.assertRaises(CommandError):
            self._calistir(egitim_yili="1999-2000")

    def test_okulbilgideki_aktif_yil_otomatik_kullanilir(self):
        yil = EgitimOgretimYili.objects.create(
            egitim_yili="2025-2026",
            egitim_baslangic=datetime.date(2025, 9, 1),
            egitim_bitis=datetime.date(2026, 6, 20),
        )
        okul = OkulBilgi.get()
        okul.okul_egtyil = yil
        okul.save()

        self._calistir()  # --egitim-yili verilmedi

        self.assertGreater(OrtakDers.objects.filter(egitim_yili=yil).count(), 0)

    def test_ikinci_calistirma_kopya_olusturmaz(self):
        EgitimOgretimYili.objects.create(
            egitim_yili="2025-2026",
            egitim_baslangic=datetime.date(2025, 9, 1),
            egitim_bitis=datetime.date(2026, 6, 20),
        )

        self._calistir(egitim_yili="2025-2026")
        ortak_sayisi_1 = OrtakDers.objects.count()
        grup_sayisi_1 = SecmeliDersGrubu.objects.count()
        ders_sayisi_1 = SecmeliDers.objects.count()
        brans_sayisi_1 = Brans.objects.count()

        self._calistir(egitim_yili="2025-2026")

        self.assertEqual(OrtakDers.objects.count(), ortak_sayisi_1)
        self.assertEqual(SecmeliDersGrubu.objects.count(), grup_sayisi_1)
        self.assertEqual(SecmeliDers.objects.count(), ders_sayisi_1)
        self.assertEqual(Brans.objects.count(), brans_sayisi_1)


class SecmeliDersAdlarinaOnekEkleMigrationTestCase(TestCase):
    """0029_secmeli_ders_adlarina_onek_ekle: havuzdaki ön eksiz seçmeli ders adları ve
    onlara ad üzerinden bağlı grup dersleri "SEÇMELİ " ön ekini almalı."""

    def _calistir(self):
        import importlib

        from django.apps import apps

        importlib.import_module(
            "secmelidersler.migrations.0029_secmeli_ders_adlarina_onek_ekle"
        ).onek_ekle(apps, None)

    def setUp(self):
        SecmeliDersHavuzu.objects.create(ders_adi="KLASİK AHLAK METİNLERİ")
        SecmeliDersHavuzu.objects.create(ders_adi="SEÇMELİ FİZİK")
        grup = SecmeliDersGrubu.objects.create(sinif_seviyesi=11, adi="TEST GRUBU")
        self.ahlak = SecmeliDers.objects.create(grup=grup, ders_adi="KLASİK AHLAK METİNLERİ (2)")
        self.fizik = SecmeliDers.objects.create(grup=grup, ders_adi="SEÇMELİ FİZİK (4)")
        self.havuzsuz = SecmeliDers.objects.create(grup=grup, ders_adi="HAVUZDA OLMAYAN DERS (1)")

    def test_onek_eklenir_saat_eki_korunur(self):
        self._calistir()
        self.assertEqual(
            set(SecmeliDersHavuzu.objects.values_list("ders_adi", flat=True)),
            {"SEÇMELİ KLASİK AHLAK METİNLERİ", "SEÇMELİ FİZİK"},
        )
        for ders in (self.ahlak, self.fizik, self.havuzsuz):
            ders.refresh_from_db()
        self.assertEqual(self.ahlak.ders_adi, "SEÇMELİ KLASİK AHLAK METİNLERİ (2)")
        self.assertEqual(self.fizik.ders_adi, "SEÇMELİ FİZİK (4)")
        self.assertEqual(self.havuzsuz.ders_adi, "HAVUZDA OLMAYAN DERS (1)")

    def test_ikinci_calistirma_degistirmez(self):
        self._calistir()
        self._calistir()
        self.ahlak.refresh_from_db()
        self.assertEqual(self.ahlak.ders_adi, "SEÇMELİ KLASİK AHLAK METİNLERİ (2)")

    def test_cakisan_ad_atlanir(self):
        SecmeliDersHavuzu.objects.create(ders_adi="SEÇMELİ KLASİK AHLAK METİNLERİ")
        self._calistir()
        self.assertTrue(SecmeliDersHavuzu.objects.filter(ders_adi="KLASİK AHLAK METİNLERİ").exists())
        self.ahlak.refresh_from_db()
        self.assertEqual(self.ahlak.ders_adi, "KLASİK AHLAK METİNLERİ (2)")
