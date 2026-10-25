"""nobet app testleri.

Sahte veri `okul.testing` yardımcılarıyla üretilir. Kapsam:
  - NobetGorevi.objects.aktif() (arşiv + aktif nöbet tarihi)
  - ders doldurma sorgu yardımcıları (nobet/views/ders_doldurma/_queries.py)
  - yetki kontrolleri (nöbet dağıtım, ders doldurma, günün nöbetçileri, manuel dağıtım)
  - haftalık rotasyon akışı (önizle → kaydet / iptal)
  - ders doldurma akışı (hesapla → kaydet → sil)
  - manuel dağıtım kaydı
  - günün nöbetçileri yer değişikliği (kaydet / sıfırla)

Algoritmanın (AdvancedNobetDagitim) kendisi utility/tests.py içinde test ediliyor.
"""

import datetime

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from nobet.models import (
    GunlukNobetCizelgesi,
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
)
from nobet.views.ders_doldurma._queries import (
    aktif_devamsizliklar,
    aktif_gorev_tarihi,
    ders_programi_by_ogretmenler,
    en_son_kayit_dt,
)
from okul.testing import (
    ders_programi_olustur,
    devamsizlik_olustur,
    kullanici_olustur,
    nobet_gorevi_olustur,
    nobet_ogretmen_olustur,
    nobet_yeri_olustur,
    personel_olustur,
    sinif_sube_olustur,
)
from okul.utils import set_aktif_tarih

PAZARTESI = datetime.date(2025, 9, 8)
LISTE_TARIHI = datetime.date(2025, 9, 1)


def _gun_ici(tarih, saat=10):
    return timezone.make_aware(datetime.datetime.combine(tarih, datetime.time(saat, 0)))


# ─────────────────────────────────────────────────────────────
# Model / QuerySet
# ─────────────────────────────────────────────────────────────


class NobetGoreviAktifTestCase(TestCase):
    def test_arsivlenmis_gorevler_haric_tutulur(self):
        aktif = nobet_gorevi_olustur()
        nobet_gorevi_olustur(arsivlendi=True)

        self.assertEqual(list(NobetGorevi.objects.aktif()), [aktif])

    def test_aktif_tarih_yoksa_en_guncel_liste_kullanilir(self):
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 9, 1))
        yeni = nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 10, 1))

        self.assertEqual(list(NobetGorevi.objects.aktif()), [yeni])

    def test_aktif_tarih_konfigurasyonu_onceliklidir(self):
        eski = nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 9, 1))
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 10, 1))
        # set_aktif_tarih geriye dönük tarihi kabul etmez; ilk kayıt olduğu için yazılır.
        set_aktif_tarih("nobet_listesi", datetime.date(2025, 9, 1))

        self.assertEqual(list(NobetGorevi.objects.aktif()), [eski])

    def test_eski_yilin_arsivlenmis_listesi_aktif_sayilmaz(self):
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2024, 9, 1), arsivlendi=True)

        self.assertFalse(NobetGorevi.objects.aktif().exists())


# ─────────────────────────────────────────────────────────────
# Ders doldurma sorgu yardımcıları
# ─────────────────────────────────────────────────────────────


