"""secmelidersler servisleri ve tasdikname akışı için testler.

Kapsam: ders adı normalleştirme, norm kadro, şube token yardımcıları, seçim sayısı
uyarıları, gelecek yıl şube dağılımı (_sube_dagit / plan_sinif_dagilimi), tasdikname
ekle/sil (Ogrenci.aktif senkronu). Varsayılan veri yükleme komutu ve migration testleri
secmelidersler/tests.py içinde.
"""

import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from ogrenci.models import OgrenciAyrilma
from okul.models import EgitimOgretimYili, SinifSube, SinifSubeYil
from okul.testing import aktif_egitim_yili_olustur, kullanici_olustur, ogrenci_olustur
from secmelidersler.models import (
    Alan,
    AlanDers,
    OgrenciSinifTekrari,
    OgrenciTasdikname,
    SecmeliDers,
    SecmeliDersGrubu,
    SecmeliDersHavuzu,
    normalize_ders_adi,
)
from secmelidersler.services.ders_dagilimi import _sube_dagit, plan_sinif_dagilimi
from secmelidersler.services.ders_yuku import (
    _sube_token_ayikla,
    _sube_token_etiket,
    _sube_token_saat,
    _sube_tokenlari_genislet,
    acik_sube_harfleri,
    norm_kadro,
    normalize_sube_metni,
    sube_sayilari,
)
from secmelidersler.services.secim_sayisi import secim_sayisi_asim_uyarilari


class SafYardimcilarTestCase(SimpleTestCase):
    def test_normalize_ders_adi(self):
        self.assertEqual(normalize_ders_adi("SEÇMELİ TARİH (4)"), "SEÇMELİ TARİH")
        self.assertEqual(normalize_ders_adi("  FİZİK   (2) "), "FİZİK")
        self.assertEqual(normalize_ders_adi("MATEMATİK*"), "MATEMATİK")

    def test_norm_kadro_sinirlari(self):
        for saat, norm in [(0, 0), (5, 0), (6, 1), (30, 1), (31, 2), (42, 2),
                           (43, 2), (56, 2), (57, 3), (63, 3), (78, 4)]:
            with self.subTest(saat=saat):
                self.assertEqual(norm_kadro(saat), norm)

    def test_normalize_sube_metni(self):
        self.assertEqual(normalize_sube_metni(" b, a ,A,, c"), ("A", "B", "C"))
        self.assertEqual(normalize_sube_metni(""), ())

    def test_sube_tokenlari(self):
        self.assertEqual(_sube_token_ayikla("A"), ("A", None))
        self.assertEqual(_sube_token_ayikla("A#2#3"), ("A", 3))
        self.assertEqual(_sube_token_ayikla("A#2#x"), ("A", None))
        self.assertEqual(_sube_token_etiket("A#1#2"), "A·2s")
        self.assertEqual(_sube_token_etiket("B"), "B")
        self.assertEqual(_sube_token_saat("B", 4), 4)
        self.assertEqual(_sube_token_saat("B#1#1", 4), 1)
        self.assertEqual(
            _sube_tokenlari_genislet(["A", "B", "C"], {"B": [1, 3]}),
            ["A", "B#1#1", "B#2#3", "C"],
        )


class _Ogr:
    def __init__(self, okulno, cinsiyet):
        self.okulno, self.cinsiyet = okulno, cinsiyet


class SubeDagitTestCase(SimpleTestCase):
    def test_bos_liste(self):
        self.assertEqual(_sube_dagit([], 10, 0), ([], 0))

    def test_kiz_erkek_dengesi_ve_harf_sirasi(self):
        ogrs = [_Ogr(i, "K") for i in range(1, 6)] + [_Ogr(i, "E") for i in range(6, 14)]

        subeler, sonraki = _sube_dagit(ogrs, 10, harf_idx=2, maks=5)

        # 13 öğrenci / 5 → 3 şube; 5 kız → 2,2,1; 8 erkek → 3,3,2.
        self.assertEqual(sonraki, 5)
        self.assertEqual([s["label"] for s in subeler], ["10/C", "10/D", "10/E"])
        self.assertEqual([(s["kiz_sayi"], s["erkek_sayi"]) for s in subeler], [(2, 3), (2, 3), (1, 2)])
        tumu = [o.okulno for s in subeler for o in s["ogrenciler"]]
        self.assertEqual(sorted(tumu), list(range(1, 14)))
        for s in subeler:
            no = [o.okulno for o in s["ogrenciler"]]
            self.assertEqual(no, sorted(no))


def _secmeli_ders(grup, ad, saat="2"):
    return SecmeliDers.objects.create(grup=grup, ders_adi=ad, saat_secenekleri=saat)


