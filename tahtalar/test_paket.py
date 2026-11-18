"""tahtalar — ajan .deb paketi: üretim, sayfa yetkisi ve süreli indirme linki."""

import io
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from okul.testing import kullanici_olustur
from tahtalar.models import Tahta
from tahtalar.services import ajan_paketi

ANAHTAR = "test-kayit_anahtari-123"
SUNUCU = "https://okul.test"


def _ar_uyeleri(veri):
    """ar arşivini {ad: içerik} olarak açar."""
    assert veri[:8] == b"!<arch>\n"
    uyeler, i = {}, 8
    while i < len(veri):
        baslik = veri[i : i + 60]
        ad = baslik[:16].decode().strip().rstrip("/")
        boyut = int(baslik[48:58].decode().strip())
        uyeler[ad] = veri[i + 60 : i + 60 + boyut]
        i += 60 + boyut + (boyut % 2)
    return uyeler


def _tar(veri):
    return tarfile.open(fileobj=io.BytesIO(veri), mode="r:gz")


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class PaketUretimTestCase(TestCase):
    def setUp(self):
        self.klasor = tempfile.TemporaryDirectory()
        self.addCleanup(self.klasor.cleanup)
        # Varsayılan: sunucuda CA yok.
        yama = mock.patch.object(ajan_paketi, "CA_DOSYASI", Path(self.klasor.name) / "yok.crt")
        yama.start()
        self.addCleanup(yama.stop)

    def _paket(self, sunucu=SUNUCU):
        uyeler = _ar_uyeleri(ajan_paketi.paket_olustur(sunucu))
        return uyeler, _tar(uyeler["control.tar.gz"]), _tar(uyeler["data.tar.gz"])

    def test_paket_yapisi(self):
        uyeler, kontrol, veri = self._paket()
        self.assertEqual(list(uyeler), ["debian-binary", "control.tar.gz", "data.tar.gz"])
        self.assertEqual(uyeler["debian-binary"], b"2.0\n")
        control = kontrol.extractfile("./control").read().decode()
        self.assertIn("Package: okul-ajan\n", control)
        self.assertIn(f"Version: {ajan_paketi.ajan_surumu()}\n", control)
        self.assertIn("Architecture: all\n", control)
        for betik in ("./postinst", "./prerm", "./postrm"):
            self.assertEqual(kontrol.getmember(betik).mode, 0o755)
        adlar = veri.getnames()
        self.assertIn("./opt/okul-ajan/okul_ajan.py", adlar)
        self.assertIn("./lib/systemd/system/okul-ajan.service", adlar)
        self.assertNotIn("./usr/share/okul-ajan/yerel-ca.crt", adlar)
        for uye in veri.getmembers():
            self.assertEqual((uye.uid, uye.gid, uye.uname), (0, 0, "root"))

    def test_ajan_kodu_degistirilmeden_gomulur(self):
        _, _, veri = self._paket()
        self.assertEqual(
            veri.extractfile("./opt/okul-ajan/okul_ajan.py").read(),
            (ajan_paketi.AJAN_KLASORU / "okul_ajan.py").read_bytes(),
        )

    def test_kurulum_ayari_gomulur_ve_yalniz_root_okur(self):
        _, _, veri = self._paket("okul.test:8443/")
        uye = veri.getmember("./usr/share/okul-ajan/kurulum.conf")
        self.assertEqual(uye.mode, 0o600)
        icerik = veri.extractfile(uye).read().decode()
        self.assertIn("SUNUCU_ADRESI='https://okul.test:8443'", icerik)
        self.assertIn(f"TAHTA_KAYIT_ANAHTARI='{ANAHTAR}'", icerik)

    def test_ca_varsa_https_icin_gomulur(self):
        ca = Path(self.klasor.name) / "ca.crt"
        ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nX\n")
        with mock.patch.object(ajan_paketi, "CA_DOSYASI", ca):
            _, _, veri = self._paket()
            self.assertEqual(
                veri.extractfile("./usr/share/okul-ajan/yerel-ca.crt").read(), ca.read_bytes()
            )
            _, _, veri = self._paket("http://okul.test")
            self.assertNotIn("./usr/share/okul-ajan/yerel-ca.crt", veri.getnames())

    def test_gecersiz_sunucu_adresi(self):
        for adres in ("", "https://okul.test/'; rm -rf /", "ftp://x", "https://a b"):
            with self.subTest(adres=adres), self.assertRaises(ajan_paketi.PaketHatasi):
                ajan_paketi.paket_olustur(adres)

    def test_kayit_anahtari_yoksa_paket_uretilmez(self):
        for anahtar in ("", "kotu'anahtar"):
            with self.subTest(anahtar=anahtar), override_settings(TAHTA_KAYIT_ANAHTARI=anahtar):
                with self.assertRaises(ajan_paketi.PaketHatasi):
                    ajan_paketi.paket_olustur(SUNUCU)

    def test_bakimci_betikleri_sozdizimi(self):
        _, kontrol, _ = self._paket()
        for betik in ("./postinst", "./prerm", "./postrm"):
            with self.subTest(betik=betik):
                sonuc = subprocess.run(
                    ["sh", "-n"], input=kontrol.extractfile(betik).read(), capture_output=True
                )
                self.assertEqual(sonuc.returncode, 0, sonuc.stderr)

    @unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb kurulu değil")
    def test_dpkg_deb_paketi_okur(self):
        yol = Path(self.klasor.name) / ajan_paketi.paket_dosya_adi()
        yol.write_bytes(ajan_paketi.paket_olustur(SUNUCU))
        bilgi = subprocess.run(["dpkg-deb", "--info", yol], capture_output=True, text=True)
        self.assertEqual(bilgi.returncode, 0, bilgi.stderr)
        self.assertIn("Package: okul-ajan", bilgi.stdout)
        icerik = subprocess.run(["dpkg-deb", "--contents", yol], capture_output=True, text=True)
        self.assertEqual(icerik.returncode, 0, icerik.stderr)
        self.assertIn("root/root", icerik.stdout)
        self.assertIn("./opt/okul-ajan/okul_ajan.py", icerik.stdout)


