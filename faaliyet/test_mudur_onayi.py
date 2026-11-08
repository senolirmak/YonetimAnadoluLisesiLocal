"""Okul müdürü faaliyetleri görür, onaylar/reddeder ve raporlara erişir;
düzenleme, silme ve e-Okul işaretleme müdür yardımcısında kalır."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from okul.testing import kullanici_olustur, personel_olustur

from .models import Faaliyet


class OkulMuduruFaaliyetTests(TestCase):
    def setUp(self):
        self.ogretmen = personel_olustur(adi_soyadi="Faaliyet Öğretmeni")
        self.faaliyet = Faaliyet.objects.create(
            konu="Müze gezisi", tarih=timezone.localdate(), yer="Müze", ogretmen=self.ogretmen
        )
        self.mudur = kullanici_olustur("okul_muduru", first_name="Okul", last_name="Müdürü")
        personel_olustur(user=self.mudur, adi_soyadi="Okul Müdürü Kişi")
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")

    def test_mudur_onay_listesini_gorur_ve_onaylar(self):
        self.client.force_login(self.mudur)
        resp = self.client.get(reverse("faaliyet:faaliyet_onay_listesi"))
        self.assertContains(resp, "Müze gezisi")
        self.assertEqual(resp.context["bekleyen_faaliyet_sayisi"], 1)
        self.assertEqual(resp.context["yan_menu"], "includes/ogrenci_menu.html")

        self.client.post(reverse("faaliyet:faaliyet_onayla", args=[self.faaliyet.pk]))
        self.faaliyet.refresh_from_db()
        self.assertEqual(self.faaliyet.durum, Faaliyet.DURUM_ONAYLANDI)
        self.assertEqual(self.faaliyet.onaylayan_adi, "Okul Müdürü Kişi")

    def test_ilk_onay_korunur(self):
        self.client.force_login(self.mudur)
        self.client.post(reverse("faaliyet:faaliyet_onayla", args=[self.faaliyet.pk]))
        self.faaliyet.refresh_from_db()
        ilk_zaman = self.faaliyet.onay_zamani

        self.client.force_login(self.mudur_yrd)
        resp = self.client.post(reverse("faaliyet:faaliyet_onayla", args=[self.faaliyet.pk]), follow=True)
        self.assertContains(resp, "zaten Okul Müdürü Kişi tarafından onaylanmış")
        self.faaliyet.refresh_from_db()
        self.assertEqual((self.faaliyet.onaylayan_adi, self.faaliyet.onay_zamani), ("Okul Müdürü Kişi", ilk_zaman))

    def test_mudur_reddedebilir(self):
        self.client.force_login(self.mudur)
        self.client.post(reverse("faaliyet:faaliyet_reddet", args=[self.faaliyet.pk]), {"ret_aciklamasi": "Uygun değil"})
        self.faaliyet.refresh_from_db()
        self.assertEqual(self.faaliyet.durum, Faaliyet.DURUM_REDDEDILDI)

    def test_mudur_raporlara_erisir(self):
        Faaliyet.objects.filter(pk=self.faaliyet.pk).update(durum=Faaliyet.DURUM_ONAYLANDI, devamsizlik_girildi=True)
        self.client.force_login(self.mudur)
        for ad in ("faaliyet:faaliyet_yonetim_listesi", "faaliyet:faaliyet_toplu_rapor",
                   "faaliyet:faaliyet_ogrenci_rapor"):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.context["yan_menu"], "includes/ogrenci_menu.html")
        for ad in ("faaliyet:faaliyet_detay", "faaliyet:faaliyet_rapor"):
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad, args=[self.faaliyet.pk])).status_code, 200)
        resp = self.client.get(reverse("faaliyet:faaliyet_rapor_pdf", args=[self.faaliyet.pk]))
        self.assertTrue(resp.content.startswith(b"%PDF"))
        resp = self.client.get(reverse("faaliyet:faaliyet_toplu_rapor_pdf"))
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_mudurde_duzenleme_silme_eokul_kapali(self):
        self.client.force_login(self.mudur)
        resp = self.client.get(reverse("faaliyet:faaliyet_yonetim_listesi"))
        self.assertNotContains(resp, reverse("faaliyet:faaliyet_sil", args=[self.faaliyet.pk]))
        self.client.post(reverse("faaliyet:faaliyet_sil", args=[self.faaliyet.pk]))
        self.assertTrue(Faaliyet.objects.filter(pk=self.faaliyet.pk).exists())
        resp = self.client.post(reverse("faaliyet:faaliyet_eokul_isaretle"), {"faaliyet": self.faaliyet.pk, "ogrenci": 1})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(self.client.get(reverse("faaliyet:faaliyet_ogrenci_rapor")).context["eokul_isaretleyebilir"])

    def test_ana_sayfa_ve_menu(self):
        self.client.force_login(self.mudur)
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, "Bekleyen Faaliyet Onayı")
        resp = self.client.get(reverse("ogrenci_islemleri"))
        self.assertContains(resp, reverse("faaliyet:faaliyet_onay_listesi"))

    def test_ogretmen_hala_giremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("faaliyet:faaliyet_onay_listesi"))
        self.assertRedirects(resp, reverse("index"), fetch_redirect_response=False)
        self.client.post(reverse("faaliyet:faaliyet_onayla", args=[self.faaliyet.pk]))
        self.faaliyet.refresh_from_db()
        self.assertEqual(self.faaliyet.durum, Faaliyet.DURUM_BEKLEMEDE)
