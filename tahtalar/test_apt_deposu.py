"""tahtalar — APT deposu: imza anahtarı, depo dosyaları, paketin depo kaynağını
kurması ve tahtadaki uygulamanın kendini güncellemesi."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from okul.testing import kullanici_olustur
from tahtalar.models import Tahta
from tahtalar.services import ajan_api, apt_deposu, depo_anahtari, kurulum_paketi, openpgp
from tahtalar.test_paket import _ar_uyeleri, _tar
from tahtalar.tests import _ajan_modulu

ANAHTAR = "test-kayit_anahtari-123"
SUNUCU = "https://okul.test"
GPGV = shutil.which("gpgv")


class _GeciciAnahtarMixin:
    """Anahtar dosyasını geçici klasöre yönlendirir (geliştirme makinesindekine dokunmaz)."""

    def setUp(self):
        super().setUp()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.yol = Path(self.klasor.name)
        for modul, ad, deger in (
            (depo_anahtari, "ANAHTAR_DOSYASI", self.yol / "anahtar.json"),
            (kurulum_paketi, "CA_DOSYASI", self.yol / "yok.crt"),
            (apt_deposu, "ARSIV_KLASORU", self.yol / "arsiv"),
        ):
            yama = mock.patch.object(modul, ad, deger)
            yama.start()
            self.addCleanup(yama.stop)

    def _anahtar_uret(self):
        return depo_anahtari.imza_anahtari_olustur()

    def _gpgv(self, *dosyalar):
        anahtarlik = self.yol / "anahtarlik.gpg"
        anahtarlik.write_bytes(depo_anahtari.acik_anahtarlik())
        return subprocess.run(
            [GPGV, "--keyring", str(anahtarlik), *map(str, dosyalar)],
            capture_output=True,
            text=True,
        )


class OpenPgpTestCase(TestCase):
    def test_crc24_bilinen_deger(self):
        self.assertEqual(openpgp._crc24(b""), 0xB704CE)

    def test_mpi(self):
        self.assertEqual(openpgp._mpi(b"\x00\x01"), b"\x00\x01\x01")
        self.assertEqual(openpgp._mpi(b"\x40" + b"\x00" * 32)[:2], b"\x01\x07")  # 263 bit

    def test_ayni_tohum_ayni_anahtar_ve_imza(self):
        tohum = bytes(range(32))
        a, b = openpgp.Anahtar(tohum, 1), openpgp.Anahtar(tohum, 1)
        self.assertEqual(a.parmak_izi, b.parmak_izi)
        self.assertEqual(a.ayrik_imza(b"x", 5), b.ayrik_imza(b"x", 5))
        # Oluşturma zamanı parmak izine girer.
        self.assertNotEqual(a.parmak_izi, openpgp.Anahtar(tohum, 2).parmak_izi)

    def test_acik_metin_imzada_tire_kacirilir(self):
        metin = openpgp.Anahtar(bytes(32), 1).acik_metin_imza("A: 1\n-B\n", 1).decode()
        self.assertTrue(metin.startswith("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n"))
        self.assertIn("\nA: 1\n- -B\n-----BEGIN PGP SIGNATURE-----\n", metin)


class DepoAnahtariTestCase(_GeciciAnahtarMixin, TestCase):
    def test_anahtar_yoksa_depo_kapali(self):
        self.assertIsNone(depo_anahtari.imza_anahtari())
        self.assertFalse(depo_anahtari.depo_hazir_mi())
        self.assertIsNone(depo_anahtari.acik_anahtarlik())

    def test_uretilen_anahtar_yalniz_sahibine_okunur_ve_ayni_okunur(self):
        anahtar = self._anahtar_uret()
        self.assertEqual(os.stat(depo_anahtari.ANAHTAR_DOSYASI).st_mode & 0o777, 0o600)
        self.assertEqual(depo_anahtari.imza_anahtari().parmak_izi, anahtar.parmak_izi)
        self.assertTrue(depo_anahtari.depo_hazir_mi())

    def test_var_olan_anahtar_zorla_olmadan_degismez(self):
        ilk = self._anahtar_uret()
        with self.assertRaises(depo_anahtari.AnahtarHatasi):
            depo_anahtari.imza_anahtari_olustur()
        self.assertEqual(depo_anahtari.imza_anahtari().parmak_izi, ilk.parmak_izi)
        yeni = depo_anahtari.imza_anahtari_olustur(zorla=True)
        self.assertNotEqual(yeni.parmak_izi, ilk.parmak_izi)

    def test_bozuk_dosya(self):
        depo_anahtari.ANAHTAR_DOSYASI.write_text("{bozuk")
        with self.assertRaises(depo_anahtari.AnahtarHatasi):
            depo_anahtari.imza_anahtari()
        self.assertFalse(depo_anahtari.depo_hazir_mi())

    def test_yonetim_komutu(self):
        call_command("tahta_apt_anahtari_olustur", stdout=open(os.devnull, "w"))
        parmak_izi = depo_anahtari.imza_anahtari().parmak_izi
        # İkinci çalıştırma anahtarı değiştirmez, hata da vermez.
        call_command("tahta_apt_anahtari_olustur", stdout=open(os.devnull, "w"))
        self.assertEqual(depo_anahtari.imza_anahtari().parmak_izi, parmak_izi)


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class DepoPaketiTestCase(_GeciciAnahtarMixin, TestCase):
    ANAHTARLIK = "./usr/share/keyrings/akal-eta-yonetim.gpg"
    KURULUM = "./usr/share/akal-eta-yonetim/kurulum.conf"

    def test_anahtar_yoksa_depo_paketi_yok_kurulum_paketinde_anahtarlik_yok(self):
        with self.assertRaises(kurulum_paketi.PaketHatasi):
            kurulum_paketi.depo_paketi_olustur()
        veri = _tar(_ar_uyeleri(kurulum_paketi.paket_olustur(SUNUCU))["data.tar.gz"])
        self.assertNotIn(self.ANAHTARLIK, veri.getnames())

    def test_depo_paketi_gizli_bilgi_tasimaz_ve_belirlenimci(self):
        self._anahtar_uret()
        ca = self.yol / "ca.crt"
        ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nX\n")
        with mock.patch.object(kurulum_paketi, "CA_DOSYASI", ca):
            paket = kurulum_paketi.depo_paketi_olustur()
            self.assertEqual(paket, kurulum_paketi.depo_paketi_olustur())
        self.assertNotIn(ANAHTAR.encode(), paket)
        self.assertNotIn(b"okul.test", paket)
        veri = _tar(_ar_uyeleri(paket)["data.tar.gz"])
        adlar = veri.getnames()
        self.assertNotIn(self.KURULUM, adlar)
        self.assertNotIn("./usr/share/akal-eta-yonetim/yerel-ca.crt", adlar)
        self.assertEqual(veri.extractfile(self.ANAHTARLIK).read(), depo_anahtari.acik_anahtarlik())

    def test_kurulum_paketi_anahtarligi_da_tasir(self):
        self._anahtar_uret()
        veri = _tar(_ar_uyeleri(kurulum_paketi.paket_olustur(SUNUCU))["data.tar.gz"])
        self.assertIn(self.KURULUM, veri.getnames())
        self.assertEqual(veri.getmember(self.ANAHTARLIK).mode, 0o644)


class DepoUcNoktalariTestCase(_GeciciAnahtarMixin, TestCase):
    def _al(self, ad, onek=""):
        """onek="./": APT'nin düz depoda istediği "apt/./<dosya>" biçimi."""
        url = reverse("tahtalar:apt_deposu", args=[ad])
        return self.client.get(url[: -len(ad)] + onek + ad)

    def test_anahtar_yoksa_404(self):
        for ad in apt_deposu.DOSYALAR:
            self.assertEqual(self._al(ad).status_code, 404)

    def test_dosyalar_oturumsuz_sunulur_ve_ozetler_tutar(self):
        self._anahtar_uret()
        deb_adi = kurulum_paketi.paket_dosya_adi()
        deb = self._al(deb_adi).content
        packages = self._al("Packages", "./").content
        release = self._al("Release").content.decode()
        self.assertTrue(deb.startswith(b"!<arch>\n"))

        pk = packages.decode()
        self.assertIn("Package: akal-eta-yonetim\n", pk)
        self.assertIn(f"Version: {kurulum_paketi.uygulama_surumu()}\n", pk)
        self.assertIn(f"Filename: {deb_adi}\n", pk)
        self.assertIn(f"Size: {len(deb)}\n", pk)
        self.assertIn(f"SHA256: {hashlib.sha256(deb).hexdigest()}\n", pk)
        self.assertTrue(pk.rstrip("\n").split("\n")[-1].startswith(" "))  # açıklama sonda
        self.assertIn(
            f" {hashlib.sha256(packages).hexdigest()} {len(packages)} Packages\n", release
        )
        self.assertIn("Date: Thu, 01 Jan 2026 00:00:00 GMT\n", release)

        inrelease = self._al("InRelease", "./").content.decode()
        self.assertIn(release, inrelease)
        self.assertEqual(self._al("InRelease").content, self._al("InRelease").content)

    def test_bilinmeyen_dosya_ve_post(self):
        self._anahtar_uret()
        self.assertEqual(self._al("Packages.gz").status_code, 404)
        self.assertEqual(self._al("akal-eta-yonetim_0.1_all.deb").status_code, 404)
        url = reverse("tahtalar:apt_deposu", args=["Release"])
        self.assertEqual(self.client.post(url).status_code, 405)

    @unittest.skipUnless(GPGV, "gpgv kurulu değil")
    def test_gpgv_imzalari_dogrular(self):
        self._anahtar_uret()
        for ad in ("InRelease", "Release", "Release.gpg"):
            (self.yol / ad).write_bytes(self._al(ad).content)
        sonuc = self._gpgv(self.yol / "InRelease")
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)
        sonuc = self._gpgv(self.yol / "Release.gpg", self.yol / "Release")
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)
        # Değiştirilmiş Release reddedilir.
        (self.yol / "Release").write_text("Origin: sahte\n")
        self.assertNotEqual(
            self._gpgv(self.yol / "Release.gpg", self.yol / "Release").returncode, 0
        )

    @unittest.skipUnless(shutil.which("apt-ftparchive"), "apt-ftparchive kurulu değil")
    def test_packages_apt_ftparchive_ile_ayni(self):
        self._anahtar_uret()
        (self.yol / kurulum_paketi.paket_dosya_adi()).write_bytes(
            kurulum_paketi.depo_paketi_olustur()
        )
        beklenen = subprocess.run(
            ["apt-ftparchive", "packages", "."], cwd=self.yol, capture_output=True, text=True
        ).stdout
        self.assertIn("SHA256:", beklenen)
        pk = self._al("Packages").content.decode()
        for satir in beklenen.splitlines():
            if satir.startswith(("SHA256:", "Size:", "Package:", "Version:")):
                self.assertIn(satir, pk)


