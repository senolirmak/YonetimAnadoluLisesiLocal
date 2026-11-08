"""okul/yonetim/seviye-sorumlusu — müdür yardımcılarının sorumlu olduğu sınıf seviyeleri."""

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse

from okul.forms import SinifSeviyesiSorumlusuForm
from okul.models import SinifSeviyesiSorumlusu
from okul.testing import (
    aktif_egitim_yili_olustur,
    kullanici_olustur,
    personel_olustur,
    sinif_sube_olustur,
)


class SinifSeviyesiSorumlusuTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        for sinif in (9, 10, 11, 12):
            sinif_sube_olustur(sinif, "A")
        self.myrd1 = personel_olustur(gorev_tipi="Müdür Yardımcısı")
        self.myrd2 = personel_olustur(gorev_tipi="Müdür Yardımcısı")
        self.emekli_myrd = personel_olustur(gorev_tipi="Müdür Yardımcısı", durum="Emekli")
        self.ogretmen = personel_olustur(gorev_tipi="Öğretmen")
        self.url = reverse("okul:yonetim_list", args=["seviye-sorumlusu"])

    def test_formda_yalnizca_gorevdeki_mudur_yardimcilari_ve_okulun_seviyeleri(self):
        form = SinifSeviyesiSorumlusuForm()
        self.assertEqual(set(form.fields["personel"].queryset), {self.myrd1, self.myrd2})
        self.assertEqual([c[0] for c in form.fields["sinif"].choices], [9, 10, 11, 12])
        self.assertEqual(form.fields["egitim_yili"].initial, self.yil)

    def test_bir_mudur_yardimcisi_birden_fazla_seviyeden_sorumlu_olabilir(self):
        for sinif in (9, 10):
            form = SinifSeviyesiSorumlusuForm({"egitim_yili": self.yil.pk, "sinif": sinif, "personel": self.myrd1.pk})
            self.assertTrue(form.is_valid(), form.errors)
            form.save()
        self.assertEqual(self.myrd1.seviye_sorumluluklari.count(), 2)

    def test_bir_seviyenin_yilda_tek_sorumlusu_olur(self):
        SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=9, personel=self.myrd1)
        form = SinifSeviyesiSorumlusuForm({"egitim_yili": self.yil.pk, "sinif": 9, "personel": self.myrd2.pk})
        self.assertFalse(form.is_valid())
        with self.assertRaises(IntegrityError):
            SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=9, personel=self.myrd2)

    def test_ogretmen_atanamaz(self):
        form = SinifSeviyesiSorumlusuForm({"egitim_yili": self.yil.pk, "sinif": 11, "personel": self.ogretmen.pk})
        self.assertFalse(form.is_valid())
        self.assertIn("personel", form.errors)

    def test_okul_yonetimi_sayfalari(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("okul:yonetim_index"))
        self.assertContains(resp, "Sınıf Seviyesi Sorumluları")
        resp = self.client.post(reverse("okul:yonetim_create", args=["seviye-sorumlusu"]),
                                {"egitim_yili": self.yil.pk, "sinif": 12, "personel": self.myrd2.pk})
        self.assertRedirects(resp, self.url)
        resp = self.client.get(self.url)
        self.assertContains(resp, self.myrd2.adi_soyadi)
        self.assertContains(resp, "2025-2026")

    def test_yalnizca_mudur_yardimcisi_yonetir(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
