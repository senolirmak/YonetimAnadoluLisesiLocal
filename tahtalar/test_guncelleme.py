"""tahtalar — "güncelle" komutu: sunucu tarafı ve ajan (systemctl/systemd-run sahte)."""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from okul.testing import kullanici_olustur
from tahtalar.models import Tahta, TahtaKomutu
from tahtalar.services import ajan_api
from tahtalar.tests import _ajan_modulu


class SunucuGuncellemeTestCase(TestCase):
    def setUp(self):
        self.tahta = Tahta.objects.create(ad="K101", makine_kimligi="m1", token_ozeti="t1")

    def test_ajanin_bildirdigi_guncelleme_kaydedilir(self):
        ajan_api.durum_guncelle(
            self.tahta, {"guncelleme": {"durum": "basarili", "zaman": 1_700_000_000}}
        )
        self.tahta.refresh_from_db()
        self.assertEqual(self.tahta.guncelleme_durumu, Tahta.GUNCELLEME_BASARILI)
        self.assertEqual(int(self.tahta.guncelleme_zamani.timestamp()), 1_700_000_000)

    def test_bilgi_yoksa_onceki_kayit_korunur_gecersiz_deger_yok_sayilir(self):
        ajan_api.durum_guncelle(self.tahta, {"guncelleme": {"durum": "basarisiz", "zaman": 5}})
        for gecersiz in (None, "x", {"durum": "uydurma", "zaman": 9}, {"durum": "basarili"}):
            ajan_api.durum_guncelle(self.tahta, {"guncelleme": gecersiz})
        self.tahta.refresh_from_db()
        self.assertEqual(self.tahta.guncelleme_durumu, Tahta.GUNCELLEME_BASARISIZ)

    def test_sayfadan_toplu_guncelle(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        self.client.post(
            reverse("tahtalar:komut_ver"), {"komut": "guncelle", "tahta": [self.tahta.pk]}
        )
        self.assertEqual(TahtaKomutu.objects.get().komut, TahtaKomutu.GUNCELLE)

    def test_sayfa_guncelleme_filtresi_ve_sutunu(self):
        Tahta.objects.filter(pk=self.tahta.pk).update(guncelleme_durumu="yarida_kaldi")
        Tahta.objects.create(
            ad="K102", makine_kimligi="m2", token_ozeti="t2", guncelleme_durumu="basarili"
        )
        self.client.force_login(kullanici_olustur("okul_muduru"))
        yanit = self.client.get(reverse("tahtalar:liste"), {"filtre": "guncelleme"})
        self.assertEqual([t.ad for t in yanit.context["tahtalar"]], ["K101"])
        self.assertEqual(yanit.context["ozet"]["guncelleme"], 1)
        self.assertContains(yanit, "Yarıda kaldı")
        self.assertContains(yanit, "Seçilenleri güncelle")

    @override_settings(TAHTA_KAYIT_ANAHTARI="k")
    def test_api_uzerinden_komut_teslim_edilir(self):
        token = self.client.post(
            reverse("tahtalar:api_kayit"),
            json.dumps({"kayit_anahtari": "k", "makine_kimligi": "m9"}),
            content_type="application/json",
        ).json()["token"]
        tahta = Tahta.objects.get(makine_kimligi="m9")
        ajan_api.komut_olustur([tahta], TahtaKomutu.GUNCELLE)
        yanit = self.client.post(
            reverse("tahtalar:api_durum"),
            "{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(yanit.json()["komutlar"][0]["komut"], "guncelle")


def _calisma(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class AjanGuncellemeTestCase(TestCase):
    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.ajan.DURUM_KLASORU = self.klasor.name
        self.dosya = Path(self.klasor.name) / "guncelleme"

    def tearDown(self):
        self.klasor.cleanup()

    def _sahte_run(self, aktif=False, systemd_run_kodu=0):
        cagrilar = []

        def run(arguman, **kw):
            cagrilar.append(arguman)
            if arguman[:2] == ["systemctl", "is-active"]:
                return _calisma("active\n" if aktif else "inactive\n", 0 if aktif else 3)
            if arguman[0] == "systemd-run":
                return _calisma(
                    returncode=systemd_run_kodu, stderr="hata" if systemd_run_kodu else ""
                )
            return _calisma()

        return mock.patch.object(self.ajan.subprocess, "run", side_effect=run), cagrilar

    def test_guncelleme_ayri_birimde_baslatilir(self):
        yama, cagrilar = self._sahte_run()
        with yama:
            durum, mesaj = self.ajan.komutu_uygula("guncelle")
        self.assertEqual((durum, mesaj), ("tamamlandi", "Güncelleme başlatıldı."))
        systemd_run = next(c for c in cagrilar if c[0] == "systemd-run")
        self.assertIn("--unit=akal-eta-yonetim-guncelleme", systemd_run)
        self.assertEqual(systemd_run[-1], str(self.dosya))
        betik = systemd_run[systemd_run.index("-c") + 1]
        self.assertIn("--force-confold", betik)
        self.assertIn("dpkg --configure -a", betik)
        self.assertNotIn("full-upgrade", betik)
        self.assertNotIn("dist-upgrade", betik)
        self.assertTrue(self.dosya.read_text().startswith("suruyor "))

    def test_surerken_ikinci_guncelleme_baslatilmaz(self):
        yama, cagrilar = self._sahte_run(aktif=True)
        with yama:
            durum, _ = self.ajan.komutu_uygula("guncelle")
        self.assertEqual(durum, "basarisiz")
        self.assertFalse(any(c[0] == "systemd-run" for c in cagrilar))

    def test_guncelleme_surerken_kapatilmaz(self):
        for komut in ("kapat", "yeniden_baslat"):
            yama, cagrilar = self._sahte_run(aktif=True)
            with yama:
                durum, mesaj = self.ajan.komutu_uygula(komut)
            self.assertEqual(durum, "basarisiz")
            self.assertIn("Güncelleme sürüyor", mesaj)
            self.assertFalse(
                any(c[0] == "systemctl" and c[1] in ("poweroff", "reboot") for c in cagrilar)
            )

    def test_systemd_run_basarisizsa_durum_dosyasi_kalmaz(self):
        yama, _ = self._sahte_run(systemd_run_kodu=1)
        with yama:
            durum, _ = self.ajan.komutu_uygula("guncelle")
        self.assertEqual(durum, "basarisiz")
        self.assertFalse(self.dosya.exists())

    def test_guncelleme_durumu_okuma(self):
        self.assertIsNone(self.ajan.guncelleme_durumu())

        self.dosya.write_text("basarili 1700000000 0\n")
        self.assertEqual(self.ajan.guncelleme_durumu(), {"durum": "basarili", "zaman": 1700000000})

        simdi = int(time.time())
        self.dosya.write_text(f"suruyor {simdi}\n")
        yama, _ = self._sahte_run(aktif=True)
        with yama:
            self.assertEqual(self.ajan.guncelleme_durumu()["durum"], "suruyor")
        # Birim çalışmıyor ama sonuç yazılmamış: tahta güncellemede kapanmış.
        yama, _ = self._sahte_run(aktif=False)
        with yama:
            self.assertEqual(self.ajan.guncelleme_durumu()["durum"], "yarida_kaldi")

    def test_guncelleme_betigi_sonucu_dosyaya_yazar(self):
        """Betiği apt/dpkg yerine sahte komutlarla gerçekten çalıştırır."""
        sahte = Path(self.klasor.name) / "bin"
        sahte.mkdir()
        for ad, kod in (("dpkg", 0), ("apt-get", 0)):
            (sahte / ad).write_text(f"#!/bin/sh\nexit {kod}\n")
            (sahte / ad).chmod(0o755)
        ortam = {"PATH": f"{sahte}:/usr/bin:/bin"}
        subprocess.run(
            ["/bin/sh", "-c", self.ajan.GUNCELLEME_BETIGI, "test", str(self.dosya)],
            env=ortam,
            check=False,
        )
        self.assertTrue(self.dosya.read_text().startswith("basarili "))

        (sahte / "apt-get").write_text("#!/bin/sh\nexit 100\n")
        sonuc = subprocess.run(
            ["/bin/sh", "-c", self.ajan.GUNCELLEME_BETIGI, "test", str(self.dosya)],
            env=ortam,
            check=False,
        )
        self.assertEqual(sonuc.returncode, 100)
        self.assertTrue(self.dosya.read_text().startswith("basarisiz "))
        self.assertTrue(self.dosya.read_text().rstrip().endswith(" 100"))
