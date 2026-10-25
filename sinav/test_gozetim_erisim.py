"""Sınav günü öğretmen sayfalarına erişim kuralları (sinav/services/gozetim_erisim.py).

Senaryo: Pazartesi 10:30 sınavı, salon "Salon-9_A". Ders saatleri okul.testing'e göre
1. ders 08:00–08:40, 2. ders 09:00–09:40, 3. ders 10:00–10:40; sınavdan önce biten son
ders 2. ders. Buna göre:
  - gözetmen öğretmen salon yoklamasını 10:22–11:10 arasında açabilir,
  - 2. derste 9/A'ya giren öğretmen sınıf listesini 09:00–10:20 arasında açabilir.
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from okul.testing import (
    ders_programi_olustur,
    ders_saati_olustur,
    kullanici_olustur,
    personel_olustur,
    sinif_sube_olustur,
    zamani_dondur,
)
from sinav.services.gozetim_erisim import salon_gozetim_erisimi, sinif_listesi_erisimi

GUN = datetime.date(2025, 11, 3)  # Pazartesi
SAAT = "10:30"
SALON = "Salon-9_A"


class GozetimErisimTestCase(TestCase):
    def setUp(self):
        from sinav.models import OturmaPlani, OturmaUretim, SinavBilgisi, TakvimUretim

        for no in (1, 2, 3):
            ders_saati_olustur(no)
        sinif_9a = sinif_sube_olustur(9, "A")

        self.sinav = SinavBilgisi.objects.create(
            egitim_ogretim_yili="2025-2026", donem="1", sinav_adi="1",
            sinav_baslangic_tarihi=GUN, eokul_veri_tarihi=datetime.date(2025, 10, 1), aktif=True,
        )
        self.uretim = TakvimUretim.objects.create(sinav=self.sinav, aktif=True)
        OturmaUretim.objects.create(takvim_uretim=self.uretim, tarih=GUN, saat=SAAT, oturum=1)

        self.gozetmen_user = kullanici_olustur("ogretmen")
        self.gozetmen = personel_olustur(user=self.gozetmen_user)
        self.sinif_ogretmeni_user = kullanici_olustur("ogretmen")
        self.sinif_ogretmeni = personel_olustur(user=self.sinif_ogretmeni_user)
        ders_programi_olustur(self.sinif_ogretmeni, 2, sinif_9a)
        self.baska_user = kullanici_olustur("ogretmen")
        personel_olustur(user=self.baska_user)

        for sira, sinifsube in enumerate(["9/A", "10/B"], start=1):
            OturmaPlani.objects.create(
                sinav=self.sinav, uretim=self.uretim, tarih=GUN, saat=SAAT, oturum=1,
                salon=SALON, sira_no=sira, okulno=str(100 + sira), sinifsube=sinifsube,
                adi_soyadi=f"Öğrenci {sira}", ders_adi="MATEMATİK",
                gozetmen_fk=self.gozetmen, salon_sinif_sube=sinif_9a,
            )

    # ── servis ───────────────────────────────────────────────

    def test_salon_yoklamasi_yalnizca_gozetmene_ve_saat_penceresinde(self):
        def erisim(personel, simdi, tarih=GUN, salon=SALON):
            return salon_gozetim_erisimi(personel, self.uretim, tarih, SAAT, salon, GUN, simdi)

        self.assertFalse(erisim(self.gozetmen, "10:21"))
        self.assertTrue(erisim(self.gozetmen, "10:22"))
        self.assertTrue(erisim(self.gozetmen, "11:10"))
        self.assertFalse(erisim(self.gozetmen, "11:11"))
        self.assertFalse(erisim(self.gozetmen, "10:30", tarih=GUN + datetime.timedelta(days=1)))
        self.assertFalse(erisim(self.gozetmen, "10:30", salon="Salon-10_B"))
        self.assertFalse(erisim(self.sinif_ogretmeni, "10:30"))
        self.assertFalse(erisim(None, "10:30"))

    def test_nobet_devriyle_ustlenilen_salon_da_acilir(self):
        """Devamsız öğretmenin 3. ders (sınav saati) yerine 9/A'ya giren nöbetçi."""
        from django.utils import timezone

        from nobet.models import NobetGecmisi
        from okul.testing import nobet_ogretmen_olustur
        from sinav.models import Takvim

        Takvim.objects.create(
            sinav=self.sinav, uretim=self.uretim, tarih=GUN, saat=SAAT, oturum=1,
            ders_saati=ders_saati_olustur(3), subeler="9/A",
        )
        nobetci = nobet_ogretmen_olustur()
        NobetGecmisi.objects.create(
            saat=3, sinif="9/A", devamsiz=0, atandi=1, ogretmen=nobetci,
            tarih=timezone.make_aware(datetime.datetime.combine(GUN, datetime.time(8, 0))),
        )

        self.assertTrue(
            salon_gozetim_erisimi(nobetci.personel, self.uretim, GUN, SAAT, SALON, GUN, "10:30")
        )
        self.assertFalse(
            salon_gozetim_erisimi(nobetci.personel, self.uretim, GUN, SAAT, SALON, GUN, "12:00")
        )

    def test_sinif_listesi_yalnizca_onceki_dersin_ogretmenine_ve_saat_penceresinde(self):
        def erisim(personel, simdi, sinifsube="9/A", oturum=1):
            return sinif_listesi_erisimi(personel, self.uretim, GUN, SAAT, sinifsube, oturum, GUN, simdi)

        self.assertFalse(erisim(self.sinif_ogretmeni, "08:59"))
        self.assertTrue(erisim(self.sinif_ogretmeni, "09:00"))
        self.assertTrue(erisim(self.sinif_ogretmeni, "10:20"))
        self.assertFalse(erisim(self.sinif_ogretmeni, "10:21"))
        self.assertFalse(erisim(self.sinif_ogretmeni, "09:30", sinifsube="10/B"))
        self.assertFalse(erisim(self.sinif_ogretmeni, "09:30", oturum=2))
        self.assertFalse(erisim(self.gozetmen, "09:30"))

    # ── view'lar ─────────────────────────────────────────────

    def _yoklama(self, user, saat, dakika, method="get", **veri):
        self.client.force_login(user)
        url = reverse("sinav_salon_yoklama") + f"?tarih={GUN.isoformat()}&saat={SAAT}&salon={SALON}"
        with zamani_dondur(GUN, saat, dakika):
            return getattr(self.client, method)(url, veri)

    def test_salon_yoklamasi_sayfasi(self):
        from sinav.models import SinavSalonYoklama

        self.assertEqual(self._yoklama(self.gozetmen_user, 10, 25).status_code, 200)
        self.assertEqual(self._yoklama(self.gozetmen_user, 9, 0).status_code, 403)
        self.assertEqual(self._yoklama(self.baska_user, 10, 25).status_code, 403)

        resp = self._yoklama(self.baska_user, 10, 25, method="post", durum_101="yok")
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(SinavSalonYoklama.objects.exists())

        self._yoklama(self.gozetmen_user, 10, 25, method="post", durum_101="yok")
        self.assertEqual(SinavSalonYoklama.objects.get(okulno="101").durum, "yok")

    def test_yonetici_saat_ve_atama_kontrolunden_muaf(self):
        yonetici = kullanici_olustur("mudur_yardimcisi")
        self.assertEqual(self._yoklama(yonetici, 15, 0).status_code, 200)

    def _pdf(self, user, saat, dakika, sinifsube="9/A"):
        self.client.force_login(user)
        url = (
            reverse("sinav:sinif_listesi_pdf_view")
            + f"?uretim={self.uretim.pk}&tarih={GUN.isoformat()}&saat={SAAT}&oturum=1"
            + (f"&sinifsube={sinifsube}" if sinifsube else "")
        )
        with zamani_dondur(GUN, saat, dakika):
            return self.client.get(url)

    def test_sinif_listesi_pdf(self):
        resp = self._pdf(self.sinif_ogretmeni_user, 9, 30)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

        self.assertEqual(self._pdf(self.sinif_ogretmeni_user, 11, 0).status_code, 403)
        self.assertEqual(self._pdf(self.sinif_ogretmeni_user, 9, 30, sinifsube="10/B").status_code, 403)
        self.assertEqual(self._pdf(self.sinif_ogretmeni_user, 9, 30, sinifsube=None).status_code, 403)
        self.assertEqual(self._pdf(self.baska_user, 9, 30).status_code, 403)

        # Yönetici (PDF Rapor sayfası) şube filtresi olmadan, her saatte indirebilir.
        self.assertEqual(self._pdf(kullanici_olustur("okul_muduru"), 15, 0, sinifsube=None).status_code, 200)

    def test_eski_sinif_listesi_sayfasi(self):
        url = reverse("ogretmen_gozetim_sinif_listesi") + f"?tarih={GUN.isoformat()}&saat={SAAT}&sinifsube=9/A"
        self.client.force_login(self.sinif_ogretmeni_user)
        with zamani_dondur(GUN, 9, 30):
            self.assertEqual(self.client.get(url).status_code, 200)
        with zamani_dondur(GUN, 12, 0):
            self.assertEqual(self.client.get(url).status_code, 403)

    def test_gozetim_ekrani_dugmeleri_ayni_kurala_gore_acar(self):
        """Ana ekran (ogretmen_sinav_gozetim) ile sayfaların kuralı tutarlı olmalı."""
        self.client.force_login(self.gozetmen_user)
        with zamani_dondur(GUN, 10, 25):
            resp = self.client.get(reverse("ogretmen_sinav_gozetim"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("sinav_salon_yoklama"))
