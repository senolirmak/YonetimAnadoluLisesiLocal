"""tahtalar — MEB Lider envanteri içe aktarma ve ajanla MAC eşleştirmesi (uydurma veriyle)."""

import io
import json
import tempfile
from pathlib import Path

import openpyxl
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tahtalar.models import Tahta, TahtaEnvanteri
from tahtalar.services import ajan_api
from tahtalar.services.envanter_import import SUTUNLAR, envanteri_yukle

BASLIKLAR = list(SUTUNLAR)


def _satir(lider_id, mac, sube, **kw):
    deger = {
        "Lider Id": lider_id,
        "MAC": mac,
        "Okul Kodu": 999999,
        "Şube Adı": sube,
        "Faz": "Test Faz",
        "Durumu": "Çevrimdışı",
        "Aktif/Pasif": "Aktif",
        "IP Adresi 1": "10.9.0.5",
        "Oluşturulma Tarihi": "05/01/2026 09:30:00",
        "Durum Değişim Tarihi": "06/02/2026 14:00:00",
        "İşletim Sistemi Versiyonu": "Test OS 1",
        "Ahenk Versiyonu": "9.9.9",
        "Marka": "ORNEK",
        "Model": "M1",
        "İşlemci": "Test CPU",
        "RAM(GB)": "8",
        "Toplam Disk Alanı(GB)": 100,
        "Kullanılan Disk Alanı(GB)": 40,
        "Boş Disk Alanı(GB)": 60,
    }
    deger.update(kw)
    return [deger[b] for b in BASLIKLAR]


def _excel(*satirlar, basliklar=BASLIKLAR):
    kitap = openpyxl.Workbook()
    sayfa = kitap.active
    sayfa.append(basliklar)
    for satir in satirlar:
        sayfa.append(satir)
    tampon = io.BytesIO()
    kitap.save(tampon)
    tampon.seek(0)
    return tampon


class EnvanterImportTestCase(TestCase):
    def test_satirlari_donusturerek_ekler(self):
        sonuc = envanteri_yukle(
            _excel(
                _satir(1, "AA-BB-CC-00-00-01", "K101", **{"Durumu": "Çevrimiçi"}),
                _satir(2, "aa:bb:cc:00:00:02", "K102", **{"Aktif/Pasif": "Pasif"}),
            )
        )
        self.assertEqual((sonuc.eklenen, sonuc.guncellenen, sonuc.hatalar), (2, 0, []))
        e = TahtaEnvanteri.objects.get(lider_id=1)
        self.assertEqual(e.mac_adresi, "aa:bb:cc:00:00:01")
        self.assertEqual(e.okul_kodu, "999999")
        self.assertTrue(e.lider_cevrimici)
        self.assertTrue(e.lider_aktif)
        self.assertEqual(e.ram_gb, 8)
        self.assertEqual(e.disk_bos_gb, 60)
        olusturma = timezone.localtime(e.lider_olusturulma)
        self.assertEqual((olusturma.day, olusturma.month, olusturma.hour), (5, 1, 9))
        self.assertFalse(TahtaEnvanteri.objects.get(lider_id=2).lider_aktif)

    def test_tekrar_calistirmak_gunceller(self):
        envanteri_yukle(_excel(_satir(1, "aa:bb:cc:00:00:01", "K101")))
        sonuc = envanteri_yukle(_excel(_satir(1, "aa:bb:cc:00:00:01", "K101-Lab")))
        self.assertEqual((sonuc.eklenen, sonuc.guncellenen), (0, 1))
        self.assertEqual(TahtaEnvanteri.objects.get().sube_adi, "K101-Lab")

    def test_gecersiz_satirlar_atlanir(self):
        sonuc = envanteri_yukle(
            _excel(
                _satir(1, "bozuk-mac", "K101"),
                _satir("abc", "aa:bb:cc:00:00:02", "K102"),
                _satir(3, "aa:bb:cc:00:00:03", ""),
                _satir(4, "aa:bb:cc:00:00:04", "K104", **{"RAM(GB)": "?"}),
            )
        )
        self.assertEqual(sonuc.eklenen, 1)
        self.assertEqual(len(sonuc.hatalar), 3)
        self.assertIsNone(TahtaEnvanteri.objects.get().ram_gb)

    def test_ayni_mac_iki_lider_kaydinda_olamaz(self):
        sonuc = envanteri_yukle(
            _excel(_satir(1, "aa:bb:cc:00:00:01", "A"), _satir(2, "aa:bb:cc:00:00:01", "B"))
        )
        self.assertEqual(sonuc.eklenen, 1)
        self.assertIn("MAC", sonuc.hatalar[0])

    def test_eksik_sutun_hatasi(self):
        from tahtalar.services.envanter_import import EnvanterHatasi

        with self.assertRaises(EnvanterHatasi):
            envanteri_yukle(_excel(["x"], basliklar=["Lider Id", "Şube Adı"]))

    def test_once_kaydolan_tahta_aktarimda_eslesir(self):
        tahta = Tahta.objects.create(
            ad="etap-pc",
            hostname="etap-pc",
            makine_kimligi="m1",
            token_ozeti="t1",
            mac_adresleri="aa:bb:cc:00:00:07, aa:bb:cc:00:00:01",
        )
        sonuc = envanteri_yukle(_excel(_satir(1, "aa:bb:cc:00:00:01", "K101")))
        self.assertEqual(sonuc.baglanan, 1)
        tahta.refresh_from_db()
        self.assertEqual((tahta.ad, tahta.konum), ("K101", "K101"))
        self.assertEqual(tahta.envanter.lider_id, 1)

    def test_yonetim_komutu(self):
        with tempfile.TemporaryDirectory() as klasor:
            yol = Path(klasor) / "liste.xlsx"
            yol.write_bytes(_excel(_satir(1, "aa:bb:cc:00:00:01", "K101")).getvalue())
            cikti = io.StringIO()
            call_command("tahta_envanteri_yukle", str(yol), stdout=cikti)
            self.assertIn("1 eklendi", cikti.getvalue())
            with self.assertRaises(CommandError):
                call_command("tahta_envanteri_yukle", str(Path(klasor) / "yok.xlsx"))


