"""tahtalar — ajan API'si, komut kuyruğu, admin eylemleri ve ajanın okuma yardımcıları."""

import importlib.util
import json
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from okul.testing import kullanici_olustur
from tahtalar.models import CEVRIMICI_ESIK, KOMUT_GECERLILIK, Tahta, TahtaKomutu
from tahtalar.services import ajan_api

ANAHTAR = "test-kayit-anahtari"


def _durum_verisi(**kw):
    veri = {
        "makine_kimligi": "a" * 32,
        "hostname": "tahta-10a",
        "ip_adresi": "10.0.0.15",
        "isletim_sistemi": "Pardus ETAP 23",
        "ajan_surumu": "1.0.0",
        "acik_kalma_suresi": 3600,
        "ahenk_servisi": "calisiyor",
        "meb_kayitli": True,
    }
    veri.update(kw)
    return veri


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class AjanApiTestCase(TestCase):
    def _post(self, ad, veri, token=None):
        basliklar = {"HTTP_AUTHORIZATION": f"Token {token}"} if token else {}
        return self.client.post(
            reverse(f"tahtalar:{ad}"),
            data=json.dumps(veri),
            content_type="application/json",
            **basliklar,
        )

    def _kaydol(self, **kw):
        yanit = self._post("api_kayit", _durum_verisi(kayit_anahtari=ANAHTAR, **kw))
        self.assertEqual(yanit.status_code, 200)
        return yanit.json()["token"]

    def test_kayit_tahta_olusturur_ve_token_ozetini_saklar(self):
        token = self._kaydol()
        tahta = Tahta.objects.get()
        self.assertEqual(tahta.ad, "tahta-10a")
        self.assertEqual(tahta.ahenk_servisi, Tahta.AHENK_CALISIYOR)
        self.assertTrue(tahta.meb_kayitli)
        self.assertTrue(tahta.cevrimici)
        self.assertNotEqual(tahta.token_ozeti, token)
        self.assertEqual(tahta.token_ozeti, ajan_api.token_ozeti(token))

    def test_yanlis_anahtarla_kayit_reddedilir(self):
        yanit = self._post("api_kayit", _durum_verisi(kayit_anahtari="yanlis"))
        self.assertEqual(yanit.status_code, 403)
        self.assertFalse(Tahta.objects.exists())

    @override_settings(TAHTA_KAYIT_ANAHTARI="")
    def test_anahtar_tanimli_degilse_kayit_kapali(self):
        yanit = self._post("api_kayit", _durum_verisi(kayit_anahtari=""))
        self.assertEqual(yanit.status_code, 403)

    def test_yeniden_kayit_ayni_tahtayi_kullanir_eski_token_gecersiz_olur(self):
        eski = self._kaydol()
        Tahta.objects.update(ad="10-A", konum="2. kat")
        yeni = self._kaydol()
        self.assertEqual(Tahta.objects.count(), 1)
        tahta = Tahta.objects.get()
        self.assertEqual((tahta.ad, tahta.konum), ("10-A", "2. kat"))
        self.assertEqual(self._post("api_durum", {}, eski).status_code, 401)
        self.assertEqual(self._post("api_durum", {}, yeni).status_code, 200)

    def test_pasif_tahta_baglanamaz_ve_yeniden_kaydolamaz(self):
        token = self._kaydol()
        Tahta.objects.update(aktif=False)
        self.assertEqual(self._post("api_durum", _durum_verisi(), token).status_code, 401)
        yanit = self._post("api_kayit", _durum_verisi(kayit_anahtari=ANAHTAR))
        self.assertEqual(yanit.status_code, 403)

    def test_tokensiz_durum_istegi_reddedilir(self):
        self.assertEqual(self._post("api_durum", _durum_verisi()).status_code, 401)

    def test_durum_gecersiz_degerleri_guvenli_kaydeder(self):
        token = self._kaydol()
        self._post(
            "api_durum",
            _durum_verisi(
                ip_adresi="bozuk",
                ahenk_servisi="rm -rf",
                meb_kayitli="evet",
                acik_kalma_suresi=-5,
                hostname="x" * 500,
            ),
            token,
        )
        tahta = Tahta.objects.get()
        self.assertIsNone(tahta.ip_adresi)
        self.assertEqual(tahta.ahenk_servisi, Tahta.AHENK_BILINMIYOR)
        self.assertIsNone(tahta.meb_kayitli)
        self.assertIsNone(tahta.acik_kalma_suresi)
        self.assertEqual(len(tahta.hostname), 100)

    def test_bozuk_json_400(self):
        token = self._kaydol()
        yanit = self.client.post(
            reverse("tahtalar:api_durum"),
            data="{bozuk",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        )
        self.assertEqual(yanit.status_code, 400)

    def test_get_istegi_kabul_edilmez(self):
        self.assertEqual(self.client.get(reverse("tahtalar:api_durum")).status_code, 405)

    def test_komut_bir_kez_teslim_edilir_ve_sonuc_kaydedilir(self):
        token = self._kaydol()
        tahta = Tahta.objects.get()
        ajan_api.komut_olustur([tahta], TahtaKomutu.KAPAT)

        komutlar = self._post("api_durum", _durum_verisi(), token).json()["komutlar"]
        self.assertEqual([k["komut"] for k in komutlar], ["kapat"])
        komut = TahtaKomutu.objects.get()
        self.assertEqual(komut.durum, TahtaKomutu.GONDERILDI)

        # İkinci turda aynı komut tekrar gelmez.
        sonuc = {"id": komut.pk, "durum": "tamamlandi", "mesaj": ""}
        yanit = self._post("api_durum", _durum_verisi(sonuclar=[sonuc]), token)
        self.assertEqual(yanit.json()["komutlar"], [])
        komut.refresh_from_db()
        self.assertEqual(komut.durum, TahtaKomutu.TAMAMLANDI)
        self.assertIsNotNone(komut.tamamlanma)

    def test_tahta_baska_tahtanin_komutunu_guncelleyemez(self):
        token = self._kaydol()
        baska = Tahta.objects.create(ad="B", makine_kimligi="b" * 32, token_ozeti="x")
        komut = TahtaKomutu.objects.create(
            tahta=baska, komut=TahtaKomutu.KAPAT, durum=TahtaKomutu.GONDERILDI
        )
        sonuc = {"id": komut.pk, "durum": "basarisiz", "mesaj": "sahte"}
        self._post("api_durum", _durum_verisi(sonuclar=[sonuc]), token)
        komut.refresh_from_db()
        self.assertEqual(komut.durum, TahtaKomutu.GONDERILDI)

    def test_suresi_dolan_komut_teslim_edilmez(self):
        token = self._kaydol()
        tahta = Tahta.objects.get()
        ajan_api.komut_olustur([tahta], TahtaKomutu.KAPAT)
        TahtaKomutu.objects.update(
            olusturma=timezone.now() - KOMUT_GECERLILIK - timedelta(seconds=1)
        )
        yanit = self._post("api_durum", _durum_verisi(), token)
        self.assertEqual(yanit.json()["komutlar"], [])
        self.assertEqual(TahtaKomutu.objects.get().durum, TahtaKomutu.IPTAL)


