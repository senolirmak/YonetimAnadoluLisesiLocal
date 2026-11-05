"""Sınıf oturma planı: servis ve view testleri."""

from django.test import TestCase
from django.urls import reverse

from ogrenci.models import SinifOturmaDuzeni
from ogrenci.services import oturma_duzeni as od
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_olustur,
    ders_programi_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_sube_olustur,
)


class OturmaDuzeniTemel(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.sinif = sinif_sube_olustur(9, "A")
        self.diger_sinif = sinif_sube_olustur(9, "B")
        self.ogr1 = ogrenci_olustur(9, "A")
        self.ogr2 = ogrenci_olustur(9, "A")
        self.yabanci = ogrenci_olustur(9, "B")

        self.rehber = kullanici_olustur("ogretmen")
        personel = personel_olustur(user=self.rehber)
        ders_programi_olustur(
            personel, 1, sinif_sube=self.sinif,
            ders=ders_olustur("Rehberlik ve Yönlendirme"),
        )
        self.ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=self.ogretmen)


class ServisTestCase(OturmaDuzeniTemel):
    def test_rehber_yalnizca_kendi_sinifini_duzenler(self):
        self.assertEqual(od.rehber_sinifi(self.rehber), self.sinif)
        self.assertTrue(od.duzenleyebilir_mi(self.rehber, self.sinif))
        self.assertFalse(od.duzenleyebilir_mi(self.rehber, self.diger_sinif))
        self.assertFalse(od.duzenleyebilir_mi(self.ogretmen, self.sinif))
        self.assertTrue(od.duzenleyebilir_mi(kullanici_olustur(superuser=True), self.diger_sinif))

    def test_kaydet_onceki_duzeni_degistirir(self):
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk})
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(2, 3): self.ogr2.pk})
        kayitlar = list(SinifOturmaDuzeni.objects.values_list("ogrenci_id", "sira_no", "kolon_no"))
        self.assertEqual(kayitlar, [(self.ogr2.pk, 2, 3)])

    def test_baska_sinifin_ogrencisi_reddedilir(self):
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk})
        with self.assertRaises(ValueError):
            od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 2): self.yabanci.pk})
        # Hata durumunda mevcut düzen korunur
        self.assertEqual(SinifOturmaDuzeni.objects.get().ogrenci, self.ogr1)

    def test_ayni_ogrenci_iki_koltuga_konamaz(self):
        with self.assertRaises(ValueError):
            od.oturma_duzeni_kaydet(
                self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk, (1, 2): self.ogr1.pk}
            )

    def test_pasif_ogrenci_yerlestirilemez(self):
        self.ogr2.aktif = False
        self.ogr2.save()
        with self.assertRaises(ValueError):
            od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr2.pk})

    def test_gecersiz_koltuk_verisi(self):
        with self.assertRaises(ValueError):
            od.koltuklari_oku({"koltuk_1_1": "abc"})
        self.assertEqual(od.koltuklari_oku({"koltuk_1_1": "5", "koltuk_9_9": "7"}), {(1, 1): 5})

    def test_grid_ve_secim_listesi(self):
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(2, 4): self.ogr1.pk})
        grid, yerlesmis = od.oturma_grid(self.sinif, self.yil)
        self.assertEqual(yerlesmis, {self.ogr1.pk})
        # 2. sıra, 2. grup, 2. koltuk = kolon 4
        self.assertEqual(grid[1][1][1]["ogr"], self.ogr1)
        plan_durumu = {s["sinif_sube"]: s["plan_var"] for s in od.secilebilir_siniflar(self.yil)}
        self.assertEqual(plan_durumu, {self.sinif: True, self.diger_sinif: False})


