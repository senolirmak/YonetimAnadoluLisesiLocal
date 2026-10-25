"""dersdefteri yetki testleri."""

from django.test import TestCase
from django.urls import reverse

from okul.testing import ders_programi_olustur, kullanici_olustur, personel_olustur


class DersDefteriYetkiTestCase(TestCase):
    def setUp(self):
        self.sahip_user = kullanici_olustur("ogretmen")
        self.ders = ders_programi_olustur(personel_olustur(user=self.sahip_user), 1)
        self.url = reverse("dersdefteri:kayit_form", args=[self.ders.pk])

    def test_kendi_dersine_yazar(self):
        self.client.force_login(self.sahip_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_baska_ogretmen_rehber_ve_disiplin_yazamaz(self):
        for grup in ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"):
            user = kullanici_olustur(grup)
            personel_olustur(user=user)
            self.client.force_login(user)
            with self.subTest(grup=grup):
                self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_ust_yonetici_baskasinin_dersine_yazabilir(self):
        for grup in ("mudur_yardimcisi", "okul_muduru"):
            self.client.force_login(kullanici_olustur(grup))
            with self.subTest(grup=grup):
                self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_rehber_gecmisi_okuyabilir(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        self.assertEqual(self.client.get(reverse("dersdefteri:gecmis_listesi")).status_code, 200)
