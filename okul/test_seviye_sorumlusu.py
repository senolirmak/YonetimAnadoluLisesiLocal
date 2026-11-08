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

    def test_okul_yonetiminde_ders_yuku_karti(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("okul:yonetim_index"))
        self.assertContains(resp, "Branş Bazlı Ders Yükü")
        self.assertContains(resp, f'{reverse("secmeli_ders_yuku")}?yil={self.yil.pk}')
        self.assertEqual(resp.context["ders_yuku_ozeti"]["brans"], 0)

    def test_ust_yonetici_yonetir(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.force_login(kullanici_olustur("okul_muduru"))
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_okul_muduru_okul_yonetiminde(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.get(reverse("okul:yonetim_index"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["yan_menu"], "includes/yonetim_menu.html")
        self.assertEqual(resp.context["yonetim_menu"]["aktif_sayfa"], "okul:yonetim_index")
        self.assertContains(resp, reverse("kurul:index"))
        for kapali in ("yonetim_paneli", "okul_ayarlari", "yedekleme:yedek_listesi", "personel_listesi",
                       "veriaktar_ana"):
            self.assertNotContains(resp, f'href="{reverse(kapali)}"')
        self.assertContains(resp, "Görüntüle")

        # Branş Bazlı Ders Yükü: kart görünür, rapor salt okunur açılır
        rapor = f'{reverse("secmeli_ders_yuku")}?yil={self.yil.pk}'
        self.assertContains(resp, "Branş Bazlı Ders Yükü")
        self.assertContains(resp, rapor)
        resp = self.client.get(rapor)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["duzenleyebilir"])
        self.assertEqual(resp.context["yan_menu"], "includes/yonetim_menu.html")
        self.assertEqual(resp.context["yonetim_menu"]["aktif_sayfa"], "okul:yonetim_index")
        self.assertNotContains(resp, reverse("secmeli_norm_kadro_arsivle"))
        self.assertNotContains(resp, reverse("secmeli_alan_sube_atama"))
        self.assertEqual(self.client.post(reverse("secmeli_norm_kadro_arsivle"), {"yil": self.yil.pk}).status_code, 403)
        self.assertEqual(self.client.get(reverse("secmeli_alan_sube_atama")).status_code, 403)

        # Salt okunur: liste açılır, ekleme/düzenleme/silme kapalı
        kayit = SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=9, personel=self.myrd1)
        resp = self.client.get(self.url)
        self.assertContains(resp, self.myrd1.adi_soyadi)
        self.assertNotContains(resp, reverse("okul:yonetim_create", args=["seviye-sorumlusu"]))
        self.assertNotContains(resp, reverse("okul:yonetim_update", args=["seviye-sorumlusu", kayit.pk]))
        for url in (reverse("okul:yonetim_create", args=["seviye-sorumlusu"]),
                    reverse("okul:yonetim_update", args=["seviye-sorumlusu", kayit.pk]),
                    reverse("okul:yonetim_delete", args=["seviye-sorumlusu", kayit.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
                self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.assertTrue(SinifSeviyesiSorumlusu.objects.filter(pk=kayit.pk).exists())
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, reverse("okul:yonetim_index"))
        self.assertContains(resp, reverse("kurul:index"))
