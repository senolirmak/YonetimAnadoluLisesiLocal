from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from okul.models import OkulBilgi
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_olustur,
    ders_programi_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_sube_olustur,
)

from .models import KulupDanisman, KulupUyelik, SosyalKulup
from .services.uyelik import sinif_kuluplerini_kaydet


class EgitimYiliDamgasiTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")

    def test_danisman_aktif_yil_ile_damgalanir(self):
        d = KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel_olustur())
        self.assertEqual(d.egitim_yili, self.yil)

    def test_uyelik_aktif_yil_ile_damgalanir(self):
        u = KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogrenci_olustur())
        self.assertEqual(u.egitim_yili, self.yil)
        self.assertEqual(u.gorev, KulupUyelik.GOREV_UYE)

    def test_acikca_verilen_yil_korunur(self):
        eski = aktif_egitim_yili_olustur("2024-2025")
        aktif_egitim_yili_olustur("2025-2026")  # aktif yılı geri al
        u = KulupUyelik.objects.create(
            kulup=self.kulup, ogrenci=ogrenci_olustur(), egitim_yili=eski
        )
        self.assertEqual(u.egitim_yili, eski)

    def test_aktif_yil_degisince_eski_kayit_degismez(self):
        u = KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogrenci_olustur())
        aktif_egitim_yili_olustur("2026-2027")
        u.gorev = "baskan"
        u.save()
        u.refresh_from_db()
        self.assertEqual(u.egitim_yili, self.yil)

    def test_aktif_yil_yoksa_kayit_reddedilir(self):
        OkulBilgi.objects.update(okul_egtyil=None)
        with self.assertRaises(ValidationError):
            KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel_olustur())
        self.assertFalse(KulupDanisman.objects.exists())

    def test_full_clean_bos_yili_doldurur(self):
        u = KulupUyelik(kulup=self.kulup, ogrenci=ogrenci_olustur())
        u.full_clean()
        self.assertEqual(u.egitim_yili, self.yil)


class TekillikTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.kulup2 = SosyalKulup.objects.create(ad="Tiyatro Kulübü")

    def test_ogrenci_ayni_yilda_iki_kulube_uye_olamaz(self):
        ogr = ogrenci_olustur()
        KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogr)
        with self.assertRaises(IntegrityError), transaction.atomic():
            KulupUyelik.objects.create(kulup=self.kulup2, ogrenci=ogr)

    def test_ogrenci_farkli_yillarda_farkli_kulube_uye_olabilir(self):
        ogr = ogrenci_olustur()
        KulupUyelik.objects.create(kulup=self.kulup, ogrenci=ogr)
        yeni = aktif_egitim_yili_olustur("2026-2027")
        u = KulupUyelik.objects.create(kulup=self.kulup2, ogrenci=ogr)
        self.assertEqual(u.egitim_yili, yeni)
        self.assertEqual(ogr.kulup_uyelikleri.count(), 2)

    def test_ayni_danisman_ayni_yilda_tekrar_eklenemez(self):
        ogretmen = personel_olustur()
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=ogretmen)
        with self.assertRaises(IntegrityError), transaction.atomic():
            KulupDanisman.objects.create(kulup=self.kulup, ogretmen=ogretmen)

    def test_kulube_birden_fazla_danisman_atanabilir(self):
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel_olustur())
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel_olustur())
        self.assertEqual(self.kulup.danismanlar.filter(egitim_yili=self.yil).count(), 2)


class SinifKulupKaydetServisTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.satranc = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.tiyatro = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        self.ogr1 = ogrenci_olustur(9, "A")
        self.ogr2 = ogrenci_olustur(9, "A")
        self.baska_sinif = ogrenci_olustur(9, "B")

    def _kaydet(self, secimler):
        return sinif_kuluplerini_kaydet(9, "A", secimler, self.yil)

    def test_ekle_degistir_kaldir(self):
        self.assertEqual(self._kaydet({self.ogr1.pk: self.satranc.pk, self.ogr2.pk: self.satranc.pk}), (2, 0, 0))
        KulupUyelik.objects.filter(ogrenci=self.ogr1).update(gorev="baskan")

        self.assertEqual(self._kaydet({self.ogr1.pk: self.tiyatro.pk, self.ogr2.pk: None}), (0, 1, 1))
        u = KulupUyelik.objects.get(ogrenci=self.ogr1)
        self.assertEqual((u.kulup, u.gorev, u.egitim_yili), (self.tiyatro, KulupUyelik.GOREV_UYE, self.yil))
        self.assertFalse(KulupUyelik.objects.filter(ogrenci=self.ogr2).exists())

    def test_ayni_kulup_secilirse_gorev_korunur(self):
        KulupUyelik.objects.create(ogrenci=self.ogr1, kulup=self.satranc, gorev="baskan")
        self.assertEqual(self._kaydet({self.ogr1.pk: self.satranc.pk}), (0, 0, 0))
        self.assertEqual(KulupUyelik.objects.get(ogrenci=self.ogr1).gorev, "baskan")

    def test_baska_sinif_ve_pasif_ogrenci_yok_sayilir(self):
        pasif = ogrenci_olustur(9, "A", aktif=False)
        self._kaydet({self.baska_sinif.pk: self.satranc.pk, pasif.pk: self.satranc.pk})
        self.assertFalse(KulupUyelik.objects.exists())

    def test_pasif_kulube_yeni_uye_alinmaz_hicbir_sey_kaydedilmez(self):
        pasif = SosyalKulup.objects.create(ad="Eski Kulüp", aktif=False)
        with self.assertRaises(ValueError):
            self._kaydet({self.ogr1.pk: self.satranc.pk, self.ogr2.pk: pasif.pk})
        self.assertFalse(KulupUyelik.objects.exists())

    def test_pasif_kulupteki_mevcut_uye_korunabilir(self):
        eski = SosyalKulup.objects.create(ad="Eski Kulüp")
        KulupUyelik.objects.create(ogrenci=self.ogr1, kulup=eski)
        eski.aktif = False
        eski.save()
        self.assertEqual(self._kaydet({self.ogr1.pk: eski.pk}), (0, 0, 0))

    def test_gecmis_yil_kaydina_dokunulmaz(self):
        eski_yil = aktif_egitim_yili_olustur("2024-2025")
        KulupUyelik.objects.create(ogrenci=self.ogr1, kulup=self.tiyatro, egitim_yili=eski_yil)
        aktif_egitim_yili_olustur("2025-2026")
        self._kaydet({self.ogr1.pk: None})
        self._kaydet({self.ogr1.pk: self.satranc.pk})
        self.assertEqual(
            set(KulupUyelik.objects.values_list("egitim_yili__egitim_yili", "kulup__ad")),
            {("2024-2025", "Tiyatro Kulübü"), ("2025-2026", "Satranç Kulübü")},
        )


