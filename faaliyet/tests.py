from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from devamsizlik.models import OgrenciDevamsizlik
from ogrenci.models import Ogrenci
from okul.models import DersSaatleri, Personel

from .models import Faaliyet, FaaliyetDersSaati
from .services.toplu_rapor import tamamlanan_faaliyetler, tarihe_gore_grupla, toplu_rapor_pdf


class FaaliyetTopluRaporTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("admin", "a@a.com", "x")
        cls.ogretmen_user = User.objects.create_user("ogr", password="x")
        cls.personel = Personel.objects.create(
            user=cls.ogretmen_user, kimlikno="11111111111", adi_soyadi="Ayşe Öğretmen"
        )
        for no in (1, 2):
            DersSaatleri.objects.create(
                derssaati_no=no, derssaati_baslangic=time(8 + no), derssaati_bitis=time(8 + no, 40)
            )
        cls.ogr1, cls.ogr2 = (
            Ogrenci.objects.create(
                okulno=100 + i, sinif=9, sube="A", tckimlikno=f"2222222222{i}",
                adi=f"Ad{i}", soyadi=f"Soyad{i}", dogumtarihi=date(2010, 1, 1), cinsiyet="E",
            )
            for i in (1, 2)
        )
        cls.gun1 = date(2026, 10, 5)
        cls.gun2 = date(2026, 10, 6)

        cls.f1 = cls._faaliyet("Gezi", cls.gun1, tamam=True, devamsiz={(cls.ogr1, 2)})
        cls.f2 = cls._faaliyet("Seminer", cls.gun1, tamam=True)
        cls.f3 = cls._faaliyet("Tiyatro", cls.gun2, tamam=True)
        cls._faaliyet("Bekleyen", cls.gun2, tamam=False)

    @classmethod
    def _faaliyet(cls, konu, tarih, tamam, devamsiz=()):
        f = Faaliyet.objects.create(
            konu=konu, tarih=tarih, yer="Okul", ogretmen=cls.personel,
            durum=Faaliyet.DURUM_ONAYLANDI, devamsizlik_girildi=tamam,
        )
        for no in (1, 2):
            FaaliyetDersSaati.objects.create(
                faaliyet=f, ders_no=no, baslangic=time(8 + no), bitis=time(8 + no, 40)
            )
        f.ogrenciler.set([cls.ogr1, cls.ogr2])
        for ogr, no in devamsiz:
            OgrenciDevamsizlik.objects.create(
                ogrenci=ogr, tarih=tarih, ders_saati=DersSaatleri.objects.get(derssaati_no=no),
                ders_adi=f"Faaliyet: {konu}", ogretmen_adi="x", aciklama=f"Faaliyet: {konu}",
            )
        return f

    def test_yalnizca_tamamlananlar_tarihe_gore_gruplanir(self):
        rapor = tarihe_gore_grupla(tamamlanan_faaliyetler())
        self.assertEqual([g["tarih"] for g in rapor["gunler"]], [self.gun1, self.gun2])
        self.assertEqual(
            [s["faaliyet"].konu for s in rapor["gunler"][0]["faaliyetler"]], ["Gezi", "Seminer"]
        )
        self.assertEqual(rapor["toplam"]["faaliyet"], 3)

    def test_devamsizlik_sayimi(self):
        # Aynı gün aynı öğrenci/ders saatleriyle yapılan "Seminer", "Gezi"nin
        # devamsızlığını almamalı
        rapor = tarihe_gore_grupla(tamamlanan_faaliyetler())
        gezi = rapor["gunler"][0]["faaliyetler"][0]
        self.assertEqual(len(gezi["devamsizlar"]), 1)
        self.assertEqual(gezi["devamsizlar"][0]["ogr"], self.ogr1)
        self.assertEqual(gezi["devamsizlar"][0]["dersler"], [2])
        # Tam katılan öğrenci de katılımcı listesinde yer alır
        self.assertEqual(
            [(k["ogr"], k["dersler"]) for k in gezi["ogrenciler"]],
            [(self.ogr1, [2]), (self.ogr2, [])],
        )
        self.assertEqual(rapor["toplam"]["devamsiz_ogrenci"], 1)
        self.assertEqual(rapor["toplam"]["devamsiz_ders"], 1)

    def test_tarih_filtresi(self):
        rapor = tarihe_gore_grupla(tamamlanan_faaliyetler(tarih_bas="2026-10-06"))
        self.assertEqual([g["tarih"] for g in rapor["gunler"]], [self.gun2])

    def test_view_ve_pdf(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse("faaliyet:faaliyet_toplu_rapor"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Gezi")
        self.assertNotContains(r, "Bekleyen")
        r = self.client.get(reverse("faaliyet:faaliyet_toplu_rapor_pdf"))
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_ogretmen_erisemez(self):
        self.client.force_login(self.ogretmen_user)
        r = self.client.get(reverse("faaliyet:faaliyet_toplu_rapor"))
        self.assertEqual(r.status_code, 302)

    def test_pdf_cok_devamsizli_faaliyet_sayfalara_bolunur(self):
        # Tüm devamsızlar tek hücrede olsaydı satır sayfadan uzun olur → LayoutError
        ogrenciler = [
            Ogrenci.objects.create(
                okulno=1000 + i, sinif=10, sube="B", tckimlikno=f"3{i:010d}",
                adi=f"Ogr{i}", soyadi="Kalabalik", dogumtarihi=date(2010, 1, 1), cinsiyet="K",
            )
            for i in range(120)
        ]
        f = Faaliyet.objects.create(
            konu="Kalabalık", tarih=date(2026, 10, 7), yer="Salon", ogretmen=self.personel,
            durum=Faaliyet.DURUM_ONAYLANDI, devamsizlik_girildi=True,
        )
        FaaliyetDersSaati.objects.create(faaliyet=f, ders_no=1, baslangic=time(9), bitis=time(9, 40))
        f.ogrenciler.set(ogrenciler)
        ds1 = DersSaatleri.objects.get(derssaati_no=1)
        OgrenciDevamsizlik.objects.bulk_create(
            OgrenciDevamsizlik(
                ogrenci=o, tarih=f.tarih, ders_saati=ds1, ders_adi="Faaliyet: Kalabalık",
                ogretmen_adi="x", aciklama="Faaliyet: Kalabalık",
            )
            for o in ogrenciler
        )
        rapor = tarihe_gore_grupla(tamamlanan_faaliyetler(tarih_bas="2026-10-07"))
        self.assertEqual(rapor["toplam"]["devamsiz_ogrenci"], 120)
        self.assertTrue(toplu_rapor_pdf(rapor).startswith(b"%PDF"))
