"""personeldevamsizlik app testleri — öğretmen devamsızlık kayıtları (CRUD).

Bu kayıtlar nöbet ders doldurmanın girdisidir (bkz. nobet/tests.py).
"""

import datetime

from django.test import TestCase
from django.urls import reverse

from okul.testing import devamsizlik_olustur, kullanici_olustur, nobet_ogretmen_olustur
from personeldevamsizlik.forms import DevamsizlikForm
from personeldevamsizlik.models import Devamsizlik

PAZARTESI = datetime.date(2025, 9, 8)


class DevamsizlikModelTestCase(TestCase):
    def setUp(self):
        self.ogretmen = nobet_ogretmen_olustur()

    def test_bitis_tarihi_sureden_hesaplanir(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI, sure=3)
        self.assertEqual(kayit.bitis_tarihi, datetime.date(2025, 9, 10))
        self.assertEqual(kayit.goreve_baslama_tarihi, datetime.date(2025, 9, 11))

    def test_tek_gunluk_devamsizlik_ayni_gun_biter(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI, sure=1)
        self.assertEqual(kayit.bitis_tarihi, PAZARTESI)

    def test_sure_degisince_bitis_guncellenir(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI, sure=1)
        kayit.sure = 5
        kayit.save()
        self.assertEqual(kayit.bitis_tarihi, datetime.date(2025, 9, 12))


class DevamsizlikFormTestCase(TestCase):
    def setUp(self):
        self.ogretmen = nobet_ogretmen_olustur()

    def _form(self, **veri):
        data = {
            "ogretmen": self.ogretmen.pk,
            "baslangic_tarihi": PAZARTESI.isoformat(),
            "devamsiz_tur": 1,
            "sure": 1,
            "gorevlendirme_yapilsin": "on",
        }
        data.update(veri)
        return DevamsizlikForm(data=data)

    def test_tum_gun_isaretliyse_sekiz_saat_kaydedilir(self):
        form = self._form(tum_gun="on", secilen_saatler=["2"])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().ders_saatleri, "1,2,3,4,5,6,7,8")

    def test_secilen_saatler_kaydedilir(self):
        form = self._form(secilen_saatler=["2", "5"])
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().ders_saatleri, "2,5")

    def test_hicbir_saat_secilmezse_tum_gun_sayilir(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().ders_saatleri, "1,2,3,4,5,6,7,8")

    def test_mevcut_kayitta_saatler_ve_tum_gun_onceden_doldurulur(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI, sure=2, ders_saatleri="3,4")
        form = DevamsizlikForm(instance=kayit)

        self.assertEqual(form.fields["secilen_saatler"].initial, ["3", "4"])
        self.assertFalse(form.fields["tum_gun"].initial)
        self.assertEqual(form.fields["goreve_baslama_tarihi"].initial, "10.09.2025")


class DevamsizlikViewTestCase(TestCase):
    def setUp(self):
        self.ogretmen = nobet_ogretmen_olustur()
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")

    def test_yetkiler(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI)
        urller = [
            reverse("devamsizlik_list"),
            reverse("devamsizlik_create"),
            reverse("devamsizlik_update", args=[kayit.pk]),
            reverse("devamsizlik_delete", args=[kayit.pk]),
        ]
        for url in urller:
            with self.subTest(url=url, kim="anonim"):
                self.assertEqual(self.client.get(url).status_code, 302)

        # Bu ekranlar yalnızca müdür yardımcısına açık (okul müdürü/rehber dahil değil).
        for grup in ("ogretmen", "rehber_ogretmen", "okul_muduru"):
            self.client.force_login(kullanici_olustur(grup))
            for url in urller:
                with self.subTest(url=url, kim=grup):
                    self.assertEqual(self.client.get(url).status_code, 403)

        self.client.force_login(self.mudur_yrd)
        for url in urller:
            with self.subTest(url=url, kim="mudur_yardimcisi"):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_liste_arsivlenmis_kayitlari_gostermez(self):
        aktif = devamsizlik_olustur(self.ogretmen, PAZARTESI)
        devamsizlik_olustur(self.ogretmen, datetime.date(2024, 9, 9), arsivlendi=True)
        self.client.force_login(self.mudur_yrd)

        resp = self.client.get(reverse("devamsizlik_list"))

        self.assertEqual(list(resp.context["devamsizliklar"]), [aktif])

    def test_olustur_duzenle_sil(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.post(
            reverse("devamsizlik_create"),
            {
                "ogretmen": self.ogretmen.pk,
                "baslangic_tarihi": PAZARTESI.isoformat(),
                "devamsiz_tur": 1,
                "sure": 2,
                "secilen_saatler": ["1", "2"],
                "gorevlendirme_yapilsin": "on",
            },
        )
        self.assertRedirects(resp, reverse("devamsizlik_list"))
        kayit = Devamsizlik.objects.get()
        self.assertEqual(kayit.ders_saatleri, "1,2")
        self.assertEqual(kayit.bitis_tarihi, datetime.date(2025, 9, 9))

        self.client.post(
            reverse("devamsizlik_update", args=[kayit.pk]),
            {
                "ogretmen": self.ogretmen.pk,
                "baslangic_tarihi": PAZARTESI.isoformat(),
                "devamsiz_tur": 2,
                "sure": 4,
                "tum_gun": "on",
            },
        )
        kayit.refresh_from_db()
        self.assertEqual(kayit.devamsiz_tur, 2)
        self.assertEqual(kayit.bitis_tarihi, datetime.date(2025, 9, 11))
        self.assertEqual(kayit.ders_saatleri, "1,2,3,4,5,6,7,8")
        self.assertFalse(kayit.gorevlendirme_yapilsin)

        self.client.post(reverse("devamsizlik_delete", args=[kayit.pk]))
        self.assertFalse(Devamsizlik.objects.exists())
