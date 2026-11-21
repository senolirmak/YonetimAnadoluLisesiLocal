"""FET bilgisayarından gelen ders programı + nöbet paketleri (dersprogrami/services/fet_yayin.py)."""

import datetime
import io
import json
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from dersprogrami.models import DersProgrami, FetYayini
from dersprogrami.services.fet_kopru import fet_disa_aktar
from dersprogrami.services.fet_yayin import (
    FetYayinHatasi,
    aktif_yap,
    ice_al,
    on_kontrol,
    paket_kaydet,
    paket_oku,
    reddet,
)
from dersprogrami.tests import ESKI_TARIH, _yerlestir
from nobet.models import NobetGorevi, NobetYerleri
from okul.models import AktifVeriKonfigurasyonu, DersHavuzu, DersSaatleri, Personel, SinifSube
from okul.testing import kullanici_olustur, personel_olustur

YENI_TARIH = datetime.date(2026, 11, 23)
ANAHTAR = "test-yayin-anahtari"
NOBET = [
    {"gun": "Pazartesi", "ogretmen": "MAT HOCA", "yer": "BAHÇE"},
    {"gun": "Salı", "ogretmen": "ALMANCA HOCA", "yer": "GİRİŞ"},
    {"gun": "Cuma", "ogretmen": "FRANSIZCA HOCA", "yer": "BAHÇE"},
]


def paket(fet: bytes, tarih=YENI_TARIH, nobet=None, **manifest) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps({
            "surum": 1, "cozum": "cozum_test/timetables/ders_programi_cozum", "uygulama_tarihi": tarih.isoformat(),
            "okul_adi": "Test Lisesi", "egitim_yili": "2026-2027", "donem": "1. Dönem", "kaynak": "fet-pc",
            **manifest,
        }))
        zf.writestr("program.fet", fet)
        zf.writestr("nobet.json", json.dumps(NOBET if nobet is None else nobet))
    return tampon.getvalue()


class FetYayinTemel(TestCase):
    def setUp(self):
        DersSaatleri.objects.all().delete()
        saat = {n: DersSaatleri.objects.create(derssaati_no=n, derssaati_baslangic=datetime.time(7 + n),
                                               derssaati_bitis=datetime.time(7 + n, 40)) for n in range(1, 9)}
        SinifSube.objects.all().delete()
        a = SinifSube.objects.create(sinif=9, sube="A")
        mat_ogr = Personel.objects.create(kimlikno="1", adi_soyadi="MAT HOCA")
        dil1 = Personel.objects.create(kimlikno="2", adi_soyadi="ALMANCA HOCA")
        Personel.objects.create(kimlikno="3", adi_soyadi="FRANSIZCA HOCA")
        mat = DersHavuzu.objects.create(ders_adi="MATEMATİK T")
        almanca = DersHavuzu.objects.create(ders_adi="ALMANCA T")
        for ogr, ders, gun, no in ((mat_ogr, mat, "Monday", 1), (mat_ogr, mat, "Monday", 2),
                                   (dil1, almanca, "Tuesday", 5)):
            DersProgrami.objects.create(ogretmen=ogr, sinif_sube=a, ders=ders, gun=gun,
                                        ders_saati=saat[no], uygulama_tarihi=ESKI_TARIH)
        AktifVeriKonfigurasyonu.objects.update_or_create(
            veri_turu="ders_programi", defaults={"uygulama_tarihi": ESKI_TARIH})
        # FET'in ürettiği çözümü taklit et: aktif programı dışa aktar ve yerleştir
        self.fet = _yerlestir(fet_disa_aktar())