class SurumArsiviTestCase(_GeciciAnahtarMixin, TestCase):
    def _surumlu_paket(self, surum):
        """Aynı paketin başka bir sürümü (arşivde eski sürümü taklit eder)."""
        with mock.patch.object(kurulum_paketi, "uygulama_surumu", return_value=surum):
            return kurulum_paketi.depo_paketi_olustur()

    def _arsive_koy(self, *surumler):
        apt_deposu.ARSIV_KLASORU.mkdir(exist_ok=True)
        for surum in surumler:
            (apt_deposu.ARSIV_KLASORU / f"akal-eta-yonetim_{surum}_all.deb").write_bytes(
                self._surumlu_paket(surum)
            )

    def test_guncel_surum_arsivlenir_ve_degismez(self):
        self._anahtar_uret()
        apt_deposu.depo_dosyasi("Packages")
        yol = apt_deposu.ARSIV_KLASORU / kurulum_paketi.paket_dosya_adi()
        self.assertEqual(yol.read_bytes(), kurulum_paketi.depo_paketi_olustur())
        zaman = yol.stat().st_mtime_ns
        apt_deposu.depo_dosyasi("Packages")
        apt_deposu.guncel_surumu_arsivle()
        self.assertEqual(yol.stat().st_mtime_ns, zaman)

    def test_eski_surumler_listelenir_ve_indirilir(self):
        self._anahtar_uret()
        self._arsive_koy("0.9.0", "1.0.0", "1.1.0", "1.1.10", "1.1.9", "1.1.2")
        pk = apt_deposu.depo_dosyasi("Packages").decode()
        surumler = [s.split(": ")[1] for s in pk.splitlines() if s.startswith("Version: ")]
        guncel = kurulum_paketi.uygulama_surumu()
        # Son 5: dördü arşivden (sayısal sıralı), sonuncusu güncel.
        self.assertEqual(surumler, ["1.1.0", "1.1.2", "1.1.9", "1.1.10", guncel])
        self.assertIn("Filename: akal-eta-yonetim_1.1.9_all.deb\n", pk)
        eski = apt_deposu.depo_dosyasi("akal-eta-yonetim_1.1.9_all.deb")
        self.assertEqual(
            hashlib.sha256(eski).hexdigest(),
            hashlib.sha256(self._surumlu_paket("1.1.9")).hexdigest(),
        )
        self.assertIn(f"SHA256: {hashlib.sha256(eski).hexdigest()}\n", pk)
        # Listede olmayan eski sürüm sunulmaz.
        self.assertIsNone(apt_deposu.depo_dosyasi("akal-eta-yonetim_0.9.0_all.deb"))

    def test_arsiv_yazilamazsa_depo_calisir(self):
        self._anahtar_uret()
        apt_deposu.ARSIV_KLASORU.write_text("klasör değil")
        with self.assertLogs("tahtalar.services.apt_deposu", "WARNING"):
            self.assertIsNotNone(apt_deposu.depo_dosyasi("InRelease"))

    @unittest.skipUnless(GPGV, "gpgv kurulu değil")
    def test_cok_surumlu_depo_imzasi_dogrulanir(self):
        self._anahtar_uret()
        self._arsive_koy("1.1.0")
        (self.yol / "InRelease").write_bytes(apt_deposu.depo_dosyasi("InRelease"))
        self.assertEqual(self._gpgv(self.yol / "InRelease").returncode, 0)


