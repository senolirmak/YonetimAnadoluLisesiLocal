"""disiplin erişim testleri (KVKK)."""

import datetime

from django.test import TestCase
from django.urls import reverse

from disiplin.models import DisiplinGorusme as Gorusme
from okul.testing import kullanici_olustur, ogrenci_olustur, personel_olustur


def _uye():
    user = kullanici_olustur("disiplin_kurulu")
    return user, personel_olustur(user=user)


def _gorusme(uye, gizli=False):
    return Gorusme.objects.create(
        ogrenci=ogrenci_olustur(), tarih=datetime.date(2025, 10, 1), tur="bireysel",
        konu="Örnek konu", kayit_eden=uye, gizli=gizli,
    )


class GorusmeDetayErisimTestCase(TestCase):
    def setUp(self):
        self.uye1_user, self.uye1 = _uye()
        self.uye2_user, self.uye2 = _uye()
        self.acik = _gorusme(self.uye1)
        self.gizli = _gorusme(self.uye1, gizli=True)

    def _durum(self, user, gorusme):
        self.client.force_login(user)
        return self.client.get(reverse("disiplin:gorusme_detay", args=[gorusme.pk])).status_code

    def test_sahibi_gizli_dahil_gorur(self):
        self.assertEqual(self._durum(self.uye1_user, self.acik), 200)
        self.assertEqual(self._durum(self.uye1_user, self.gizli), 200)

    def test_baska_uye_pk_ile_acamaz(self):
        self.assertEqual(self._durum(self.uye2_user, self.acik), 302)
        self.assertEqual(self._durum(self.uye2_user, self.gizli), 302)

    def test_mudur_yardimcisi_gizli_olmayani_gorur(self):
        mudur = kullanici_olustur("mudur_yardimcisi")
        self.assertEqual(self._durum(mudur, self.acik), 200)
        self.assertEqual(self._durum(mudur, self.gizli), 302)

    def test_ogretmen_ve_disiplin_goremez(self):
        for grup in ("ogretmen", "rehber_ogretmen", "okul_muduru"):
            with self.subTest(grup=grup):
                self.assertEqual(self._durum(kullanici_olustur(grup), self.acik), 302)

    def test_liste_yalnizca_kendi_kayitlari(self):
        _gorusme(self.uye2)
        self.client.force_login(self.uye1_user)
        resp = self.client.get(reverse("disiplin:gorusme_liste"))
        self.assertEqual({g.kayit_eden_id for g in resp.context["gorusmeler"]}, {self.uye1.pk})

    def test_pasif_mudur_yardimcisi_goremez(self):
        from okul.models import OkulYonetici

        mudur = kullanici_olustur("mudur_yardimcisi")
        OkulYonetici.objects.create(user=mudur, unvan="mudur_yardimcisi", aktif=False)
        self.assertEqual(self._durum(mudur, self.acik), 302)
