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
