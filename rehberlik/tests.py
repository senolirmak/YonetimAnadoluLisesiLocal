"""rehberlik erişim testleri (KVKK — özel nitelikli kişisel veri)."""

import datetime

from django.test import TestCase
from django.urls import reverse

from okul.testing import kullanici_olustur, ogrenci_olustur, personel_olustur
from rehberlik.models import Gorusme


def _rehber():
    user = kullanici_olustur("rehber_ogretmen")
    return user, personel_olustur(user=user)


def _gorusme(rehber, gizli=False):
    return Gorusme.objects.create(
        ogrenci=ogrenci_olustur(), tarih=datetime.date(2025, 10, 1), tur="bireysel",
        konu="Örnek konu", rehber=rehber, gizli=gizli,
    )


class GorusmeDetayErisimTestCase(TestCase):
    def setUp(self):
        self.rehber1_user, self.rehber1 = _rehber()
        self.rehber2_user, self.rehber2 = _rehber()
        self.acik = _gorusme(self.rehber1)
        self.gizli = _gorusme(self.rehber1, gizli=True)

    def _durum(self, user, gorusme):
        self.client.force_login(user)
        return self.client.get(reverse("rehberlik:gorusme_detay", args=[gorusme.pk])).status_code

    def test_sahibi_gizli_dahil_gorur(self):
        self.assertEqual(self._durum(self.rehber1_user, self.acik), 200)
        self.assertEqual(self._durum(self.rehber1_user, self.gizli), 200)

    def test_baska_rehber_pk_ile_acamaz(self):
        self.assertEqual(self._durum(self.rehber2_user, self.acik), 302)
        self.assertEqual(self._durum(self.rehber2_user, self.gizli), 302)

    def test_mudur_yardimcisi_gizli_olmayani_gorur(self):
        mudur = kullanici_olustur("mudur_yardimcisi")
        self.assertEqual(self._durum(mudur, self.acik), 200)
        self.assertEqual(self._durum(mudur, self.gizli), 302)

    def test_ogretmen_ve_disiplin_goremez(self):
        for grup in ("ogretmen", "disiplin_kurulu", "okul_muduru"):
            with self.subTest(grup=grup):
                self.assertEqual(self._durum(kullanici_olustur(grup), self.acik), 302)

    def test_liste_yalnizca_kendi_kayitlari(self):
        _gorusme(self.rehber2)
        self.client.force_login(self.rehber1_user)
        resp = self.client.get(reverse("rehberlik:gorusme_liste"))
        self.assertEqual({g.rehber_id for g in resp.context["gorusmeler"]}, {self.rehber1.pk})