class DersDoldurmaSorgulariTestCase(TestCase):
    def setUp(self):
        self.ogretmen = nobet_ogretmen_olustur()

    def test_aktif_devamsizliklar_tarih_araligina_bakar(self):
        kayit = devamsizlik_olustur(self.ogretmen, PAZARTESI, sure=3)

        self.assertEqual(aktif_devamsizliklar(PAZARTESI + datetime.timedelta(days=2)), [kayit])
        self.assertEqual(aktif_devamsizliklar(PAZARTESI + datetime.timedelta(days=3)), [])
        self.assertEqual(aktif_devamsizliklar(PAZARTESI - datetime.timedelta(days=1)), [])

    def test_aktif_devamsizliklar_gorevlendirme_filtresi(self):
        devamsizlik_olustur(self.ogretmen, PAZARTESI, gorevlendirme_yapilsin=False)

        self.assertEqual(len(aktif_devamsizliklar(PAZARTESI)), 1)
        self.assertEqual(aktif_devamsizliklar(PAZARTESI, sadece_gorevlendirilebilir=True), [])

    def test_aktif_gorev_tarihi_arsivi_ve_gelecegi_yok_sayar(self):
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 9, 1))
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 9, 5), arsivlendi=True)
        nobet_gorevi_olustur(uygulama_tarihi=datetime.date(2025, 12, 1))

        self.assertEqual(aktif_gorev_tarihi(PAZARTESI), datetime.date(2025, 9, 1))

    def test_ders_programi_by_ogretmenler_saat_sinif_haritasi(self):
        p = self.ogretmen.personel
        ders_programi_olustur(p, 1, sinif_sube_olustur(9, "A"))
        ders_programi_olustur(p, 3, sinif_sube_olustur(10, "B"))
        ders_programi_olustur(p, 2, gun="Tuesday")

        sonuc = ders_programi_by_ogretmenler([p.pk], "Monday", LISTE_TARIHI)

        self.assertEqual(sonuc, {p.pk: {1: "9/A", 3: "10/B"}})

    def test_en_son_kayit_dt_arsivlenmisleri_yok_sayar(self):
        NobetGecmisi.objects.create(
            saat=1, sinif="9/A", devamsiz=1, tarih=_gun_ici(PAZARTESI, 9), ogretmen=self.ogretmen
        )
        NobetAtanamayan.objects.create(
            saat=2, sinif="9/A", tarih=_gun_ici(PAZARTESI, 11), ogretmen=self.ogretmen
        )
        NobetGecmisi.objects.create(
            saat=3,
            sinif="9/A",
            devamsiz=1,
            tarih=_gun_ici(PAZARTESI, 12),
            ogretmen=self.ogretmen,
            arsivlendi=True,
        )

        self.assertEqual(en_son_kayit_dt(PAZARTESI), _gun_ici(PAZARTESI, 11))
        self.assertIsNone(en_son_kayit_dt(PAZARTESI + datetime.timedelta(days=1)))


# ─────────────────────────────────────────────────────────────
# Yetkiler
# ─────────────────────────────────────────────────────────────


