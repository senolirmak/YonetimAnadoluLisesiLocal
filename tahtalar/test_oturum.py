"""tahtalar — tahtada açık oturumlar: ajan (sahte loginctl), sunucu doğrulaması ve sayfa."""

import hashlib
import subprocess
import time
from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from ebagiris.models import EbaHesap
from okul.testing import kullanici_olustur, personel_olustur
from tahtalar.models import CEVRIMICI_ESIK, Tahta
from tahtalar.services import ajan_api
from tahtalar.tests import _ajan_modulu

OTURUM = {
    "kullanici": "ogrt1",
    "ad": "Deneme Öğretmen",
    "aktif": True,
    "tur": "x11",
    "baslangic": 1_700_000_000,
}


class SunucuOturumTestCase(TestCase):
    def setUp(self):
        self.tahta = Tahta.objects.create(
            ad="K101", makine_kimligi="m1", token_ozeti="t1", son_gorulme=timezone.now()
        )

    def test_oturumlar_dogrulanarak_kaydedilir(self):
        ajan_api.durum_guncelle(
            self.tahta,
            {
                "oturumlar": [
                    {**OTURUM, "fazla_alan": "atılır", "ad": "x" * 300},
                    {"kullanici": "", "aktif": True},  # kullanıcısız: atlanır
                    {"kullanici": "ogr2", "aktif": "evet", "tur": "<script>", "baslangic": -1},
                    "bozuk",
                ]
            },
        )
        self.tahta.refresh_from_db()
        ilk, ikinci = self.tahta.oturumlar
        self.assertEqual(
            set(ilk),
            {"kullanici", "ad", "aktif", "tur", "baslangic", "eba", "personel_id", "personel"},
        )
        self.assertEqual(len(ilk["ad"]), 100)
        self.assertEqual(
            ikinci,
            {
                "kullanici": "ogr2",
                "ad": "",
                "aktif": False,
                "tur": "",
                "baslangic": None,
                "eba": False,
                "personel_id": None,
                "personel": "",
            },
        )

    def test_her_bildirimde_uzerine_yazilir_gecmis_tutulmaz(self):
        ajan_api.durum_guncelle(self.tahta, {"oturumlar": [OTURUM]})
        ajan_api.durum_guncelle(self.tahta, {"oturumlar": []})
        self.tahta.refresh_from_db()
        self.assertEqual(self.tahta.oturumlar, [])

    def test_cevrimdisi_tahtada_aktif_oturum_gosterilmez(self):
        self.tahta.oturumlar = [OTURUM]
        self.assertEqual(self.tahta.aktif_oturum["kullanici"], "ogrt1")
        self.tahta.son_gorulme = timezone.now() - CEVRIMICI_ESIK - timedelta(seconds=1)
        self.assertIsNone(self.tahta.aktif_oturum)

    def test_sayfada_oturum_ve_kapatma_uyarisi(self):
        Tahta.objects.filter(pk=self.tahta.pk).update(
            oturumlar=[OTURUM, {**OTURUM, "kullanici": "ogr2", "aktif": False}]
        )
        Tahta.objects.create(
            ad="K102", makine_kimligi="m2", token_ozeti="t2", son_gorulme=timezone.now()
        )
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        yanit = self.client.get(reverse("tahtalar:liste"))
        self.assertContains(yanit, "Deneme Öğretmen")
        self.assertContains(yanit, "+1 arka planda")
        self.assertContains(yanit, 'data-oturum="K101"')
        self.assertContains(yanit, "Giriş ekranında")  # K102: çevrimiçi, oturum yok

    def test_ogretmen_oturum_bilgisini_goremez(self):
        Tahta.objects.filter(pk=self.tahta.pk).update(oturumlar=[OTURUM])
        self.client.force_login(kullanici_olustur("ogretmen"))
        yanit = self.client.get(reverse("tahtalar:liste"))
        self.assertEqual(yanit.status_code, 403)


def _loginctl_sahte(oturumlar):
    """oturumlar: {id: show-session çıktısı}"""

    def run(arguman, **kw):
        if arguman[:2] == ["loginctl", "list-sessions"]:
            satirlar = [f"{i} 1000 x seat0 tty7" for i in oturumlar]
            return subprocess.CompletedProcess(arguman, 0, stdout="\n".join(satirlar), stderr="")
        if arguman[:2] == ["loginctl", "show-session"]:
            return subprocess.CompletedProcess(arguman, 0, stdout=oturumlar[arguman[2]], stderr="")
        raise AssertionError(arguman)

    return run


class AjanOturumTestCase(TestCase):
    def setUp(self):
        self.ajan = _ajan_modulu()

    def test_yalnizca_kullanici_oturumlari_aktif_once(self):
        mono = int(time.monotonic() * 1e6) - 600 * 1_000_000  # 10 dk önce
        cikti = {
            "c1": "Name=lightdm\nClass=greeter\nActive=no\nState=online\nType=x11\n",
            "2": "Name=arka\nClass=user\nActive=no\nState=online\nType=tty\n",
            "3": f"Name=ogrt1\nClass=user\nActive=yes\nState=active\nType=x11\nTimestampMonotonic={mono}\n",
            "4": "Name=ogrt1\nClass=manager\nActive=yes\nState=active\n",
            "5": "Name=giden\nClass=user\nActive=no\nState=closing\n",
        }
        with mock.patch.object(self.ajan.subprocess, "run", side_effect=_loginctl_sahte(cikti)):
            with mock.patch.object(
                self.ajan, "_hesap_bilgisi", side_effect=lambda k: (f"Ad {k}", "")
            ):
                liste = self.ajan.oturumlar()
        self.assertEqual([o["kullanici"] for o in liste], ["ogrt1", "arka"])
        self.assertTrue(liste[0]["aktif"])
        self.assertEqual(liste[0]["ad"], "Ad ogrt1")
        self.assertAlmostEqual(liste[0]["baslangic"], time.time() - 600, delta=5)
        self.assertIsNone(liste[1]["baslangic"])

    def test_loginctl_yoksa_bos_liste(self):
        with mock.patch.object(self.ajan.subprocess, "run", side_effect=OSError):
            self.assertEqual(self.ajan.oturumlar(), [])