class PaketOkumaTests(FetYayinTemel):
    def test_gecerli_paket_ozeti(self):
        p = paket_oku(paket(self.fet))
        self.assertEqual(p["uygulama_tarihi"], YENI_TARIH)
        self.assertEqual(p["ozet"]["satir"], 3)
        self.assertEqual(p["ozet"]["sube"], 1)
        self.assertEqual(p["ozet"]["nobet"], 3)
        self.assertEqual(p["okul_adi"], "Test Lisesi")

    def test_bozuk_paketler_reddedilir(self):
        for veri in (b"zip degil", paket(self.fet, surum=2), paket(self.fet, uygulama_tarihi="23.11.2026"),
                     paket(self.fet, nobet=[{"gun": "Pazar", "ogretmen": "X", "yer": ""}]),
                     paket(b"<fet/>")):
            with self.subTest(veri=veri[:20]), self.assertRaises(FetYayinHatasi):
                paket_oku(veri)

    def test_ayni_icerik_ikinci_kez_kaydedilmez(self):
        y1, yeni1 = paket_kaydet(paket(self.fet))
        y2, yeni2 = paket_kaydet(paket(self.fet, kaynak="baska-pc"))   # manifest farkı imzayı değiştirmez
        self.assertTrue(yeni1)
        self.assertFalse(yeni2)
        self.assertEqual(y1.pk, y2.pk)
        self.assertEqual(FetYayini.objects.count(), 1)


class IceAlmaTests(FetYayinTemel):
    def test_ice_al_ders_programi_ve_nobeti_yeni_surum_olarak_yazar_aktif_yapmaz(self):
        yayin, _ = paket_kaydet(paket(self.fet))
        kontrol = on_kontrol(yayin)
        self.assertEqual(kontrol["engeller"], [])
        self.assertEqual(kontrol["yeni_nobet_yeri"], ["BAHÇE", "GİRİŞ"])

        sonuc = ice_al(yayin)
        self.assertEqual(sonuc["ders"], 3)
        self.assertEqual(sonuc["nobet"], 3)
        self.assertEqual(DersProgrami.objects.filter(uygulama_tarihi=YENI_TARIH).count(), 3)
        self.assertEqual(DersProgrami.objects.filter(uygulama_tarihi=ESKI_TARIH).count(), 3)
        nobetler = NobetGorevi.objects.filter(uygulama_tarihi=YENI_TARIH)
        self.assertEqual(sorted(nobetler.values_list("nobet_gun", flat=True)), ["Friday", "Monday", "Tuesday"])
        self.assertEqual(NobetYerleri.objects.count(), 2)
        yayin.refresh_from_db()
        self.assertEqual(yayin.durum, FetYayini.DURUM_ICE_ALINDI)
        # aktif yapılmadı
        self.assertEqual(AktifVeriKonfigurasyonu.objects.get(veri_turu="ders_programi").uygulama_tarihi, ESKI_TARIH)
        self.assertFalse(AktifVeriKonfigurasyonu.objects.filter(veri_turu="nobet_listesi").exists())
        with self.assertRaises(FetYayinHatasi):
            ice_al(yayin)

    def test_ayni_tarihte_program_varsa_hicbir_sey_yazilmaz(self):
        yayin, _ = paket_kaydet(paket(self.fet, tarih=ESKI_TARIH))
        self.assertTrue(on_kontrol(yayin)["engeller"])
        with self.assertRaises(FetYayinHatasi):
            ice_al(yayin)
        self.assertFalse(NobetGorevi.objects.exists())
        yayin.refresh_from_db()
        self.assertEqual(yayin.durum, FetYayini.DURUM_BEKLIYOR)

    def test_sistemde_olmayan_nobetci_atlanir(self):
        nobet = NOBET + [{"gun": "Cuma", "ogretmen": "YABANCI KİŞİ", "yer": "BAHÇE"}]
        yayin, _ = paket_kaydet(paket(self.fet, nobet=nobet))
        self.assertEqual(on_kontrol(yayin)["eksik_nobetci"], ["YABANCI KİŞİ"])
        sonuc = ice_al(yayin)
        self.assertEqual(sonuc["nobet"], 3)
        self.assertTrue(any("YABANCI KİŞİ" in u for u in sonuc["uyarilar"]))
        self.assertFalse(Personel.objects.filter(adi_soyadi="YABANCI KİŞİ").exists())

    def test_aktif_yap_ders_programi_ve_nobeti_birlikte_aktif_yapar(self):
        yayin, _ = paket_kaydet(paket(self.fet))
        with self.assertRaises(FetYayinHatasi):
            aktif_yap(yayin)   # önce içeri alınmalı
        ice_al(yayin)
        aktif_yap(yayin)
        for tur in ("ders_programi", "nobet_listesi"):
            self.assertEqual(AktifVeriKonfigurasyonu.objects.get(veri_turu=tur).uygulama_tarihi, YENI_TARIH)

    def test_reddet(self):
        yayin, _ = paket_kaydet(paket(self.fet))
        reddet(yayin)
        yayin.refresh_from_db()
        self.assertEqual(yayin.durum, FetYayini.DURUM_REDDEDILDI)
        with self.assertRaises(FetYayinHatasi):
            ice_al(yayin)


