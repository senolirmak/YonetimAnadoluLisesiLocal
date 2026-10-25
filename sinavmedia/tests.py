"""sinavmedia: sınav medyası dosyalarına erişim (sinavmedia/services/erisim.py).

Önceden dosyalar Nginx tarafından /media/ altından kontrolsüz sunuluyordu; dinleme sınavı
ses dosyası sınavdan önce, giriş yapmadan indirilebiliyordu.
"""

import datetime
import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from okul.testing import kullanici_olustur

GUN = datetime.date(2025, 11, 3)
SAAT = "10:30"
_MEDYA_KOK = tempfile.mkdtemp(prefix="sinavmedia_test_")


def _simdi(saat, dakika):
    """Erişim servisi timezone.now() kullanır; sınav günündeki bir ana sabitler."""
    from unittest import mock

    from django.utils import timezone

    an = timezone.make_aware(datetime.datetime.combine(GUN, datetime.time(saat, dakika)))
    return mock.patch("django.utils.timezone.now", return_value=an)


@override_settings(MEDIA_ROOT=_MEDYA_KOK)
class SinavMedyaDosyaTestCase(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(_MEDYA_KOK, ignore_errors=True)

    def setUp(self):
        from sinav.models import SinavBilgisi, Takvim, TakvimUretim
        from sinavmedia.models import SinavMedia

        sinav = SinavBilgisi.objects.create(
            egitim_ogretim_yili="2025-2026", donem="1", sinav_adi="1", aktif=True,
            sinav_baslangic_tarihi=GUN, eokul_veri_tarihi=datetime.date(2025, 10, 1),
        )
        uretim = TakvimUretim.objects.create(sinav=sinav, aktif=True)
        takvim = Takvim.objects.create(
            sinav=sinav, uretim=uretim, tarih=GUN, saat=SAAT, oturum=1,
            sinav_turu="Uygulama", subeler="9/A",
        )
        self.medya = SinavMedia.objects.create(
            takvim=takvim, seviye=9,
            dosya=SimpleUploadedFile("dinleme.mp3", b"ID3-sahte-ses", content_type="audio/mpeg"),
        )
        self.url = reverse("sinavmedia:dosya", args=[self.medya.pk])
        self.ogretmen = kullanici_olustur("ogretmen")

    def _durum(self, user, saat, dakika):
        self.client.force_login(user)
        with _simdi(saat, dakika):
            return self.client.get(self.url)

    def test_anonim_login_sayfasina_yonlenir(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].startswith(settings.LOGIN_URL))

    def test_ogretmen_yalnizca_sinav_penceresinde(self):
        self.assertEqual(self._durum(self.ogretmen, 10, 29).status_code, 403)
        resp = self._durum(self.ogretmen, 10, 50)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b"".join(resp.streaming_content), b"ID3-sahte-ses")
        self.assertEqual(resp["Content-Type"], "audio/mpeg")
        self.assertIn("no-store", resp["Cache-Control"])
        self.assertEqual(self._durum(self.ogretmen, 11, 30).status_code, 200)  # 60. dakika
        self.assertEqual(self._durum(self.ogretmen, 11, 31).status_code, 403)

    def test_serbest_ve_mudur_yardimcisi_her_zaman(self):
        self.assertEqual(self._durum(kullanici_olustur("mudur_yardimcisi"), 8, 0).status_code, 200)
        self.medya.serbest = True
        self.medya.save()
        self.assertEqual(self._durum(self.ogretmen, 8, 0).status_code, 200)

    @override_settings(SINAVMEDIA_X_ACCEL=True)
    def test_nginx_modunda_x_accel_redirect(self):
        resp = self._durum(self.ogretmen, 10, 35)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"")
        self.assertEqual(resp["X-Accel-Redirect"], "/korumali-medya/" + self.medya.dosya.name)

    def test_oynatici_korumali_adresi_kullanir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("sinavmedia:oynat", args=[self.medya.pk]))
        self.assertContains(resp, self.url)
        self.assertNotContains(resp, self.medya.dosya.url)

    def test_ogretmen_medya_sayfasi_korumali_adresi_kullanir(self):
        from okul.testing import personel_olustur, sinif_sube_olustur
        from sinav.models import OturmaPlani

        personel = personel_olustur(user=self.ogretmen)
        OturmaPlani.objects.create(
            sinav=self.medya.takvim.sinav, uretim=self.medya.takvim.uretim, tarih=GUN, saat=SAAT,
            oturum=1, salon="Salon-9_A", sira_no=1, okulno="1", sinifsube="9/A",
            adi_soyadi="Öğrenci", ders_adi="İNGİLİZCE", gozetmen_fk=personel,
            salon_sinif_sube=sinif_sube_olustur(9, "A"),
        )
        resp = self._sayfa(10, 31)
        self.assertContains(resp, self.url)
        self.assertNotContains(resp, self.medya.dosya.url)
        self.assertNotContains(self._sayfa(9, 0), self.url)  # sınavdan önce bağlantı yok

    def _sayfa(self, saat, dakika):
        self.client.force_login(self.ogretmen)
        with _simdi(saat, dakika):
            return self.client.get(reverse("ogretmen_sinav_medya"))