class NobetYetkiTestCase(TestCase):
    def setUp(self):
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")
        self.rehber = kullanici_olustur("rehber_ogretmen")
        self.ogretmen = kullanici_olustur("ogretmen")

    def test_giris_yapmayan_kullanici_login_sayfasina_yonlenir(self):
        for ad in ("nobet_dagitim", "nobet_ders_doldurma", "gunun_nobetcileri", "manuel_dagitim"):
            with self.subTest(ad=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 302)

    def test_ogretmen_yonetim_sayfalarina_erisemez(self):
        self.client.force_login(self.ogretmen)
        for ad in ("nobet_dagitim", "nobet_ders_doldurma", "gunun_nobetcileri", "manuel_dagitim"):
            with self.subTest(ad=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 403)

    def test_rehber_ogretmen_goruntuler_ama_degistiremez(self):
        self.client.force_login(self.rehber)

        self.assertEqual(self.client.get(reverse("nobet_dagitim")).status_code, 200)
        self.assertEqual(self.client.get(reverse("nobet_ders_doldurma")).status_code, 200)

        resp = self.client.post(reverse("nobet_dagitim"), {"rotasyon_onizle": "1"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(reverse("nobet_ders_doldurma"), {"kaydet": "1"})
        self.assertEqual(resp.status_code, 403)
        resp = self.client.post(reverse("gunun_nobetcileri"), {"sifirla": "1"})
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.get(reverse("manuel_dagitim")).status_code, 403)

    def test_mudur_yardimcisi_sayfalari_acar(self):
        self.client.force_login(self.mudur_yrd)
        for ad in ("nobet_dagitim", "nobet_ders_doldurma", "gunun_nobetcileri"):
            with self.subTest(ad=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 200)


# ─────────────────────────────────────────────────────────────
# Haftalık rotasyon
# ─────────────────────────────────────────────────────────────


class NobetRotasyonTestCase(TestCase):
    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.yer_a = nobet_yeri_olustur("A Bahçe")
        self.yer_b = nobet_yeri_olustur("B Koridor")
        self.yer_c = nobet_yeri_olustur("C Kantin")
        self.g1 = nobet_gorevi_olustur(nobet_yeri=self.yer_a)
        self.g2 = nobet_gorevi_olustur(nobet_yeri=self.yer_b)
        self.g3 = nobet_gorevi_olustur(nobet_yeri=self.yer_c)
        # Salı'da tek görev var: rotasyon için en az iki yer gerekir, değişmemeli.
        self.tek = nobet_gorevi_olustur(nobet_yeri=self.yer_a, nobet_gun="Tuesday")

    def _yerler(self):
        return {
            g.pk: g.nobet_yeri.ad
            for g in NobetGorevi.objects.select_related("nobet_yeri")
        }

    def test_onizleme_veritabanini_degistirmez(self):
        once = self._yerler()

        self.client.post(reverse("nobet_dagitim"), {"rotasyon_onizle": "1"})

        self.assertEqual(self._yerler(), once)
        onizleme = self.client.session["rotation_preview"]
        self.assertEqual(
            onizleme,
            {
                str(self.g1.pk): "B Koridor",
                str(self.g2.pk): "C Kantin",
                str(self.g3.pk): "A Bahçe",
            },
        )

    def test_kaydet_rotasyonu_uygular_ve_onizlemeyi_temizler(self):
        self.client.post(reverse("nobet_dagitim"), {"rotasyon_onizle": "1"})
        self.client.post(reverse("nobet_dagitim"), {"rotasyon_kaydet": "1"})

        yerler = self._yerler()
        self.assertEqual(yerler[self.g1.pk], "B Koridor")
        self.assertEqual(yerler[self.g2.pk], "C Kantin")
        self.assertEqual(yerler[self.g3.pk], "A Bahçe")
        self.assertEqual(yerler[self.tek.pk], "A Bahçe")
        self.assertNotIn("rotation_preview", self.client.session)

    def test_iptal_onizlemeyi_siler(self):
        once = self._yerler()
        self.client.post(reverse("nobet_dagitim"), {"rotasyon_onizle": "1"})
        self.client.post(reverse("nobet_dagitim"), {"rotasyon_iptal": "1"})

        self.assertNotIn("rotation_preview", self.client.session)
        self.assertEqual(self._yerler(), once)

    def test_onizlemesiz_kaydet_hicbir_seyi_degistirmez(self):
        once = self._yerler()
        self.client.post(reverse("nobet_dagitim"), {"rotasyon_kaydet": "1"})

        self.assertEqual(self._yerler(), once)


# ─────────────────────────────────────────────────────────────
# Ders doldurma akışı
# ─────────────────────────────────────────────────────────────


class DersDoldurmaAkisiTestCase(TestCase):
    """Pazartesi 2. saatte devamsız öğretmenin 9/A dersi var; tek nöbetçi o saatte boş."""

    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.url = reverse("nobet_ders_doldurma")

        self.devamsiz = nobet_ogretmen_olustur()
        ders_programi_olustur(self.devamsiz.personel, 2, sinif_sube_olustur(9, "A"))
        devamsizlik_olustur(self.devamsiz, PAZARTESI)

        self.nobetci = nobet_ogretmen_olustur()
        nobet_gorevi_olustur(ogretmen=self.nobetci)
        ders_programi_olustur(self.nobetci.personel, 5, sinif_sube_olustur(10, "B"))

    def _hesapla(self):
        return self.client.post(
            self.url, {"hesapla": "1", "tarih": PAZARTESI.isoformat(), "max_shifts": 2}
        )

    def test_hesapla_bos_dersi_nobetciye_atar_ama_kaydetmez(self):
        resp = self._hesapla()

        self.assertEqual(resp.status_code, 200)
        atamalar = self.client.session["nobet_assignments"]
        self.assertEqual(len(atamalar), 1)
        self.assertEqual(atamalar[0]["hour"], 2)
        self.assertEqual(atamalar[0]["class"], "9/A")
        self.assertEqual(atamalar[0]["teacher_id"], self.nobetci.personel.pk)
        self.assertEqual(atamalar[0]["absent_teacher_id"], self.devamsiz.personel.pk)
        self.assertEqual(self.client.session["nobet_unassigned"], [])
        self.assertFalse(NobetGecmisi.objects.exists())

    def test_nobetci_o_saatte_derste_ise_ders_atanamaz(self):
        ders_programi_olustur(self.nobetci.personel, 2, sinif_sube_olustur(11, "C"))

        self._hesapla()

        self.assertEqual(self.client.session["nobet_assignments"], [])
        atanamayan = self.client.session["nobet_unassigned"]
        self.assertEqual([(u["hour"], u["class"]) for u in atanamayan], [(2, "9/A")])

    def test_gorevlendirme_istenmeyen_devamsizlik_dagitima_girmez(self):
        from personeldevamsizlik.models import Devamsizlik

        Devamsizlik.objects.update(gorevlendirme_yapilsin=False)

        self._hesapla()

        self.assertEqual(self.client.session["nobet_assignments"], [])
        self.assertEqual(self.client.session["nobet_unassigned"], [])

    def test_kaydet_ve_sil(self):
        self._hesapla()
        self.client.post(self.url, {"kaydet": "1"})

        kayit = NobetGecmisi.objects.get()
        self.assertEqual(kayit.ogretmen, self.nobetci)
        self.assertEqual(kayit.saat, 2)
        self.assertEqual(kayit.sinif, "9/A")
        self.assertEqual(kayit.devamsiz, self.devamsiz.personel.pk)
        self.assertEqual(timezone.localtime(kayit.tarih).date(), PAZARTESI)

        resp = self.client.post(self.url, {"sil": "1", "tarih": PAZARTESI.isoformat(), "max_shifts": 2})

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(NobetGecmisi.objects.exists())

    def test_get_kayitli_dagilimi_yukler(self):
        NobetGecmisi.objects.create(
            saat=2,
            sinif="9/A",
            devamsiz=self.devamsiz.personel.pk,
            tarih=_gun_ici(PAZARTESI),
            ogretmen=self.nobetci,
        )

        resp = self.client.get(self.url, {"tarih": PAZARTESI.isoformat()})

        self.assertTrue(resp.context["loaded_from_db"])
        self.assertEqual(len(resp.context["assignments"]), 1)
        self.assertEqual(resp.context["assignments"][0]["teacher_id"], self.nobetci.personel.pk)


# ─────────────────────────────────────────────────────────────
# Manuel dağıtım
# ─────────────────────────────────────────────────────────────


class ManuelDagitimTestCase(TestCase):
    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.url = reverse("manuel_dagitim")

        self.devamsiz = nobet_ogretmen_olustur()
        ders_programi_olustur(self.devamsiz.personel, 1, sinif_sube_olustur(9, "A"))
        ders_programi_olustur(self.devamsiz.personel, 2, sinif_sube_olustur(9, "B"))
        devamsizlik_olustur(self.devamsiz, PAZARTESI)

        self.nobetci = nobet_ogretmen_olustur()
        nobet_gorevi_olustur(ogretmen=self.nobetci)

    def test_kayit_yoksa_get_ders_doldurmaya_yonlendirir(self):
        resp = self.client.get(self.url, {"tarih": PAZARTESI.isoformat()})

        self.assertEqual(resp.status_code, 302)
        self.assertFalse(NobetGecmisi.objects.exists())

    def test_secilen_hucre_atanir_secilmeyen_ders_atanamayan_olur(self):
        p_id = self.devamsiz.personel.pk
        resp = self.client.post(
            self.url,
            {
                "kaydet": "1",
                "target_date_hidden": PAZARTESI.isoformat(),
                f"cell_{self.nobetci.personel.pk}_1": f"{p_id}|9/A",
            },
        )

        self.assertEqual(resp.status_code, 302)
        atama = NobetGecmisi.objects.get()
        self.assertEqual((atama.ogretmen, atama.saat, atama.sinif), (self.nobetci, 1, "9/A"))
        atanamayan = NobetAtanamayan.objects.get()
        self.assertEqual(
            (atanamayan.ogretmen, atanamayan.saat, atanamayan.sinif), (self.devamsiz, 2, "9/B")
        )

    def test_yeniden_kaydetmek_ayni_gunun_eski_kayitlarini_degistirir(self):
        NobetGecmisi.objects.create(
            saat=5, sinif="12/Z", devamsiz=0, tarih=_gun_ici(PAZARTESI, 8), ogretmen=self.nobetci
        )

        self.client.post(
            self.url, {"kaydet": "1", "target_date_hidden": PAZARTESI.isoformat()}
        )

        self.assertFalse(NobetGecmisi.objects.exists())
        self.assertEqual(NobetAtanamayan.objects.count(), 2)


# ─────────────────────────────────────────────────────────────
# Günün nöbetçileri
# ─────────────────────────────────────────────────────────────


class GununNobetcileriTestCase(TestCase):
    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.url = reverse("gunun_nobetcileri")
        self.gorev = nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("Bahçe"))

    def test_kaydet_gunluk_yer_degisikligi_yazar_sifirla_siler(self):
        resp = self.client.post(
            f"{self.url}?tarih={PAZARTESI.isoformat()}",
            {"kaydet": "1", f"place_{self.gorev.pk}": "Kantin"},
        )

        self.assertEqual(resp.status_code, 302)
        kayit = GunlukNobetCizelgesi.objects.get()
        self.assertEqual(
            (kayit.tarih, kayit.ogretmen, kayit.nobet_yeri), (PAZARTESI, self.gorev.ogretmen, "Kantin")
        )
        # Haftalık liste etkilenmez.
        self.gorev.refresh_from_db()
        self.assertEqual(self.gorev.nobet_yeri.ad, "Bahçe")

        self.client.post(f"{self.url}?tarih={PAZARTESI.isoformat()}", {"sifirla": "1"})

        self.assertFalse(GunlukNobetCizelgesi.objects.exists())

    def test_ayni_gun_ikinci_kayit_ustune_yazar(self):
        for yer in ("Kantin", "Koridor"):
            self.client.post(
                f"{self.url}?tarih={PAZARTESI.isoformat()}",
                {"kaydet": "1", f"place_{self.gorev.pk}": yer},
            )

        self.assertEqual(GunlukNobetCizelgesi.objects.get().nobet_yeri, "Koridor")


