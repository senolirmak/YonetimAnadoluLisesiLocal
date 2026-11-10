"""Haftalık nöbet rotasyonu ve seçilen yerin az nöbetçili günde boş bırakılması."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from nobet.models import NobetGorevi
from nobet.services.rotasyon import gun_rotasyonu
from okul.testing import kullanici_olustur, nobet_gorevi_olustur, nobet_yeri_olustur


class GunRotasyonuTests(SimpleTestCase):
    def test_bos_yer_secilmezse_duz_kaydirma(self):
        yeni, uyari = gun_rotasyonu([("a", "BAHÇE"), ("b", "KANTİN"), ("c", "ZEMİN")])
        self.assertIsNone(uyari)
        self.assertEqual(yeni, {"a": "KANTİN", "b": "ZEMİN", "c": "BAHÇE"})

    def test_esik_ve_ustunde_secilen_yer_normal_doner(self):
        yerler = [f"YER {i:02d}" for i in range(4)] + ["GİRİŞ ORTA"]
        gorevler = sorted(((f"g{i}", y) for i, y in enumerate(yerler)), key=lambda gy: gy[1])
        yeni, uyari = gun_rotasyonu(gorevler, yerler, bos_yer="GİRİŞ ORTA", esik=5)
        self.assertIsNone(uyari)
        self.assertIn("GİRİŞ ORTA", yeni.values())

    def test_esigin_altinda_secilen_yer_bos_kalir(self):
        aday = ["BAHÇE", "GİRİŞ ORTA", "KANTİN", "KORİDOR", "ÇAY OCAĞI"]
        gorevler = [("a", "BAHÇE"), ("b", "GİRİŞ ORTA"), ("c", "KANTİN")]
        yeni, uyari = gun_rotasyonu(gorevler, aday, bos_yer="GİRİŞ ORTA", esik=11)
        self.assertIsNone(uyari)
        # Yerine boş yerlerden Türkçe alfabede ilki (ÇAY OCAĞI) girer;
        # sıralı küme BAHÇE, ÇAY OCAĞI(b), KANTİN bir adım kayar
        self.assertEqual(yeni, {"a": "ÇAY OCAĞI", "b": "KANTİN", "c": "BAHÇE"})

    def test_herhangi_bir_yer_secilebilir(self):
        gorevler = [("a", "BAHÇE"), ("b", "KANTİN")]
        yeni, _ = gun_rotasyonu(gorevler, ["BAHÇE", "KANTİN", "ZEMİN"], bos_yer="BAHÇE", esik=3)
        self.assertNotIn("BAHÇE", yeni.values())
        self.assertEqual(sorted(yeni.values()), ["KANTİN", "ZEMİN"])

    def test_ad_buyuk_kucuk_harf_ve_bosluk_farki_yok_sayilir(self):
        yeni, _ = gun_rotasyonu(
            [("a", "BAHÇE"), ("b", "Giriş  Orta ")], ["BAHÇE", "KANTİN"], bos_yer="GİRİŞ ORTA"
        )
        self.assertEqual(sorted(yeni.values()), ["BAHÇE", "KANTİN"])

    def test_bos_yer_yoksa_uyari_verir(self):
        yeni, uyari = gun_rotasyonu(
            [("a", "BAHÇE"), ("b", "GİRİŞ ORTA")], ["BAHÇE", "GİRİŞ ORTA"], bos_yer="GİRİŞ ORTA"
        )
        self.assertIn("GİRİŞ ORTA", uyari)
        self.assertEqual(yeni, {"a": "GİRİŞ ORTA", "b": "BAHÇE"})

    def test_tek_nobetci_bosaltilan_yerdeyse_bos_yere_gecer(self):
        yeni, _ = gun_rotasyonu([("a", "GİRİŞ ORTA")], ["GİRİŞ ORTA", "KANTİN"], bos_yer="GİRİŞ ORTA")
        self.assertEqual(yeni, {"a": "KANTİN"})


OKUL_YERLERI = [
    "1.KAT GÜNEY", "1.KAT KUZEY", "2.KAT GÜNEY", "2.KAT KUZEY", "3.KAT GUNEY",
    "BAHÇE ÖN ARKA_1", "BAHÇE ÖN ARKA_2", "BAHÇE ÖN ARKA_3", "GİRİŞ GÜNEY", "GİRİŞ KUZEY",
]


def _haftalar(yerler, hafta_sayisi):
    """Rotasyonu art arda uygular; her öğretmenin hafta hafta yerlerini döndürür."""
    durum = {f"o{i}": y for i, y in enumerate(yerler)}
    gecmis = {o: [y] for o, y in durum.items()}
    for _ in range(hafta_sayisi):
        sirali = sorted(durum.items(), key=lambda gy: gy[1])
        durum, _ = gun_rotasyonu(sirali)
        for o, y in durum.items():
            gecmis[o].append(y)
    return gecmis


class AyniTurYerlerTests(SimpleTestCase):
    """Bahçe gibi numaralı aynı tür yerler döngüde birbirinden uzak tutulur."""

    def test_bahce_art_arda_iki_hafta_gelmez(self):
        for o, yerler in _haftalar(OKUL_YERLERI, 20).items():
            for once, sonra in zip(yerler, yerler[1:]):
                self.assertFalse(
                    once.startswith("BAHÇE") and sonra.startswith("BAHÇE"),
                    f"{o}: {yerler}",
                )

    def test_her_ogretmen_her_yere_bir_kez_ugrar(self):
        n = len(OKUL_YERLERI)
        for o, yerler in _haftalar(OKUL_YERLERI, n - 1).items():
            self.assertEqual(sorted(yerler), sorted(OKUL_YERLERI), o)

    def test_ayni_yerde_birden_fazla_nobetci_her_hafta_degisir(self):
        yerler = ["BAHÇE", "BAHÇE", "KANTİN", "KORİDOR", "ZEMİN", "GİRİŞ"]
        for o, sira in _haftalar(yerler, 12).items():
            for once, sonra in zip(sira, sira[1:]):
                self.assertNotEqual(once, sonra, f"{o}: {sira}")


class RotasyonEkraniTests(TestCase):
    def setUp(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.url = reverse("nobet_dagitim")
        self.bahce = nobet_yeri_olustur("BAHÇE")
        self.giris = nobet_yeri_olustur("GİRİŞ ORTA")
        self.kantin = nobet_yeri_olustur("KANTİN")
        self.koridor = nobet_yeri_olustur("KORİDOR")
        # Pazartesi 3 nöbetçi; KORİDOR yalnızca Salı kullanılıyor (geçerli listede)
        self.g1 = nobet_gorevi_olustur(nobet_yeri=self.bahce)
        self.g2 = nobet_gorevi_olustur(nobet_yeri=self.giris)
        self.g3 = nobet_gorevi_olustur(nobet_yeri=self.kantin)
        self.sali = nobet_gorevi_olustur(nobet_yeri=self.koridor, nobet_gun="Tuesday")
        # Geçerli listede olmayan yer aday olamaz
        nobet_yeri_olustur("ARKA BAHÇE")

    def _yerler(self):
        return dict(NobetGorevi.objects.values_list("pk", "nobet_yeri__ad"))

    def test_secilen_yer_rotasyonla_birlikte_bosaltilir(self):
        resp = self.client.post(self.url, {"rotasyon_onizle": "1", "bos_yer": "GİRİŞ ORTA", "esik": "11"})
        self.assertIn("KORİDOR", [s["yer"] for s in resp.context["tablo_satirlari"]])
        self.assertContains(resp, "GİRİŞ ORTA boş bırakıldı")

        self.client.post(self.url, {"rotasyon_kaydet": "1"})
        yerler = self._yerler()
        # g2 GİRİŞ ORTA yerine o gün boş KORİDOR'u tutuyormuş gibi sayılır; sıra
        # BAHÇE(g1) → KANTİN(g3) → KORİDOR(g2) bir adım kayar
        self.assertEqual(
            {k: yerler[k] for k in (self.g1.pk, self.g2.pk, self.g3.pk)},
            {self.g1.pk: "KANTİN", self.g3.pk: "KORİDOR", self.g2.pk: "BAHÇE"},
        )

    def test_yer_secilmezse_duz_rotasyon(self):
        self.client.post(self.url, {"rotasyon_onizle": "1", "bos_yer": "", "esik": "11"})
        self.client.post(self.url, {"rotasyon_kaydet": "1"})
        yerler = self._yerler()
        self.assertEqual(
            {k: yerler[k] for k in (self.g1.pk, self.g2.pk, self.g3.pk)},
            {self.g1.pk: "GİRİŞ ORTA", self.g2.pk: "KANTİN", self.g3.pk: "BAHÇE"},
        )

    def test_esik_asilmazsa_secilen_yer_doner(self):
        self.client.post(self.url, {"rotasyon_onizle": "1", "bos_yer": "GİRİŞ ORTA", "esik": "3"})
        self.assertIn("GİRİŞ ORTA", self.client.session["rotation_preview"].values())

    def test_gecersiz_yer_ve_esik_kurali_kapatir(self):
        self.client.post(self.url, {"rotasyon_onizle": "1", "bos_yer": "ARKA BAHÇE", "esik": "abc"})
        self.assertEqual(self.client.session["rotasyon_ayarlari"], {"bos_yer": "", "esik": 11})

    def test_secim_hatirlanir_ve_listede_yalnizca_gecerli_yerler(self):
        self.client.post(self.url, {"rotasyon_onizle": "1", "bos_yer": "GİRİŞ ORTA", "esik": "9"})
        self.client.post(self.url, {"rotasyon_iptal": "1"})
        resp = self.client.get(self.url)
        self.assertEqual(resp.context["rotasyon_ayarlari"], {"bos_yer": "GİRİŞ ORTA", "esik": 9})
        self.assertEqual(resp.context["rotasyon_yerleri"], ["BAHÇE", "GİRİŞ ORTA", "KANTİN", "KORİDOR"])
        self.assertContains(resp, '<option value="GİRİŞ ORTA" selected>')

    def test_ogretmen_rotasyon_yapamaz(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.post(self.url, {"rotasyon_onizle": "1"}).status_code, 403)


class GununNobetcileriYerListesiTests(TestCase):
    """Günün nöbetçileri ekranındaki yer seçim listesi yalnızca geçerli listedeki yerleri sunar."""

    def test_secim_listesinde_yalnizca_gecerli_listedeki_yerler(self):
        import datetime

        from nobet.models import GunlukNobetCizelgesi

        eski = datetime.date(2025, 2, 3)
        nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("ESKİ LİSTE YERİ"), uygulama_tarihi=eski)
        nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("ARŞİV YERİ"), arsivlendi=True)
        nobet_yeri_olustur("HİÇ KULLANILMAYAN")
        pzt = nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("ZEMİN"))
        nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("ÇAY OCAĞI"), nobet_gun="Friday")
        nobet_gorevi_olustur(nobet_yeri=nobet_yeri_olustur("BAHÇE"), nobet_gun="Tuesday")
        tarih = datetime.date(2025, 9, 8)  # Pazartesi
        # O güne kaydedilmiş, geçerli listede olmayan yer seçili kalabilmeli
        GunlukNobetCizelgesi.objects.create(tarih=tarih, ogretmen=pzt.ogretmen, nobet_yeri="ESKİ LİSTE YERİ")

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("gunun_nobetcileri"), {"tarih": tarih.isoformat()})
        self.assertEqual(
            resp.context["tum_yerler"], ["BAHÇE", "ÇAY OCAĞI", "ESKİ LİSTE YERİ", "ZEMİN"]
        )