class YayinAdresiTests(FetYayinTemel):
    def _gonder(self, anahtar=ANAHTAR, veri=None):
        dosya = SimpleUploadedFile("paket.zip", veri or paket(self.fet), content_type="application/zip")
        basliklar = {"HTTP_AUTHORIZATION": f"Bearer {anahtar}"} if anahtar else {}
        return self.client.post(reverse("fet_yayin_al"), {"paket": dosya}, **basliklar)

    @override_settings(FET_YAYIN_ANAHTARI="")
    def test_anahtar_tanimli_degilse_kapali(self):
        self.assertEqual(self._gonder().status_code, 503)

    @override_settings(FET_YAYIN_ANAHTARI=ANAHTAR)
    def test_anahtar_denetimi_ve_kayit(self):
        self.assertEqual(self._gonder(anahtar="yanlis").status_code, 403)
        self.assertEqual(self._gonder(anahtar="").status_code, 403)
        self.assertEqual(self.client.get(reverse("fet_yayin_al")).status_code, 405)
        r = self._gonder()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.json()["yeni"])
        r = self._gonder()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["yeni"])
        self.assertEqual(self._gonder(veri=b"bozuk").status_code, 400)
        self.assertEqual(FetYayini.objects.count(), 1)
        self.assertFalse(DersProgrami.objects.filter(uygulama_tarihi=YENI_TARIH).exists())


class GelenKutusuEkranTests(FetYayinTemel):
    def _giris(self, grup):
        u = kullanici_olustur(grup)
        personel_olustur(user=u)
        self.client.force_login(u)

    def test_yetki(self):
        yayin, _ = paket_kaydet(paket(self.fet))
        for grup, beklenen in (("ogretmen", 403), ("rehber_ogretmen", 403), ("okul_muduru", 200)):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(reverse("fet_gelen_detay", args=[yayin.pk])).status_code, beklenen)

    def test_ekrandan_ice_al_ve_aktif_yap(self):
        yayin, _ = paket_kaydet(paket(self.fet))
        self._giris("okul_muduru")
        self.assertContains(self.client.get(reverse("fet_kopru")), "cozum_test")
        self.assertContains(self.client.get(reverse("fet_gelen_detay", args=[yayin.pk])), "İçeri al")
        self.client.post(reverse("fet_gelen_islem", args=[yayin.pk, "ice-al"]))
        self.assertEqual(NobetGorevi.objects.filter(uygulama_tarihi=YENI_TARIH).count(), 3)
        self.client.post(reverse("fet_gelen_islem", args=[yayin.pk, "aktif-yap"]))
        self.assertEqual(AktifVeriKonfigurasyonu.objects.get(veri_turu="nobet_listesi").uygulama_tarihi, YENI_TARIH)

    def test_elle_paket_yukleme(self):
        self._giris("okul_muduru")
        r = self.client.post(reverse("fet_paket_yukle"),
                             {"paket": SimpleUploadedFile("p.zip", paket(self.fet))})
        yayin = FetYayini.objects.get()
        self.assertRedirects(r, reverse("fet_gelen_detay", args=[yayin.pk]))
