"""kurul — toplantı, gündem, katılım, karar, onay akışı, PDF'ler ve view'lar."""

import datetime

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse

from kurul.models import Karar, Katilim, Kurul, KurulTuru, Toplanti
from kurul.services import toplanti as ts
from kurul.services.toplanti_pdf import duyuru_pdf, karar_defteri_pdf, tutanak_pdf
from kurul.services.uyelik import uye_ekle
from okul.testing import (
    aktif_egitim_yili_olustur,
    kullanici_olustur,
    personel_olustur,
    zamani_dondur,
)

BUGUN = datetime.date(2025, 10, 6)


def _tur(kod, **kw):
    kw.setdefault("ad", kod)
    kw.setdefault("kategori", KurulTuru.KATEGORI_KURUL)
    kw.setdefault("mevzuat_dayanagi", "Test")
    return KurulTuru.objects.create(kod=kod, **kw)


class _Kurulum(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.kurul = Kurul.objects.create(
            tur=_tur("zumre", ad="Matematik Zümresi",
                     gundem_onerileri="Bir önceki toplantıda alınan kararlar\nPlanların incelenmesi\nOrtak sınavlar"),
            egitim_yili=self.yil,
        )
        self.baskan_user = kullanici_olustur("ogretmen")
        self.baskan = personel_olustur(user=self.baskan_user, adi_soyadi="Başkan Öğretmen")
        self.uye_user = kullanici_olustur("ogretmen")
        self.uye = personel_olustur(user=self.uye_user, adi_soyadi="Üye Öğretmen")
        uye_ekle(self.kurul, personel=self.baskan, gorev="baskan")
        uye_ekle(self.kurul, personel=self.uye, gorev="uye")
        self.myrd = kullanici_olustur("mudur_yardimcisi")
        self.mudur = kullanici_olustur("okul_muduru")

    def _toplanti(self, tarih=BUGUN, kurul=None):
        return ts.toplanti_olustur(kurul or self.kurul, tarih=tarih, saat=datetime.time(15, 0), yer="Öğretmenler odası")


class ToplantiServisTests(_Kurulum):
    def test_olusturma_numara_katilim_ve_sabit_gundem(self):
        t1 = self._toplanti()
        self.assertEqual(t1.no, 1)
        self.assertEqual(
            list(t1.katilimlar.values_list("ad", "gorev")),
            [("Başkan Öğretmen", "Başkan"), ("Üye Öğretmen", "Üye")],
        )
        self.assertEqual([m.baslik for m in t1.gundem.all()], [ts.ACILIS_MADDESI, ts.DILEK_MADDESI])

        t2 = self._toplanti(BUGUN + datetime.timedelta(days=30))
        self.assertEqual(t2.no, 2)
        self.assertEqual(ts.onceki_toplanti(t2), t1)
        basliklar = [m.baslik for m in t2.gundem.all()]
        self.assertEqual(basliklar, [ts.ACILIS_MADDESI, ts.ONCEKI_KARARLAR_MADDESI, ts.DILEK_MADDESI])
        self.assertTrue(t2.gundem.get(baslik=ts.ONCEKI_KARARLAR_MADDESI).onceki_kararlar)

    def test_iptal_edilen_onceki_toplanti_sayilmaz(self):
        t1 = self._toplanti()
        ts.durum_degistir(t1, "iptal", self.myrd)
        t2 = self._toplanti(BUGUN + datetime.timedelta(days=7))
        self.assertIsNone(ts.onceki_toplanti(t2))

    def test_gundem_ekle_tasi_sil(self):
        t = self._toplanti()
        self.assertEqual(ts.gundem_ekle(t, ["Planların incelenmesi", " ", "Ortak sınavlar", "Planların incelenmesi"]), 2)
        self.assertEqual(
            [m.baslik for m in t.gundem.all()],
            [ts.ACILIS_MADDESI, "Planların incelenmesi", "Ortak sınavlar", ts.DILEK_MADDESI],
        )
        ts.gundem_tasi(t.gundem.get(baslik="Ortak sınavlar"), -1)
        self.assertEqual([m.sira for m in t.gundem.all()], [1, 2, 3, 4])
        self.assertEqual(t.gundem.get(sira=2).baslik, "Ortak sınavlar")
        ts.gundem_sil(t.gundem.get(baslik="Ortak sınavlar"))
        self.assertEqual([m.sira for m in t.gundem.all()], [1, 2, 3])

    def test_katilim_ve_esitleme(self):
        t = self._toplanti()
        k = t.katilimlar.get(ad="Üye Öğretmen")
        ts.katilimi_kaydet(t, {k.pk: (Katilim.DURUM_MAZERETLI, "Raporlu")})
        k.refresh_from_db()
        self.assertEqual((k.durum, k.aciklama), (Katilim.DURUM_MAZERETLI, "Raporlu"))

        uye_ekle(self.kurul, personel=personel_olustur(adi_soyadi="Yeni Gelen"))
        self.assertEqual(ts.katilimi_esitle(t), 1)
        self.assertEqual(ts.katilimi_esitle(t), 0)

    def test_katilim_uye_cikarilsa_da_tutanakta_kalir(self):
        t = self._toplanti()
        self.kurul.uyeler.get(personel=self.uye).delete()
        self.assertTrue(t.katilimlar.filter(ad="Üye Öğretmen", uye=None).exists())

    def test_karar_numaralanir_ve_oy_cokluguna_oy_gerekir(self):
        t = self._toplanti()
        k1 = ts.karar_ekle(t, metin="Ortak sınav takvimi kabul edildi.")
        self.assertEqual((k1.no, k1.oylama_metni), (1, "Oy birliği"))
        with self.assertRaises(ValidationError):
            ts.karar_ekle(t, metin="Oy sayısı yok", oylama=Karar.OYLAMA_OYCOKLUGU)
        k2 = ts.karar_ekle(t, metin="Proje ödevi", oylama=Karar.OYLAMA_OYCOKLUGU, kabul=5, ret=2, cekimser=1)
        self.assertEqual(k2.no, 2)
        self.assertIn("5", k2.oylama_metni)

    def test_durum_akisi_ve_onay_yetkisi(self):
        t = self._toplanti()
        with zamani_dondur(BUGUN - datetime.timedelta(days=2), 9):
            ts.durum_degistir(t, "duyur", self.baskan_user)
        self.assertEqual(t.durum, Toplanti.DURUM_DUYURULDU)
        self.assertTrue(t.duyuru_suresi_yetersiz)

        with self.assertRaises(ValidationError):
            ts.durum_degistir(t, "onayla", self.mudur)  # önce yapılmalı
        with zamani_dondur(BUGUN, 17):
            ts.durum_degistir(t, "yapildi", self.baskan_user)
        with self.assertRaises(PermissionDenied):
            ts.durum_degistir(t, "onayla", self.baskan_user)
        ts.durum_degistir(t, "onayla", self.mudur)
        t.refresh_from_db()
        self.assertEqual((t.durum, t.onaylayan), (Toplanti.DURUM_ONAYLANDI, self.mudur))
        self.assertIsNotNone(t.onay_tarihi)

        # Onaylanan toplantı düzenlenemez; karar takibi sürer.
        with self.assertRaises(ValidationError):
            ts.gundem_ekle(t, ["Geç kalan madde"])
        with self.assertRaises(ValidationError):
            ts.karar_ekle(t, metin="Geç karar")

        ts.durum_degistir(t, "onayi_kaldir", self.mudur)
        self.assertEqual(t.durum, Toplanti.DURUM_YAPILDI)

    def test_ileri_tarihli_toplanti_yapildi_sayilamaz(self):
        t = self._toplanti(BUGUN + datetime.timedelta(days=3))
        with zamani_dondur(BUGUN, 10), self.assertRaises(ValidationError):
            ts.durum_degistir(t, "yapildi", self.myrd)

    def test_karar_takibi_onaydan_sonra_da_guncellenir(self):
        t = self._toplanti()
        k = ts.karar_ekle(t, metin="Karar")
        with zamani_dondur(BUGUN, 17):
            ts.durum_degistir(t, "yapildi", self.myrd)
        ts.durum_degistir(t, "onayla", self.mudur)
        ts.karar_takibi(k, Karar.TAKIP_TAMAM, "Uygulandı")
        k.refresh_from_db()
        self.assertEqual((k.takip_durumu, k.takip_notu), (Karar.TAKIP_TAMAM, "Uygulandı"))

    def test_gizli_kurulda_gundem_ve_karar_tutulmaz(self):
        gizli = Kurul.objects.create(tur=_tur("onur", ad="Onur Kurulu", gizli=True), egitim_yili=self.yil)
        uye_ekle(gizli, personel=self.uye, gorev="uye")
        t = self._toplanti(kurul=gizli)
        self.assertFalse(t.gundem.exists())
        self.assertEqual(t.katilimlar.count(), 1)
        with self.assertRaises(ValidationError):
            ts.gundem_ekle(t, ["Öğrenci X"])
        with self.assertRaises(ValidationError):
            ts.karar_ekle(t, metin="Karar")

    def test_yetkiler(self):
        self.assertTrue(ts.toplanti_yonetebilir(self.myrd, self.kurul))
        self.assertTrue(ts.toplanti_yonetebilir(self.baskan_user, self.kurul))
        self.assertFalse(ts.toplanti_yonetebilir(self.uye_user, self.kurul))
        self.assertTrue(ts.toplanti_gorebilir(self.uye_user, self.kurul))
        self.assertTrue(ts.toplanti_gorebilir(self.mudur, self.kurul))
        disaridan = kullanici_olustur("ogretmen")
        personel_olustur(user=disaridan)
        self.assertFalse(ts.toplanti_gorebilir(disaridan, self.kurul))
        self.assertTrue(ts.onaylayabilir(self.mudur))
        self.assertFalse(ts.onaylayabilir(self.baskan_user))

    def test_personel_toplantilari(self):
        with zamani_dondur(BUGUN, 9):
            self._toplanti(BUGUN - datetime.timedelta(days=10))
            yaklasan = self._toplanti(BUGUN + datetime.timedelta(days=5))
            self.assertEqual(list(ts.personel_toplantilari(self.uye, self.yil)), [yaklasan])
            self.assertEqual(ts.personel_toplantilari(self.uye, self.yil, yalnizca_yaklasan=False).count(), 2)
            self.assertFalse(ts.personel_toplantilari(personel_olustur(), self.yil).exists())


class ToplantiPdfTests(_Kurulum):
    def test_pdfler_uretilir(self):
        t1 = self._toplanti()
        ts.gundem_ekle(t1, ["Planların incelenmesi"])
        ts.karar_ekle(t1, metin="Planlar kabul edildi.", sorumlu=self.uye, termin=BUGUN)
        with zamani_dondur(BUGUN, 17):
            ts.durum_degistir(t1, "yapildi", self.myrd)
        ts.durum_degistir(t1, "onayla", self.mudur)
        t2 = self._toplanti(BUGUN + datetime.timedelta(days=30))
        for pdf in (duyuru_pdf(t1, "Test Lisesi"), tutanak_pdf(t1, "Test Lisesi", "Müdür"),
                    tutanak_pdf(t2, "Test Lisesi", ""), karar_defteri_pdf(self.kurul, "Test Lisesi")):
            self.assertTrue(pdf.startswith(b"%PDF"))

    def test_onay_tarihi_bos_olsa_da_tutanak_uretilir(self):
        """Durum admin panelinden 'onaylandı' yapılmış olabilir."""
        t = self._toplanti()
        Toplanti.objects.filter(pk=t.pk).update(durum=Toplanti.DURUM_ONAYLANDI)
        t.refresh_from_db()
        self.assertTrue(tutanak_pdf(t, "", "").startswith(b"%PDF"))

    def test_gizli_kurul_pdfleri(self):
        gizli = Kurul.objects.create(tur=_tur("onur", ad="Onur Kurulu", gizli=True), egitim_yili=self.yil)
        t = self._toplanti(kurul=gizli)
        self.assertTrue(duyuru_pdf(t, "").startswith(b"%PDF"))
        self.assertTrue(tutanak_pdf(t, "", "").startswith(b"%PDF"))


class ToplantiViewTests(_Kurulum):
    def test_baskan_ogretmen_toplanti_acar_ve_yonetir(self):
        self.client.force_login(self.baskan_user)
        url = reverse("kurul:toplantilar", args=[self.kurul.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["gorev_menu"]["aktif_sayfa"], "kurul:gorevlerim")

        resp = self.client.post(url, {"tarih": "2025-10-20", "saat": "15:00", "yer": "Kütüphane", "tur": "olagan"})
        t = Toplanti.objects.get()
        detay = reverse("kurul:toplanti_detay", args=[t.pk])
        self.assertRedirects(resp, detay)

        resp = self.client.get(detay)
        self.assertEqual(resp.context["oneriler"], ["Planların incelenmesi", "Ortak sınavlar"])
        self.client.post(detay, {"islem": "gundem_ekle", "oneri": ["Planların incelenmesi"], "baslik": "Serbest madde"})
        self.assertEqual(t.gundem.count(), 4)
        madde = t.gundem.get(baslik="Serbest madde")
        self.client.post(detay, {"islem": "gorusme", f"gorusme_{madde.pk}": "Görüşüldü."})
        madde.refresh_from_db()
        self.assertEqual(madde.gorusme, "Görüşüldü.")

        k = t.katilimlar.get(ad="Üye Öğretmen")
        self.client.post(detay, {"islem": "katilim", f"durum_{k.pk}": "katilmadi", f"aciklama_{k.pk}": ""})
        k.refresh_from_db()
        self.assertEqual(k.durum, "katilmadi")

        resp = self.client.post(detay, {"islem": "karar_ekle", "metin": "Oy çokluğu", "oylama": "oycoklugu"})
        self.assertEqual(resp.status_code, 200)  # form hatasıyla yeniden çizilir
        self.assertFalse(t.kararlar.exists())
        self.client.post(detay, {"islem": "karar_ekle", "metin": "Karar metni", "oylama": "oybirligi",
                                 "gundem_maddesi": madde.pk, "takip_durumu": "bekliyor"})
        self.assertEqual(t.kararlar.get().gundem_maddesi, madde)

        # Başkan onaylayamaz
        self.assertEqual(self.client.post(detay, {"islem": "onayla"}).status_code, 403)

        for yol in ("kurul:toplanti_duyuru_pdf", "kurul:toplanti_tutanak_pdf"):
            resp = self.client.get(reverse(yol, args=[t.pk]))
            self.assertTrue(resp.content.startswith(b"%PDF"))
        resp = self.client.get(reverse("kurul:karar_defteri", args=[self.kurul.pk]))
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_uye_goruntuler_ama_degistiremez_yabanci_goremez(self):
        t = self._toplanti()
        detay = reverse("kurul:toplanti_detay", args=[t.pk])
        self.client.force_login(self.uye_user)
        resp = self.client.get(detay)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.context["yonetebilir"])
        self.assertEqual(self.client.post(detay, {"islem": "gundem_ekle", "baslik": "X"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("kurul:toplantilar", args=[self.kurul.pk]), {}).status_code, 403)

        yabanci = kullanici_olustur("ogretmen")
        personel_olustur(user=yabanci)
        self.client.force_login(yabanci)
        self.assertEqual(self.client.get(detay).status_code, 403)
        self.assertEqual(self.client.get(reverse("kurul:toplanti_tutanak_pdf", args=[t.pk])).status_code, 403)

    def test_mudur_onaylar_onaydan_sonra_duzenleme_kapanir(self):
        t = self._toplanti()
        with zamani_dondur(BUGUN, 17):
            ts.durum_degistir(t, "yapildi", self.myrd)
        detay = reverse("kurul:toplanti_detay", args=[t.pk])
        self.client.force_login(self.mudur)
        self.client.post(detay, {"islem": "onayla"})
        t.refresh_from_db()
        self.assertEqual(t.durum, Toplanti.DURUM_ONAYLANDI)

        self.client.force_login(self.baskan_user)
        resp = self.client.get(detay)
        self.assertFalse(resp.context["yonetebilir"])
        self.assertTrue(resp.context["takip_edebilir"])
        resp = self.client.post(detay, {"islem": "gundem_ekle", "baslik": "Geç madde"}, follow=True)
        self.assertContains(resp, "düzenlenemez")

    def test_toplanti_takvimi_ve_gorevlerim(self):
        with zamani_dondur(BUGUN, 9):
            t = self._toplanti(BUGUN + datetime.timedelta(days=5))
            self.client.force_login(self.myrd)
            resp = self.client.get(reverse("kurul:toplanti_takvimi"))
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.context["yaklasan"], [t])
            self.assertEqual(resp.context["yonetim_menu"]["aktif_sayfa"], "kurul:toplanti_takvimi")

            self.client.force_login(self.uye_user)
            self.assertEqual(self.client.get(reverse("kurul:toplanti_takvimi")).status_code, 403)
            resp = self.client.get(reverse("kurul:gorevlerim"))
            self.assertContains(resp, "Matematik Zümresi — 1. toplantı")