class OgrenciKulupBelirleViewTests(TestCase):
    url = reverse("sosyalkulup:ogrenci_kulup_belirle")

    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        self.ss_9a = sinif_sube_olustur(9, "A")
        self.ogr_9a = ogrenci_olustur(9, "A")
        self.ogr_9b = ogrenci_olustur(9, "B")

    def _rehber_ogretmen(self, sinif_sube):
        user = kullanici_olustur("ogretmen")
        ders_programi_olustur(
            personel_olustur(user=user), 1, sinif_sube, ders=ders_olustur("REHBERLİK VE YÖNLENDİRME")
        )
        return user

    def test_rehber_ogretmen_kendi_sinifini_gorur(self):
        self.client.force_login(self._rehber_ogretmen(self.ss_9a))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual([o.pk for o, _ in resp.context["satirlar"]], [self.ogr_9a.pk])
        self.assertFalse(resp.context["sinif_secimi"])

    def test_rehber_ogretmen_kulup_kaydeder(self):
        self.client.force_login(self._rehber_ogretmen(self.ss_9a))
        resp = self.client.post(self.url, {f"kulup_{self.ogr_9a.pk}": self.kulup.pk})
        self.assertRedirects(resp, self.url, fetch_redirect_response=False)
        u = KulupUyelik.objects.get(ogrenci=self.ogr_9a)
        self.assertEqual((u.kulup, u.egitim_yili), (self.kulup, self.yil))

    def test_rehber_ogretmen_baska_sinifa_yazamaz(self):
        ss_9b = sinif_sube_olustur(9, "B")
        self.client.force_login(self._rehber_ogretmen(self.ss_9a))
        # sinif_sube parametresi öğretmen için dikkate alınmaz
        self.client.post(
            self.url, {"sinif_sube": ss_9b.pk, f"kulup_{self.ogr_9b.pk}": self.kulup.pk}
        )
        self.assertFalse(KulupUyelik.objects.exists())

    def test_rehberligi_olmayan_ogretmen_yonlendirilir(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertRedirects(self.client.get(self.url), reverse("index"), fetch_redirect_response=False)
        self.client.post(self.url, {f"kulup_{self.ogr_9a.pk}": self.kulup.pk})
        self.assertFalse(KulupUyelik.objects.exists())

    def test_rehber_ogretmen_grubu_da_sinifi_yoksa_yonlendirilir(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        self.assertRedirects(self.client.get(self.url), reverse("index"), fetch_redirect_response=False)

    def test_mudur_yardimcisi_sinif_secerek_kaydeder(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["satirlar"], [])

        resp = self.client.post(
            self.url, {"sinif_sube": self.ss_9a.pk, f"kulup_{self.ogr_9a.pk}": self.kulup.pk}
        )
        self.assertRedirects(resp, f"{self.url}?sinif_sube={self.ss_9a.pk}", fetch_redirect_response=False)
        self.assertTrue(KulupUyelik.objects.filter(ogrenci=self.ogr_9a, kulup=self.kulup).exists())

    def test_gecersiz_deger_kaydedilmez(self):
        self.client.force_login(self._rehber_ogretmen(self.ss_9a))
        self.client.post(self.url, {f"kulup_{self.ogr_9a.pk}": "abc"})
        self.assertFalse(KulupUyelik.objects.exists())

    def test_aktif_yil_yoksa_kayit_yapilmaz(self):
        OkulBilgi.objects.update(okul_egtyil=None)
        self.client.force_login(self._rehber_ogretmen(self.ss_9a))
        resp = self.client.post(self.url, {f"kulup_{self.ogr_9a.pk}": self.kulup.pk}, follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(KulupUyelik.objects.exists())
