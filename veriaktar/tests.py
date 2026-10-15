from datetime import date
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from openpyxl import Workbook

from ogrenci.models import Ogrenci, OgrenciAyrilma
from secmelidersler.models import OgrenciTasdikname

from .services.ogrenci_import_service import OgrenciIsleyici


def _eokul_dosyasi(siniflar):
    """{(sinif, sube): [(okulno, adi, soyadi), ...]} → e-Okul OOG01001R020 düzeninde xlsx."""
    wb = Workbook()
    ws = wb.active
    for (sinif, sube), ogrenciler in siniflar.items():
        ws.append([f"{sinif}. Sınıf / {sube} Şubesi"])
        for sira, (okulno, adi, soyadi) in enumerate(ogrenciler, start=1):
            satir = [None] * 13
            satir[0], satir[1], satir[4], satir[8], satir[12] = sira, okulno, adi, soyadi, "Erkek"
            ws.append(satir)
    buf = BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("OOG01001R020.xlsx", buf.getvalue())


def _ogrenci(okulno, sinif=9, sube="A", aktif=True, **kw):
    kw.setdefault("tckimlikno", str(okulno).zfill(11))
    return Ogrenci.objects.create(
        okulno=okulno, sinif=sinif, sube=sube, adi="AD", soyadi="SOYAD",
        dogumtarihi=date(2000, 1, 1), cinsiyet="E", aktif=aktif, **kw,
    )


class OgrenciIsleyiciTest(TestCase):
    def test_yer_tutucu_tc_cakisirsa_ogrenci_yine_de_eklenir(self):
        # Okul numarası değişmiş eski bir kayıt, yeni öğrencinin yer tutucusunu tutuyor.
        _ogrenci(20263126, tckimlikno="00000003126", aktif=False)

        sonuc = OgrenciIsleyici(_eokul_dosyasi({(12, "D"): [(3126, "YAREN", "GENÇ")]})).calistir()

        self.assertEqual(sonuc["hatali"], 0)
        yeni = Ogrenci.objects.get(okulno=3126)
        self.assertTrue(yeni.aktif)
        self.assertNotEqual(yeni.tckimlikno, "00000003126")

    def test_arsivdeki_ogrenci_listede_varsa_tekrar_aktif_olur(self):
        o = _ogrenci(100, aktif=False)
        OgrenciAyrilma.objects.create(ogrenci=o, sebep="nakil")

        sonuc = OgrenciIsleyici(_eokul_dosyasi({(10, "B"): [(100, "ALİ", "VELİ")]})).calistir()

        o.refresh_from_db()
        self.assertTrue(o.aktif)
        self.assertEqual((o.sinif, o.sube), (10, "B"))
        self.assertFalse(OgrenciAyrilma.objects.filter(ogrenci=o).exists())
        self.assertEqual(len(sonuc["aktiflestirilen"]), 1)

    def test_tasdikname_alan_ogrenci_aktif_yapilmaz(self):
        o = _ogrenci(200, aktif=False)
        OgrenciTasdikname.objects.create(ogrenci=o)

        sonuc = OgrenciIsleyici(_eokul_dosyasi({(11, "C"): [(200, "AYŞE", "KAYA")]})).calistir()

        o.refresh_from_db()
        self.assertFalse(o.aktif)
        self.assertEqual(len(sonuc["tasdikli_listede"]), 1)

    def test_mevcut_gercek_tc_ve_dogum_tarihi_korunur(self):
        o = _ogrenci(300, tckimlikno="12345678901")
        o.dogumtarihi = date(2009, 5, 17)
        o.save()

        OgrenciIsleyici(_eokul_dosyasi({(9, "A"): [(300, "MEHMET", "ÖZ")]})).calistir()

        o.refresh_from_db()
        self.assertEqual(o.tckimlikno, "12345678901")
        self.assertEqual(o.dogumtarihi, date(2009, 5, 17))
        self.assertEqual(o.adi, "MEHMET")

    def test_aktif_sayisi_eokul_listesiyle_esitlenir(self):
        _ogrenci(1)
        _ogrenci(2)
        _ogrenci(3, aktif=False)  # listede var → aktif olmalı
        _ogrenci(4)  # listede yok → nakil

        OgrenciIsleyici(
            _eokul_dosyasi({(9, "A"): [(1, "A", "B"), (2, "C", "D"), (3, "E", "F"), (5, "G", "H")]})
        ).calistir()

        self.assertEqual(
            set(Ogrenci.objects.filter(aktif=True).values_list("okulno", flat=True)), {1, 2, 3, 5}
        )
