"""ogrenci app testleri — öğrenci listesi, Excel yükleme, yeni kayıt, ayrılma, özel durumlar."""

import datetime
import io

import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from ogrenci.forms import OgrenciDetayForm
from ogrenci.models import Ogrenci, OgrenciAyrilma, OgrenciMuaf
from ogrenci.views import normalize_cinsiyet
from okul.models import SinifSubeYil
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_olustur,
    ders_programi_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_sube_olustur,
)


class YardimciFonksiyonTestCase(TestCase):
    def test_normalize_cinsiyet(self):
        for deger, beklenen in [
            ("Erkek", "E"), (" e ", "E"), ("KIZ", "K"), ("kız", "K"), ("bayan", "K"),
            ("", None), (None, None), ("belirsiz", None),
        ]:
            with self.subTest(deger=deger):
                self.assertEqual(normalize_cinsiyet(deger), beklenen)

    def test_telefon_bicimi(self):
        self.assertTrue(OgrenciDetayForm({"velitelefon": "(532) 123 45 67"}).is_valid())
        form = OgrenciDetayForm({"velitelefon": "05321234567"})
        self.assertFalse(form.is_valid())
        self.assertIn("velitelefon", form.errors)

    def test_bos_telefon_none_kaydedilir(self):
        form = OgrenciDetayForm({"velitelefon": ""})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["velitelefon"])