def _ozet(eba_id):
    return hashlib.md5(eba_id.encode()).hexdigest()


class EbaPersonelEslesmesiTestCase(TestCase):
    def setUp(self):
        self.tahta = Tahta.objects.create(
            ad="K101", makine_kimligi="m1", token_ozeti="t1", son_gorulme=timezone.now()
        )
        self.personel = personel_olustur()
        EbaHesap.objects.create(personel=self.personel, eba_id="eba-12345")

    def _bildir(self, *oturumlar):
        ajan_api.durum_guncelle(self.tahta, {"oturumlar": list(oturumlar)})
        self.tahta.refresh_from_db()
        return self.tahta.oturumlar

    def test_eba_hesabi_bagli_ogretmen_personelle_eslesir(self):
        (oturum,) = self._bildir({**OTURUM, "eba_ozeti": _ozet("eba-12345")})
        self.assertEqual(oturum["personel_id"], self.personel.pk)
        self.assertEqual(oturum["personel"], self.personel.adi_soyadi)
        self.assertTrue(oturum["eba"])

    def test_eba_ozeti_saklanmaz(self):
        (oturum,) = self._bildir({**OTURUM, "eba_ozeti": _ozet("eba-12345")})
        self.assertNotIn("eba_ozeti", oturum)
        self.assertNotIn(_ozet("eba-12345"), str(self.tahta.oturumlar))

    def test_baglanmamis_eba_hesabi_ve_yerel_hesap(self):
        eba, yerel = self._bildir(
            {**OTURUM, "eba_ozeti": _ozet("baska-kisi")},
            {**OTURUM, "kullanici": "etapadmin", "aktif": False},
        )
        self.assertEqual((eba["eba"], eba["personel_id"]), (True, None))
        self.assertEqual((yerel["eba"], yerel["personel_id"]), (False, None))

    def test_bozuk_degerler_sunucuyu_dusurmez(self):
        oturumlar = self._bildir(
            {**OTURUM, "eba_ozeti": ["liste"], "tur": ["x11"]},
            {**OTURUM, "eba_ozeti": "kısa"},
        )
        self.assertEqual([o["eba"] for o in oturumlar], [False, False])
        self.assertEqual(oturumlar[0]["tur"], "")
        # Diğer alanlarda da liste/sözlük değerler 500 vermemeli.
        ajan_api.durum_guncelle(
            self.tahta, {"ahenk_servisi": ["x"], "guncelleme": {"durum": {}, "zaman": 1}}
        )
        ajan_api.sonuclari_isle(self.tahta, [{"id": 1, "durum": ["tamamlandi"]}])

    def test_sayfada_personel_adi_gorunur(self):
        self._bildir({**OTURUM, "eba_ozeti": _ozet("eba-12345")})
        self.client.force_login(kullanici_olustur("okul_muduru"))
        yanit = self.client.get(reverse("tahtalar:liste"))
        self.assertContains(yanit, self.personel.adi_soyadi)
        self.assertContains(yanit, "✓ Personel")

    def test_sayfada_eba_ve_yerel_hesap_etiketleri(self):
        self._bildir({**OTURUM, "eba_ozeti": _ozet("baska-kisi")})
        self.client.force_login(kullanici_olustur("okul_muduru"))
        self.assertContains(self.client.get(reverse("tahtalar:liste")), "EBA girişi")
        self._bildir({**OTURUM, "kullanici": "etapadmin", "ad": ""})
        self.assertContains(self.client.get(reverse("tahtalar:liste")), "Yerel hesap (etapadmin)")


class AjanGecosTestCase(TestCase):
    def setUp(self):
        self.ajan = _ajan_modulu()

    def _gecos(self, gecos):
        kayit = mock.Mock(pw_gecos=gecos)
        return mock.patch.object(self.ajan.pwd, "getpwnam", return_value=kayit)

    def test_eta_qr_login_hesabi(self):
        ozet = _ozet("eba-1")
        with self._gecos(f"Ayşe Yılmaz,,,,{ozet}"):
            self.assertEqual(self.ajan._hesap_bilgisi("ayseyilmaz"), ("Ayşe Yılmaz", ozet))

    def test_yerel_hesap_ve_bozuk_gecos(self):
        with self._gecos("ETAP Yönetici,,,"):
            self.assertEqual(self.ajan._hesap_bilgisi("etapadmin"), ("ETAP Yönetici", ""))
        with self._gecos("X,,,,md5-degil"):
            self.assertEqual(self.ajan._hesap_bilgisi("x"), ("X", ""))
        with mock.patch.object(self.ajan.pwd, "getpwnam", side_effect=KeyError):
            self.assertEqual(self.ajan._hesap_bilgisi("yok"), ("", ""))