@override_settings(TAHTA_KAYIT_ANAHTARI=ANAHTAR)
class PaketSayfasiTestCase(TestCase):
    url = reverse("tahtalar:paket")

    def _giris(self, grup="mudur_yardimcisi"):
        self.client.force_login(kullanici_olustur(grup))

    def test_yalniz_ust_yonetici_girer(self):
        for grup in ("mudur_yardimcisi", "okul_muduru"):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(self.url).status_code, 200)
        for grup in ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.assertEqual(
                    self.client.post(self.url, {"sunucu": SUNUCU, "islem": "indir"}).status_code,
                    403,
                )
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_dogrudan_indirme(self):
        self._giris()
        yanit = self.client.post(self.url, {"sunucu": SUNUCU, "islem": "indir"})
        self.assertEqual(yanit.status_code, 200)
        self.assertIn(ajan_paketi.paket_dosya_adi(), yanit["Content-Disposition"])
        self.assertEqual(yanit["Cache-Control"], "no-store")
        self.assertTrue(yanit.content.startswith(b"!<arch>\n"))

    def test_link_uretilir_ve_oturumsuz_indirilir(self):
        self._giris()
        yanit = self.client.post(self.url, {"sunucu": SUNUCU, "islem": "link"})
        link = yanit.context["link"]
        self.assertTrue(link.startswith(SUNUCU + "/tahtalar/paket/indir/"))
        self.assertContains(yanit, "sudo apt install -y")

        self.client.logout()
        yanit = self.client.get(link.removeprefix(SUNUCU))
        self.assertEqual(yanit.status_code, 200)
        kurulum = _tar(_ar_uyeleri(yanit.content)["data.tar.gz"]).extractfile(
            "./usr/share/okul-ajan/kurulum.conf"
        )
        self.assertIn(f"SUNUCU_ADRESI='{SUNUCU}'", kurulum.read().decode())

    def test_bozuk_ya_da_suresi_dolmus_link(self):
        token = ajan_paketi.indirme_tokeni_uret(SUNUCU)
        url = reverse("tahtalar:paket_link", args=[token[:-2] + "xx"])
        self.assertEqual(self.client.get(url).status_code, 404)
        url = reverse("tahtalar:paket_link", args=[token])
        with mock.patch.object(ajan_paketi, "LINK_GECERLILIK_SN", -1):
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_anahtar_degisirse_link_yeni_anahtarla_paket_verir(self):
        token = ajan_paketi.indirme_tokeni_uret(SUNUCU)
        url = reverse("tahtalar:paket_link", args=[token])
        with override_settings(TAHTA_KAYIT_ANAHTARI=""):
            self.assertEqual(self.client.get(url).status_code, 404)

    def test_anahtar_yoksa_sayfa_uyarir(self):
        self._giris()
        with override_settings(TAHTA_KAYIT_ANAHTARI=""):
            yanit = self.client.post(self.url, {"sunucu": SUNUCU, "islem": "link"})
        self.assertContains(yanit, "TAHTA_KAYIT_ANAHTARI tanımlı değil")
        self.assertNotIn("link", yanit.context)

    def test_eski_surumlu_tahtalar_listelenir(self):
        surum = ajan_paketi.ajan_surumu()
        Tahta.objects.create(ad="Eski", makine_kimligi="1", token_ozeti="1", ajan_surumu="0.9.0")
        Tahta.objects.create(ad="Guncel", makine_kimligi="2", token_ozeti="2", ajan_surumu=surum)
        self._giris()
        yanit = self.client.get(self.url)
        self.assertEqual([t.ad for t in yanit.context["eski_surumlu"]], ["Eski"])
