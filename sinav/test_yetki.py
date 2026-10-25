"""sinav yönetim view'larının yetki testleri.

Bu view'lar önceden yalnızca @require_POST ya da @login_required taşıyordu; giriş yapmamış biri
bile öğrenci silebiliyordu. Artık hepsi @ust_yonetici_required (müdür yardımcısı / okul müdürü).
"""

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from okul.testing import kullanici_olustur, ogrenci_olustur

# (url adı, argümanlar)
YONETIM_URLLERI = [
    ("sinav:index", []), ("sinav:veri_yukle_sayfasi", []), ("sinav:veri_yukle", []),
    ("sinav:veri_yukle_onayla", []), ("sinav:parametre_kaydet", []),
    ("sinav:temel_veriler", []), ("sinav:veri_aktar", []), ("sinav:subeders", []),
    ("sinav:takvim", []), ("sinav:oturma", []), ("sinav:oturma_secili", []),
    ("sinav:oturma_plani_pdf_view", []), ("sinav:oturma_plani_toplu_pdf_view", []),
    ("sinav:sinif_listesi_toplu_pdf_view", []), ("sinav:oturum_bazli_toplu_pdf_view", []),
    ("sinav:sinav_takvimi_pdf_view", []), ("sinav:sinav_takvimi_subesiz_pdf_view", []),
    ("sinav:gorev_durumu", ["x"]), ("sinav:gorev_iptal", ["x"]),
    ("sinav:okul_bilgileri_kaydet", []), ("sinav:sinav_bilgisi_listesi", []),
    ("sinav:sinav_bilgisi_duzenle", [1]), ("sinav:sinav_bilgisi_aktif_yap", [1]),
    ("sinav:sinav_bilgisi_sil", [1]), ("sinav:takvim_uretim_aktif_yap", [1]),
    ("sinav:gozetmen_ozet", []), ("sinav:ogrenci_yonetim", []), ("sinav:ogrenci_ekle", []),
    ("sinav:sinav_ogrenci_senkronize_et", []),
    ("sinav:ders_ayarlari", []), ("sinav:ders_ayarlari_kaydet", []),
    ("sinav:ders_ayarlari_varsayilan", []), ("sinav:sabit_sinav_ekle", []),
    ("sinav:sabit_sinav_sil", [0]), ("sinav:catisma_grubu_ekle", []),
    ("sinav:catisma_grubu_sil", [0]), ("sinav:catisma_grubu_varsayilan", []),
    ("sinav:esleme_ekle", []), ("sinav:esleme_sil", [0]),
    ("sinav:takvim_sayfasi", []), ("sinav:takvim_gecmisi", []), ("sinav:pdf_rapor", []),
    ("sinav:takvim_uretim_sil", [1]), ("sinav:takvim_uretim_kullan", [1]),
    ("sinav:takvim_uretim_aciklama_guncelle", [1]), ("sinav:takvim_onizleme", []),
    ("sinav:takvim_onayla", []), ("sinav:takvim_onizleme_iptal", []),
    ("sinav:takvim_guncelle", []), ("sinav:takvim_onizleme_guncelle", []),
    ("sinav:takvim_ders_duzenle", []), ("sinav:sinav_yoklama_raporu", []),
    ("sinav:sinav_yoklama_yok_detay", []), ("sinav:mazeret_yoklama_simule", []),
]

# Müdür yardımcısının boş veritabanında sorunsuz açabilmesi gereken sayfalar.
ACILMALI = ["sinav:index", "sinav:ders_ayarlari", "sinav:sinav_bilgisi_listesi",
            "sinav:takvim_sayfasi", "sinav:takvim_gecmisi", "sinav:ogrenci_yonetim", "sinav:gozetmen_ozet"]


class SinavYonetimYetkiTestCase(TestCase):
    def test_anonim_login_sayfasina_yonlenir(self):
        for ad, args in YONETIM_URLLERI:
            with self.subTest(ad=ad):
                resp = self.client.post(reverse(ad, args=args))
                self.assertEqual(resp.status_code, 302)
                self.assertTrue(resp["Location"].startswith(settings.LOGIN_URL), resp["Location"])

    def test_ogretmen_rehber_ve_disiplin_403_alir(self):
        for grup in ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"):
            self.client.force_login(kullanici_olustur(grup))
            for ad, args in YONETIM_URLLERI:
                with self.subTest(grup=grup, ad=ad):
                    self.assertEqual(self.client.post(reverse(ad, args=args)).status_code, 403)

    def test_anonim_ve_ogretmen_ogrenci_silemez(self):
        ogr = ogrenci_olustur()
        url = reverse("sinav:ogrenci_sil", args=[ogr.pk])

        self.client.post(url)
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.client.post(url)

        self.assertTrue(type(ogr).objects.filter(pk=ogr.pk).exists())

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.client.post(url)
        self.assertFalse(type(ogr).objects.filter(pk=ogr.pk).exists())

    def test_ust_yonetici_sayfalari_acar(self):
        for grup in ("mudur_yardimcisi", "okul_muduru"):
            self.client.force_login(kullanici_olustur(grup))
            for ad in ACILMALI:
                with self.subTest(grup=grup, ad=ad):
                    self.assertEqual(self.client.get(reverse(ad)).status_code, 200)
