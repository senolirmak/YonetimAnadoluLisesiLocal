"""tahtalar — ETA envanter kaydı: sunucu tarafı (durum, komut, sayfa) ve ajan
(ETA sunucusu sahte; gerçek api-etap.eba.gov.tr'ye hiç bağlanılmaz)."""

import json
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from okul.models import OkulBilgi
from okul.testing import kullanici_olustur
from tahtalar.models import Tahta, TahtaEnvanteri, TahtaKomutu
from tahtalar.services import ajan_api
from tahtalar.tests import _ajan_modulu

ANAHTAR = "test-kayit-anahtari"


def _tahta(ad="10-A", **kw):
    n = Tahta.objects.count() + 1
    kw.setdefault("son_gorulme", timezone.now())
    return Tahta.objects.create(ad=ad, makine_kimligi=str(n), token_ozeti=str(n), **kw)


class EtaDurumuIslemeTestCase(TestCase):
    def setUp(self):
        self.tahta = _tahta()

    def _isle(self, bilgi):
        ajan_api.eta_bilgisini_isle(self.tahta, bilgi)
        self.tahta.save()
        self.tahta.refresh_from_db()

    def test_kayitli_bilgi_saklanir(self):
        self._isle(
            {"zaman": 1700000000, "kayitli": True, "okul_kodu": "123456",
             "okul_adi": "Örnek Lisesi", "birim_adi": "10-A", "hata": ""}
        )
        self.assertIs(self.tahta.eta_kayitli, True)
        self.assertEqual(
            (self.tahta.eta_okul_kodu, self.tahta.eta_okul_adi, self.tahta.eta_birim_adi),
            ("123456", "Örnek Lisesi", "10-A"),
        )
        self.assertEqual(self.tahta.eta_kontrol_zamani.timestamp(), 1700000000)

    def test_etada_degisen_birim_adi_tahta_adi_olur(self):
        # Örn. ETA kaydı tahtadaki eta-register ile değiştirildi.
        self._isle({"zaman": 1700000000, "kayitli": True, "okul_kodu": "1", "birim_adi": "10-A"})
        self._isle({"zaman": 1700000100, "kayitli": True, "okul_kodu": "1", "birim_adi": "Kimya Lab"})
        self.assertEqual(self.tahta.ad, "Kimya Lab")

    def test_ilk_bildirilen_birim_adi_tahta_adi_olur(self):
        self._isle({"zaman": 1700000000, "kayitli": True, "okul_kodu": "1", "birim_adi": "11-B"})
        self.assertEqual(self.tahta.ad, "11-B")

    def test_birim_adi_degismediyse_elle_verilen_ad_korunur(self):
        self._isle({"zaman": 1700000000, "kayitli": True, "okul_kodu": "1", "birim_adi": "10-A"})
        self.tahta.ad = "10-A sınıfı tahtası"
        self.tahta.save()
        self._isle({"zaman": 1700000100, "kayitli": True, "okul_kodu": "1", "birim_adi": "10-A"})
        self.assertEqual(self.tahta.ad, "10-A sınıfı tahtası")

    def test_kayitsiz_ya_da_hatali_sorgu_adi_degistirmez(self):
        for bilgi in ({"zaman": 1700000000, "kayitli": False},
                      {"zaman": 1700000100, "kayitli": None, "hata": "x"}):
            with self.subTest(bilgi=bilgi):
                self._isle(bilgi)
                self.assertEqual(self.tahta.ad, "10-A")

    def test_kayitsiz_olunca_eski_bilgi_silinir(self):
        self._isle({"zaman": 1700000000, "kayitli": True, "okul_kodu": "1", "birim_adi": "X1"})
        self._isle({"zaman": 1700000100, "kayitli": False})
        self.assertIs(self.tahta.eta_kayitli, False)
        self.assertEqual(self.tahta.eta_okul_kodu + self.tahta.eta_birim_adi, "")

    def test_sorgu_hatasinda_son_bilinen_durum_korunur(self):
        self._isle({"zaman": 1700000000, "kayitli": True, "okul_kodu": "1", "birim_adi": "X1"})
        self._isle({"zaman": 1700000100, "kayitli": None, "hata": "ulaşılamadı"})
        self.assertIs(self.tahta.eta_kayitli, True)
        self.assertEqual(self.tahta.eta_birim_adi, "X1")
        self.assertEqual(self.tahta.eta_hata, "ulaşılamadı")

    def test_bilgi_yoksa_ya_da_bozuksa_degismez(self):
        for bilgi in (None, "x", {}, {"zaman": "dun", "kayitli": True}, {"zaman": True}):
            with self.subTest(bilgi=bilgi):
                self._isle(bilgi)
                self.assertIsNone(self.tahta.eta_kayitli)
                self.assertIsNone(self.tahta.eta_kontrol_zamani)

    @override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
    def test_durum_ucu_eta_bilgisini_kaydeder(self):
        tahta, token = ajan_api.tahta_kaydet({"kayit_anahtari": ANAHTAR, "makine_kimligi": "b" * 32})
        yanit = self.client.post(
            reverse("tahtalar:api_durum"),
            json.dumps({"eta": {"zaman": 1700000000, "kayitli": False}}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(yanit.status_code, 200)
        tahta.refresh_from_db()
        self.assertIs(tahta.eta_kayitli, False)


class EtaKomutuTestCase(TestCase):
    def setUp(self):
        self.t1, self.t2 = _tahta("10-A"), _tahta("10-B")

    def test_parametreli_komut_teslim_edilir(self):
        ajan_api.eta_kayit_komutu_olustur([(self.t1, "10-A")], "123456")
        ajan_api.komut_olustur([self.t1], TahtaKomutu.KAPAT)
        komutlar = ajan_api.bekleyen_komutlari_teslim_et(self.t1)
        self.assertEqual(
            [(k["komut"], k.get("parametreler")) for k in komutlar],
            [("eta_kaydet", {"okul_kodu": "123456", "birim_adi": "10-A"}), ("kapat", None)],
        )

    def test_yeni_komut_bekleyen_eskisinin_yerine_gecer(self):
        ajan_api.eta_kayit_komutu_olustur([(self.t1, "ESKI")], "1")
        ajan_api.eta_kayit_komutu_olustur([(self.t1, "YENI"), (self.t2, "10-B")], "1")
        bekleyen = TahtaKomutu.objects.filter(durum=TahtaKomutu.BEKLIYOR)
        self.assertEqual(
            sorted(k.parametreler["birim_adi"] for k in bekleyen), ["10-B", "YENI"]
        )
        self.assertEqual(TahtaKomutu.objects.filter(durum=TahtaKomutu.IPTAL).count(), 1)

    def test_panel_komutu_olarak_verilemez(self):
        with self.assertRaises(ValueError):
            ajan_api.komut_olustur([self.t1], TahtaKomutu.ETA_KAYDET)

    def test_dogrulama(self):
        self.assertEqual(ajan_api.eta_okul_kodu_dogrula(" 123456 "), "123456")
        self.assertEqual(ajan_api.eta_birim_adi_dogrula("  10   A "), "10 A")
        for kod in ("", "12a", "1" * 13, None):
            with self.subTest(kod=kod), self.assertRaises(ValueError):
                ajan_api.eta_okul_kodu_dogrula(kod)
        for ad in ("", "A", "1234567890123", None):
            with self.subTest(ad=ad), self.assertRaises(ValueError):
                ajan_api.eta_birim_adi_dogrula(ad)

    def test_birim_onerisi(self):
        self.t1.ad = "10-A sınıfı akıllı tahtası"
        self.assertEqual(ajan_api.eta_birim_onerisi(self.t1), "10-A sınıfı")
        envanter = TahtaEnvanteri.objects.create(lider_id=1, mac_adresi="aa:bb:cc:dd:ee:01", sube_adi="11-C")
        self.t1.envanter = envanter
        self.assertEqual(ajan_api.eta_birim_onerisi(self.t1), "11-C")
        self.t1.eta_birim_adi = "Lab-1"
        self.assertEqual(ajan_api.eta_birim_onerisi(self.t1), "Lab-1")


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class EtaKomutuSonucuTahtaAdiTestCase(TestCase):
    """Başarılı ETA kaydı tahtanın panelde görünen adını birim adı yapar."""

    def setUp(self):
        self.tahta, self.token = ajan_api.tahta_kaydet(
            {"kayit_anahtari": ANAHTAR, "makine_kimligi": "c" * 32, "hostname": "etap-pc"}
        )
        self.tahta.ad = "10-A"
        self.tahta.save()

    def _komut_ve_sonuc(self, birim, durum, diger_tahta=False):
        ajan_api.eta_kayit_komutu_olustur([(self.tahta, birim)], "123456")
        komut = ajan_api.bekleyen_komutlari_teslim_et(self.tahta)[0]
        if diger_tahta:
            baska, token = ajan_api.tahta_kaydet(
                {"kayit_anahtari": ANAHTAR, "makine_kimligi": "d" * 32}
            )
        else:
            token = self.token
        yanit = self.client.post(
            reverse("tahtalar:api_durum"),
            json.dumps({"hostname": "etap-pc", "sonuclar": [
                {"id": komut["id"], "durum": durum, "mesaj": "ok"}
            ]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(yanit.status_code, 200)
        self.tahta.refresh_from_db()
        return TahtaKomutu.objects.get(pk=komut["id"])

    def test_basarili_kayit_tahta_adini_birim_adi_yapar(self):
        komut = self._komut_ve_sonuc("Fizik Lab", TahtaKomutu.TAMAMLANDI)
        self.assertEqual(komut.durum, TahtaKomutu.TAMAMLANDI)
        self.assertEqual(self.tahta.ad, "Fizik Lab")

    def test_basarisiz_kayit_adi_degistirmez(self):
        komut = self._komut_ve_sonuc("Fizik Lab", TahtaKomutu.BASARISIZ)
        self.assertEqual(komut.durum, TahtaKomutu.BASARISIZ)
        self.assertEqual(self.tahta.ad, "10-A")

    def test_baska_tahtanin_bildirdigi_sonuc_adi_degistirmez(self):
        komut = self._komut_ve_sonuc("Fizik Lab", TahtaKomutu.TAMAMLANDI, diger_tahta=True)
        self.assertEqual(komut.durum, TahtaKomutu.GONDERILDI)
        self.assertEqual(self.tahta.ad, "10-A")

    def test_diger_komutlar_adi_degistirmez(self):
        ajan_api.komut_olustur([self.tahta], TahtaKomutu.GUNCELLE)
        komut = ajan_api.bekleyen_komutlari_teslim_et(self.tahta)[0]
        ajan_api.sonuclari_isle(self.tahta, [{"id": komut["id"], "durum": "tamamlandi"}])
        self.tahta.refresh_from_db()
        self.assertEqual(self.tahta.ad, "10-A")

    def test_cevrimici_listesinde_yeni_ad_gorunur(self):
        self._komut_ve_sonuc("Fizik Lab", TahtaKomutu.TAMAMLANDI)
        self.client.force_login(kullanici_olustur("okul_muduru"))
        yanit = self.client.get(reverse("tahtalar:liste") + "?filtre=cevrimici")
        self.assertContains(yanit, "<strong>Fizik Lab</strong>", html=False)


class EtaSayfasiTestCase(TestCase):
    url = reverse("tahtalar:eta")

    def setUp(self):
        self.t1, self.t2 = _tahta("10-A"), _tahta("10-B")
        okul = OkulBilgi.get()
        okul.okul_kodu = "123456"
        okul.save()

    def _giris(self, grup="mudur_yardimcisi"):
        self.client.force_login(kullanici_olustur(grup))

    def test_yetki(self):
        for grup in ("mudur_yardimcisi", "okul_muduru"):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(self.url).status_code, 200)
        for grup in ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.client.post(self.url, {"okul_kodu": "1", "tahta": [self.t1.pk], f"birim_{self.t1.pk}": "10-A"})
        self.assertFalse(TahtaKomutu.objects.exists())

    def test_sayfa_okul_kodunu_ve_birim_onerisini_gosterir(self):
        Tahta.objects.filter(pk=self.t2.pk).update(
            eta_kayitli=True, eta_okul_kodu="999999", eta_okul_adi="Başka Okul", eta_birim_adi="B-1"
        )
        self._giris()
        yanit = self.client.get(self.url)
        self.assertContains(yanit, 'value="123456"')
        self.assertContains(yanit, f'name="birim_{self.t1.pk}" value="10-A"')
        self.assertContains(yanit, "Başka bir okul koduna kayıtlı.")

    def test_secili_tahtalara_komut_verilir(self):
        self._giris()
        yanit = self.client.post(
            self.url,
            {"okul_kodu": "123456", "tahta": [self.t1.pk], f"birim_{self.t1.pk}": "10-A",
             f"birim_{self.t2.pk}": "x"},
        )
        self.assertRedirects(yanit, self.url, fetch_redirect_response=False)
        komut = TahtaKomutu.objects.get()
        self.assertEqual((komut.tahta, komut.komut), (self.t1, TahtaKomutu.ETA_KAYDET))
        self.assertEqual(komut.parametreler, {"okul_kodu": "123456", "birim_adi": "10-A"})

    def test_gecersiz_girdide_hic_komut_verilmez(self):
        self._giris()
        for veri in (
            {"okul_kodu": "abc", "tahta": [self.t1.pk], f"birim_{self.t1.pk}": "10-A"},
            {"okul_kodu": "1", "tahta": [self.t1.pk, self.t2.pk],
             f"birim_{self.t1.pk}": "10-A", f"birim_{self.t2.pk}": "çok-uzun-birim-adı"},
            {"okul_kodu": "1"},
        ):
            with self.subTest(veri=veri):
                self.client.post(self.url, veri)
        self.assertFalse(TahtaKomutu.objects.exists())

    def test_pasif_tahtaya_komut_verilmez(self):
        Tahta.objects.filter(pk=self.t1.pk).update(aktif=False)
        self._giris()
        self.client.post(self.url, {"okul_kodu": "1", "tahta": [self.t1.pk], f"birim_{self.t1.pk}": "10-A"})
        self.assertFalse(TahtaKomutu.objects.exists())

    def test_tahtalar_sayfasinda_eta_dugmesi_yok(self):
        self._giris()
        yanit = self.client.get(reverse("tahtalar:liste"))
        self.assertNotContains(yanit, 'value="eta_kaydet"')
        self.client.post(reverse("tahtalar:komut_ver"), {"komut": "eta_kaydet", "tahta": [self.t1.pk]})
        self.assertFalse(TahtaKomutu.objects.exists())


class AjanEtaTestCase(TestCase):
    """Ajanın ETA işlemleri; eta_istek ve üretici listesi sahte."""

    OKUL = {"code": 123456, "name": "Örnek Lisesi", "city_id": 6, "town_id": 60}
    MAC = "aa:bb:cc:dd:ee:ff"

    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.ajan.DURUM_KLASORU = self.klasor.name
        self.istekler = []
        self.yanitlar = {}
        for ad, deger in (
            ("eta_mac", mock.Mock(return_value=self.MAC)),
            ("eta_uretici_destekli", mock.Mock(return_value=True)),
            ("eta_istek", mock.Mock(side_effect=self._sahte_istek)),
            ("eta_kayit_verisi", mock.Mock(return_value={"mac_id": self.MAC, "unit_name": "10-A"})),
        ):
            yama = mock.patch.object(self.ajan, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)

    def _sahte_istek(self, yol, veri=None):
        self.istekler.append((yol.split("?")[0], veri))
        yanit = self.yanitlar.get(yol.split("?")[0])
        if isinstance(yanit, Exception):
            raise yanit
        return yanit or (404, {"msg": "yok"})

    def _kayitli(self, kayitli, board_id=7):
        self.yanitlar["/board/check"] = (
            200,
            {"registered": kayitli,
             "data": {"board_id": board_id, "school_code": 111, "school_name": "Eski Okul",
                      "unit_name": "ESKI"} if kayitli else None},
        )

    def test_kayitsiz_tahta_kaydedilir(self):
        self._kayitli(False)
        self.yanitlar["/school/code/123456"] = (200, {"data": self.OKUL})
        self.yanitlar["/board"] = (201, {"msg": "ok"})
        durum, mesaj = self.ajan.komutu_uygula("eta_kaydet", {"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "tamamlandi", mesaj)
        self.assertIn("kaydedildi: Örnek Lisesi / 10-A", mesaj)
        self.assertIn(("/board", {"mac_id": self.MAC, "unit_name": "10-A"}), self.istekler)
        self.assertNotIn("/board/update", [y for y, _ in self.istekler])

    def test_kayitli_tahta_guncellenir(self):
        self._kayitli(True, board_id=42)
        self.yanitlar["/school/code/123456"] = (200, {"data": self.OKUL})
        self.yanitlar["/board/update"] = (200, {})
        durum, mesaj = self.ajan.eta_kaydet({"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "tamamlandi", mesaj)
        self.assertIn(
            ("/board/update", {"id": 42, "school_code": 123456, "unit_name": "10-A", "mac_id": self.MAC}),
            self.istekler,
        )
        self.assertNotIn("/board", [y for y, _ in self.istekler])

    def test_okul_kodu_bulunamazsa_kayit_yapilmaz(self):
        self._kayitli(False)
        self.yanitlar["/school/code/123456"] = (404, {"msg": "Okul bulunamadı"})
        durum, mesaj = self.ajan.eta_kaydet({"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "basarisiz")
        self.assertIn("Okul bulunamadı", mesaj)
        self.assertNotIn("/board", [y for y, _ in self.istekler])

    def test_sunucu_reddederse_mesaj_iletilir(self):
        self._kayitli(False)
        self.yanitlar["/school/code/123456"] = (200, {"data": self.OKUL})
        self.yanitlar["/board"] = (409, {"msg": "Bu MAC başka okulda kayıtlı"})
        durum, mesaj = self.ajan.eta_kaydet({"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "basarisiz")
        self.assertIn("409", mesaj)
        self.assertIn("başka okulda", mesaj)

    def test_desteklenmeyen_uretici_kaydedilmez(self):
        self.ajan.eta_uretici_destekli.return_value = False
        durum, _ = self.ajan.eta_kaydet({"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "basarisiz")
        self.assertEqual(self.istekler, [])

    def test_gecersiz_parametre_istek_gondermez(self):
        for parametre in (None, {}, {"okul_kodu": "12a", "birim_adi": "10-A"},
                          {"okul_kodu": "1", "birim_adi": "A"}, {"okul_kodu": "1", "birim_adi": "x" * 13}):
            with self.subTest(parametre=parametre):
                self.assertEqual(self.ajan.eta_kaydet(parametre)[0], "basarisiz")
        self.assertEqual(self.istekler, [])

    def test_ag_hatasi(self):
        self.yanitlar["/school/code/123456"] = self.ajan.EtaHatasi("ETA sunucusuna ulaşılamadı: zaman aşımı")
        durum, mesaj = self.ajan.eta_kaydet({"okul_kodu": "123456", "birim_adi": "10-A"})
        self.assertEqual(durum, "basarisiz")
        self.assertIn("ulaşılamadı", mesaj)

    def test_durum_gunde_bir_sorgulanir(self):
        self._kayitli(True)
        bilgi = self.ajan.eta_bilgisi()
        self.assertEqual(
            {k: bilgi[k] for k in ("kayitli", "okul_kodu", "okul_adi", "birim_adi", "hata")},
            {"kayitli": True, "okul_kodu": "111", "okul_adi": "Eski Okul", "birim_adi": "ESKI", "hata": ""},
        )
        self.assertNotIn("board_id", bilgi)
        self.ajan.eta_bilgisi()
        self.assertEqual(len(self.istekler), 1)
        self.ajan.eta_bilgisi(zorla=True)
        self.assertEqual(len(self.istekler), 2)

        # Bir gün sonra yeniden sorgulanır.
        dosya = Path(self.klasor.name) / "eta.json"
        eski = json.loads(dosya.read_text())
        eski["zaman"] -= self.ajan.ETA_KONTROL_ARALIGI + 1
        dosya.write_text(json.dumps(eski))
        self.ajan.eta_bilgisi()
        self.assertEqual(len(self.istekler), 3)

    def test_hata_saatte_bir_yeniden_denenir(self):
        self.yanitlar["/board/check"] = (500, {"msg": "bakımda"})
        bilgi = self.ajan.eta_bilgisi()
        self.assertIsNone(bilgi["kayitli"])
        self.assertIn("bakımda", bilgi["hata"])
        dosya = Path(self.klasor.name) / "eta.json"
        eski = json.loads(dosya.read_text())
        eski["zaman"] = int(time.time()) - self.ajan.ETA_HATA_ARALIGI - 1
        dosya.write_text(json.dumps(eski))
        self.ajan.eta_bilgisi()
        self.assertEqual(len(self.istekler), 2)

    def test_registered_alani_hata_kodunda_da_gecerli(self):
        # eta-register'daki interpret_device_status ile aynı davranış.
        self.yanitlar["/board/check"] = (500, {"registered": False})
        self.assertIs(self.ajan.eta_bilgisi()["kayitli"], False)

    def test_mac_bulunamazsa(self):
        self.ajan.eta_mac.return_value = None
        bilgi = self.ajan.eta_bilgisi()
        self.assertIsNone(bilgi["kayitli"])
        self.assertIn("MAC", bilgi["hata"])
        self.assertEqual(self.istekler, [])


class AjanEtaMacTestCase(TestCase):
    """eta_mac: etainfo yokken ilk kablolu PCI kartı (sahte /sys/class/net)."""

    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.kok = Path(self.klasor.name)

    def _arayuz(self, ad, mac, alt_sistem="pci", kablosuz=False, surucu=True):
        aygit = self.kok / "aygitlar" / ad
        (aygit / "suruculer").mkdir(parents=True)
        (self.kok / "altsistem" / alt_sistem).mkdir(parents=True, exist_ok=True)
        (aygit / "subsystem").symlink_to(self.kok / "altsistem" / alt_sistem)
        if surucu:
            (aygit / "driver").symlink_to(aygit / "suruculer")
        net = self.kok / "net" / ad
        net.mkdir(parents=True)
        (net / "device").symlink_to(aygit)
        (net / "address").write_text(mac + "\n")
        if kablosuz:
            (net / "wireless").mkdir()

    def test_ilk_kablolu_pci_karti(self):
        self._arayuz("enp1s0", "11:11:11:11:11:11")
        self._arayuz("wlp2s0", "22:22:22:22:22:22", kablosuz=True)
        self._arayuz("enx0", "33:33:33:33:33:33", alt_sistem="usb")
        self.assertEqual(self.ajan.eta_mac(str(self.kok / "net")), "11:11:11:11:11:11")

    def test_uygun_kart_yoksa_none(self):
        self._arayuz("wlp2s0", "22:22:22:22:22:22", kablosuz=True)
        self._arayuz("veth0", "44:44:44:44:44:44", surucu=False)
        self.assertIsNone(self.ajan.eta_mac(str(self.kok / "net")))


class AjanEtaUreticiTestCase(TestCase):
    """eta_uretici_destekli: ETAP listesi sahte, USB aygıtları sahte /sys."""

    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        kok = Path(self.klasor.name)
        for girdi, uretici in (("1-1", "2621\n"), ("1-2", "046D\n"), ("1-1:1.0", "ffff\n")):
            (kok / girdi).mkdir()
            (kok / girdi / "idVendor").write_text(uretici)
        gercek = self.ajan.usb_ureticileri
        yama = mock.patch.object(self.ajan, "usb_ureticileri", lambda: gercek(str(kok)))
        yama.start()
        self.addCleanup(yama.stop)

    def _liste(self, liste):
        yanit = mock.MagicMock()
        yanit.__enter__.return_value.read.return_value = json.dumps(liste).encode()
        return mock.patch.object(self.ajan.urllib.request, "urlopen", return_value=yanit)

    def test_usb_ureticileri(self):
        self.assertEqual(self.ajan.usb_ureticileri(), {"2621", "046d"})

    def test_listede_varsa_destekli(self):
        for liste in (["2621"], [{"vendor": "0x2621"}], ["0X046D"], [{"vendor": "046d", "ad": "x"}]):
            with self.subTest(liste=liste), self._liste(liste):
                self.assertTrue(self.ajan.eta_uretici_destekli())

    def test_listede_yoksa_ya_da_bozuksa_desteksiz(self):
        for liste in ([], ["1234"], {"vendor": "2621"}, [None, 5]):
            with self.subTest(liste=liste), self._liste(liste):
                self.assertFalse(self.ajan.eta_uretici_destekli())

    def test_liste_alinamazsa_hata(self):
        with mock.patch.object(self.ajan.urllib.request, "urlopen", side_effect=OSError("yok")):
            with self.assertRaises(self.ajan.EtaHatasi):
                self.ajan.eta_uretici_destekli()
