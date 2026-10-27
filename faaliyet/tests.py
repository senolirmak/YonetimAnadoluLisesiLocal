from datetime import date, time

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from devamsizlik.models import OgrenciDevamsizlik
from ogrenci.models import Ogrenci
from okul.models import DersSaatleri, Personel

from .models import Faaliyet, FaaliyetDersSaati, FaaliyetEokulKaydi
from .services.eokul import EokulIsaretHatasi, eokul_isaretle
from .services.toplu_rapor import (
    ogrenci_rapor_pdf,
    ogrenciye_gore_grupla,
    tamamlanan_faaliyetler,
    tarihe_gore_grupla,
    toplu_rapor_pdf,
)


class FaaliyetVerisiMixin:
    """İki öğrenci, üç tamamlanmış ve bir devamsızlığı girilmemiş faaliyet."""

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


class FaaliyetTopluRaporTestCase(FaaliyetVerisiMixin, TestCase):
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


class FaaliyetOgrenciRaporTestCase(FaaliyetVerisiMixin, TestCase):
    def test_ogrenciye_gore_tarih_sirali_devamsizlar_haric(self):
        rapor = ogrenciye_gore_grupla(tamamlanan_faaliyetler())
        self.assertEqual([g["ogr"] for g in rapor["ogrenciler"]], [self.ogr1, self.ogr2])
        konular = [[s["faaliyet"].konu for s in g["faaliyetler"]] for g in rapor["ogrenciler"]]
        # ogr1 "Gezi"nin 2. dersinde devamsız → o faaliyet ogr1'in listesine girmez
        self.assertEqual(konular, [["Seminer", "Tiyatro"], ["Gezi", "Seminer", "Tiyatro"]])
        self.assertEqual(rapor["toplam"], {"ogrenci": 2, "katilim": 5, "eokul": 0})

    def test_hic_katilimi_olmayan_ogrenci_listelenmez(self):
        # Yalnızca "Gezi" raporlanırsa ogr1'in (devamsız) hiç katılımı kalmaz
        rapor = ogrenciye_gore_grupla(tamamlanan_faaliyetler().filter(pk=self.f1.pk))
        self.assertEqual([g["ogr"] for g in rapor["ogrenciler"]], [self.ogr2])

    def test_sinif_ve_arama_filtresi(self):
        faaliyetler = tamamlanan_faaliyetler()
        self.assertEqual(ogrenciye_gore_grupla(faaliyetler, sinif="10")["ogrenciler"], [])
        self.assertEqual(
            len(ogrenciye_gore_grupla(faaliyetler, sinif="9", sube="a")["ogrenciler"]), 2
        )
        for ara in ("102", "ad2 soyad2"):
            rapor = ogrenciye_gore_grupla(faaliyetler, ara=ara)
            self.assertEqual([g["ogr"] for g in rapor["ogrenciler"]], [self.ogr2])

    def test_ogrenci_rapor_view_ve_pdf(self):
        self.client.force_login(self.admin)
        url = reverse("faaliyet:faaliyet_ogrenci_rapor")
        r = self.client.get(url, {"sinif": "9/A", "ara": "101"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ad1 Soyad1")
        self.assertNotContains(r, "Ad2 Soyad2")
        self.assertNotContains(r, "Bekleyen")
        self.assertNotContains(r, "Gezi")
        self.assertNotContains(r, "Devamsız:")
        r = self.client.get(
            reverse("faaliyet:faaliyet_ogrenci_rapor_pdf"), {"sinif": "9/A", "ara": "<b>"}
        )
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))

    def test_ogrenci_rapor_ogretmen_erisemez(self):
        self.client.force_login(self.ogretmen_user)
        r = self.client.get(reverse("faaliyet:faaliyet_ogrenci_rapor"))
        self.assertEqual(r.status_code, 302)

    def test_ogrenci_rapor_pdf_cok_faaliyet(self):
        rapor = ogrenciye_gore_grupla(tamamlanan_faaliyetler())
        self.assertTrue(ogrenci_rapor_pdf(rapor).startswith(b"%PDF"))


