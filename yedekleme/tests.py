"""Yedekleme app testleri.

pg_dump/pg_restore gerektiren gerçek yedekleme/geri yükleme akışları burada test
edilmez (test ortamı sqlite kullanır, bkz. config/settings/test.py) — bunun yerine
güvenlik açısından kritik iki nokta doğrulanır: dosya adı doğrulaması (path
traversal koruması) ve yetki sınırı (yalnızca mudur_yardimcisi).
"""

import tempfile
from pathlib import Path

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase

from yedekleme.services import yedek_servisi


class GuvenliYolTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._orijinal_backup_dir = yedek_servisi.BACKUP_DIR
        yedek_servisi.BACKUP_DIR = self.gecici_dizin

    def tearDown(self):
        yedek_servisi.BACKUP_DIR = self._orijinal_backup_dir

    def _dosya_olustur(self, ad: str, icerik: bytes = b"sahte-dump") -> Path:
        yol = self.gecici_dizin / ad
        yol.write_bytes(icerik)
        return yol

    def test_gecerli_dosya_kabul_edilir(self):
        self._dosya_olustur("nobet_db_web_20260101_000000.dump")
        yol = yedek_servisi.guvenli_yol("nobet_db_web_20260101_000000.dump")
        self.assertEqual(yol.name, "nobet_db_web_20260101_000000.dump")

    def test_path_traversal_reddedilir(self):
        # backups/ dışına çıkmaya çalışan bir ad — dizin bileşenleri Path(...).name ile
        # atılır, kalan "passwd" ise .dump ile bitmediği için zaten reddedilir.
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.guvenli_yol("../../../../etc/passwd")

    def test_dump_olmayan_uzanti_reddedilir(self):
        self._dosya_olustur("zararli.sh")
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.guvenli_yol("zararli.sh")

    def test_var_olmayan_dosya_reddedilir(self):
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.guvenli_yol("hic_olmayan.dump")

    def test_gizli_dump_uzantili_traversal_de_reddedilir(self):
        # "..%2f" gibi encode edilmiş varyantlar Django URL çözümleyicisine hiç
        # ulaşmadan önce decode edilmiş olur; burada düz "../" biçimini test ediyoruz.
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.guvenli_yol("../.env")

    def test_yedekleri_listele_yalnizca_dump_dosyalarini_gorur(self):
        self._dosya_olustur("a.dump")
        self._dosya_olustur("b.dump")
        self._dosya_olustur("okunmamali.txt")
        yedekler = yedek_servisi.yedekleri_listele()
        self.assertEqual({y.ad for y in yedekler}, {"a.dump", "b.dump"})


class YetkiTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.mudur_yardimcisi = User.objects.create_user("mudur", password="test-pass-123")
        grup, _ = Group.objects.get_or_create(name="mudur_yardimcisi")
        self.mudur_yardimcisi.groups.add(grup)

        self.ogretmen = User.objects.create_user("ogretmen", password="test-pass-123")

    def test_giris_yapmamis_kullanici_login_sayfasina_yonlenir(self):
        yanit = self.client.get("/yedekleme/")
        self.assertEqual(yanit.status_code, 302)
        self.assertIn("/giris/", yanit.url)

    def test_yetkisiz_kullanici_reddedilir(self):
        self.client.login(username="ogretmen", password="test-pass-123")
        yanit = self.client.get("/yedekleme/")
        self.assertEqual(yanit.status_code, 403)

    def test_mudur_yardimcisi_erisebilir(self):
        self.client.login(username="mudur", password="test-pass-123")
        yanit = self.client.get("/yedekleme/")
        self.assertEqual(yanit.status_code, 200)

    def test_indirme_var_olmayan_dosya_icin_404_doner(self):
        self.client.login(username="mudur", password="test-pass-123")
        yanit = self.client.get("/yedekleme/hic-yok.dump/indir/")
        self.assertEqual(yanit.status_code, 404)

    def test_indirme_path_traversal_404_doner(self):
        self.client.login(username="mudur", password="test-pass-123")
        # Django URL çözümleyicisi "/" içeren bir <str:dosya_adi> segmentini zaten
        # eşleştirmez; burada tek segmentlik ama backups/ dışını hedefleyemeyen bir
        # ad deneniyor (uzantı .dump değil → guvenli_yol reddeder).
        yanit = self.client.get("/yedekleme/zararli.dump.txt/indir/")
        self.assertEqual(yanit.status_code, 404)
