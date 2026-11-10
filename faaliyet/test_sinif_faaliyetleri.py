"""Sınıf rehber öğretmeni, kendi sınıfının öğrencilerinin katıldığı faaliyetleri görür."""

import datetime

from django.test import TestCase
from django.urls import reverse

from devamsizlik.models import OgrenciDevamsizlik
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_saati_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_rehberi_ata,
    sinif_sube_olustur,
)

from .models import Faaliyet, FaaliyetDersSaati

TARIH = datetime.date(2026, 10, 5)


class SinifFaaliyetleriTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        aktif_egitim_yili_olustur("2025-2026")
        cls.url = reverse("faaliyet:sinif_faaliyetleri")

        cls.rehber = kullanici_olustur("ogretmen")
        sinif_rehberi_ata(personel_olustur(user=cls.rehber), sinif_sube_olustur(10, "A"))
        cls.ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=cls.ogretmen)

        cls.ali = ogrenci_olustur(10, "A", adi="Ali", soyadi="Kaya")
        cls.ayse = ogrenci_olustur(10, "A", adi="Ayşe", soyadi="Demir")
        cls.veli = ogrenci_olustur(10, "A", adi="Veli", soyadi="Katılmayan")
        cls.yabanci = ogrenci_olustur(10, "B", adi="Yabancı", soyadi="Öğrenci")

        sorumlu = personel_olustur(adi_soyadi="Sorumlu Öğretmen")
        cls.ds1 = ders_saati_olustur(1)

        def faaliyet(konu, ogrenciler, **kw):
            f = Faaliyet.objects.create(
                konu=konu, tarih=TARIH, yer="Müze", ogretmen=sorumlu, **kw
            )
            FaaliyetDersSaati.objects.create(
                faaliyet=f, ders_no=1, baslangic=datetime.time(8, 30), bitis=datetime.time(9, 10)
            )
            f.ogrenciler.set(ogrenciler)
            return f

        tamam = {"durum": Faaliyet.DURUM_ONAYLANDI, "devamsizlik_girildi": True}
        faaliyet("Müze gezisi", [cls.ali, cls.ayse, cls.yabanci], **tamam)
        faaliyet("Bilim fuarı", [cls.ali], **tamam)
        faaliyet("Onay bekleyen gezi", [cls.ali, cls.veli])
        # Ayşe tiyatroya kaydedilmiş ama devamsız sayılmış → rapora girmez
        faaliyet("Tiyatro", [cls.ayse], **tamam)
        OgrenciDevamsizlik.objects.create(
            ogrenci=cls.ayse, tarih=TARIH, ders_saati=cls.ds1,
            ders_adi="Faaliyet: Tiyatro", ogretmen_adi="x", aciklama="Faaliyet: Tiyatro",
        )

    def test_rehber_sinifinin_faaliyetlerini_gorur(self):
        self.client.force_login(self.rehber)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)

        katilim = {g["ogr"].pk: [s["faaliyet"].konu for s in g["faaliyetler"]]
                   for g in resp.context["ogrenciler"]}
        self.assertEqual(katilim, {
            self.ali.pk: ["Müze gezisi", "Bilim fuarı"],
            self.ayse.pk: ["Müze gezisi"],
        })
        self.assertEqual([o.pk for o in resp.context["katilmayanlar"]], [self.veli.pk])
        self.assertContains(resp, "Sorumlu Öğretmen")
        self.assertNotContains(resp, "Yabancı")
        self.assertNotContains(resp, "Onay bekleyen gezi")
        self.assertNotContains(resp, "Tiyatro")
        # Salt okunur: e-Okul işaretleme kutusu yok
        self.assertNotContains(resp, "eokul-kutu")

    def test_arama_ve_tarih_filtresi(self):
        self.client.force_login(self.rehber)
        resp = self.client.get(self.url, {"ara": "Ayşe"})
        self.assertEqual([g["ogr"].pk for g in resp.context["ogrenciler"]], [self.ayse.pk])
        self.assertEqual(resp.context["katilmayanlar"], [])

        resp = self.client.get(self.url, {"tarih_bas": "2026-10-06"})
        self.assertEqual(resp.context["ogrenciler"], [])

    def test_rehberligi_olmayan_yonlendirilir(self):
        for kullanici in (self.ogretmen, kullanici_olustur("mudur_yardimcisi")):
            with self.subTest(kullanici=kullanici.username):
                self.client.force_login(kullanici)
                resp = self.client.get(self.url)
                self.assertRedirects(resp, reverse("ogrenci_islemleri"))

    def test_menu_baglantisi_yalnizca_rehbere_gorunur(self):
        sayfa = reverse("ogrenci_islemleri")
        self.client.force_login(self.rehber)
        resp = self.client.get(sayfa)
        self.assertContains(resp, "Sınıfımın Faaliyetleri")
        self.assertContains(resp, f'href="{self.url}"')

        for kullanici in (self.ogretmen, kullanici_olustur("mudur_yardimcisi")):
            with self.subTest(kullanici=kullanici.username):
                self.client.force_login(kullanici)
                self.assertNotContains(self.client.get(sayfa), f'href="{self.url}"')

    def test_sayfa_ogrenci_menusunde_acilir(self):
        self.client.force_login(self.rehber)
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["yan_menu"], "includes/ogrenci_menu.html")
        self.assertEqual(resp.context["ogrenci_menu"]["aktif_sayfa"], "faaliyet:sinif_faaliyetleri")
