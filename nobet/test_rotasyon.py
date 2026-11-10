"""Haftalık nöbet rotasyonu: nöbetçi sayısı 11'den az olan günde GİRİŞ ORTA boş kalır."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from nobet.models import NobetGorevi
from nobet.services.rotasyon import GIRIS_ORTA_ESIGI, gun_rotasyonu
from okul.testing import kullanici_olustur, nobet_gorevi_olustur, nobet_yeri_olustur


class GunRotasyonuTests(SimpleTestCase):
    def test_esik_ve_ustunde_giris_orta_normal_doner(self):
        yerler = [f"YER {i:02d}" for i in range(GIRIS_ORTA_ESIGI - 1)] + ["GİRİŞ ORTA"]
        gorevler = sorted(((f"g{i}", y) for i, y in enumerate(yerler)), key=lambda gy: gy[1])
        yeni, uyari = gun_rotasyonu(gorevler, yerler)
        self.assertIsNone(uyari)
        self.assertIn("GİRİŞ ORTA", yeni.values())
        # Herkes listedeki bir sonraki yere geçer
        self.assertEqual(sorted(yeni.values()), sorted(yerler))
        self.assertTrue(all(yeni[g] != y for g, y in gorevler))

    def test_esigin_altinda_giris_orta_bos_kalir(self):
        aktif = ["BAHÇE", "GİRİŞ ORTA", "KANTİN", "KORİDOR", "ÇAY OCAĞI"]
        gorevler = [("a", "BAHÇE"), ("b", "GİRİŞ ORTA"), ("c", "KANTİN")]
        yeni, uyari = gun_rotasyonu(gorevler, aktif)
        self.assertIsNone(uyari)
        self.assertNotIn("GİRİŞ ORTA", yeni.values())
        # GİRİŞ ORTA'nın yerine boş yerlerden Türkçe alfabede ilki (ÇAY OCAĞI) girer;
        # sıralı küme BAHÇE, ÇAY OCAĞI(b), KANTİN bir adım kayar
        self.assertEqual(yeni, {"a": "ÇAY OCAĞI", "b": "KANTİN", "c": "BAHÇE"})

    def test_ad_buyuk_kucuk_harf_ve_bosluk_farki_yok_sayilir(self):
        yeni, _ = gun_rotasyonu([("a", "BAHÇE"), ("b", "Giriş  Orta ")], ["BAHÇE", "KANTİN"])
        self.assertEqual(sorted(yeni.values()), ["BAHÇE", "KANTİN"])

    def test_bos_yer_yoksa_uyari_verir(self):
        yeni, uyari = gun_rotasyonu([("a", "BAHÇE"), ("b", "GİRİŞ ORTA")], ["BAHÇE", "GİRİŞ ORTA"])
        self.assertIsNotNone(uyari)
        self.assertEqual(yeni, {"a": "GİRİŞ ORTA", "b": "BAHÇE"})

    def test_tek_nobetci_giris_ortadaysa_bos_yere_gecer(self):
        yeni, _ = gun_rotasyonu([("a", "GİRİŞ ORTA")], ["GİRİŞ ORTA", "KANTİN"])
        self.assertEqual(yeni, {"a": "KANTİN"})


class RotasyonEkraniTests(TestCase):
    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.bahce = nobet_yeri_olustur("BAHÇE")
        self.giris = nobet_yeri_olustur("GİRİŞ ORTA")
        self.kantin = nobet_yeri_olustur("KANTİN")
        self.koridor = nobet_yeri_olustur("KORİDOR")  # Pazartesi kimse tutmuyor
        self.g1 = nobet_gorevi_olustur(nobet_yeri=self.bahce)
        self.g2 = nobet_gorevi_olustur(nobet_yeri=self.giris)
        self.g3 = nobet_gorevi_olustur(nobet_yeri=self.kantin)

    def test_kaydedilen_rotasyonda_giris_orta_bos(self):
        resp = self.client.post(reverse("nobet_dagitim"), {"rotasyon_onizle": "1"})
        # Önizleme tablosunda KORİDOR satırı görünür
        self.assertIn("KORİDOR", [s["yer"] for s in resp.context["tablo_satirlari"]])

        self.client.post(reverse("nobet_dagitim"), {"rotasyon_kaydet": "1"})
        yerler = dict(NobetGorevi.objects.values_list("pk", "nobet_yeri__ad"))
        # g2 GİRİŞ ORTA yerine boş KORİDOR'u tutuyormuş gibi sayılır; sıra
        # BAHÇE(g1) → KANTİN(g3) → KORİDOR(g2) bir adım kayar
        self.assertEqual(
            yerler, {self.g1.pk: "KANTİN", self.g3.pk: "KORİDOR", self.g2.pk: "BAHÇE"}
        )
        self.assertNotIn("GİRİŞ ORTA", yerler.values())


class GirisOrtaDuzeltmesiTests(TestCase):
    """Mevcut çizelgede 11'den az nöbetçili günde GİRİŞ ORTA nöbetçisi boş yere taşınır."""

    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.url = reverse("nobet_dagitim")
        self.giris = nobet_yeri_olustur("GİRİŞ ORTA")
        self.bahce = nobet_yeri_olustur("BAHÇE")
        self.kantin = nobet_yeri_olustur("KANTİN")  # Pazartesi kimse tutmuyor
        # Pazartesi: 2 nöbetçi (eşiğin altında)
        self.pzt_giris = nobet_gorevi_olustur(nobet_yeri=self.giris)
        self.pzt_bahce = nobet_gorevi_olustur(nobet_yeri=self.bahce)
        # Salı: 11 nöbetçi (eşikte) — GİRİŞ ORTA dolu kalmalı
        self.sali_giris = nobet_gorevi_olustur(nobet_yeri=self.giris, nobet_gun="Tuesday")
        for _ in range(GIRIS_ORTA_ESIGI - 1):
            nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur(), nobet_gun="Tuesday")

    def _yerler(self):
        return dict(NobetGorevi.objects.values_list("pk", "nobet_yeri__ad"))

    def test_onizle_sonra_kaydet(self):
        once = self._yerler()
        resp = self.client.post(self.url, {"giris_orta_onizle": "1"}, follow=True)
        self.assertEqual(self._yerler(), once)  # önizleme hiçbir şeyi değiştirmez
        self.assertEqual(self.client.session["rotation_preview"], {str(self.pzt_giris.pk): "KANTİN"})
        self.assertContains(resp, "GİRİŞ ORTA düzeltmesi önizleme modundasınız")
        self.assertContains(resp, "Pazartesi: GİRİŞ ORTA → KANTİN")

        resp = self.client.post(self.url, {"rotasyon_kaydet": "1"})
        self.assertContains(resp, "GİRİŞ ORTA düzeltmesi kaydedildi")
        sonra = self._yerler()
        self.assertEqual(sonra[self.pzt_giris.pk], "KANTİN")
        self.assertEqual(sonra[self.sali_giris.pk], "GİRİŞ ORTA")
        degisen = {pk for pk in once if once[pk] != sonra[pk]}
        self.assertEqual(degisen, {self.pzt_giris.pk})
        self.assertNotIn("onizleme_turu", self.client.session)

    def test_duzeltme_gerekmiyorsa_bilgi_verir(self):
        NobetGorevi.objects.filter(pk=self.pzt_giris.pk).update(nobet_yeri=self.kantin)
        resp = self.client.post(self.url, {"giris_orta_onizle": "1"})
        self.assertContains(resp, "Düzeltme gerekmiyor")
        self.assertNotIn("rotation_preview", self.client.session)

    def test_iptal_cizelgeyi_degistirmez(self):
        once = self._yerler()
        self.client.post(self.url, {"giris_orta_onizle": "1"})
        self.client.post(self.url, {"rotasyon_iptal": "1"})
        self.assertEqual(self._yerler(), once)
        self.assertNotIn("onizleme_turu", self.client.session)

    def test_ogretmen_duzeltme_yapamaz(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.post(self.url, {"giris_orta_onizle": "1"}).status_code, 403)
