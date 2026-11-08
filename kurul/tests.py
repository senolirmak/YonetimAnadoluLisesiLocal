"""kurul — katalog, yıl kurulumu, üyelik servisleri ve view'lar."""

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from kurul.models import Kurul, KurulTuru, KurulUyesi
from kurul.services.katalog import katalog_bossa_yukle, katalogu_yukle
from kurul.services.kurulum import acilmamis_turler, yil_kurulumu
from kurul.services.uyelik import (
    gorev_yuku,
    otomatik_uyeleri_uygula,
    personel_uyelikleri,
    uye_ekle,
)
from okul.models import Brans
from okul.testing import (
    aktif_egitim_yili_olustur,
    ders_programi_olustur,
    kullanici_olustur,
    ogrenci_olustur,
    personel_olustur,
    sinif_sube_olustur,
)


def _tur(kod, **kw):
    kw.setdefault("ad", kod)
    kw.setdefault("kategori", KurulTuru.KATEGORI_KURUL)
    kw.setdefault("mevzuat_dayanagi", "Test")
    return KurulTuru.objects.create(kod=kod, **kw)


class KatalogTests(TestCase):
    def test_katalog_yuklenir_ve_tekrar_yuklemede_ezilmez(self):
        s = katalogu_yukle()
        self.assertGreater(s["eklenen"], 20)
        tur = KurulTuru.objects.get(kod="ogretmenler-kurulu")
        self.assertEqual(tur.otomatik_uyelik, KurulTuru.OTOMATIK_TUM_PERSONEL)
        tur.ad = "Okulun düzenlediği ad"
        tur.save()
        s2 = katalogu_yukle()
        self.assertEqual((s2["eklenen"], s2["atlanan"]), (0, s["eklenen"]))
        tur.refresh_from_db()
        self.assertEqual(tur.ad, "Okulun düzenlediği ad")
        katalogu_yukle(guncelle=True)
        tur.refresh_from_db()
        self.assertEqual(tur.ad, "Öğretmenler Kurulu")

    def test_katalog_metinleri_alan_sinirlarini_asmaz(self):
        """SQLite uzunluk sınırını uygulamaz; PostgreSQL uygular. Katalog burada denetlenir."""
        import json

        from kurul.models import KurulYapiKalemi
        from kurul.services.katalog import KATALOG_DOSYASI

        for kayit in json.loads(KATALOG_DOSYASI.read_text(encoding="utf-8")):
            for model, veri in [(KurulTuru, kayit)] + [(KurulYapiKalemi, y) for y in kayit["yapi"]]:
                for alan in model._meta.fields:
                    deger = veri.get(alan.name)
                    if alan.max_length and isinstance(deger, str):
                        with self.subTest(kod=kayit["kod"], alan=alan.name):
                            self.assertLessEqual(len(deger), alan.max_length)

    def test_bossa_yukle_yalnizca_bos_tabloda(self):
        self.assertTrue(katalog_bossa_yukle())
        self.assertFalse(katalog_bossa_yukle())

    def test_katalogdaki_kodlar_ve_kapsamlar(self):
        katalogu_yukle()
        self.assertEqual(KurulTuru.objects.get(kod="sube-ogretmenler-kurulu").kapsam, KurulTuru.KAPSAM_SUBE)
        self.assertEqual(KurulTuru.objects.get(kod="zumre-ogretmenler-kurulu").kapsam, KurulTuru.KAPSAM_BRANS)
        self.assertTrue(KurulTuru.objects.get(kod="odul-disiplin-kurulu").gizli)


class YilKurulumuTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        katalogu_yukle()
        self.mat = Brans.objects.create(ad="Matematik")
        self.fiz = Brans.objects.create(ad="Fizik")
        self.mudur = personel_olustur(gorev_tipi="Okul Müdürü")
        self.myrd = personel_olustur(gorev_tipi="Müdür Yardımcısı", brans=self.mat)
        self.ogr1 = personel_olustur(gorev_tipi="Öğretmen", brans=self.mat)
        self.ogr2 = personel_olustur(gorev_tipi="Öğretmen", brans=self.fiz)
        self.rehber = personel_olustur(gorev_tipi="Rehberlik")
        self.emekli = personel_olustur(gorev_tipi="Öğretmen", brans=self.mat, durum="Emekli")
        self.a9 = sinif_sube_olustur(9, "A")
        ders_programi_olustur(self.ogr1, 1, self.a9)

    def _kurul(self, kod, **kapsam):
        return Kurul.objects.get(tur__kod=kod, egitim_yili=self.yil, **kapsam)

    def _uye_idleri(self, kurul):
        return set(kurul.uyeler.values_list("personel_id", flat=True))

    def test_butun_kurullar_iskelet_olarak_acilir_otomatik_uyeler_eklenir(self):
        yil_kurulumu(self.yil)
        self.assertFalse(acilmamis_turler(self.yil).exists())
        # Okul geneli 27 tür + 1 şube kurulu + 2 zümre kurulu
        self.assertEqual(Kurul.objects.filter(egitim_yili=self.yil).count(), 27 + 1 + 2)

        ok = self._kurul("ogretmenler-kurulu")
        self.assertEqual(self._uye_idleri(ok),
                         {self.mudur.pk, self.myrd.pk, self.ogr1.pk, self.ogr2.pk, self.rehber.pk})
        self.assertEqual(ok.uyeler.get(gorev=KurulUyesi.GOREV_BASKAN).personel, self.mudur)

        sube = self._kurul("sube-ogretmenler-kurulu", sinif_sube=self.a9)
        self.assertEqual(self._uye_idleri(sube), {self.ogr1.pk, self.rehber.pk})

        # Zümre: branştaki öğretmenler; yönetici görevdekiler ve emekliler hariç
        self.assertEqual(self._uye_idleri(self._kurul("zumre-ogretmenler-kurulu", brans=self.mat)), {self.ogr1.pk})
        self.assertEqual(self._uye_idleri(self._kurul("zumre-ogretmenler-kurulu", brans=self.fiz)), {self.ogr2.pk})

        # Seçimle doldurulan kurullar boş iskelet olarak açılır
        self.assertFalse(self._kurul("ihale-komisyonu").uyeler.exists())

    def test_kurulum_tekrar_calisinca_bir_sey_degismez_ve_elle_degisiklik_korunur(self):
        yil_kurulumu(self.yil)
        ok = self._kurul("ogretmenler-kurulu")
        ok.uyeler.filter(personel=self.ogr2).delete()  # elle çıkarıldı
        s = yil_kurulumu(self.yil)
        self.assertEqual(s["acilan"], 0)
        # Otomatik uygulama çıkarılan kişiyi yeniden ekler — bu bilinçli bir işlemdir
        self.assertEqual(s["otomatik_uye"], 1)

    def test_zumre_baskanlari_kurulu_baskanlardan_olusur(self):
        yil_kurulumu(self.yil)
        zb = self._kurul("zumre-baskanlari-kurulu")
        self.assertEqual(zb.uyeler.count(), 0)
        zumre = self._kurul("zumre-ogretmenler-kurulu", brans=self.mat)
        zumre.uyeler.filter(personel=self.ogr1).update(gorev=KurulUyesi.GOREV_BASKAN)
        self.assertEqual(otomatik_uyeleri_uygula(zb), 1)
        self.assertEqual(self._uye_idleri(zb), {self.ogr1.pk})


class UyelikTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.tur = _tur("kantin", kategori=KurulTuru.KATEGORI_KOMISYON)
        self.kurul = Kurul.objects.create(tur=self.tur, egitim_yili=self.yil)
        self.p = personel_olustur()

    def test_personel_ogrenci_ve_dis_uye_eklenir(self):
        uye_ekle(self.kurul, personel=self.p, gorev=KurulUyesi.GOREV_BASKAN)
        uye_ekle(self.kurul, ogrenci=ogrenci_olustur(10, "B"))
        u = uye_ekle(self.kurul, dis_uye="  Okul-Aile Birliği temsilcisi (veli) ", asil=False)
        self.assertEqual(u.dis_uye, "Okul-Aile Birliği temsilcisi (veli)")
        self.assertEqual(self.kurul.uyeler.count(), 3)

    def test_ayni_kisi_iki_kez_eklenemez(self):
        uye_ekle(self.kurul, personel=self.p)
        with self.assertRaises(ValidationError):
            uye_ekle(self.kurul, personel=self.p)

    def test_uye_tek_kaynaktan_olmali(self):
        with self.assertRaises(ValidationError):
            uye_ekle(self.kurul)
        with self.assertRaises(ValidationError):
            uye_ekle(self.kurul, personel=self.p, dis_uye="Veli")

    def test_gorev_yuku_otomatik_kurullari_saymaz(self):
        otomatik = Kurul.objects.create(
            tur=_tur("ok", otomatik_uyelik=KurulTuru.OTOMATIK_TUM_PERSONEL), egitim_yili=self.yil
        )
        uye_ekle(otomatik, personel=self.p)
        diger = personel_olustur()
        uye_ekle(self.kurul, personel=diger)
        satirlar = gorev_yuku(self.yil)
        self.assertEqual(satirlar[0]["personel"], diger)
        self.assertEqual(len(satirlar[0]["gorevler"]), 1)
        p_satiri = next(s for s in satirlar if s["personel"] == self.p)
        self.assertEqual(p_satiri["gorevler"], [])

    def test_personel_uyelikleri_yila_gore(self):
        uye_ekle(self.kurul, personel=self.p)
        eski = aktif_egitim_yili_olustur("2024-2025")
        aktif_egitim_yili_olustur("2025-2026")
        Kurul.objects.create(tur=_tur("eski"), egitim_yili=eski).uyeler.create(personel=self.p)
        self.assertEqual([u.kurul for u in personel_uyelikleri(self.p, self.yil)], [self.kurul])


class KurulViewTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        self.myrd = kullanici_olustur("mudur_yardimcisi")
        personel_olustur(user=self.myrd)

    def test_yonetim_sayfalari_yalnizca_mudur_yardimcisina(self):
        for grup in ("ogretmen", "okul_muduru", "rehber_ogretmen"):
            with self.subTest(grup=grup):
                self.client.force_login(kullanici_olustur(grup))
                self.assertEqual(self.client.get(reverse("kurul:index")).status_code, 403)

    def test_ilk_acilista_katalog_yuklenir_ve_menu_gorunur(self):
        self.client.force_login(self.myrd)
        resp = self.client.get(reverse("kurul:index"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(KurulTuru.objects.exists())
        self.assertContains(resp, "Öğretmenler Kurulu")
        self.assertEqual(resp.context["yonetim_menu"]["aktif_sayfa"], "kurul:index")

    def test_yil_kurulumu_ve_uye_islemleri(self):
        katalogu_yukle()
        p = personel_olustur()
        self.client.force_login(self.myrd)
        self.client.post(reverse("kurul:yil_kurulumu"))
        kurul = Kurul.objects.get(tur__kod="kantin-denetleme-komisyonu")
        url = reverse("kurul:kurul_detay", args=[kurul.pk])

        resp = self.client.post(url, {"islem": "uye_ekle", "uye_turu": "personel", "personel": p.pk,
                                      "gorev": "baskan", "asil": "on"})
        self.assertRedirects(resp, url)
        uye = kurul.uyeler.get()
        self.assertEqual((uye.personel, uye.gorev, uye.asil), (p, "baskan", True))

        self.client.post(url, {"islem": "gorev", "uye": uye.pk, "gorev": "uye", "asil": "0"})
        uye.refresh_from_db()
        self.assertEqual((uye.gorev, uye.asil), ("uye", False))

        resp = self.client.post(url, {"islem": "uye_ekle", "uye_turu": "dis", "dis_uye": "", "gorev": "uye"})
        self.assertContains(resp, "Dış üyenin unvanını")

        self.client.post(url, {"islem": "cikar", "uye": uye.pk})
        self.assertFalse(kurul.uyeler.exists())

    def test_gorevlendirme_pdf(self):
        katalogu_yukle()
        yil_kurulumu(self.yil)
        self.client.force_login(self.myrd)
        resp = self.client.get(reverse("kurul:gorevlendirme_pdf"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_ogretmen_kendi_gorevlerini_gorur(self):
        ogretmen = kullanici_olustur("ogretmen")
        p = personel_olustur(user=ogretmen)
        kurul = Kurul.objects.create(tur=_tur("tk", ad="Tören ve Kutlama"), egitim_yili=self.yil)
        uye_ekle(kurul, personel=p, gorev="baskan")
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("kurul:gorevlerim"))
        self.assertContains(resp, "Tören ve Kutlama")
        self.assertEqual(resp.context["gorev_menu"]["aktif_sayfa"], "kurul:gorevlerim")
        resp = self.client.get(reverse("gorevlerim"))
        self.assertContains(resp, "Tören ve Kutlama — Başkan")
        self.assertContains(resp, reverse("kurul:gorevlerim"))


class YapiTests(TestCase):
    def setUp(self):
        self.yil = aktif_egitim_yili_olustur("2025-2026")
        katalogu_yukle()
        self.myrd = personel_olustur(gorev_tipi="Müdür Yardımcısı")
        self.o1 = personel_olustur(gorev_tipi="Öğretmen")
        self.o2 = personel_olustur(gorev_tipi="Öğretmen")
        self.o3 = personel_olustur(gorev_tipi="Öğretmen")
        self.ogrenci = ogrenci_olustur(12, "A")

    def _kurul(self, kod):
        return Kurul.objects.create(tur=KurulTuru.objects.get(kod=kod), egitim_yili=self.yil)

    def test_29_turun_hepsinin_yapisi_var(self):
        self.assertEqual(KurulTuru.objects.count(), 29)
        self.assertFalse(KurulTuru.objects.filter(yapi__isnull=True).exists())
        disiplin = list(KurulTuru.objects.get(kod="odul-disiplin-kurulu").yapi.all())
        self.assertEqual(disiplin[0].gorev, "baskan")
        self.assertEqual(disiplin[0].personel_secimi, "mudur_yardimcisi")
        self.assertEqual((disiplin[1].asil_sayisi, disiplin[1].yedek_sayisi), (2, 2))

    def test_personel_secenekleri_kaleme_gore_daralir(self):
        from kurul.services.uyelik import personel_secenekleri

        baskan, ogretmen = list(KurulTuru.objects.get(kod="odul-disiplin-kurulu").yapi.all())[:2]
        self.assertEqual(list(personel_secenekleri(baskan)), [self.myrd])
        self.assertNotIn(self.myrd, personel_secenekleri(ogretmen))

    def test_yapi_formu_kaydedilir_ve_doluluk_hesaplanir(self):
        from kurul.forms import KurulYapiFormu
        from kurul.services.uyelik import yapi_doluluk, yapiyi_kaydet

        kurul = self._kurul("odul-disiplin-kurulu")
        b, ogr, onur, oab = kurul.tur.yapi.all()
        self.assertEqual(yapi_doluluk(kurul), {"dolu": 0, "gereken": 5})
        form = KurulYapiFormu(kurul, {
            f"k{b.pk}_asil_0": self.myrd.pk,
            f"k{ogr.pk}_asil_0": self.o1.pk, f"k{ogr.pk}_asil_1": self.o2.pk, f"k{ogr.pk}_yedek_0": self.o3.pk,
            f"k{onur.pk}_asil_0": self.ogrenci.pk,
            f"k{oab.pk}_asil_0": "Okul-Aile Birliği temsilcisi",
        })
        self.assertTrue(form.is_valid(), form.errors)
        yapiyi_kaydet(kurul, form.secimler())
        self.assertEqual(yapi_doluluk(kurul), {"dolu": 5, "gereken": 5})
        self.assertEqual(kurul.uyeler.get(gorev="baskan").personel, self.myrd)
        self.assertFalse(kurul.uyeler.get(personel=self.o3).asil)
        self.assertEqual(kurul.uyeler.get(kalem=oab).dis_uye, "Okul-Aile Birliği temsilcisi")

        # Yeniden açılan form mevcut üyelerle dolu gelir; bir kişi çıkarılınca kuruldan silinir
        form = KurulYapiFormu(kurul)
        self.assertEqual(form.fields[f"k{ogr.pk}_asil_1"].initial, self.o2.pk)
        yapiyi_kaydet(kurul, {ogr: {"asil": [self.o1, None], "yedek": [None, None]}})
        self.assertFalse(kurul.uyeler.filter(personel__in=[self.o2, self.o3]).exists())
        self.assertEqual(kurul.uyeler.count(), 4)

    def test_ayni_kisi_iki_yere_secilemez(self):
        from kurul.services.uyelik import yapiyi_kaydet

        kurul = self._kurul("toren-kutlama-komisyonu")
        b, ogr, _ = kurul.tur.yapi.all()
        with self.assertRaises(ValidationError):
            yapiyi_kaydet(kurul, {b: {"asil": [self.o1], "yedek": []}, ogr: {"asil": [self.o1, None], "yedek": []}})
        self.assertFalse(kurul.uyeler.exists())

    def test_otomatik_uye_baskan_secilince_tasinir_birakilinca_geri_doner(self):
        from kurul.services.uyelik import yapiyi_kaydet

        brans = Brans.objects.create(ad="Kimya")
        for p in (self.o1, self.o2):
            p.brans = brans
            p.save()
        kurul = Kurul.objects.create(tur=KurulTuru.objects.get(kod="zumre-ogretmenler-kurulu"),
                                     egitim_yili=self.yil, brans=brans)
        otomatik_uyeleri_uygula(kurul)
        baskan_kalemi = kurul.tur.yapi.get(gorev="baskan")
        yapiyi_kaydet(kurul, {baskan_kalemi: {"asil": [self.o1], "yedek": []}})
        self.assertEqual(kurul.uyeler.filter(personel=self.o1).count(), 1)
        self.assertEqual(kurul.uyeler.get(personel=self.o1).gorev, "baskan")
        yapiyi_kaydet(kurul, {baskan_kalemi: {"asil": [None], "yedek": []}})
        uye = kurul.uyeler.get(personel=self.o1)
        self.assertEqual((uye.gorev, uye.kalem.otomatik), ("uye", True))

    def test_kurul_sayfasindan_yapi_kaydi_ve_yapilar_listesi(self):
        kullanici = kullanici_olustur("mudur_yardimcisi")
        personel_olustur(user=kullanici)
        self.client.force_login(kullanici)
        kurul = self._kurul("kantin-denetleme-komisyonu")
        b = kurul.tur.yapi.get(gorev="baskan")
        url = reverse("kurul:kurul_detay", args=[kurul.pk])
        resp = self.client.get(url)
        self.assertContains(resp, "Kurul Yapısı — Başkan ve Üyeler")
        self.assertContains(resp, "Sağlık bilgisi / biyoloji öğretmeni (tercihen)")
        resp = self.client.post(url, {"islem": "yapi", f"k{b.pk}_asil_0": self.myrd.pk})
        self.assertRedirects(resp, url)
        self.assertEqual(kurul.uyeler.get().personel, self.myrd)

        resp = self.client.get(reverse("kurul:katalog"))
        self.assertContains(resp, "Kurul ve Komisyon Yapıları")
        self.assertContains(resp, "Okul meclisi başkanı veya yardımcısı")


class OnerilenBaskanTests(TestCase):
    def setUp(self):
        from okul.models import SinifSeviyesiSorumlusu

        self.yil = aktif_egitim_yili_olustur("2025-2026")
        katalogu_yukle()
        self.mudur = personel_olustur(gorev_tipi="Okul Müdürü")
        self.myrd9 = personel_olustur(gorev_tipi="Müdür Yardımcısı")
        self.myrd10 = personel_olustur(gorev_tipi="Müdür Yardımcısı")
        self.ogr = personel_olustur(gorev_tipi="Öğretmen")
        self.a9, self.a10, self.a11 = sinif_sube_olustur(9, "A"), sinif_sube_olustur(10, "A"), sinif_sube_olustur(11, "A")
        for ss in (self.a9, self.a10, self.a11):
            ders_programi_olustur(self.ogr, 1, ss)
        SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=9, personel=self.myrd9)
        SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=10, personel=self.myrd10)

    def _sube(self, ss):
        return Kurul.objects.get(tur__kod="sube-ogretmenler-kurulu", egitim_yili=self.yil, sinif_sube=ss)

    def _baskan(self, kurul):
        u = kurul.uyeler.filter(gorev="baskan").first()
        return u.personel if u else None

    def test_yil_kurulumu_sube_kuruluna_seviye_sorumlusunu_baskan_yapar(self):
        yil_kurulumu(self.yil)
        self.assertEqual(self._baskan(self._sube(self.a9)), self.myrd9)
        self.assertEqual(self._baskan(self._sube(self.a10)), self.myrd10)
        # Sorumlusu tanımlanmamış seviye boş kalır
        self.assertIsNone(self._baskan(self._sube(self.a11)))
        # Başkan yapının başkan kalemindedir; üyeler otomatik kalemde
        kurul = self._sube(self.a9)
        self.assertEqual(kurul.uyeler.get(personel=self.myrd9).kalem.gorev, "baskan")
        self.assertTrue(kurul.uyeler.get(personel=self.ogr).kalem.otomatik)
        # Öğretmenler kurulunun başkanı müdür
        ok = Kurul.objects.get(tur__kod="ogretmenler-kurulu", egitim_yili=self.yil)
        self.assertEqual(self._baskan(ok), self.mudur)

    def test_secilmis_baskana_dokunulmaz(self):
        from kurul.services.uyelik import yapiyi_kaydet

        yil_kurulumu(self.yil)
        kurul = self._sube(self.a9)
        baskan_kalemi = kurul.tur.yapi.get(gorev="baskan")
        yapiyi_kaydet(kurul, {baskan_kalemi: {"asil": [self.myrd10], "yedek": []}})
        otomatik_uyeleri_uygula(kurul)
        self.assertEqual(self._baskan(kurul), self.myrd10)
        self.assertEqual(kurul.uyeler.filter(gorev="baskan").count(), 1)

    def test_tur_sayfasindan_onerilerle_tamamlanir(self):
        from okul.models import SinifSeviyesiSorumlusu

        yil_kurulumu(self.yil)
        SinifSeviyesiSorumlusu.objects.create(egitim_yili=self.yil, sinif=11, personel=self.myrd10)
        kullanici = kullanici_olustur("mudur_yardimcisi")
        personel_olustur(user=kullanici)
        self.client.force_login(kullanici)
        url = reverse("kurul:tur_detay", args=["sube-ogretmenler-kurulu"])
        resp = self.client.get(url)
        self.assertContains(resp, f"Öneri: {self.myrd10.adi_soyadi}")
        resp = self.client.post(reverse("kurul:tur_tamamla", args=["sube-ogretmenler-kurulu"]))
        self.assertRedirects(resp, url)
        self.assertEqual(self._baskan(self._sube(self.a11)), self.myrd10)
