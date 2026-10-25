"""sinav yardımcı fonksiyonları ve küçük servisleri için testler.

Kapsam: sinav/utils.py (saat hesapları, slot erişim pencereleri, gözetmen bulma,
AdminOverride), sinav/services/takvim_duzenleme.py (oturum numaralama, takvim onayı),
sinav/services/ders_ayarlari.py, mazeret ILP tarih yardımcıları.
GA motorları sinav/tests.py içinde test ediliyor.
"""

import datetime

from django.test import RequestFactory, SimpleTestCase, TestCase

from okul.testing import (
    ders_olustur,
    ders_programi_olustur,
    ders_saati_olustur,
    kullanici_olustur,
    personel_olustur,
    sinif_sube_olustur,
)
from sinav.services.ders_ayarlari import (
    get_ayarlar,
    mutate_ayar_listesi,
    parse_ders_ayarlari_post,
)
from sinav.services.mazeret_ilp import _nth_is_gunu, _parse_tatil, _time_add_dk
from sinav.services.takvim_duzenleme import (
    _oturum_atamalarini_hesapla,
    onizleme_oturumlarini_yeniden_numarala,
    takvimi_onayla,
)
from sinav.utils import (
    AdminOverride,
    gozetmen_bul,
    onceki_ders_saati,
    saat_offset,
    salon_goster,
    slot_aktif_mi,
    slot_listesi_aktif_isle,
)

BUGUN = datetime.date(2025, 11, 3)  # Pazartesi
YARIN = BUGUN + datetime.timedelta(days=1)


def _sinav_olustur(**kwargs):
    from sinav.models import SinavBilgisi

    kwargs.setdefault("aktif", True)
    return SinavBilgisi.objects.create(
        egitim_ogretim_yili="2025-2026",
        donem="1",
        sinav_adi="1",
        sinav_baslangic_tarihi=BUGUN,
        eokul_veri_tarihi=datetime.date(2025, 10, 1),
        **kwargs,
    )


class SaatYardimcilariTestCase(SimpleTestCase):
    def test_onceki_ders_saati(self):
        self.assertEqual(onceki_ders_saati("10:30"), "09:40")
        self.assertEqual(onceki_ders_saati("08:50"), "08:00")
        self.assertEqual(onceki_ders_saati("00:49"), None)

    def test_saat_offset(self):
        self.assertEqual(saat_offset("10:30", -8), "10:22")
        self.assertEqual(saat_offset("23:50", 15), "24:05")  # gün taşması kontrol edilmez
        self.assertEqual(saat_offset("00:10", -30), "00:00")

    def test_salon_goster(self):
        self.assertEqual(salon_goster("Salon-10_B"), "Salon 10/B")

    def test_mazeret_saat_ve_is_gunu(self):
        self.assertEqual(_time_add_dk(datetime.time(8, 50), 40), datetime.time(9, 30))
        tatil = _parse_tatil("2025-11-04, 2025-11-05 gecersiz")
        self.assertEqual(tatil, {datetime.date(2025, 11, 4), datetime.date(2025, 11, 5)})
        # Pazartesi 0. iş günü; Salı-Çarşamba tatil → 1. iş günü Perşembe; Cuma'dan sonra Pazartesi.
        self.assertEqual(_nth_is_gunu(BUGUN, 0, tatil), BUGUN)
        self.assertEqual(_nth_is_gunu(BUGUN, 1, tatil), datetime.date(2025, 11, 6))
        self.assertEqual(_nth_is_gunu(BUGUN, 3, tatil), datetime.date(2025, 11, 10))