def _secim(ogrenci, ders, saat=2):
    from ogrencidersleri.models import OgrenciSecmeliDers

    return OgrenciSecmeliDers.objects.create(ogrenci=ogrenci, ders=ders, secilen_saat=saat)


class SecimSayisiTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.eski_yil = EgitimOgretimYili.objects.create(
            egitim_yili="2024-2025",
            egitim_baslangic=datetime.date(2024, 9, 1),
            egitim_bitis=datetime.date(2025, 6, 20),
        )
        SecmeliDersHavuzu.objects.create(ders_adi="SEÇMELİ TARİH", secimsayisi=1)
        self.grup_eski = SecmeliDersGrubu.objects.create(egitim_yili=self.eski_yil, sinif_seviyesi=10, adi="G")
        self.grup = SecmeliDersGrubu.objects.create(egitim_yili=self.yil, sinif_seviyesi=11, adi="G")
        self.tarih_eski = _secmeli_ders(self.grup_eski, "SEÇMELİ TARİH (2)")
        self.tarih = _secmeli_ders(self.grup, "SEÇMELİ TARİH (4)")
        self.ogr = ogrenci_olustur(11, "A")

    def test_ilk_secim_uyari_vermez(self):
        self.assertEqual(secim_sayisi_asim_uyarilari(self.ogr, [(self.tarih, 4)]), [])

    def test_gecmis_yilda_secilen_ders_saat_eki_farkli_olsa_da_sayilir(self):
        _secim(self.ogr, self.tarih_eski)

        uyarilar = secim_sayisi_asim_uyarilari(self.ogr, [(self.tarih, 4)], haric_egitim_yili=self.yil)

        self.assertEqual(len(uyarilar), 1)
        self.assertIn("SEÇMELİ TARİH", uyarilar[0])
        self.assertIn("2. seçimi", uyarilar[0])

    def test_ayni_yilin_eski_kayitlari_sayilmaz(self):
        _secim(self.ogr, self.tarih)
        self.assertEqual(
            secim_sayisi_asim_uyarilari(self.ogr, [(self.tarih, 4)], haric_egitim_yili=self.yil), []
        )

    def test_sinif_tekrari_yilindaki_secim_sayilmaz(self):
        _secim(self.ogr, self.tarih_eski)
        OgrenciSinifTekrari.objects.create(ogrenci=self.ogr, egitim_yili=self.eski_yil)

        self.assertEqual(
            secim_sayisi_asim_uyarilari(self.ogr, [(self.tarih, 4)], haric_egitim_yili=self.yil), []
        )

    def test_havuzda_olmayan_ders_denetlenmez(self):
        diger = _secmeli_ders(self.grup, "SEÇMELİ ASTRONOMİ (2)")
        self.assertEqual(secim_sayisi_asim_uyarilari(self.ogr, [(diger, 2), (diger, 2)]), [])


