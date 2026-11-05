"""Sınıf rehber öğretmeni tablosu: servis ve yönetim ekranı testleri."""

from django.test import TestCase
from django.urls import reverse

from ogrenci.services import rehberlik as rh
from okul.models import EgitimOgretimYili, SinifRehberOgretmeni, SinifSubeYil
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_olustur,
    ders_programi_olustur,
    kullanici_olustur,
    personel_olustur,
    sinif_rehberi_ata,
    sinif_sube_olustur,
)


class RehberTemel(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.s9a = sinif_sube_olustur(9, "A")
        self.s9b = sinif_sube_olustur(9, "B")
        self.s9c = sinif_sube_olustur(9, "C")
        self.ali = personel_olustur(adi_soyadi="Ali Örnek")
        self.ayse = personel_olustur(adi_soyadi="Ayşe Örnek")
        # Ders adı iki farklı yazımla: ikisi de öneri olarak görülmeli
        self.rehberlik = ders_olustur("REHBERLİK VE YÖNLENDİRME")
        ders_programi_olustur(self.ali, 3, sinif_sube=self.s9a, ders=self.rehberlik, gun="Tuesday")
        ders_programi_olustur(self.ayse, 5, sinif_sube=self.s9b, ders=self.rehberlik)


class OneriTestCase(RehberTemel):
    def test_oneriler_sinifa_gore_gun_ve_saatle_gelir(self):
        oneriler = rh.ders_programi_onerileri()
        self.assertEqual(oneriler[self.s9a.pk][0]["personel"], self.ali)
        self.assertEqual(oneriler[self.s9a.pk][0]["saatler"], ["Salı 3. ders"])
        self.assertEqual(oneriler[self.s9b.pk][0]["personel"], self.ayse)
        self.assertNotIn(self.s9c.pk, oneriler)

    def test_noktasiz_i_ile_yazilmis_ders_de_oneri_olur(self):
        s10 = sinif_sube_olustur(10, "A")
        ders_programi_olustur(self.ali, 1, sinif_sube=s10, ders=ders_olustur("Rehberlik ve Yönlendirme"))
        self.assertEqual(rh.ders_programi_onerileri()[s10.pk][0]["personel"], self.ali)

    def test_tablo_durumlari(self):
        sinif_rehberi_ata(self.ali, self.s9a)         # öneriyle aynı
        sinif_rehberi_ata(self.ali, self.s9b)         # öneri Ayşe → farklı
        s10 = sinif_sube_olustur(10, "A")
        sinif_rehberi_ata(self.ayse, s10)             # önerisi yok → elle
        durumlar = {s["sinif_sube"]: s["durum"] for s in rh.rehber_tablosu(self.yil)}
        self.assertEqual(durumlar, {
            self.s9a: rh.UYUMLU,
            self.s9b: rh.FARKLI,
            self.s9c: rh.ONERI_YOK,
            s10: rh.ELLE,
        })

    def test_kapali_sinif_kaydi_yoksa_listelenmez(self):
        SinifSubeYil.objects.create(sinif_sube=self.s9c, egitim_yili=self.yil, acik=False)
        siniflar = [s["sinif_sube"] for s in rh.rehber_tablosu(self.yil)]
        self.assertNotIn(self.s9c, siniflar)


class YonetimServisTestCase(RehberTemel):
    def test_toplu_kabul_yalnizca_bos_ve_tek_onerili_siniflara_uygulanir(self):
        sinif_rehberi_ata(self.ali, self.s9b)  # mevcut kayıt korunmalı
        # 9/C'ye iki öğretmen öneriliyor → atlanmalı
        ders_programi_olustur(self.ali, 1, sinif_sube=self.s9c, ders=self.rehberlik)
        ders_programi_olustur(self.ayse, 2, sinif_sube=self.s9c, ders=self.rehberlik)
        kullanici = kullanici_olustur("mudur_yardimcisi")

        self.assertEqual(rh.onerileri_toplu_kabul_et(self.yil, kullanici), 1)
        kayitlar = dict(SinifRehberOgretmeni.objects.values_list("sinif_sube", "personel"))
        self.assertEqual(kayitlar, {self.s9a.pk: self.ali.pk, self.s9b.pk: self.ali.pk})
        self.assertEqual(
            SinifRehberOgretmeni.objects.get(sinif_sube=self.s9a).guncelleyen, kullanici
        )

    def test_ata_degistirir_kaldir_siler(self):
        rh.rehber_ata(self.s9a, self.ali, self.yil, None)
        rh.rehber_ata(self.s9a, self.ayse, self.yil, None)
        self.assertEqual(SinifRehberOgretmeni.objects.get().personel, self.ayse)
        self.assertEqual(rh.rehber_kaldir(self.s9a, self.yil), 1)
        self.assertFalse(SinifRehberOgretmeni.objects.exists())

    def test_okuma_aktif_yila_baglidir(self):
        eski = EgitimOgretimYili.objects.create(
            egitim_yili="2024-2025",
            egitim_baslangic=self.yil.egitim_baslangic.replace(year=2024),
            egitim_bitis=self.yil.egitim_bitis.replace(year=2025),
        )
        kullanici = kullanici_olustur("ogretmen")
        self.ali.user = kullanici
        self.ali.save()
        sinif_rehberi_ata(self.ali, self.s9a, egitim_yili=eski)
        self.assertIsNone(rh.rehberlik_sinif_sube(kullanici))
        self.assertIsNone(rh.sinif_rehber_ogretmeni(self.s9a))

        sinif_rehberi_ata(self.ali, self.s9b)
        self.assertEqual(rh.rehberlik_sinif_sube(kullanici), self.s9b)
        self.assertEqual(rh.sinif_rehber_ogretmeni(self.s9b), self.ali)

    def test_atanmamis_sinif_sayisi(self):
        self.assertEqual(rh.atanmamis_sinif_sayisi(self.yil), 3)
        sinif_rehberi_ata(self.ali, self.s9a)
        self.assertEqual(rh.atanmamis_sinif_sayisi(self.yil), 2)
        self.assertEqual(rh.atanmamis_sinif_sayisi(None), 0)


class YonetimEkraniTestCase(RehberTemel):
    url = reverse("rehber_ogretmenler")

    def test_ogretmen_sayfayi_goremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_rehber_ogretmen_grubu_gorur_ama_degistiremez(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["duzenleyebilir"])
        self.assertNotContains(r, "Öneriyi kabul et")
        r = self.client.post(self.url, {"islem": "toplu_kabul"})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(SinifRehberOgretmeni.objects.exists())

    def test_mudur_yardimcisi_oneriyi_kabul_eder_degistirir_kaldirir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        r = self.client.get(self.url)
        self.assertTrue(r.context["duzenleyebilir"])
        self.assertEqual(r.context["toplu_kabul_sayisi"], 2)

        self.client.post(self.url, {"islem": "toplu_kabul"})
        self.assertEqual(SinifRehberOgretmeni.objects.count(), 2)

        self.client.post(self.url, {"islem": "ata", "sinif_sube": self.s9c.pk, "personel": self.ali.pk})
        self.assertEqual(SinifRehberOgretmeni.objects.get(sinif_sube=self.s9c).personel, self.ali)

        self.client.post(self.url, {"islem": "ata", "sinif_sube": self.s9a.pk, "personel": self.ayse.pk})
        self.assertEqual(SinifRehberOgretmeni.objects.get(sinif_sube=self.s9a).personel, self.ayse)

        self.client.post(self.url, {"islem": "kaldir", "sinif_sube": self.s9b.pk})
        self.assertFalse(SinifRehberOgretmeni.objects.filter(sinif_sube=self.s9b).exists())

    def test_ayrilmis_personel_atanamaz(self):
        self.ali.durum = "Ayrıldı-Tayin"
        self.ali.save()
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        r = self.client.post(self.url, {"islem": "ata", "sinif_sube": self.s9a.pk, "personel": self.ali.pk})
        self.assertEqual(r.status_code, 404)

    def test_ana_sayfada_atanmamis_uyarisi(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.assertContains(self.client.get(reverse("index")), "rehber öğretmeni kaydedilmemiş")
        for ss, p in ((self.s9a, self.ali), (self.s9b, self.ayse), (self.s9c, self.ali)):
            sinif_rehberi_ata(p, ss)
        self.assertNotContains(self.client.get(reverse("index")), "rehber öğretmeni kaydedilmemiş")