# ─────────────────────────────────────────────────────────────
# PDF / PNG çıktıları
# ─────────────────────────────────────────────────────────────


class NobetCiktiTestCase(TestCase):
    def test_ciktilar_yalnizca_yoneticilere_acik(self):
        from okul.testing import yetki_dogrula

        urller = [reverse(ad) + f"?tarih={PAZARTESI.isoformat()}" for ad in (
            "download_ders_doldurma_pdf", "download_ders_doldurma_png",
            "download_gunun_nobetcileri_pdf", "download_gunun_nobetcileri_png",
            "download_unassigned_ders_png",
        )]
        yetki_dogrula(self, urller, ("ogretmen",), ("mudur_yardimcisi", "rehber_ogretmen"))

    def test_dagitilamayan_dersler_png_uretilir(self):
        """Önceden eksik reportlab importları (A4, Spacer, ParagraphStyle) yüzünden 500 veriyordu."""
        import shutil
        import unittest

        if not shutil.which("pdftoppm"):
            raise unittest.SkipTest("poppler-utils (pdftoppm) kurulu değil")

        devamsiz = nobet_ogretmen_olustur()
        zaman = _gun_ici(PAZARTESI, 10)
        NobetAtanamayan.objects.create(saat=2, sinif="9/A", tarih=zaman, ogretmen=devamsiz)
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

        resp = self.client.get(
            reverse("download_unassigned_ders_png"),
            {"tarih": timezone.localtime(zaman).strftime("%Y-%m-%d %H:%M:%S")},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "image/png")


class OgretmenSayfalariTestCase(TestCase):
    """Öğretmen sayfaları, açamayacağı yönetim ekranlarına bağlantı göstermez."""

    def test_ogretmene_yonetim_baglantisi_gosterilmez(self):
        user = kullanici_olustur("ogretmen")
        nobet_ogretmen_olustur(personel=personel_olustur(user=user))
        self.client.force_login(user)
        for ad in ("ogretmen_haftalik_nobet", "ogretmen_gunun_nobetcileri", "ogretmen_ders_doldurma"):
            with self.subTest(ad=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertNotContains(resp, f'href="{reverse("nobet_dagitim")}"')
                self.assertNotContains(resp, f'href="{reverse("devamsizlik_list")}"')
