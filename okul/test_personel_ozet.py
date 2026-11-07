"""okul.services.personel_ozet — ana sayfadaki "Aktif Personel" kartı."""

import datetime

from django.test import TestCase
from django.urls import reverse

from okul.services.personel_ozet import aktif_personel_ozeti
from okul.testing import (
    devamsizlik_olustur,
    kullanici_olustur,
    nobet_ogretmen_olustur,
    personel_olustur,
)


class AktifPersonelOzetiTests(TestCase):
    def test_sayilar(self):
        bugun = datetime.date(2025, 10, 15)
        personel_olustur(gorev_tipi="Öğretmen", cinsiyet=False)
        personel_olustur(gorev_tipi="Öğretmen", cinsiyet=True)
        personel_olustur(gorev_tipi="Müdür Yardımcısı", cinsiyet=True)
        personel_olustur(gorev_tipi=None, cinsiyet=False)
        personel_olustur(gorev_tipi="Öğretmen", durum="Analık İzinli")  # geçici görev dışı
        personel_olustur(gorev_tipi="Öğretmen", durum="Emekli")  # arşiv: hiç sayılmaz
        izinli = nobet_ogretmen_olustur(personel_olustur(gorev_tipi="Öğretmen", cinsiyet=True))
        devamsizlik_olustur(izinli, bugun)

        ozet = aktif_personel_ozeti(bugun)

        self.assertEqual(
            [(g["gorev"], g["kadin"], g["erkek"], g["toplam"]) for g in ozet["gorevler"]],
            [("Öğretmen", 1, 2, 3), ("Müdür Yardımcısı", 0, 1, 1), ("Belirtilmemiş", 1, 0, 1)],
        )
        self.assertEqual(ozet["toplam"], {"kadin": 2, "erkek": 3, "toplam": 5})
        self.assertEqual(ozet["gecici_gorev_disi"], 1)
        self.assertEqual(ozet["bugun_devamsiz"], 1)

    def test_ana_sayfada_kart_gorunur(self):
        personel_olustur(gorev_tipi="Öğretmen")
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, "Aktif Personel")
        self.assertContains(resp, "Görevde Toplam")

    def test_personel_listesi_dugmesi_okul_yonetimine_gider(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("index"))
        self.assertContains(
            resp, f'href="{reverse("okul:yonetim_list", args=["personel"])}" class="btn btn-sm"'
        )
