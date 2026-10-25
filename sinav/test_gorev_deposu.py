"""Arka plan görev durumu (sinav/services/gorev_deposu.py).

Prod'da Gunicorn 3 worker ile çalışır; görevi başlatan worker ile durumu soran worker
farklı olabilir. Önceden durum yalnızca başlatan worker'ın belleğindeydi: diğer
worker'lar 404 dönüyor, sayfa sonsuza kadar "Calisiyor..." gösteriyordu.
Burada "başka worker" durumu, işlem içi yerel kaydı silerek taklit edilir.
"""

import threading
from unittest import mock

from django.core.cache import caches
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from okul.testing import kullanici_olustur
from sinav.services import gorev_deposu


def _baska_worker_gibi():
    """Bu işlemin yerel görev kaydını gizler: sorgu yalnızca paylaşılan depodan okunabilir."""
    return mock.patch.object(gorev_deposu, "_yerel", {})


class GorevDeposuTestCase(SimpleTestCase):
    def setUp(self):
        caches["gorevler"].clear()
        gorev_deposu._iptal_onbellek.clear()
        gorev_deposu._son_yazma.clear()

    def test_durum_baska_worker_tarafindan_okunur(self):
        gorev_deposu.olustur("g1")
        gorev_deposu.log_ekle("g1", "> baslatildi")
        gorev_deposu.bitir("g1")

        with _baska_worker_gibi():
            durum = gorev_deposu.durum("g1")

        self.assertEqual(durum["logs"], ["> baslatildi"])
        self.assertTrue(durum["done"])
        self.assertFalse(durum["error"])

    def test_bilinmeyen_gorev(self):
        self.assertIsNone(gorev_deposu.durum("yok"))
        self.assertFalse(gorev_deposu.iptal_iste("yok"))

    def test_iptal_baska_worker_dan_istenir_gorev_gorur(self):
        gorev_deposu.olustur("g2")
        with _baska_worker_gibi():
            self.assertTrue(gorev_deposu.iptal_iste("g2"))
            durum = gorev_deposu.durum("g2")

        self.assertTrue(gorev_deposu.iptal_istendi_mi("g2"))
        self.assertTrue(durum["cancelled"])
        self.assertEqual(durum["logs"][-1], gorev_deposu.IPTAL_MESAJI)

    def test_bitmis_gorev_iptal_edilemez(self):
        gorev_deposu.olustur("g3")
        gorev_deposu.bitir("g3", hata=True)
        self.assertFalse(gorev_deposu.iptal_iste("g3"))
        self.assertTrue(gorev_deposu.durum("g3")["error"])

    def test_sik_loglar_kisilir_ama_bitiste_hepsi_yazilir(self):
        gorev_deposu.olustur("g4")
        with mock.patch.object(caches["gorevler"], "set", wraps=caches["gorevler"].set) as yaz:
            for i in range(200):
                gorev_deposu.log_ekle("g4", f"satir {i}")
            self.assertLess(yaz.call_count, 10)
            gorev_deposu.bitir("g4")

        with _baska_worker_gibi():
            self.assertEqual(len(gorev_deposu.durum("g4")["logs"]), 200)

    def test_paralel_log_yazimi(self):
        gorev_deposu.olustur("g5")

        def yaz(n):
            for i in range(50):
                gorev_deposu.log_ekle("g5", f"{n}-{i}")

        threadler = [threading.Thread(target=yaz, args=(n,)) for n in range(4)]
        for t in threadler:
            t.start()
        for t in threadler:
            t.join()
        gorev_deposu.bitir("g5")
        self.assertEqual(len(gorev_deposu.durum("g5")["logs"]), 200)


class GorevViewTestCase(TestCase):
    def setUp(self):
        caches["gorevler"].clear()
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))

    def test_durum_ve_iptal_endpointleri_paylasilan_depoyu_kullanir(self):
        gorev_deposu.olustur("v1")
        gorev_deposu.log_ekle("v1", "> calisiyor")

        with _baska_worker_gibi():
            resp = self.client.get(reverse("sinav:gorev_durumu", args=["v1"]))
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.json()["done"])
            self.client.post(reverse("sinav:gorev_iptal", args=["v1"]))
            self.assertTrue(self.client.get(reverse("sinav:gorev_durumu", args=["v1"])).json()["cancelled"])

        self.assertTrue(gorev_deposu.iptal_istendi_mi("v1"))
        self.assertEqual(self.client.get(reverse("sinav:gorev_durumu", args=["yok"])).status_code, 404)

    def test_baslatilan_gorev_tamamlaninca_tamamlandi_doner(self):
        """calistir_* → thread → bitince durum 'done'. Ağır iş yerine sahte bir adım çalıştırılır."""
        from sinav import views

        bitti = threading.Event()

        def sahte_adim():
            bitti.set()

        with mock.patch.dict(views.ADIM_FUNCLARI, {"subeders": (sahte_adim, "Sube-ders")}):
            task_id = self.client.post(reverse("sinav:subeders")).json()["task_id"]
            self.assertTrue(bitti.wait(5))
            for _ in range(50):
                durum = self.client.get(reverse("sinav:gorev_durumu", args=[task_id])).json()
                if durum["done"]:
                    break
                threading.Event().wait(0.05)

        self.assertTrue(durum["done"])
        self.assertFalse(durum["error"], durum["logs"])
        self.assertIn("+ Sube-ders tamamlandi.", durum["logs"])


class GorevDeposuYazilamazTestCase(TestCase):
    """Önbellek klasörüne yazılamazsa (prod'da yaşandı: klasör başka kullanıcıya ait, 0700)
    Çalıştır düğmesi sessizce 500 vermesin, açık bir JSON hata dönsün."""

    def test_yazilamayan_depo_json_hata_doner(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        with mock.patch.object(gorev_deposu, "_depo") as depo:
            depo.return_value.set.side_effect = PermissionError("[Errno 13] Permission denied")
            with self.assertLogs("sinav.views", level="ERROR"):
                resp = self.client.post(reverse("sinav:takvim"))

        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp["Content-Type"], "application/json")
        self.assertIn("Görev başlatılamadı", resp.json()["error"])

    def test_onbellek_klasoru_kullaniciya_ozel(self):
        import os

        from django.conf import settings as dj_settings

        from config.settings import base

        self.assertTrue(base.CACHES["gorevler"]["LOCATION"].endswith(f"_{os.getuid()}"))
        self.assertIn("gorevler", dj_settings.CACHES)
