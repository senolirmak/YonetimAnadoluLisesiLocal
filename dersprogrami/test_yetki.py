"""dersprogrami view'larının yetki davranışı (okul.auth'a geçişte korunmalı)."""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from okul.testing import aktif_egitim_yili_olustur, kullanici_olustur, personel_olustur

YONETICI_SAYFALARI = (
    "ogretmen_program",
    "sinif_ogretmenleri",
    "dersprogrami_listesi",
    "rehber_ogretmenler",
    "ogretmen_ders_listesi",
)
UST_YONETICI_SAYFALARI = ("sinif_program", "dersprogrami_yukle", "fet_kopru")


class DersProgramiYetkiTests(TestCase):
    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")

    def _get(self, grup, ad):
        u = kullanici_olustur(grup) if grup else kullanici_olustur()
        personel_olustur(user=u)
        self.client.force_login(u)
        return self.client.get(reverse(ad))

    def test_giris_yapmamis_kullanici_geri_donus_adresiyle_girise_yonlenir(self):
        for ad in (*YONETICI_SAYFALARI, *UST_YONETICI_SAYFALARI, "haftalik_ders_programi"):
            with self.subTest(sayfa=ad):
                url = reverse(ad)
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp["Location"].startswith(settings.LOGIN_URL))
                self.assertIn(f"next={url}", resp["Location"])

    def test_yonetici_sayfalari(self):
        for ad in YONETICI_SAYFALARI:
            for grup, beklenen in (
                ("ogretmen", 403),
                (None, 403),
                ("rehber_ogretmen", 200),
                ("disiplin_kurulu", 200),
                ("okul_muduru", 200),
                ("mudur_yardimcisi", 200),
            ):
                with self.subTest(sayfa=ad, grup=grup):
                    self.assertEqual(self._get(grup, ad).status_code, beklenen)

    def test_ust_yonetici_sayfalari(self):
        for ad in UST_YONETICI_SAYFALARI:
            for grup, beklenen in (
                ("ogretmen", 403),
                ("rehber_ogretmen", 403),
                ("disiplin_kurulu", 403),
                ("okul_muduru", 200),
                ("mudur_yardimcisi", 200),
            ):
                with self.subTest(sayfa=ad, grup=grup):
                    self.assertEqual(self._get(grup, ad).status_code, beklenen)

    def test_haftalik_program_ogretmen_secimi_yalnizca_yoneticide(self):
        for grup, secim_var in (("ogretmen", False), ("rehber_ogretmen", True), ("mudur_yardimcisi", True)):
            with self.subTest(grup=grup):
                resp = self._get(grup, "haftalik_ders_programi")
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.context["tum_ogretmenler"] is not None, secim_var)

    def test_ogretmen_programinda_tarih_degistirme_yalnizca_ust_yoneticide(self):
        for grup, beklenen in (("rehber_ogretmen", False), ("okul_muduru", True), ("mudur_yardimcisi", True)):
            with self.subTest(grup=grup):
                resp = self._get(grup, "ogretmen_program")
                self.assertEqual(resp.context["tarih_degistirebilir"], beklenen)