class KomutOlusturTestCase(TestCase):
    def setUp(self):
        self.t1 = Tahta.objects.create(ad="A", makine_kimligi="1", token_ozeti="1")
        self.t2 = Tahta.objects.create(ad="B", makine_kimligi="2", token_ozeti="2")

    def test_ayni_bekleyen_komut_tekrarlanmaz(self):
        self.assertEqual(ajan_api.komut_olustur([self.t1], TahtaKomutu.KAPAT), 1)
        self.assertEqual(ajan_api.komut_olustur([self.t1, self.t2], TahtaKomutu.KAPAT), 1)
        self.assertEqual(TahtaKomutu.objects.count(), 2)

    def test_bilinmeyen_komut_reddedilir(self):
        with self.assertRaises(ValueError):
            ajan_api.komut_olustur([self.t1], "rm -rf /")

    def test_cevrimici_cevrimdisi_ayrimi(self):
        Tahta.objects.filter(pk=self.t1.pk).update(son_gorulme=timezone.now())
        Tahta.objects.filter(pk=self.t2.pk).update(
            son_gorulme=timezone.now() - CEVRIMICI_ESIK - timedelta(seconds=1)
        )
        self.assertEqual(list(Tahta.objects.cevrimici()), [self.t1])
        self.assertEqual(list(Tahta.objects.cevrimdisi()), [self.t2])
        Tahta.objects.create(ad="C", makine_kimligi="3", token_ozeti="3")
        self.assertEqual(Tahta.objects.cevrimdisi().count(), 2)


