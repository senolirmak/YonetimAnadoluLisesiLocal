"""devamsizlik app testleri — öğretmenin ders yoklaması ve öğrenci devamsızlık raporları."""

import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from devamsizlik.models import OgrenciDevamsizlik
from okul.testing import (
    ders_programi_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_sube_olustur,
)

PAZARTESI = datetime.date(2025, 9, 8)
SALI = datetime.date(2025, 9, 9)
# okul.testing.ders_saati_olustur: N. ders → (8+N-1):00–:40. 3. ders = 10:00–10:40.
UCUNCU_DERS = 3


def _zamani_dondur(tarih, saat, dakika=0):
    """timezone.localdate()/localtime() argümansız çağrıldığında sabit zaman döndürür."""
    sabit = timezone.make_aware(datetime.datetime.combine(tarih, datetime.time(saat, dakika)))
    gercek_localtime = timezone.localtime

    def sahte_localtime(value=None, timezone=None):
        if value is None:
            return sabit
        return gercek_localtime(value, timezone)

    return mock.patch.multiple(
        "django.utils.timezone",
        localdate=mock.Mock(return_value=tarih),
        localtime=sahte_localtime,
    )


class YoklamaTestCase(TestCase):
    """9/A sınıfında Pazartesi 3. derse giren bir öğretmen ve üç öğrenci."""

    def setUp(self):
        self.user = kullanici_olustur("ogretmen")
        self.personel = personel_olustur(user=self.user)
        self.ders = ders_programi_olustur(self.personel, UCUNCU_DERS, sinif_sube_olustur(9, "A"))
        self.ogr1 = ogrenci_olustur(9, "A")
        self.ogr2 = ogrenci_olustur(9, "A")
        self.pasif = ogrenci_olustur(9, "A", aktif=False)
        ogrenci_olustur(10, "A")  # başka sınıf

        self.yonetici = kullanici_olustur("mudur_yardimcisi")
        self.yonetici_personel = personel_olustur(user=self.yonetici)
        ders_programi_olustur(
            self.yonetici_personel, UCUNCU_DERS, sinif_sube_olustur(9, "A"), gun="Tuesday"
        )

    def _url(self, ders_saati=None):
        if ders_saati:
            return reverse("devamsizlik:ogretmen_devamsizlik_ders", args=[ders_saati])
        return reverse("devamsizlik:ogretmen_devamsizlik")

    def test_personel_kaydi_olmayan_kullanici_ana_sayfaya_doner(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(self._url())
        self.assertRedirects(resp, reverse("index"), fetch_redirect_response=False)

    def test_ders_saatinde_aktif_ders_acilir_ve_sadece_aktif_ogrenciler_listelenir(self):
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 10, 15):
            resp = self.client.get(self._url())

        self.assertEqual(resp.context["durum"], "form")
        self.assertEqual(resp.context["secili_ders"], self.ders)
        self.assertEqual(list(resp.context["ogrenciler"]), [self.ogr1, self.ogr2])

    def test_ders_saati_disinda_ders_secim_ekrani_gelir(self):
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 13, 0):
            resp = self.client.get(self._url())

        self.assertEqual(resp.context["durum"], "ders_sec")
        self.assertIsNone(resp.context["aktif_ders"])

    def test_ders_saati_disinda_dogrudan_url_ile_acilamaz(self):
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 13, 0):
            resp = self.client.get(self._url(UCUNCU_DERS))

        self.assertEqual(resp.status_code, 302)

    def test_dersi_olmayan_gun(self):
        self.client.force_login(self.user)
        with _zamani_dondur(SALI, 10, 15):
            resp = self.client.get(self._url())

        self.assertEqual(resp.context["durum"], "ders_yok")

    def test_ogretmen_baska_gunu_secemez(self):
        self.client.force_login(self.user)
        with _zamani_dondur(SALI, 10, 15):
            resp = self.client.get(self._url(), {"tarih": PAZARTESI.isoformat()})

        self.assertEqual(resp.context["secili_tarih"], SALI)
        self.assertEqual(resp.context["durum"], "ders_yok")

    def test_yoklama_kaydedilir_ve_tekrar_kayitta_degistirilir(self):
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 10, 15):
            self.client.post(
                self._url(UCUNCU_DERS),
                {"tarih": PAZARTESI.isoformat(), "devamsiz": [self.ogr1.pk, self.ogr2.pk]},
            )
            self.assertEqual(OgrenciDevamsizlik.objects.count(), 2)
            kayit = OgrenciDevamsizlik.objects.get(ogrenci=self.ogr1)
            self.assertEqual(kayit.tarih, PAZARTESI)
            self.assertEqual(kayit.ders_saati.derssaati_no, UCUNCU_DERS)
            self.assertEqual(kayit.ogretmen_adi, self.personel.adi_soyadi)

            self.client.post(
                self._url(UCUNCU_DERS),
                {"tarih": PAZARTESI.isoformat(), "devamsiz": [self.ogr2.pk]},
            )

        self.assertEqual(
            list(OgrenciDevamsizlik.objects.values_list("ogrenci", flat=True)), [self.ogr2.pk]
        )

    def test_ogretmen_form_tarihini_degistirerek_baska_gune_yazamaz(self):
        OgrenciDevamsizlik.objects.create(
            ogrenci=self.ogr1, tarih=SALI, ders_saati=self.ders.ders_saati,
            ders_adi="X", ogretmen_adi="X",
        )
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 10, 15):
            self.client.post(
                self._url(UCUNCU_DERS),
                {"tarih": SALI.isoformat(), "devamsiz": [self.ogr2.pk]},
            )

        # Kayıt bugüne (Pazartesi) yazıldı; Salı'nın kaydı silinmedi.
        self.assertEqual(
            set(OgrenciDevamsizlik.objects.values_list("ogrenci", "tarih")),
            {(self.ogr1.pk, SALI), (self.ogr2.pk, PAZARTESI)},
        )

    def test_yonetici_gecmis_gunun_yoklamasini_kaydedebilir(self):
        self.client.force_login(self.yonetici)
        with _zamani_dondur(PAZARTESI, 13, 0):
            self.client.post(
                self._url(UCUNCU_DERS) + f"?tarih={SALI.isoformat()}",
                {"tarih": SALI.isoformat(), "devamsiz": [self.ogr1.pk]},
            )

        kayit = OgrenciDevamsizlik.objects.get()
        self.assertEqual((kayit.ogrenci, kayit.tarih), (self.ogr1, SALI))

    def test_pasif_ogrenci_post_ile_devamsiz_yazilamaz(self):
        self.client.force_login(self.user)
        with _zamani_dondur(PAZARTESI, 10, 15):
            self.client.post(
                self._url(UCUNCU_DERS),
                {"tarih": PAZARTESI.isoformat(), "devamsiz": [self.pasif.pk]},
            )

        self.assertFalse(OgrenciDevamsizlik.objects.exists())

    def test_yonetici_gecmis_gunun_yoklamasini_acabilir(self):
        self.client.force_login(self.yonetici)
        with _zamani_dondur(PAZARTESI, 13, 0):
            resp = self.client.get(self._url(UCUNCU_DERS), {"tarih": SALI.isoformat()})

        self.assertEqual(resp.context["durum"], "form")
        self.assertEqual(resp.context["secili_tarih"], SALI)