class ViewTestCase(OturmaDuzeniTemel):
    url = reverse("sinif_oturma_plani")

    def test_giris_gerekir(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_rehber_varsayilan_olarak_kendi_sinifini_duzenler(self):
        self.client.force_login(self.rehber)
        r = self.client.get(self.url)
        self.assertEqual(r.context["sinif_sube"], self.sinif)
        self.assertTrue(r.context["duzenleyebilir"])

    def test_rehber_sinif_secim_ekranini_acabilir(self):
        self.client.force_login(self.rehber)
        r = self.client.get(self.url + "?sec=1")
        self.assertTrue(r.context["sinif_sec"])

    def test_diger_ogretmen_sinif_secer_ve_salt_okunur_gorur(self):
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk})
        self.client.force_login(self.ogretmen)
        r = self.client.get(self.url)
        self.assertTrue(r.context["sinif_sec"])

        r = self.client.get(self.url, {"sinif_sube": self.sinif.pk})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["duzenleyebilir"])
        self.assertContains(r, self.ogr1.adi)
        self.assertNotContains(r, "Oturma Düzenini Kaydet")

    def test_rehber_baska_sinifi_salt_okunur_gorur(self):
        self.client.force_login(self.rehber)
        r = self.client.get(self.url, {"sinif_sube": self.diger_sinif.pk})
        self.assertFalse(r.context["duzenleyebilir"])

    def test_yetkisiz_kayit_reddedilir(self):
        self.client.force_login(self.ogretmen)
        r = self.client.post(self.url, {"sinif_sube": self.sinif.pk, "koltuk_1_1": self.ogr1.pk})
        self.assertEqual(r.status_code, 403)
        self.client.force_login(self.rehber)
        r = self.client.post(self.url, {"sinif_sube": self.diger_sinif.pk, "koltuk_1_1": self.yabanci.pk})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(SinifOturmaDuzeni.objects.exists())

    def test_rehber_kaydeder(self):
        self.client.force_login(self.rehber)
        r = self.client.post(self.url, {"sinif_sube": self.sinif.pk, "koltuk_3_5": self.ogr2.pk})
        self.assertRedirects(r, f"{self.url}?sinif_sube={self.sinif.pk}")
        d = SinifOturmaDuzeni.objects.get()
        self.assertEqual((d.ogrenci, d.sira_no, d.kolon_no, d.guncelleyen), (self.ogr2, 3, 5, self.rehber))

    def test_gecersiz_kayit_hata_mesaji_verir(self):
        self.client.force_login(self.rehber)
        r = self.client.post(
            self.url, {"sinif_sube": self.sinif.pk, "koltuk_1_1": self.yabanci.pk}, follow=True
        )
        self.assertContains(r, "Bu sınıfa ait olmayan")
        self.assertFalse(SinifOturmaDuzeni.objects.exists())

    def test_ana_sayfada_buton_herkese_gorunur(self):
        self.client.force_login(self.ogretmen)
        self.assertContains(self.client.get(reverse("index")), "Sınıf Oturma Planları")


class PdfTestCase(OturmaDuzeniTemel):
    url = reverse("sinif_oturma_plani_pdf")

    def _metin(self, resp):
        import io

        from pypdf import PdfReader

        okuyucu = PdfReader(io.BytesIO(resp.content))
        self.assertEqual(len(okuyucu.pages), 1)
        sayfa = okuyucu.pages[0]
        # Dikey A4: yükseklik genişlikten büyük
        self.assertGreater(float(sayfa.mediabox.height), float(sayfa.mediabox.width))
        return sayfa.extract_text()

    def test_rehber_kendi_sinifinin_pdfini_alir(self):
        self.ogr1.adi, self.ogr1.soyadi = "Ayşe", "Çınar"
        self.ogr1.save()
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk})
        self.client.force_login(self.rehber)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")
        metin = self._metin(r)
        for parca in ("9/A", "2025-2026", "TAHTA", "Ayşe Çınar", "Sınıf Rehber Öğretmeni",
                      "yer almayan", self.ogr2.adi):
            self.assertIn(parca, metin)
        self.assertNotIn(self.yabanci.adi, metin)

    def test_bos_plan_da_tek_sayfa_uretir(self):
        self.client.force_login(self.rehber)
        self._metin(self.client.get(self.url, {"sinif_sube": self.sinif.pk}))

    def test_kalabalik_sinif_tek_sayfaya_sigar(self):
        ogrenciler = [
            ogrenci_olustur(9, "A", adi=f"Uzunisimliöğrenci{i}", soyadi="Çokuzunsoyadıolan")
            for i in range(40)
        ]
        koltuklar = {(s, k): ogrenciler[(s - 1) * 6 + k - 1].pk for s in range(1, 7) for k in range(1, 7)}
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, koltuklar)
        self.client.force_login(self.rehber)
        self._metin(self.client.get(self.url))

    def test_rehber_olmayan_pdf_alamaz(self):
        self.client.force_login(self.ogretmen)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.get(self.url, {"sinif_sube": self.sinif.pk}).status_code, 403)
        self.client.force_login(self.rehber)
        self.assertEqual(self.client.get(self.url, {"sinif_sube": self.diger_sinif.pk}).status_code, 403)

    def test_pdf_butonu_yalnizca_rehbere_gorunur(self):
        od.oturma_duzeni_kaydet(self.sinif, self.yil, self.rehber, {(1, 1): self.ogr1.pk})
        sayfa = reverse("sinif_oturma_plani")
        self.client.force_login(self.rehber)
        self.assertContains(self.client.get(sayfa), "PDF Al")
        self.client.force_login(self.ogretmen)
        self.assertNotContains(self.client.get(sayfa, {"sinif_sube": self.sinif.pk}), "PDF Al")


class GercekDersAdiTestCase(TestCase):
    """Ders adı veritabanında e-Okul/varsayılan veriyle aynı biçimde (noktalı büyük İ)
    kayıtlıyken de rehber öğretmen tanınmalı."""

    def test_buyuk_harfli_ders_adiyla_rehber_tanınır(self):
        aktif_egitim_yili_olustur()
        sinif = sinif_sube_olustur(11, "C")
        rehber = kullanici_olustur("ogretmen")
        ders_programi_olustur(
            personel_olustur(user=rehber), 2, sinif_sube=sinif,
            ders=ders_olustur("REHBERLİK VE YÖNLENDİRME"),
        )
        self.assertEqual(od.rehber_sinifi(rehber), sinif)
        self.assertTrue(od.duzenleyebilir_mi(rehber, sinif))
        self.assertEqual(od.sinif_rehberi(sinif), rehber.personel)
