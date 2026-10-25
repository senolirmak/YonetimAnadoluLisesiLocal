"""personel: kayıt akışı (giriş gerektirmeyen uçlar) ve hesap onayı."""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from okul.testing import kullanici_olustur, personel_olustur

SIFRE = "Guclu-Sifre-2025!"


class TcSorgulaTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.personel = personel_olustur(kimlikno="12345678901", adi_soyadi="Gizli Ad Soyad")
        self.url = reverse("tc_sorgula")

    def test_kisisel_veri_dondurmez(self):
        resp = self.client.get(self.url, {"tc": "12345678901"})

        self.assertEqual(resp.json(), {"status": "ok", "suggested_username": "12345678901"})
        self.assertNotContains(resp, "Gizli")

    def test_durumlar(self):
        self.assertEqual(self.client.get(self.url, {"tc": "99999999999"}).json(), {"status": "not_found"})
        self.personel.user = kullanici_olustur()
        self.personel.save()
        self.assertEqual(self.client.get(self.url, {"tc": "12345678901"}).json(), {"status": "has_user"})

    def test_hiz_siniri(self):
        for _ in range(10):
            self.assertEqual(self.client.get(self.url, {"tc": "99999999999"}).status_code, 200)
        self.assertEqual(self.client.get(self.url, {"tc": "12345678901"}).status_code, 429)


class KayitVeOnayTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.personel = personel_olustur(kimlikno="12345678901")

    def _kayit(self):
        return self.client.post(reverse("kayit"), {
            "tckimlikno": "12345678901", "username": "yeni_ogretmen",
            "password1": SIFRE, "password2": SIFRE,
        })

    def test_kayit_pasif_hesap_acar_onaydan_sonra_giris_yapilir(self):
        resp = self._kayit()
        self.assertRedirects(resp, reverse("login"), fetch_redirect_response=False)

        user = User.objects.get(username="yeni_ogretmen")
        self.assertFalse(user.is_active)
        self.assertTrue(user.groups.filter(name="ogretmen").exists())
        self.assertFalse(self.client.login(username="yeni_ogretmen", password=SIFRE))

        onay_url = reverse("ogretmen_kullanici_onayla", args=[self.personel.pk])
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.post(onay_url).status_code, 403)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        liste = self.client.get(reverse("ogretmen_kullanici_listesi"))
        self.assertContains(liste, "Onay Bekliyor")
        self.client.post(onay_url)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.client.logout()
        self.assertTrue(self.client.login(username="yeni_ogretmen", password=SIFRE))

    def test_kayit_hiz_siniri(self):
        for _ in range(10):
            self.client.post(reverse("kayit"), {"tckimlikno": "00000000000"})
        self.assertEqual(self._kayit().status_code, 429)
        self.assertFalse(User.objects.filter(username="yeni_ogretmen").exists())