class FaaliyetEokulTestCase(FaaliyetVerisiMixin, TestCase):
    def _konular(self, **kw):
        rapor = ogrenciye_gore_grupla(tamamlanan_faaliyetler(), **kw)
        return {
            g["ogr"].okulno: [s["faaliyet"].konu for s in g["faaliyetler"]]
            for g in rapor["ogrenciler"]
        }

    def test_isaretle_ve_kaldir(self):
        eokul_isaretle(self.f2.pk, self.ogr1.pk, True, isleyen_adi="MY")
        eokul_isaretle(self.f2.pk, self.ogr1.pk, True)  # tekrar işaretlemek tekil kalır
        self.assertEqual(FaaliyetEokulKaydi.objects.get().isleyen_adi, "MY")
        eokul_isaretle(self.f2.pk, self.ogr1.pk, False)
        self.assertFalse(FaaliyetEokulKaydi.objects.exists())

    def test_tamamlanmamis_faaliyet_ve_katilmayan_ogrenci_reddedilir(self):
        bekleyen = Faaliyet.objects.get(konu="Bekleyen")
        with self.assertRaises(EokulIsaretHatasi):
            eokul_isaretle(bekleyen.pk, self.ogr1.pk, True)
        self.f3.ogrenciler.remove(self.ogr2)
        with self.assertRaises(EokulIsaretHatasi):
            eokul_isaretle(self.f3.pk, self.ogr2.pk, True)

    def test_eokul_filtresi(self):
        eokul_isaretle(self.f2.pk, self.ogr1.pk, True)
        eokul_isaretle(self.f3.pk, self.ogr2.pk, True)
        self.assertEqual(self._konular(eokul="islendi"), {101: ["Seminer"], 102: ["Tiyatro"]})
        self.assertEqual(
            self._konular(eokul="islenmedi"), {101: ["Tiyatro"], 102: ["Gezi", "Seminer"]}
        )
        rapor = ogrenciye_gore_grupla(tamamlanan_faaliyetler())
        self.assertEqual(rapor["toplam"]["eokul"], 2)
        self.assertTrue(ogrenci_rapor_pdf(rapor).startswith(b"%PDF"))

    def test_isaretleme_view(self):
        url = reverse("faaliyet:faaliyet_eokul_isaretle")
        veri = {"faaliyet": self.f2.pk, "ogrenci": self.ogr1.pk, "islendi": "1"}

        self.client.force_login(self.ogretmen_user)
        self.assertEqual(self.client.post(url, veri).status_code, 403)
        self.assertFalse(FaaliyetEokulKaydi.objects.exists())

        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        r = self.client.post(url, veri)
        self.assertEqual(r.json(), {"islendi": True})
        self.assertTrue(FaaliyetEokulKaydi.objects.filter(faaliyet=self.f2, ogrenci=self.ogr1).exists())
        self.assertEqual(self.client.post(url, {"faaliyet": "x"}).status_code, 400)

        r = self.client.get(reverse("faaliyet:faaliyet_ogrenci_rapor"), {"eokul": "islendi"})
        self.assertContains(r, "Seminer")
        self.assertNotContains(r, "Tiyatro")
        self.assertContains(r, 'class="eokul-kutu"', count=1)
        self.assertContains(r, 'class="eokul-tumu"', count=1)

    def test_eokul_ozeti_ve_yonetim_listesi(self):
        from .services.toplu_rapor import eokul_ozeti

        eokul_isaretle(self.f1.pk, self.ogr2.pk, True)
        eokul_isaretle(self.f2.pk, self.ogr1.pk, True)
        eokul_isaretle(self.f2.pk, self.ogr2.pk, True)
        ozet = eokul_ozeti(Faaliyet.objects.all())
        # f1'de ogr1 devamsız → yalnızca ogr2 sayılır; bekleyen faaliyet özete girmez
        self.assertEqual(
            ozet,
            {
                self.f1.pk: {"islenen": 1, "katilan": 1},
                self.f2.pk: {"islenen": 2, "katilan": 2},
                self.f3.pk: {"islenen": 0, "katilan": 2},
            },
        )
        self.client.force_login(self.admin)
        r = self.client.get(reverse("faaliyet:faaliyet_yonetim_listesi"))
        self.assertContains(r, "✓ 2/2")
        self.assertContains(r, "✓ 1/1")
        self.assertContains(r, "0/2")

    def test_toplu_isaretleme_view(self):
        url = reverse("faaliyet:faaliyet_eokul_isaretle")
        self.client.force_login(self.admin)
        r = self.client.post(
            url, {"faaliyet": [self.f1.pk, self.f2.pk, self.f3.pk], "ogrenci": self.ogr2.pk, "islendi": "1"}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(FaaliyetEokulKaydi.objects.filter(ogrenci=self.ogr2).count(), 3)

        r = self.client.post(url, {"faaliyet": [self.f1.pk, self.f2.pk], "ogrenci": self.ogr2.pk, "islendi": "0"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            list(FaaliyetEokulKaydi.objects.filter(ogrenci=self.ogr2).values_list("faaliyet", flat=True)),
            [self.f3.pk],
        )

        # Biri geçersizse (tamamlanmamış faaliyet) hiçbiri kaydedilmez
        bekleyen = Faaliyet.objects.get(konu="Bekleyen")
        r = self.client.post(
            url, {"faaliyet": [self.f1.pk, bekleyen.pk], "ogrenci": self.ogr2.pk, "islendi": "1"}
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(FaaliyetEokulKaydi.objects.filter(faaliyet=self.f1).exists())