class SlotErisimTestCase(SimpleTestCase):
    """Gözetim butonu sınav saatinden 8 dk önce açılır, 40 dk sonra kapanır;
    sınıf listesi 50 dk önce açılır, 10 dk önce kapanır (SLOT_ERISIM_KURALLARI)."""

    def _aktif(self, tur, simdi, tarih=BUGUN, **ek):
        slot = {"tarih": tarih, "saat": "10:30", **ek}
        slot_listesi_aktif_isle([slot], tur, BUGUN, simdi)
        return slot["aktif"]

    def test_baska_gun_hicbir_zaman_aktif_degil(self):
        self.assertFalse(slot_aktif_mi(YARIN, "10:30", BUGUN, "10:30"))
        self.assertFalse(self._aktif("gozetim", "10:30", tarih=YARIN))
        self.assertFalse(self._aktif("siniflistesi", "09:50", tarih=YARIN, onceki_saat="09:40"))

    def test_gozetim_penceresi(self):
        for simdi, beklenen in [("10:21", False), ("10:22", True), ("11:10", True), ("11:11", False)]:
            with self.subTest(simdi=simdi):
                self.assertEqual(self._aktif("gozetim", simdi), beklenen)

    def test_sinif_listesi_penceresi(self):
        for simdi, beklenen in [("09:39", False), ("09:40", True), ("10:20", True), ("10:21", False)]:
            with self.subTest(simdi=simdi):
                self.assertEqual(self._aktif("siniflistesi", simdi), beklenen)

    def test_sinif_listesi_onceki_saat_varsa_onu_kullanir(self):
        # Öğle arası: 13:35 sınavından önceki ders 12:10'da başlıyorsa liste 12:10'da açılır
        # (sabit -50 dk kuralı 12:45 derdi).
        def aktif(simdi):
            slot = {"tarih": BUGUN, "saat": "13:35", "onceki_saat": "12:10"}
            slot_listesi_aktif_isle([slot], "siniflistesi", BUGUN, simdi)
            return slot["aktif"]

        self.assertFalse(aktif("12:09"))
        self.assertTrue(aktif("12:10"))
        self.assertTrue(aktif("13:25"))
        self.assertFalse(aktif("13:26"))


class AdminOverrideTestCase(TestCase):
    def _request(self, user):
        request = RequestFactory().get("/")
        request.user = user
        request.session = {}
        return request

    def test_sadece_superuser_icin_calisir(self):
        normal = self._request(kullanici_olustur("mudur_yardimcisi"))
        AdminOverride.enable(normal)
        self.assertFalse(AdminOverride.is_active(normal))

        admin = self._request(kullanici_olustur(superuser=True))
        self.assertTrue(AdminOverride.toggle(admin))
        self.assertTrue(AdminOverride.is_active(admin))
        self.assertFalse(AdminOverride.toggle(admin))
        self.assertFalse(AdminOverride.is_active(admin))


class GozetmenBulTestCase(TestCase):
    """Gözetmen, sınavdan 50 dk önceki derste o sınıfta olan öğretmendir."""

    def setUp(self):
        # okul.testing: 2. ders 09:00, 3. ders 10:00 başlar.
        self.ogretmen = personel_olustur(adi_soyadi="Gözetmen Öğretmen")
        ders_programi_olustur(self.ogretmen, 2, sinif_sube_olustur(9, "A"))
        ders_programi_olustur(personel_olustur(), 3, sinif_sube_olustur(9, "A"))

    def test_bulunur(self):
        self.assertEqual(gozetmen_bul(None, BUGUN, "09:50", "9/A"), "Gözetmen Öğretmen")

    def test_baska_sinif_gun_veya_saat_icin_bulunmaz(self):
        self.assertIsNone(gozetmen_bul(None, BUGUN, "09:50", "9/B"))
        self.assertIsNone(gozetmen_bul(None, YARIN, "09:50", "9/A"))
        self.assertIsNone(gozetmen_bul(None, BUGUN, "09:40", "9/A"))
        self.assertIsNone(gozetmen_bul(None, BUGUN, "09:50", "gecersiz"))

    def test_en_guncel_ders_programi_kullanilir(self):
        yeni = personel_olustur(adi_soyadi="Yeni Programdaki Öğretmen")
        ders_programi_olustur(
            yeni, 2, sinif_sube_olustur(9, "A"), uygulama_tarihi=datetime.date(2025, 10, 1)
        )
        self.assertEqual(gozetmen_bul(None, BUGUN, "09:50", "9/A"), "Yeni Programdaki Öğretmen")
        # Gelecekte yürürlüğe girecek program henüz dikkate alınmaz.
        self.assertEqual(
            gozetmen_bul(None, datetime.date(2025, 9, 15), "09:50", "9/A"), "Gözetmen Öğretmen"
        )