class TahtaAdminTestCase(TestCase):
    def setUp(self):
        self.t1 = Tahta.objects.create(ad="A", makine_kimligi="1", token_ozeti="1")
        self.t2 = Tahta.objects.create(ad="B", makine_kimligi="2", token_ozeti="2")
        self.url = reverse("admin:tahtalar_tahta_changelist")

    def _eylem(self, kullanici, eylem):
        self.client.force_login(kullanici)
        return self.client.post(
            self.url,
            {"action": eylem, "_selected_action": [self.t1.pk, self.t2.pk]},
            follow=True,
        )

    def test_liste_sayfasi_acilir(self):
        self.client.force_login(kullanici_olustur(superuser=True))
        yanit = self.client.get(self.url + "?baglanti=cevrimdisi")
        self.assertEqual(yanit.status_code, 200)
        self.assertContains(yanit, "Seçili tahtaları kapat")

    def test_toplu_kapat(self):
        yanit = self._eylem(kullanici_olustur(superuser=True), "kapat")
        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(
            set(TahtaKomutu.objects.values_list("tahta_id", "komut")),
            {(self.t1.pk, "kapat"), (self.t2.pk, "kapat")},
        )
        self.assertContains(yanit, "Çevrimdışı tahtalar")

    def test_toplu_yeniden_baslat(self):
        self._eylem(kullanici_olustur(superuser=True), "yeniden_baslat")
        self.assertEqual(TahtaKomutu.objects.filter(komut=TahtaKomutu.YENIDEN_BASLAT).count(), 2)

    def test_komut_izni_olmayan_eylemi_goremez(self):
        from django.contrib.auth.models import Permission

        kullanici = kullanici_olustur(is_staff=True)
        kullanici.user_permissions.add(
            Permission.objects.get(codename="view_tahta"),
            Permission.objects.get(codename="change_tahta"),
        )
        self._eylem(kullanici, "kapat")
        self.assertFalse(TahtaKomutu.objects.exists())


def _ajan_modulu():
    yol = Path(__file__).parent / "akal-eta-yonetim" / "akal_eta_yonetim.py"
    spec = importlib.util.spec_from_file_location("akal_eta_yonetim", yol)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class AjanOkumaTestCase(TestCase):
    """Ajanın Ahenk durumunu okuyan yardımcıları (gerçek /etc/ahenk'e dokunmaz)."""

    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.yol = Path(self.klasor.name)

    def tearDown(self):
        self.klasor.cleanup()

    def _db(self, *degerler):
        baglanti = sqlite3.connect(self.yol / "ahenk.db")
        baglanti.execute("CREATE TABLE registration (jid TEXT, registered INTEGER)")
        baglanti.executemany("INSERT INTO registration VALUES ('x', ?)", [(d,) for d in degerler])
        baglanti.commit()
        baglanti.close()

    def test_kayitli(self):
        self._db(1)
        self.assertIs(self.ajan.meb_kayit_durumu(str(self.yol)), True)

    def test_kayitsiz(self):
        self._db(0)
        self.assertIs(self.ajan.meb_kayit_durumu(str(self.yol)), False)

    def test_db_yoksa_conf_uid(self):
        (self.yol / "ahenk.conf").write_text("[CONNECTION]\nuid = abc\n")
        self.assertIs(self.ajan.meb_kayit_durumu(str(self.yol)), True)
        (self.yol / "ahenk.conf").write_text("[CONNECTION]\nuid =\n")
        self.assertIs(self.ajan.meb_kayit_durumu(str(self.yol)), False)

    def test_hicbir_dosya_yoksa_bilinmiyor(self):
        self.assertIsNone(self.ajan.meb_kayit_durumu(str(self.yol)))

    def test_ahenk_db_degismez(self):
        self._db(1)
        once = (self.yol / "ahenk.db").read_bytes()
        self.ajan.meb_kayit_durumu(str(self.yol))
        self.assertEqual((self.yol / "ahenk.db").read_bytes(), once)

    def _systemctl(self, cikti):
        return mock.patch.object(
            self.ajan.subprocess, "run", return_value=mock.Mock(stdout=cikti, returncode=0)
        )

    def test_ahenk_servis_durumu(self):
        durumlar = {
            "LoadState=loaded\nActiveState=active\n": "calisiyor",
            "LoadState=loaded\nActiveState=failed\n": "durmus",
            "LoadState=not-found\nActiveState=inactive\n": "yok",
            "": "bilinmiyor",
        }
        for cikti, beklenen in durumlar.items():
            with self._systemctl(cikti):
                self.assertEqual(self.ajan.ahenk_servis_durumu(), beklenen)

    def test_bilinmeyen_komut_calistirilmaz(self):
        with mock.patch.object(self.ajan.subprocess, "run") as run:
            durum, _ = self.ajan.komutu_uygula("rm")
        self.assertEqual(durum, "basarisiz")
        run.assert_not_called()

    def test_kapat_komutu_systemctl_poweroff(self):
        with mock.patch.object(
            self.ajan.subprocess, "run", return_value=mock.Mock(returncode=0, stderr="")
        ) as run:
            self.assertEqual(self.ajan.komutu_uygula("kapat"), ("tamamlandi", ""))
        self.assertEqual(run.call_args.args[0], ["systemctl", "poweroff", "--no-block"])