class DevamsizlikListesiTestCase(TestCase):
    def setUp(self):
        self.url = reverse("devamsizlik:ogrenci_devamsizlik_listesi")
        self.ogr_9a = ogrenci_olustur(9, "A", adi="Zeynep")
        self.ogr_10b = ogrenci_olustur(10, "B", adi="Mehmet")
        self.normal = OgrenciDevamsizlik.objects.create(
            ogrenci=self.ogr_9a, tarih=PAZARTESI, ders_adi="Matematik", ogretmen_adi="X"
        )
        self.faaliyet = OgrenciDevamsizlik.objects.create(
            ogrenci=self.ogr_10b,
            tarih=PAZARTESI,
            ders_adi="Fizik",
            ogretmen_adi="Y",
            aciklama="Faaliyet: Gezi",
        )
        self.arsiv = OgrenciDevamsizlik.objects.create(
            ogrenci=self.ogr_9a,
            tarih=datetime.date(2024, 10, 1),
            ders_adi="Kimya",
            ogretmen_adi="Z",
            arsivlendi=True,
        )
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

    def _liste(self, **params):
        return set(self.client.get(self.url, params).context["devamsizliklar"])

    def test_yetkisiz_kullanici_yonlendirilir(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertRedirects(self.client.get(self.url), reverse("index"), fetch_redirect_response=False)

    def test_varsayilan_liste_arsivi_gizler(self):
        self.assertEqual(self._liste(), {self.normal, self.faaliyet})

    def test_tarih_filtresi_arsivi_de_arar(self):
        self.assertEqual(self._liste(tarih_bas="2024-09-01", tarih_bit="2024-12-31"), {self.arsiv})

    def test_sinif_sube_ogrenci_ve_kaynak_filtreleri(self):
        self.assertEqual(self._liste(sinifsube="10/b"), {self.faaliyet})
        self.assertEqual(self._liste(ogrenci="zeyn"), {self.normal})
        self.assertEqual(self._liste(ogrenci=str(self.ogr_10b.okulno)), {self.faaliyet})
        self.assertEqual(self._liste(kaynak="faaliyet"), {self.faaliyet})
        self.assertEqual(self._liste(kaynak="normal"), {self.normal})


class DevamsizlikPdfTestCase(TestCase):
    def setUp(self):
        self.url = reverse("devamsizlik:ogrenci_devamsizlik_pdf")
        ogr = ogrenci_olustur(9, "A")
        OgrenciDevamsizlik.objects.create(
            ogrenci=ogr, tarih=PAZARTESI, ders_adi="Matematik", ogretmen_adi="X"
        )

    def test_rehber_ogretmen_rapor_alamaz(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_okul_muduru_pdf_indirir(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.post(
            self.url, {"tarih_bas": "2025-09-01", "tarih_bit": "2025-09-30", "sinif": ["9"]}
        )

        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_kayit_yoksa_form_uyariyla_doner(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.post(
            self.url, {"tarih_bas": "2025-09-01", "tarih_bit": "2025-09-30", "sinif": ["12"]}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "devamsizlik/ogrenci_devamsizlik_pdf_form.html")