class PlanSinifDagilimiTestCase(TestCase):
    """10. sınıflar 11. sınıf alanlarına seçmeli tercihlerine göre eşlenir."""

    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        grup = SecmeliDersGrubu.objects.create(egitim_yili=self.yil, sinif_seviyesi=11, adi="Alan Dersleri")
        self.fizik = _secmeli_ders(grup, "SEÇMELİ FİZİK (4)", "4")
        self.kimya = _secmeli_ders(grup, "SEÇMELİ KİMYA (4)", "4")
        self.cografya = _secmeli_ders(grup, "SEÇMELİ COĞRAFYA (4)", "4")
        self.mf = Alan.objects.create(egitim_yili=self.yil, sinif_seviyesi=11, adi="MF", sira=1)
        self.tm = Alan.objects.create(egitim_yili=self.yil, sinif_seviyesi=11, adi="TM", sira=2)
        for alan, ders in [(self.mf, self.fizik), (self.mf, self.kimya), (self.tm, self.cografya), (self.tm, self.kimya)]:
            AlanDers.objects.create(alan=alan, ders=ders, secilen_saat=4)

    def _plan(self):
        return plan_sinif_dagilimi(10, 11, self.yil, maks_sube=30)

    def test_ogrenciler_en_cok_ortusen_alana_eslenir(self):
        mf_ogr = ogrenci_olustur(10, "A", cinsiyet="K")
        _secim(mf_ogr, self.fizik)
        _secim(mf_ogr, self.kimya)
        tm_ogr = ogrenci_olustur(10, "A")
        _secim(tm_ogr, self.cografya)
        secimsiz = ogrenci_olustur(10, "B")

        plan = self._plan()

        gruplar = {g["alan"].adi: g for g in plan["alan_gruplari"]}
        self.assertEqual(gruplar["MF"]["subeler"][0]["ogrenciler"], [mf_ogr])
        self.assertEqual(gruplar["TM"]["subeler"][0]["ogrenciler"], [tm_ogr])
        # Şube harfleri alanlar boyunca sürer: MF → 11/A, TM → 11/B.
        self.assertEqual([gruplar["MF"]["subeler"][0]["label"], gruplar["TM"]["subeler"][0]["label"]],
                         ["11/A", "11/B"])
        self.assertEqual(plan["alan_yok"], [secimsiz])
        self.assertEqual((plan["toplam_ogr"], plan["toplam_sube"]), (2, 2))

    def test_tasdikname_ve_bu_yilin_sinif_tekrari_ayri_listelenir(self):
        tasdik = ogrenci_olustur(10, "A")
        OgrenciTasdikname.objects.create(ogrenci=tasdik, egitim_yili=self.yil)
        tekrar = ogrenci_olustur(10, "A")
        OgrenciSinifTekrari.objects.create(ogrenci=tekrar, egitim_yili=self.yil)

        plan = self._plan()

        self.assertEqual(plan["tasdikname"], [tasdik])
        self.assertEqual(plan["sinif_tekrari"], [tekrar])
        self.assertEqual(plan["alan_yok"], [])

    def test_okuldan_ayrilan_ogrenci_plana_girmez(self):
        nakil = ogrenci_olustur(10, "A", aktif=False)
        OgrenciAyrilma.objects.create(ogrenci=nakil, sebep="nakil")

        plan = self._plan()

        self.assertNotIn(nakil, plan["alan_yok"])

    def test_ikinci_sinif_tekrari_ile_ogrenim_hakki_biten_plana_girmez(self):
        ogr = ogrenci_olustur(10, "A", aktif=False)
        OgrenciTasdikname.objects.create(ogrenci=ogr, egitim_yili=self.yil)
        OgrenciAyrilma.objects.create(ogrenci=ogr, sebep="ogrenim_hakki")

        plan = self._plan()

        self.assertEqual((plan["tasdikname"], plan["alan_yok"]), ([], []))


class SubeSayilariTestCase(TestCase):
    def test_kapali_subeler_haric(self):
        yil = aktif_egitim_yili_olustur()
        for sinif, sube in [(9, "A"), (9, "B"), (9, "C"), (10, "A")]:
            SinifSube.objects.create(sinif=sinif, sube=sube)
        SinifSubeYil.objects.create(sinif_sube=SinifSube.objects.get(sinif=9, sube="B"), egitim_yili=yil, acik=False)

        self.assertEqual(sube_sayilari(yil), {9: 2, 10: 1})
        self.assertEqual(sube_sayilari(None), {9: 3, 10: 1})
        self.assertEqual(acik_sube_harfleri(yil, 9), ["A", "C"])


class TasdiknameTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.ogr = ogrenci_olustur(12, "A")
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

    def test_ekle_pasife_alir_sil_geri_acar(self):
        self.client.post(reverse("tasdikname_ekle"), {"ogrenci_pk": self.ogr.pk, "aciklama": "test"})

        kayit = OgrenciTasdikname.objects.get()
        self.assertEqual(kayit.egitim_yili, self.yil)
        self.ogr.refresh_from_db()
        self.assertFalse(self.ogr.aktif)

        self.client.post(reverse("tasdikname_sil", args=[kayit.pk]))

        self.assertFalse(OgrenciTasdikname.objects.exists())
        self.ogr.refresh_from_db()
        self.assertTrue(self.ogr.aktif)

    def test_ikinci_ekleme_kopya_olusturmaz(self):
        for _ in range(2):
            self.client.post(reverse("tasdikname_ekle"), {"ogrenci_pk": self.ogr.pk})
        self.assertEqual(OgrenciTasdikname.objects.count(), 1)

    def test_ogretmen_ekleyemez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.post(reverse("tasdikname_ekle"), {"ogrenci_pk": self.ogr.pk})

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(OgrenciTasdikname.objects.exists())

    def test_okuldan_ayrilmis_ogrenci_tasdikname_silinince_aktif_olmaz(self):
        OgrenciAyrilma.objects.create(ogrenci=self.ogr, sebep="nakil")
        self.ogr.aktif = False
        self.ogr.save()
        kayit = OgrenciTasdikname.objects.create(ogrenci=self.ogr, egitim_yili=self.yil)

        self.client.post(reverse("tasdikname_sil", args=[kayit.pk]))

        self.ogr.refresh_from_db()
        self.assertFalse(self.ogr.aktif)