class OturumNumaralamaTestCase(SimpleTestCase):
    def test_her_gun_saat_sirasina_gore_birden_baslar(self):
        items = [("2025-11-04", "10:30"), ("2025-11-03", "13:35"), ("2025-11-03", "08:50"),
                 ("2025-11-03", "13:35"), ("2025-11-04", "08:50")]
        self.assertEqual(_oturum_atamalarini_hesapla(items), [2, 2, 1, 2, 1])

    def test_onizleme_yerinde_numaralanir(self):
        kayitlar = [{"Tarih": "2025-11-03", "Saat": "12:10", "Oturum": 9},
                    {"Tarih": "2025-11-03", "Saat": "08:50", "Oturum": 9}]
        onizleme_oturumlarini_yeniden_numarala(kayitlar)
        self.assertEqual([r["Oturum"] for r in kayitlar], [2, 1])


class TakvimOnaylaTestCase(TestCase):
    def test_onizleme_takvime_cevrilir_ve_temizlenir(self):
        from sinav.models import Takvim, TakvimUretim

        sinav = _sinav_olustur()
        mat = ders_olustur("MATEMATİK")
        tde = ders_olustur("TÜRK DİLİ VE EDEBİYATI")
        saat = ders_saati_olustur(2)  # 09:00
        uretim = TakvimUretim.objects.create(
            sinav=sinav,
            onizleme_verisi=[
                {"Tarih": "2025-11-03", "Saat": "09:00", "Oturum": 1, "Ders": "MATEMATİK", "Subeler": "9/A,9/B"},
                {"Tarih": "2025-11-04", "Saat": "10:30", "Oturum": 2,
                 "Ders": "TÜRK DİLİ VE EDEBİYATI (Uygulama)", "Subeler": "9/A"},
            ],
        )
        # Yeniden onaylamada eski kayıtlar silinmeli.
        Takvim.objects.create(sinav=sinav, uretim=uretim, tarih=BUGUN, saat="08:00", oturum=1, subeler="x")

        self.assertEqual(takvimi_onayla(sinav, uretim), 2)

        kayitlar = list(Takvim.objects.filter(uretim=uretim).order_by("tarih"))
        self.assertEqual(len(kayitlar), 2)
        self.assertEqual((kayitlar[0].ders, kayitlar[0].ders_saati, kayitlar[0].sinav_turu), (mat, saat, ""))
        self.assertEqual((kayitlar[1].ders, kayitlar[1].ders_saati, kayitlar[1].sinav_turu), (tde, None, "Uygulama"))
        uretim.refresh_from_db()
        self.assertIsNone(uretim.onizleme_verisi)


class DersAyarlariTestCase(TestCase):
    def test_parse_gecersiz_ve_bos_alanlari_atlar(self):
        post = {
            "sabit_json": '[{"ders": "MATEMATİK"}]',
            "catisma_json": "{bozuk",
            "esleme_json": "",
            "ortak_seviyeler_json": '[12, "9", "x", 10, 9]',
        }
        self.assertEqual(
            parse_ders_ayarlari_post(post),
            {"sabit_sinavlar": [{"ders": "MATEMATİK"}], "ortak_sinav_seviyeleri": [9, 10, 12]},
        )

    def test_parse_seviye_listesi_bossa_eklenmez(self):
        self.assertEqual(parse_ders_ayarlari_post({"ortak_seviyeler_json": '["x"]'}), {})

    def test_mutate_none_donerse_kaydetmez(self):
        sinav = _sinav_olustur()

        self.assertEqual(mutate_ayar_listesi(sinav, "liste", lambda lst: lst.append("a") or "eklendi"), "eklendi")
        self.assertEqual(get_ayarlar(sinav), {"liste": ["a"]})

        mutate_ayar_listesi(sinav, "liste", lambda lst: lst.append("b") and None)
        self.assertEqual(get_ayarlar(sinav), {"liste": ["a"]})

    def test_sinav_yoksa_bos_ayar(self):
        self.assertEqual(get_ayarlar(None), {})