@override_settings(TAHTA_KAYIT_ANAHTARI="k")
class AjanEnvanterEslesmesiTestCase(TestCase):
    def setUp(self):
        self.envanter = TahtaEnvanteri.objects.create(
            lider_id=1, mac_adresi="aa:bb:cc:00:00:01", sube_adi="K205"
        )

    def _kaydol(self, macler, makine="m1", hostname="etap-pc"):
        veri = {
            "kayit_anahtari": "k",
            "makine_kimligi": makine,
            "hostname": hostname,
            "mac_adresleri": macler,
        }
        return self.client.post(
            reverse("tahtalar:api_kayit"), json.dumps(veri), content_type="application/json"
        )

    def test_kayitta_mac_ile_eslesir_ve_sube_adini_alir(self):
        self._kaydol(["AA:BB:CC:00:00:01", "aa:bb:cc:00:00:99"])
        tahta = Tahta.objects.get()
        self.assertEqual(tahta.envanter, self.envanter)
        self.assertEqual((tahta.ad, tahta.konum), ("K205", "K205"))
        self.assertEqual(tahta.mac_adresleri, "aa:bb:cc:00:00:01, aa:bb:cc:00:00:99")

    def test_elle_verilen_ad_korunur(self):
        self._kaydol(["aa:bb:cc:00:00:55"])
        Tahta.objects.update(ad="Fizik Lab", konum="Zemin")
        token = self._kaydol(["aa:bb:cc:00:00:01"]).json()["token"]
        self.client.post(
            reverse("tahtalar:api_durum"),
            json.dumps({"mac_adresleri": ["aa:bb:cc:00:00:01"]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        tahta = Tahta.objects.get()
        self.assertEqual(tahta.envanter, self.envanter)
        self.assertEqual((tahta.ad, tahta.konum), ("Fizik Lab", "Zemin"))

    def test_baska_tahtaya_bagli_envanter_tekrar_baglanmaz(self):
        self._kaydol(["aa:bb:cc:00:00:01"], makine="m1")
        self._kaydol(["aa:bb:cc:00:00:01"], makine="m2", hostname="ikinci")
        ikinci = Tahta.objects.get(makine_kimligi="m2")
        self.assertIsNone(ikinci.envanter)
        self.assertEqual(ikinci.ad, "ikinci")

    def test_mac_normalize(self):
        self.assertEqual(ajan_api.mac_normalize("AA-BB-CC-11-22-33"), "aa:bb:cc:11:22:33")
        self.assertEqual(ajan_api.mac_normalize("00:00:00:00:00:00"), "")
        self.assertEqual(ajan_api.mac_normalize("kısa"), "")
        self.assertEqual(ajan_api.mac_listesi("tek-metin"), [])


class EnvanterAdminTestCase(TestCase):
    def test_envanter_listesi_acilir(self):
        from okul.testing import kullanici_olustur

        TahtaEnvanteri.objects.create(lider_id=1, mac_adresi="aa:bb:cc:00:00:01", sube_adi="K1")
        self.client.force_login(kullanici_olustur(superuser=True))
        yanit = self.client.get(reverse("admin:tahtalar_tahtaenvanteri_changelist"))
        self.assertContains(yanit, "K1")
        yanit = self.client.get(reverse("admin:tahtalar_tahta_changelist"))
        self.assertEqual(yanit.status_code, 200)