class OgrenciListeTestCase(TestCase):
    def setUp(self):
        self.url = reverse("ogrenci:ogrenci_liste")
        self.ogr_9a = ogrenci_olustur(9, "A")
        self.ogr_9b = ogrenci_olustur(9, "B")
        self.pasif = ogrenci_olustur(9, "A", aktif=False)

    def _rehber_ogretmen(self, sinif_sube):
        user = kullanici_olustur("ogretmen")
        personel = personel_olustur(user=user)
        ders_programi_olustur(
            personel, 1, sinif_sube, ders=ders_olustur("REHBERLİK VE YÖNLENDİRME")
        )
        return user

    def test_yonetici_tum_ogrencileri_ve_pasifleri_etiketle_gorur(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        ogrenciler = self.client.get(self.url).context["ogrenciler"]

        self.assertEqual({o.pk for o in ogrenciler}, {self.ogr_9a.pk, self.ogr_9b.pk, self.pasif.pk})
        etiket = {o.pk: o.durum_etiketleri for o in ogrenciler}
        self.assertEqual(etiket[self.pasif.pk], ["Pasif"])
        self.assertEqual(etiket[self.ogr_9a.pk], [])

    def test_sinif_sube_filtresi(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        ogrenciler = self.client.get(self.url, {"sinifsube": "9/b"}).context["ogrenciler"]
        self.assertEqual([o.pk for o in ogrenciler], [self.ogr_9b.pk])

    def test_tasdikname_alan_ogrenci_listede_gorunmez(self):
        from secmelidersler.models import OgrenciTasdikname

        OgrenciTasdikname.objects.create(ogrenci=self.ogr_9b, egitim_yili=aktif_egitim_yili_olustur())
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

        pkler = {o.pk for o in self.client.get(self.url).context["ogrenciler"]}
        self.assertNotIn(self.ogr_9b.pk, pkler)

    def test_ogretmen_sadece_rehberi_oldugu_sinifi_gorur(self):
        self.client.force_login(self._rehber_ogretmen(sinif_sube_olustur(9, "A")))
        resp = self.client.get(self.url)

        self.assertTrue(resp.context["sinif_filtre_gizli"])
        self.assertEqual({o.pk for o in resp.context["ogrenciler"]}, {self.ogr_9a.pk, self.pasif.pk})

    def test_rehberligi_olmayan_ogretmen_yonlendirilir(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertRedirects(self.client.get(self.url), reverse("index"), fetch_redirect_response=False)

    def test_ogretmen_baska_sinifin_ogrencisini_duzenleyemez(self):
        self.client.force_login(self._rehber_ogretmen(sinif_sube_olustur(9, "A")))

        url_9a = reverse("ogrenci:ogrenci_detay_duzenle", args=[self.ogr_9a.pk])
        url_9b = reverse("ogrenci:ogrenci_detay_duzenle", args=[self.ogr_9b.pk])
        self.assertEqual(self.client.get(url_9a).status_code, 200)
        self.assertEqual(self.client.get(url_9b).status_code, 403)

    def test_detay_ve_adres_kaydedilir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        url = reverse("ogrenci:ogrenci_detay_duzenle", args=[self.ogr_9a.pk])

        resp = self.client.post(url, {"veli": "Veli Örnek", "velitelefon": "(532) 000 00 00", "il": "Ankara"})

        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.ogr_9a.refresh_from_db()
        self.assertEqual(self.ogr_9a.detay.veli, "Veli Örnek")
        self.assertEqual(self.ogr_9a.adres.il, "Ankara")


def _excel(satirlar):
    buf = io.BytesIO()
    pd.DataFrame(satirlar).to_excel(buf, index=False)
    return SimpleUploadedFile(
        "ogrenciler.xlsx",
        buf.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _satir(**kwargs):
    satir = {
        "OkulNo": "101", "Sinif": "9", "Sube": "A", "TCKimlikNo": "30000000001",
        "Adi": "Ali", "Soyadi": "Örnek", "DogumTarihi": "2010-05-01", "Cinsiyet": "Erkek",
    }
    satir.update(kwargs)
    return satir


class ExcelYukleTestCase(TestCase):
    def setUp(self):
        self.url = reverse("ogrenci:excel_yukle")
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

    def _yukle(self, satirlar):
        return self.client.post(self.url, {"excel_dosya": _excel(satirlar)})

    def test_yeni_ogrenci_detay_ve_adresle_eklenir(self):
        self._yukle([_satir(Veli="Veli Örnek", Il="İzmir")])

        ogr = Ogrenci.objects.get(tckimlikno="30000000001")
        self.assertEqual((ogr.okulno, ogr.sinif, ogr.sube, ogr.cinsiyet), (101, 9, "A", "E"))
        self.assertEqual(ogr.dogumtarihi, datetime.date(2010, 5, 1))
        self.assertEqual(ogr.detay.veli, "Veli Örnek")
        self.assertEqual(ogr.adres.il, "İzmir")

    def test_ayni_tc_ile_ikinci_yukleme_gunceller(self):
        self._yukle([_satir()])
        self._yukle([_satir(Sube="B", Adi="Veli")])

        ogr = Ogrenci.objects.get()
        self.assertEqual((ogr.sube, ogr.adi), ("B", "Veli"))

    def test_hatali_satir_atlanir_digerleri_yuklenir(self):
        self._yukle([
            _satir(),
            _satir(TCKimlikNo="30000000002", OkulNo="102", Sinif="dokuz"),
            _satir(TCKimlikNo="30000000003", OkulNo="103"),
        ])

        self.assertEqual(
            set(Ogrenci.objects.values_list("tckimlikno", flat=True)),
            {"30000000001", "30000000003"},
        )

    def test_eksik_zorunlu_sutun_hicbir_sey_yuklemez(self):
        satir = _satir()
        del satir["TCKimlikNo"]
        self._yukle([satir])

        self.assertFalse(Ogrenci.objects.exists())

    def test_ogretmen_excel_yukleyemez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self._yukle([_satir()])

        self.assertFalse(Ogrenci.objects.exists())


class YeniKayitTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

    def _form_verisi(self, **kwargs):
        veri = {
            "okulno": 501, "sube": "a", "tckimlikno": "40000000001", "adi": "Ayşe",
            "soyadi": "Örnek", "dogumtarihi": "2010-01-01", "cinsiyet": "K",
        }
        veri.update(kwargs)
        return veri

    def test_ogretmen_erisemez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(reverse("ogrenci:yeni_kayit_hub", args=[9])).status_code, 403)

    def test_ekle_sinif_ve_subeyi_urlden_alir(self):
        resp = self.client.post(reverse("ogrenci:yeni_kayit_ekle", args=[9, "a"]), self._form_verisi(sube="Z"))

        self.assertEqual(resp.status_code, 302)
        ogr = Ogrenci.objects.get()
        self.assertEqual((ogr.sinif, ogr.sube), (9, "A"))

    def test_kapali_subeye_ekleme_yapilamaz(self):
        SinifSubeYil.objects.create(sinif_sube=sinif_sube_olustur(9, "A"), egitim_yili=self.yil, acik=False)

        self.client.post(reverse("ogrenci:yeni_kayit_ekle", args=[9, "A"]), self._form_verisi())

        self.assertFalse(Ogrenci.objects.exists())

    def test_ogrenci_kapali_subeye_tasinamaz(self):
        ogr = ogrenci_olustur(9, "A")
        SinifSubeYil.objects.create(sinif_sube=sinif_sube_olustur(9, "B"), egitim_yili=self.yil, acik=False)

        resp = self.client.post(
            reverse("ogrenci:yeni_kayit_duzenle", args=[ogr.pk]),
            self._form_verisi(okulno=ogr.okulno, tckimlikno=ogr.tckimlikno, sube="B"),
        )

        self.assertEqual(resp.status_code, 200)
        self.assertIn("sube", resp.context["form"].errors)
        ogr.refresh_from_db()
        self.assertEqual(ogr.sube, "A")

    def test_liste_pasif_ve_sinif_tekrari_ogrencilerini_dislar(self):
        from secmelidersler.models import OgrenciSinifTekrari

        normal = ogrenci_olustur(9, "A")
        ogrenci_olustur(9, "A", aktif=False)
        tekrar = ogrenci_olustur(9, "A")
        OgrenciSinifTekrari.objects.create(ogrenci=tekrar, egitim_yili=self.yil)

        resp = self.client.get(reverse("ogrenci:yeni_kayit_liste", args=[9, "a"]))

        self.assertEqual(list(resp.context["ogrenciler"]), [normal])

    def test_sil_sadece_post_ile(self):
        ogr = ogrenci_olustur(9, "A")
        url = reverse("ogrenci:yeni_kayit_sil", args=[ogr.pk])

        self.client.get(url)
        self.assertTrue(Ogrenci.objects.filter(pk=ogr.pk).exists())

        self.client.post(url)
        self.assertFalse(Ogrenci.objects.filter(pk=ogr.pk).exists())


class AyrilmaTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.ogr = ogrenci_olustur(10, "C", adi="Kerem")

    def test_ayrilma_kaydi_ogrenciyi_pasife_alir_silinince_geri_acar(self):
        self.client.post(
            reverse("ogrenci:ayrilma_ekle"),
            {"ogrenci_pk": self.ogr.pk, "sebep": "nakil", "tarih": "2025-11-01"},
        )

        kayit = OgrenciAyrilma.objects.get()
        self.assertEqual(kayit.egitim_yili, self.yil)
        self.ogr.refresh_from_db()
        self.assertFalse(self.ogr.aktif)

        self.client.post(reverse("ogrenci:ayrilma_sil", args=[kayit.pk]))

        self.assertFalse(OgrenciAyrilma.objects.exists())
        self.ogr.refresh_from_db()
        self.assertTrue(self.ogr.aktif)

    def test_tasdikname_de_varsa_ayrilma_silinince_pasif_kalir(self):
        from secmelidersler.models import OgrenciTasdikname

        kayit = OgrenciAyrilma.objects.create(ogrenci=self.ogr, sebep="ogrenim_hakki")
        OgrenciTasdikname.objects.create(ogrenci=self.ogr, egitim_yili=self.yil)
        self.ogr.aktif = False
        self.ogr.save()

        self.client.post(reverse("ogrenci:ayrilma_sil", args=[kayit.pk]))

        self.ogr.refresh_from_db()
        self.assertFalse(self.ogr.aktif)

    def test_ikinci_ayrilma_kaydi_eklenmez(self):
        OgrenciAyrilma.objects.create(ogrenci=self.ogr, sebep="nakil")
        self.client.post(reverse("ogrenci:ayrilma_ekle"), {"ogrenci_pk": self.ogr.pk, "sebep": "vefat"})

        self.assertEqual(OgrenciAyrilma.objects.get().sebep, "nakil")

    def test_sebepsiz_kayit_reddedilir(self):
        self.client.post(reverse("ogrenci:ayrilma_ekle"), {"ogrenci_pk": self.ogr.pk})

        self.assertFalse(OgrenciAyrilma.objects.exists())
        self.ogr.refresh_from_db()
        self.assertTrue(self.ogr.aktif)

    def test_arama_kaydi_olani_ve_pasifleri_gostermez(self):
        ogrenci_olustur(10, "C", adi="Kerim", aktif=False)
        kayitli = ogrenci_olustur(10, "C", adi="Kerimcan")
        OgrenciAyrilma.objects.create(ogrenci=kayitli, sebep="nakil")

        resp = self.client.get(reverse("ogrenci:ayrilma_listesi"), {"q": "Ker"})

        self.assertEqual(resp.context["arama_sonuclari"], [self.ogr])


class OzelDurumTestCase(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur()
        self.ogr1 = ogrenci_olustur(9, "A")
        self.ogr2 = ogrenci_olustur(9, "A", sureksiz_devamsiz=True)
        self.ogr_baska = ogrenci_olustur(9, "B", sureksiz_devamsiz=True)

    def test_yetkiler(self):
        url = reverse("ogrenci:sureksiz_devamsiz_listesi")
        for grup, kod in [("ogretmen", 403), ("rehber_ogretmen", 403), ("okul_muduru", 200), ("mudur_yardimcisi", 200)]:
            self.client.force_login(kullanici_olustur(grup))
            with self.subTest(grup=grup):
                self.assertEqual(self.client.get(url).status_code, kod)

    def test_toplu_isaretleme_sadece_filtrelenen_subeyi_degistirir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.client.post(
            reverse("ogrenci:sureksiz_devamsiz_listesi"),
            {"sinifsube_filtre": "9/A", "sureksiz": [str(self.ogr1.okulno)]},
        )

        for ogr, beklenen in [(self.ogr1, True), (self.ogr2, False), (self.ogr_baska, True)]:
            ogr.refresh_from_db()
            self.assertEqual(ogr.sureksiz_devamsiz, beklenen, ogr)

    def test_toggle(self):
        url = reverse("ogrenci:sureksiz_devamsiz_toggle", args=[self.ogr1.pk])
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.post(url).status_code, 403)

        self.client.force_login(kullanici_olustur("okul_muduru"))
        self.assertEqual(self.client.post(url).json(), {"ok": True, "sureksiz": True})
        self.assertEqual(self.client.post(url).json(), {"ok": True, "sureksiz": False})

    def test_muaf_dersler_bu_yil_icin_degistirilir_onceki_yil_korunur(self):
        from okul.models import EgitimOgretimYili

        eski_yil = EgitimOgretimYili.objects.create(
            egitim_yili="2024-2025",
            egitim_baslangic=datetime.date(2024, 9, 1),
            egitim_bitis=datetime.date(2025, 6, 20),
        )
        beden, muzik, resim = ders_olustur("BEDEN"), ders_olustur("MÜZİK"), ders_olustur("RESİM")
        OgrenciMuaf.objects.create(ogrenci=self.ogr1, ders=beden, egitim_yili=eski_yil)
        OgrenciMuaf.objects.create(ogrenci=self.ogr1, ders=beden, egitim_yili=self.yil)

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.client.post(
            reverse("ogrenci:ogrenci_muaf_duzenle", args=[self.ogr1.pk]),
            {"muaf_ders": [muzik.pk, resim.pk]},
        )

        self.assertEqual(
            set(OgrenciMuaf.objects.filter(egitim_yili=self.yil).values_list("ders__ders_adi", flat=True)),
            {"MÜZİK", "RESİM"},
        )
        self.assertTrue(OgrenciMuaf.objects.filter(egitim_yili=eski_yil, ders=beden).exists())


class VarsayilanRetTestCase(TestCase):
    """Hiçbir gruba üye olmayan kullanıcı öğrenci listesine/detayına erişemez."""

    def test_grupsuz_kullanici(self):
        ogr = ogrenci_olustur(9, "A")
        self.client.force_login(kullanici_olustur())

        resp = self.client.get(reverse("ogrenci:ogrenci_liste"))
        self.assertRedirects(resp, reverse("index"), fetch_redirect_response=False)
        url = reverse("ogrenci:ogrenci_detay_duzenle", args=[ogr.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_yonetici_rolleri_tum_ogrencileri_gorur(self):
        ogr = ogrenci_olustur(9, "A")
        for grup in ("mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"):
            self.client.force_login(kullanici_olustur(grup))
            with self.subTest(grup=grup):
                self.assertEqual(len(self.client.get(reverse("ogrenci:ogrenci_liste")).context["ogrenciler"]), 1)
                url = reverse("ogrenci:ogrenci_detay_duzenle", args=[ogr.pk])
                self.assertEqual(self.client.get(url).status_code, 200)
