import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from okul.testing import (
    aktif_egitim_yili_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
)
from veriaktar.services.sosyalkulup_import_service import (
    SosyalKulupExcelHatasi,
    sosyal_kulupleri_ice_aktar,
)

from .models import KulupDanisman, KulupUyelik, SosyalKulup


def excel_olustur(satirlar, baslik=("Sıra NO", "Sosysal Kulüp", "Danışman Öğretmen(1)", "Danışman Öğretmen(2)")):
    wb = Workbook()
    ws = wb.active
    if baslik:
        ws.append(list(baslik))
    for s in satirlar:
        ws.append(list(s))
    tampon = io.BytesIO()
    wb.save(tampon)
    return SimpleUploadedFile(
        "kulupler.xlsx",
        tampon.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


class SosyalKulupExcelImportTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.ali = personel_olustur(adi_soyadi="Ali Örnekçi")
        self.ayse = personel_olustur(adi_soyadi="Ayşe  İnceoğlu")
        self.can = personel_olustur(adi_soyadi="Can Deneme")

    def test_kulupler_ve_danismanlar_aktarilir(self):
        dosya = excel_olustur([
            (1, "Satranç Kulübü", "ALİ ÖRNEKÇİ", None),
            (2, " Tiyatro  Kulübü ", "AYŞE İNCEOĞLU", "can deneme"),
            (None, None, None, None),
        ])
        sonuc = sosyal_kulupleri_ice_aktar(dosya, self.yil)

        self.assertEqual((sonuc.yeni_kulup, sonuc.danisman_atanan), (2, 3))
        self.assertEqual(sonuc.bulunamayan_ogretmenler, [])
        self.assertEqual(
            set(KulupDanisman.objects.values_list("kulup__ad", "ogretmen__adi_soyadi", "egitim_yili")),
            {
                ("Satranç Kulübü", "Ali Örnekçi", self.yil.pk),
                ("Tiyatro Kulübü", "Ayşe  İnceoğlu", self.yil.pk),
                ("Tiyatro Kulübü", "Can Deneme", self.yil.pk),
            },
        )

    def test_bulunamayan_ogretmen_raporlanir_digerleri_aktarilir(self):
        dosya = excel_olustur([(1, "Satranç Kulübü", "OLMAYAN ÖĞRETMEN", "ALİ ÖRNEKÇİ")])
        sonuc = sosyal_kulupleri_ice_aktar(dosya, self.yil)
        self.assertEqual(sonuc.bulunamayan_ogretmenler, [("Satranç Kulübü", "OLMAYAN ÖĞRETMEN")])
        self.assertEqual(KulupDanisman.objects.get().ogretmen, self.ali)

    def test_tekrar_yukleme_idempotent_ve_danisman_degisikligini_uygular(self):
        sosyal_kulupleri_ice_aktar(excel_olustur([(1, "Satranç Kulübü", "ALİ ÖRNEKÇİ", "CAN DENEME")]), self.yil)
        sonuc = sosyal_kulupleri_ice_aktar(
            excel_olustur([(1, "SATRANÇ KULÜBÜ", "ALİ ÖRNEKÇİ", None)]), self.yil
        )
        self.assertEqual(
            (sonuc.yeni_kulup, sonuc.mevcut_kulup, sonuc.danisman_atanan, sonuc.danisman_kaldirilan),
            (0, 1, 0, 1),
        )
        self.assertEqual(SosyalKulup.objects.count(), 1)
        self.assertEqual(list(KulupDanisman.objects.values_list("ogretmen", flat=True)), [self.ali.pk])

    def test_onceki_yil_danismanlari_ve_dosyada_olmayan_kulup_korunur(self):
        eski = aktif_egitim_yili_olustur("2024-2025")
        tiyatro = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        satranc = SosyalKulup.objects.create(ad="Satranç Kulübü")
        KulupDanisman.objects.create(kulup=satranc, ogretmen=self.can, egitim_yili=eski)
        KulupDanisman.objects.create(kulup=tiyatro, ogretmen=self.ayse, egitim_yili=self.yil)

        sosyal_kulupleri_ice_aktar(excel_olustur([(1, "Satranç Kulübü", "ALİ ÖRNEKÇİ", None)]), self.yil)

        self.assertTrue(KulupDanisman.objects.filter(kulup=satranc, ogretmen=self.can, egitim_yili=eski).exists())
        self.assertTrue(KulupDanisman.objects.filter(kulup=tiyatro, egitim_yili=self.yil).exists())

    def test_pasif_kulup_yeniden_aktif_olur(self):
        SosyalKulup.objects.create(ad="Satranç Kulübü", aktif=False)
        sosyal_kulupleri_ice_aktar(excel_olustur([(1, "Satranç Kulübü", None, None)]), self.yil)
        self.assertTrue(SosyalKulup.objects.get().aktif)

    def test_baslik_yoksa_hata(self):
        with self.assertRaises(SosyalKulupExcelHatasi):
            sosyal_kulupleri_ice_aktar(excel_olustur([(1, "Satranç", "Ali")], baslik=("A", "B", "C")), self.yil)

    def test_gecersiz_dosya_hata(self):
        with self.assertRaises(SosyalKulupExcelHatasi):
            sosyal_kulupleri_ice_aktar(SimpleUploadedFile("x.xlsx", b"bozuk"), self.yil)


class KulupSayfalariTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.diger = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        self.danisman_user = kullanici_olustur("ogretmen")
        self.danisman = personel_olustur(user=self.danisman_user)
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=self.danisman)
        self.ogr = ogrenci_olustur(10, "B")
        self.pasif = ogrenci_olustur(10, "B", aktif=False)
        KulupUyelik.objects.create(kulup=self.kulup, ogrenci=self.ogr)
        KulupUyelik.objects.create(kulup=self.kulup, ogrenci=self.pasif)
        self.liste_url = reverse("sosyalkulup:kulup_ogrencileri", args=[self.kulup.pk])

    def test_danisman_kendi_kulubunun_ogrencilerini_gorur(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.get(self.liste_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([u.ogrenci_id for u in resp.context["uyelikler"]], [self.ogr.pk])

    def test_danisman_baska_kulubu_goremez(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.get(reverse("sosyalkulup:kulup_ogrencileri", args=[self.diger.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_gecen_yilin_danismani_goremez(self):
        aktif_egitim_yili_olustur("2026-2027")
        self.client.force_login(self.danisman_user)
        self.assertEqual(self.client.get(self.liste_url).status_code, 403)

    def test_danisman_olmayan_ogretmen_goremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.liste_url).status_code, 403)

    def test_mudur_yardimcisi_tum_kulupleri_gorur(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.assertEqual(self.client.get(self.liste_url).status_code, 200)
        resp = self.client.get(reverse("sosyalkulup:kulup_listesi"))
        self.assertEqual(resp.status_code, 200)
        ozet = {k.ad: (k.uye_sayisi, [d.ogretmen for d in k.yil_danismanlari]) for k in resp.context["kulupler"]}
        self.assertEqual(ozet["Satranç Kulübü"], (1, [self.danisman]))
        self.assertEqual(ozet["Tiyatro Kulübü"], (0, []))

    def test_liste_ve_excel_yukleme_ogretmene_kapali(self):
        self.client.force_login(self.danisman_user)
        self.assertEqual(self.client.get(reverse("sosyalkulup:kulup_listesi")).status_code, 403)
        self.assertEqual(self.client.get(reverse("sosyalkulup:kulup_excel_yukle")).status_code, 403)

    def test_excel_yukleme_sayfasi(self):
        personel_olustur(adi_soyadi="Ali Örnekçi")
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.post(
            reverse("sosyalkulup:kulup_excel_yukle"),
            {"dosya": excel_olustur([(1, "Müzik Kulübü", "ALİ ÖRNEKÇİ", "YOK BÖYLE BİRİ")])},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["sonuc"].danisman_atanan, 1)
        self.assertContains(resp, "YOK BÖYLE BİRİ")
        self.assertTrue(SosyalKulup.objects.filter(ad="Müzik Kulübü").exists())

    def test_gorevlerim_sayfasinda_kulup_gorunur(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.get(reverse("gorevlerim"))
        self.assertEqual(list(resp.context["sosyal_kulupler"]), [self.kulup])
        self.assertContains(resp, self.liste_url)

    def test_gorevlerim_danisman_olmayanda_kart_yok(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("gorevlerim"))
        self.assertNotContains(resp, "Sosyal Kulübüm")


class KulupGorevleriTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.diger = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        self.danisman_user = kullanici_olustur("ogretmen")
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel_olustur(user=self.danisman_user))
        self.u1 = KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogrenci_olustur(9, "A"))
        self.u2 = KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogrenci_olustur(9, "B"))
        self.baska = KulupUyelik.objects.create(kulup=self.diger, ogrenci=ogrenci_olustur(9, "C"))
        self.url = reverse("sosyalkulup:kulup_ogrencileri", args=[self.kulup.pk])

    def _gorevler(self):
        return {u.pk: u.gorev for u in KulupUyelik.objects.all()}

    def test_danisman_gorevleri_kaydeder(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.post(self.url, {f"gorev_{self.u1.pk}": "baskan", f"gorev_{self.u2.pk}": "sekreter"})
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        self.assertEqual(self._gorevler()[self.u1.pk], "baskan")
        self.assertEqual(self._gorevler()[self.u2.pk], "sekreter")

    def test_ayni_gorev_iki_ogrenciye_verilemez(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.post(
            self.url, {f"gorev_{self.u1.pk}": "baskan", f"gorev_{self.u2.pk}": "baskan"}, follow=True
        )
        self.assertContains(resp, "yalnızca bir öğrenciye")
        self.assertEqual(set(self._gorevler().values()), {"uye"})

    def test_mevcut_baskanla_cakisma_reddedilir(self):
        self.u1.gorev = "baskan"
        self.u1.save()
        self.client.force_login(self.danisman_user)
        self.client.post(self.url, {f"gorev_{self.u2.pk}": "baskan"})
        self.assertEqual(self._gorevler()[self.u2.pk], "uye")

    def test_gorevler_iki_ogrenci_arasinda_degistirilebilir(self):
        self.u1.gorev = "baskan"
        self.u1.save()
        self.client.force_login(self.danisman_user)
        self.client.post(self.url, {f"gorev_{self.u1.pk}": "uye", f"gorev_{self.u2.pk}": "baskan"})
        self.assertEqual((self._gorevler()[self.u1.pk], self._gorevler()[self.u2.pk]), ("uye", "baskan"))

    def test_baska_kulubun_uyeligi_degistirilemez(self):
        self.client.force_login(self.danisman_user)
        self.client.post(self.url, {f"gorev_{self.baska.pk}": "baskan"})
        self.assertEqual(self._gorevler()[self.baska.pk], "uye")

    def test_gecersiz_gorev_reddedilir(self):
        self.client.force_login(self.danisman_user)
        self.client.post(self.url, {f"gorev_{self.u1.pk}": "kral", f"gorev_{self.u2.pk}": "sayman"})
        self.assertEqual(set(self._gorevler().values()), {"uye"})

    def test_danisman_olmayan_ogretmen_kaydedemez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.post(self.url, {f"gorev_{self.u1.pk}": "baskan"}).status_code, 403)
        self.assertEqual(self._gorevler()[self.u1.pk], "uye")

    def test_mudur_yardimcisi_kaydedebilir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.client.post(self.url, {f"gorev_{self.u1.pk}": "sayman"})
        self.assertEqual(self._gorevler()[self.u1.pk], "sayman")

    def test_sayfada_gorev_secimi_gorunur(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.get(self.url)
        self.assertContains(resp, f'name="gorev_{self.u1.pk}"')
        self.assertContains(resp, "Görevleri Kaydet")


class KulupPdfTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.diger = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        self.danisman_user = kullanici_olustur("ogretmen")
        KulupDanisman.objects.create(
            kulup=self.kulup, ogretmen=personel_olustur(user=self.danisman_user, adi_soyadi="Şule Örnekçi")
        )
        self.ogr = ogrenci_olustur(10, "B", adi="Çağrı", soyadi="Güneş")
        KulupUyelik.objects.create(kulup=self.kulup, ogrenci=self.ogr, gorev="baskan")
        self.url = reverse("sosyalkulup:kulup_ogrencileri_pdf", args=[self.kulup.pk])

    def test_danisman_pdf_alir(self):
        from pypdf import PdfReader

        self.client.force_login(self.danisman_user)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        metin = PdfReader(io.BytesIO(resp.content)).pages[0].extract_text()
        for parca in ("Satranç Kulübü", "2025-2026", "Şule Örnekçi", "Çağrı Güneş", "10/B", "Başkan"):
            self.assertIn(parca, metin)

    def test_baska_kulubun_pdfi_alinamaz(self):
        self.client.force_login(self.danisman_user)
        url = reverse("sosyalkulup:kulup_ogrencileri_pdf", args=[self.diger.pk])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_danisman_olmayan_ogretmen_pdf_alamaz(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_mudur_yardimcisi_bos_kulubun_pdfini_alir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        url = reverse("sosyalkulup:kulup_ogrencileri_pdf", args=[self.diger.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_sayfada_pdf_dugmesi_var(self):
        self.client.force_login(self.danisman_user)
        resp = self.client.get(reverse("sosyalkulup:kulup_ogrencileri", args=[self.kulup.pk]))
        self.assertContains(resp, self.url)