@override_settings(TAHTA_KAYIT_ANAHTARI="k")
class SonSurumBildirimiTestCase(_GeciciAnahtarMixin, TestCase):
    def _durum(self):
        token = self.client.post(
            reverse("tahtalar:api_kayit"),
            json.dumps({"kayit_anahtari": "k", "makine_kimligi": "m1"}),
            content_type="application/json",
        ).json()["token"]
        return self.client.post(
            reverse("tahtalar:api_durum"),
            "{}",
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {token}",
        ).json()

    def test_depo_yoksa_son_surum_bildirilmez(self):
        self.assertNotIn("son_surum", self._durum())

    def test_depo_varsa_son_surum_bildirilir_ve_arsivlenir(self):
        self._anahtar_uret()
        self.assertEqual(self._durum()["son_surum"], kurulum_paketi.uygulama_surumu())
        self.assertTrue(Tahta.objects.filter(makine_kimligi="m1").exists())
        self.assertTrue((apt_deposu.ARSIV_KLASORU / kurulum_paketi.paket_dosya_adi()).is_file())

    def test_kendini_guncelleme_sonucu_kaydedilir(self):
        tahta = Tahta.objects.create(ad="K1", makine_kimligi="x", token_ozeti="x")
        ajan_api.durum_guncelle(
            tahta,
            {
                "kendini_guncelleme": {
                    "durum": "geri_donuldu",
                    "zaman": 1_700_000_000,
                    "hedef": "1.3.0",
                }
            },
        )
        tahta.refresh_from_db()
        self.assertEqual(
            (tahta.oto_guncelleme_durumu, tahta.oto_guncelleme_hedef),
            ("geri_donuldu", "1.3.0"),
        )
        self.assertEqual(int(tahta.oto_guncelleme_zamani.timestamp()), 1_700_000_000)
        for gecersiz in (
            None,
            {"durum": "uydurma", "zaman": 5, "hedef": "1.0.0"},
            {"durum": "basarili", "zaman": 5, "hedef": "1.0; rm"},
            {"durum": "basarili", "hedef": "1.4.0"},
        ):
            ajan_api.durum_guncelle(tahta, {"kendini_guncelleme": gecersiz})
        tahta.refresh_from_db()
        self.assertEqual(tahta.oto_guncelleme_hedef, "1.3.0")


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class BakimciBetikleriTestCase(_GeciciAnahtarMixin, TestCase):
    """postinst/postrm'yi geçici bir kök altında gerçekten çalıştırır
    (/etc, /usr/share yolları köke yönlendirilir; systemctl çağrılmaz)."""

    def _kok_betigi(self, betik):
        return (
            betik.replace("/etc/", f"{self.kok}/etc/")
            .replace("/usr/share/", f"{self.kok}/usr/share/")
            .replace("/run/systemd/system", f"{self.kok}/systemd-yok")
        )

    def _kur(self, paket):
        self.kok = self.yol / "kok"
        for klasor in ("etc/apt/sources.list.d", "etc/apt/apt.conf.d", "etc/apt/preferences.d"):
            (self.kok / klasor).mkdir(parents=True, exist_ok=True)
        uyeler = _ar_uyeleri(paket)
        _tar(uyeler["data.tar.gz"]).extractall(self.kok, filter="data")
        kontrol = _tar(uyeler["control.tar.gz"])
        self.betikler = {
            ad: self._kok_betigi(kontrol.extractfile(f"./{ad}").read().decode())
            for ad in ("postinst", "postrm")
        }
        return self._calistir("postinst", "configure")

    def _calistir(self, ad, arguman):
        # dpkg-query: postinst kurulan sürümü sorar (tahtada dpkg'nin kaydı).
        sahte = self.yol / "bin"
        sahte.mkdir(exist_ok=True)
        (sahte / "dpkg-query").write_text("#!/bin/sh\nprintf 1.2.7\n")
        (sahte / "dpkg-query").chmod(0o755)
        sonuc = subprocess.run(
            ["sh", "-c", self.betikler[ad], ad, arguman],
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{sahte}:{os.environ['PATH']}"},
        )
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)
        return sonuc

    def _dosya(self, yol):
        return (self.kok / yol).read_text()

    def test_kurulum_paketi_depo_kaynagini_kurar(self):
        self._anahtar_uret()
        self._kur(kurulum_paketi.paket_olustur(SUNUCU + ":8443/"))
        anahtarlik = f"{self.kok}/usr/share/keyrings/akal-eta-yonetim.gpg"
        self.assertEqual(
            self._dosya("etc/apt/sources.list.d/akal-eta-yonetim.list"),
            f"deb [signed-by={anahtarlik}] https://okul.test:8443/tahtalar/apt/ ./\n",
        )
        apt_ayar = self._dosya("etc/apt/apt.conf.d/50akal-eta-yonetim")
        self.assertIn('Acquire::https::Proxy::okul.test "DIRECT";\n', apt_ayar)
        # Kurulu sürüm sabitlenir: genel "apt upgrade" bu paketi yükseltmez
        # (yalnızca sağlık kontrollü yol, tam sürüm belirterek).
        self.assertEqual(
            self._dosya("etc/apt/preferences.d/akal-eta-yonetim"),
            "Package: akal-eta-yonetim\nPin: version 1.2.7\nPin-Priority: 1000\n",
        )
        self.assertIn('Acquire::http::Proxy::okul.test "DIRECT";\n', apt_ayar)
        ayar = self._dosya("etc/akal-eta-yonetim/akal-eta-yonetim.conf")
        self.assertIn(f"kayit_anahtari = {ANAHTAR}\n", ayar)

    def test_depo_paketi_ayarlara_dokunmaz_ve_ca_yi_apt_icin_kopyalar(self):
        self._anahtar_uret()
        self.kok = self.yol / "kok"
        ayar_klasoru = self.kok / "etc/akal-eta-yonetim"
        ayar_klasoru.mkdir(parents=True)
        ca = ayar_klasoru / "yerel-ca.crt"
        ca.write_text("CA\n")
        ayar = ayar_klasoru / "akal-eta-yonetim.conf"
        ayar_metni = (
            "[akal-eta-yonetim]\nsunucu = http://10.0.0.5/ \nkayit_anahtari = ESKI\n"
            f"ca_dosyasi = {ca}\naralik = 90\n"
        )
        ayar.write_text(ayar_metni)

        self._kur(kurulum_paketi.depo_paketi_olustur())
        self.assertEqual(ayar.read_text(), ayar_metni)
        self.assertIn(
            " http://10.0.0.5/tahtalar/apt/ ./\n",
            self._dosya("etc/apt/sources.list.d/akal-eta-yonetim.list"),
        )
        # HTTP: CA gerekmez.
        self.assertNotIn("CaInfo", self._dosya("etc/apt/apt.conf.d/50akal-eta-yonetim"))
        self.assertFalse((self.kok / "etc/apt/akal-eta-yonetim-ca.crt").exists())

        ayar.write_text(ayar_metni.replace("http://10.0.0.5/", "https://10.0.0.5:8443"))
        self._calistir("postinst", "configure")
        apt_ca = self.kok / "etc/apt/akal-eta-yonetim-ca.crt"
        self.assertEqual(apt_ca.read_text(), "CA\n")
        self.assertEqual(apt_ca.stat().st_mode & 0o777, 0o644)
        self.assertIn(
            f'Acquire::https::10.0.0.5::CaInfo "{apt_ca}";\n',
            self._dosya("etc/apt/apt.conf.d/50akal-eta-yonetim"),
        )

    def test_anahtar_yoksa_depo_kaynagi_kurulmaz_eskisi_silinir(self):
        self.kok = self.yol / "kok"
        liste = self.kok / "etc/apt/sources.list.d/akal-eta-yonetim.list"
        liste.parent.mkdir(parents=True)
        liste.write_text("eski\n")
        self._kur(kurulum_paketi.paket_olustur(SUNUCU))
        self.assertFalse(liste.exists())

    def test_kaldirinca_depo_kaynagi_silinir_yukseltmede_kalir(self):
        self._anahtar_uret()
        self._kur(kurulum_paketi.paket_olustur(SUNUCU))
        liste = self.kok / "etc/apt/sources.list.d/akal-eta-yonetim.list"
        self._calistir("postrm", "upgrade")
        self.assertTrue(liste.exists())
        self._calistir("postrm", "remove")
        self.assertFalse(liste.exists())
        self.assertFalse((self.kok / "etc/apt/apt.conf.d/50akal-eta-yonetim").exists())
        self.assertFalse((self.kok / "etc/apt/preferences.d/akal-eta-yonetim").exists())


def _calisma(stdout="", returncode=0, stderr=""):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=stderr)


class AjanKendiniGuncellemeTestCase(TestCase):
    def setUp(self):
        self.ajan = _ajan_modulu()
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        self.ajan.DURUM_KLASORU = self.klasor.name
        self.ajan.SURUM = "1.2.0"

    def _calistir(self, son_surum, aktif=()):
        cagrilar = []

        def run(arguman, **kw):
            cagrilar.append(arguman)
            if arguman[:2] == ["systemctl", "is-active"]:
                return _calisma("active\n" if arguman[2] in aktif else "inactive\n")
            return _calisma()

        with mock.patch.object(self.ajan.subprocess, "run", side_effect=run):
            sonuc = self.ajan.kendini_guncelle(son_surum)
        return sonuc, [c for c in cagrilar if c[0] == "systemd-run"]

    def test_surum_karsilastirma(self):
        self.assertEqual(self.ajan.surum_parcalari("1.10.0"), (1, 10, 0))
        self.assertGreater(self.ajan.surum_parcalari("1.10.0"), self.ajan.surum_parcalari("1.9.9"))
        for gecersiz in (None, "", "1.2.x", 5):
            self.assertIsNone(self.ajan.surum_parcalari(gecersiz))

    def test_yeni_surum_varsa_ayri_birimde_guncellenir(self):
        basladi, cagrilar = self._calistir("1.10.0")
        self.assertTrue(basladi)
        self.assertIn("--unit=akal-eta-yonetim-kendini-guncelle", cagrilar[0])
        betik = str(Path(self.klasor.name) / "kendini-guncelle.sh")
        # Betik komut satırında verilmez (systemd ${...} ifadelerini boşaltır);
        # durum klasöründeki dosyadan çalışır.
        self.assertEqual(
            cagrilar[0][cagrilar[0].index("/bin/sh") :],
            ["/bin/sh", betik, "1.10.0", self.klasor.name, "180"],
        )
        self.assertFalse(any("${" in a for a in cagrilar[0]))
        icerik = Path(betik).read_text()
        self.assertEqual(icerik, self.ajan.KENDINI_GUNCELLEME_BETIGI)
        self.assertEqual(os.stat(betik).st_mode & 0o777, 0o600)
        self.assertIn('install "$UYG=$HEDEF"', icerik)
        self.assertIn("Dir::Etc::sourcelist", icerik)
        self.assertNotIn(" upgrade", icerik)

    def test_geri_donulen_surum_bir_daha_denenmez(self):
        (Path(self.klasor.name) / "bozuk-surumler").write_text("1.3.0\n")
        self.assertEqual(self._calistir("1.3.0"), (False, []))
        self.assertTrue(self._calistir("1.3.1")[0])

    def test_durum_bildirimi(self):
        self.assertIsNone(self.ajan.kendini_guncelleme_durumu())
        sonuc = Path(self.klasor.name) / "kendini-guncelleme-sonuc"
        sonuc.write_text("geri_donuldu 1700000000 1.3.0\n")
        self.assertEqual(
            self.ajan.kendini_guncelleme_durumu(),
            {"durum": "geri_donuldu", "zaman": 1700000000, "hedef": "1.3.0"},
        )
        sonuc.write_text("suruyor 1700000000 1.3.0\n")
        with mock.patch.object(self.ajan, "_birim_calisiyor", return_value=False):
            self.assertEqual(self.ajan.kendini_guncelleme_durumu()["durum"], "yarida_kaldi")
        with mock.patch.object(self.ajan, "_birim_calisiyor", return_value=True):
            self.assertEqual(self.ajan.kendini_guncelleme_durumu()["durum"], "suruyor")

    def test_calisiyor_isareti(self):
        self.ajan.calisiyor_isaretini_yaz()
        surum, zaman = (Path(self.klasor.name) / "calisiyor").read_text().split()
        self.assertEqual(surum, "1.2.0")
        self.assertLessEqual(abs(int(zaman) - time.time()), 5)

    def test_ayni_eski_ya_da_gecersiz_surumde_bir_sey_yapilmaz(self):
        for surum in ("1.2.0", "1.1.9", None, "bozuk"):
            with self.subTest(surum=surum):
                self.assertEqual(self._calistir(surum), (False, []))

    def test_basarisiz_deneme_saatte_bir_tekrarlanir(self):
        self.assertTrue(self._calistir("1.3.0")[0])
        self.assertFalse(self._calistir("1.3.0")[0])
        # Daha yeni bir sürüm beklemeden denenir.
        self.assertTrue(self._calistir("1.4.0")[0])
        dosya = Path(self.klasor.name) / "kendini-guncelleme"
        dosya.write_text(f"{int(time.time()) - 3601} 1.4.0\n")
        self.assertTrue(self._calistir("1.4.0")[0])

    def test_guncelleme_surerken_baslatilmaz(self):
        for birim in ("akal-eta-yonetim-guncelleme", "akal-eta-yonetim-kendini-guncelle"):
            with self.subTest(birim=birim):
                self.assertEqual(self._calistir("2.0.0", aktif=(birim,)), (False, []))

    def test_kendini_guncellerken_kapatilmaz(self):
        def run(arguman, **kw):
            if arguman[:2] == ["systemctl", "is-active"]:
                aktif = arguman[2] == "akal-eta-yonetim-kendini-guncelle"
                return _calisma("active\n" if aktif else "inactive\n")
            return _calisma()

        with mock.patch.object(self.ajan.subprocess, "run", side_effect=run):
            durum, mesaj = self.ajan.komutu_uygula("kapat")
        self.assertEqual(durum, "basarisiz")

    def test_betik_depo_tanimli_degilse_hata_verir(self):
        sonuc = self._betik(liste_var=False)
        self.assertEqual(sonuc.returncode, 1)
        self.assertIn("APT deposu tanımlı değil", sonuc.stderr)
        self.assertTrue(self._sonuc().startswith("basarisiz "))

    def _betik(self, liste_var=True, saglikli=True, kurulum="tamam", geri_donus=0):
        """Betiği apt-get / dpkg-query / sleep yerine sahte komutlarla çalıştırır.
        kurulum: "tamam" | "baslamadi" (paket değişmeden hata) | "yarida" (dpkg
        durumu değişip hata). Sahte apt-get çağrıları "apt.log"a yazılır."""
        kok = Path(self.klasor.name)
        sahte = kok / "bin"
        sahte.mkdir(exist_ok=True)
        apt_klasoru = kok / "apt"
        (apt_klasoru / "sources.list.d").mkdir(parents=True, exist_ok=True)
        if liste_var:
            (apt_klasoru / "sources.list.d/akal-eta-yonetim.list").write_text("deb x ./\n")
        (kok / "paket").write_text("1.2.0 ii ")
        komutlar = {
            "dpkg-query": f'#!/bin/sh\ncat "{kok}/paket"\n',
            "sleep": "#!/bin/sh\nexit 0\n",
            "dpkg": "#!/bin/sh\nexit 0\n",
            "apt-get": f"""#!/bin/sh
echo "$*" >> "{kok}/apt.log"
case "$*" in
  *update*) exit 0 ;;
  *akal-eta-yonetim=1.2.0*) echo "1.2.0 ii " > "{kok}/paket"; exit {geri_donus} ;;
esac
case "{kurulum}" in
  baslamadi) exit 100 ;;
  yarida) echo "1.3.0 iF " > "{kok}/paket"; exit 100 ;;
esac
echo "1.3.0 ii " > "{kok}/paket"
[ "{int(saglikli)}" = 1 ] && echo "1.3.0 $(date +%s)" > "{kok}/calisiyor"
exit 0
""",
        }
        for ad, icerik in komutlar.items():
            (sahte / ad).write_text(icerik)
            (sahte / ad).chmod(0o755)
        return subprocess.run(
            [
                "/bin/sh",
                "-c",
                self.ajan.KENDINI_GUNCELLEME_BETIGI.replace("/etc/apt", str(apt_klasoru)),
                "test",
                "1.3.0",
                str(kok),
                "15",
            ],
            env={"PATH": f"{sahte}:/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )

    def _sonuc(self):
        return (Path(self.klasor.name) / "kendini-guncelleme-sonuc").read_text()

    def _bozuk(self):
        yol = Path(self.klasor.name) / "bozuk-surumler"
        return yol.read_text().split() if yol.exists() else []

    def _apt_log(self):
        return (Path(self.klasor.name) / "apt.log").read_text()

    def test_betik_saglikliysa_basarili(self):
        sonuc = self._betik()
        self.assertEqual(sonuc.returncode, 0, sonuc.stderr)
        self.assertTrue(self._sonuc().startswith("basarili "))
        self.assertTrue(self._sonuc().rstrip().endswith(" 1.3.0"))
        self.assertNotIn("--allow-downgrades", self._apt_log())
        self.assertEqual(self._bozuk(), [])

    def test_betik_yeni_surum_konusamazsa_geri_doner(self):
        sonuc = self._betik(saglikli=False)
        self.assertEqual(sonuc.returncode, 1)
        self.assertIn("sunucuyla konuşamadı", sonuc.stderr)
        self.assertIn("--allow-downgrades install akal-eta-yonetim=1.2.0", self._apt_log())
        self.assertTrue(self._sonuc().startswith("geri_donuldu "))
        self.assertEqual(self._bozuk(), ["1.3.0"])
        # İkinci başarısızlıkta liste tekrarlanmaz.
        self._betik(saglikli=False)
        self.assertEqual(self._bozuk(), ["1.3.0"])

    def test_betik_kurulum_yarida_kalirsa_geri_doner(self):
        self._betik(kurulum="yarida")
        self.assertTrue(self._sonuc().startswith("geri_donuldu "))
        self.assertEqual(self._bozuk(), ["1.3.0"])

    def test_betik_kurulum_baslamadiysa_geri_donmez_bozuk_saymaz(self):
        sonuc = self._betik(kurulum="baslamadi")
        self.assertEqual(sonuc.returncode, 1)
        self.assertIn("1.2.0 sürümü değişmedi", sonuc.stderr)
        self.assertNotIn("--allow-downgrades", self._apt_log())
        self.assertTrue(self._sonuc().startswith("basarisiz "))
        self.assertEqual(self._bozuk(), [])

    def test_betik_geri_donus_de_basarisizsa(self):
        sonuc = self._betik(saglikli=False, geri_donus=100)
        self.assertIn("paketi elle kurun", sonuc.stderr)
        self.assertTrue(self._sonuc().startswith("basarisiz "))

    def test_tur_sunucunun_bildirdigi_surumle_cagirir(self):
        with (
            mock.patch.object(self.ajan, "durum_bilgisi", return_value={}),
            mock.patch.object(
                self.ajan, "istek", return_value={"komutlar": [], "son_surum": "9.0.0"}
            ),
            mock.patch.object(self.ajan, "kendini_guncelle") as kendini_guncelle,
        ):
            self.ajan.tur({"sunucu": SUNUCU}, "t", [])
        kendini_guncelle.assert_called_once_with("9.0.0")


class PaketSayfasiDepoDurumuTestCase(_GeciciAnahtarMixin, TestCase):
    def _sayfa(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        return self.client.get(reverse("tahtalar:paket"))

    def test_geri_donulen_tahta_listede_gorunur(self):
        self._anahtar_uret()
        Tahta.objects.create(
            ad="K7",
            makine_kimligi="7",
            token_ozeti="7",
            ajan_surumu="1.1.0",
            oto_guncelleme_durumu="geri_donuldu",
            oto_guncelleme_hedef="9.9.9",
            oto_guncelleme_zamani=timezone.now(),
        )
        self.assertContains(self._sayfa(), "9.9.9: Çalışmadı, geri dönüldü")

    def test_depo_durumu_gosterilir(self):
        self.assertContains(self._sayfa(), "tahta_apt_anahtari_olustur")
        depo_anahtari.ANAHTAR_DOSYASI.write_text("{bozuk")
        yanit = self._sayfa()
        self.assertContains(yanit, "okunamadı")
        depo_anahtari.ANAHTAR_DOSYASI.unlink()
        self._anahtar_uret()
        self.assertTrue(self._sayfa().context["depo_hazir"])
