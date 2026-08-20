"""Yedekleme app testleri.

pg_dump/pg_restore gerektiren gerçek yedekleme/geri yükleme akışları burada test
edilmez (test ortamı sqlite kullanır, bkz. config/settings/test.py) — bunun yerine
güvenlik açısından kritik iki nokta doğrulanır: dosya adı doğrulaması (path
traversal koruması) ve yetki sınırı (yalnızca mudur_yardimcisi).
"""

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from yedekleme.forms import GeriYuklemeOnayForm
from yedekleme.services import gdrive_servisi, yedek_servisi


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


class YedekYukleTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._orijinal_backup_dir = yedek_servisi.BACKUP_DIR
        yedek_servisi.BACKUP_DIR = self.gecici_dizin

    def tearDown(self):
        yedek_servisi.BACKUP_DIR = self._orijinal_backup_dir

    def test_gecerli_imzali_dosya_kaydedilir(self):
        dosya = SimpleUploadedFile("disaridan.dump", b"PGDMP-sahte-icerik")
        yol = yedek_servisi.yedek_yukle(dosya)
        self.assertTrue(yol.is_file())
        self.assertIn("disaridan", yol.name)
        self.assertEqual(yol.read_bytes(), b"PGDMP-sahte-icerik")

    def test_pgdmp_imzasi_olmayan_dosya_reddedilir(self):
        dosya = SimpleUploadedFile("sahte.dump", b"bu bir pg_dump dosyasi degil")
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.yedek_yukle(dosya)
        self.assertEqual(list(self.gecici_dizin.glob("*.dump")), [])

    def test_bos_dosya_reddedilir(self):
        dosya = SimpleUploadedFile("bos.dump", b"")
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.yedek_yukle(dosya)


class YedekSilOnayFormAksiyonuTestCase(TestCase):
    # Regresyon: sil_onay.html'deki form <form method="post"> olarak action'sız
    # yazılmıştı; bu durumda form kendi URL'ine (yedek_sil_onay) post ediyordu —
    # o view silme işlemi yapmadığı için "Evet, Sil" tıklanınca hiçbir şey
    # silinmeden aynı onay sayfası yeniden render ediliyordu.
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._orijinal_backup_dir = yedek_servisi.BACKUP_DIR
        yedek_servisi.BACKUP_DIR = self.gecici_dizin
        (self.gecici_dizin / "nobet_db_web_20260101_000000.dump").write_bytes(b"sahte-dump")

        self.client = Client()
        self.mudur_yardimcisi = User.objects.create_user("mudur-sil", password="test-pass-123")
        grup, _ = Group.objects.get_or_create(name="mudur_yardimcisi")
        self.mudur_yardimcisi.groups.add(grup)
        self.client.login(username="mudur-sil", password="test-pass-123")

    def tearDown(self):
        yedek_servisi.BACKUP_DIR = self._orijinal_backup_dir

    def test_onay_formu_gercek_silme_url_sine_post_eder(self):
        yanit = self.client.get("/yedekleme/nobet_db_web_20260101_000000.dump/sil/")
        self.assertContains(yanit, "/yedekleme/nobet_db_web_20260101_000000.dump/sil/onayla/")

    def test_onaylandiginda_dosya_gercekten_silinir(self):
        dosya_yolu = self.gecici_dizin / "nobet_db_web_20260101_000000.dump"
        self.assertTrue(dosya_yolu.exists())
        yanit = self.client.post("/yedekleme/nobet_db_web_20260101_000000.dump/sil/onayla/")
        self.assertEqual(yanit.status_code, 302)
        self.assertFalse(dosya_yolu.exists())


class CopyBloklariniSayTestCase(TestCase):
    # pg_restore --data-only -f - çıktısını hiçbir veritabanına dokunmadan
    # ayrıştıran saf fonksiyon; gerçek pg_restore/postgres gerektirmez.
    def test_birden_fazla_tablo_dogru_sayilir(self):
        metin = (
            "COPY public.auth_group (id, name) FROM stdin;\n"
            "1\tA\n2\tB\n\\.\n"
            "\n"
            "COPY public.nobet_personel (id, ad) FROM stdin;\n"
            "1\tX\n\\.\n"
        )
        self.assertEqual(
            yedek_servisi._copy_bloklarini_say(metin),
            {"auth_group": 2, "nobet_personel": 1},
        )

    def test_bos_tablo_sifir_sayilir(self):
        metin = "COPY public.bos_tablo (id) FROM stdin;\n\\.\n"
        self.assertEqual(yedek_servisi._copy_bloklarini_say(metin), {"bos_tablo": 0})

    def test_copy_blogu_olmayan_metinde_bos_sozluk_doner(self):
        self.assertEqual(yedek_servisi._copy_bloklarini_say("SET x = 1;\n"), {})


class CopyBloklariniAyristirDetayTestCase(TestCase):
    # detay_tablolari verilince sayımın yanında gerçek sütun değerlerinin de
    # döndüğünü doğrular (okul adı / aktif eğitim yılı bunun üzerine kurulu).
    def test_detay_tablosunun_satirlari_sozluk_olarak_doner(self):
        metin = (
            "COPY public.okul_bilgi (id, okul_kodu, okul_adi, okul_muduru, okul_donem_id, okul_egtyil_id) FROM stdin;\n"
            "1\t759725\tAbdurrahim Karakoç Anadolu Lisesi\tNeriman Sargın KOÇAK\t3\t2\n"
            "\\.\n"
            "COPY public.egitim_ogretim_yili (id, egitim_yili, egitim_baslangic, egitim_bitis) FROM stdin;\n"
            "1\t2025-2026\t2025-09-01\t2026-08-31\n"
            "2\t2026-2027\t2026-09-01\t2027-06-25\n"
            "\\.\n"
        )
        sayimlar, detaylar = yedek_servisi._copy_bloklarini_ayristir(
            metin, detay_tablolari=frozenset({"okul_bilgi", "egitim_ogretim_yili"})
        )
        self.assertEqual(sayimlar, {"okul_bilgi": 1, "egitim_ogretim_yili": 2})
        self.assertEqual(detaylar["okul_bilgi"][0]["okul_adi"], "Abdurrahim Karakoç Anadolu Lisesi")
        self.assertEqual(detaylar["okul_bilgi"][0]["okul_egtyil_id"], "2")
        self.assertEqual(detaylar["egitim_ogretim_yili"][1]["egitim_yili"], "2026-2027")

    def test_detay_istenmeyen_tablo_icin_sozluk_bos_kalir(self):
        metin = "COPY public.auth_group (id, name) FROM stdin;\n1\tA\n\\.\n"
        _, detaylar = yedek_servisi._copy_bloklarini_ayristir(
            metin, detay_tablolari=frozenset({"okul_bilgi"})
        )
        self.assertEqual(detaylar, {})

    def test_null_deger_none_olur(self):
        metin = "COPY public.okul_bilgi (id, okul_adi) FROM stdin;\n1\t\\N\n\\.\n"
        _, detaylar = yedek_servisi._copy_bloklarini_ayristir(
            metin, detay_tablolari=frozenset({"okul_bilgi"})
        )
        self.assertIsNone(detaylar["okul_bilgi"][0]["okul_adi"])


class OkulOzetiniCikarTestCase(TestCase):
    def test_okul_adi_ve_aktif_yil_dogru_eslesir(self):
        detaylar = {
            "okul_bilgi": [{"okul_adi": "Örnek Lisesi", "okul_egtyil_id": "2"}],
            "egitim_ogretim_yili": [
                {"id": "1", "egitim_yili": "2025-2026"},
                {"id": "2", "egitim_yili": "2026-2027"},
            ],
        }
        okul_adi, aktif_yil = yedek_servisi._okul_ozetini_cikar(detaylar)
        self.assertEqual(okul_adi, "Örnek Lisesi")
        self.assertEqual(aktif_yil, "2026-2027")

    def test_okul_bilgi_yoksa_ikisi_de_none(self):
        self.assertEqual(yedek_servisi._okul_ozetini_cikar({}), (None, None))

    def test_aktif_yil_null_ise_none_doner(self):
        detaylar = {
            "okul_bilgi": [{"okul_adi": "Örnek Lisesi", "okul_egtyil_id": None}],
            "egitim_ogretim_yili": [{"id": "1", "egitim_yili": "2025-2026"}],
        }
        okul_adi, aktif_yil = yedek_servisi._okul_ozetini_cikar(detaylar)
        self.assertEqual(okul_adi, "Örnek Lisesi")
        self.assertIsNone(aktif_yil)


class YedekBilgisiTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.dosya = self.gecici_dizin / "ornek.dump"
        self.dosya.write_bytes(yedek_servisi.PG_DUMP_IMZASI + b"-sahte-icerik")

    @patch("yedekleme.services.yedek_servisi.subprocess.run")
    def test_baslik_bilgisi_ayristirilir(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                b";\n; Archive created at 2026-08-19 13:32:05 UTC\n"
                b";     dbname: nobet_db\n;     TOC Entries: 1086\n"
            ),
            stderr=b"",
        )
        bilgi = yedek_servisi.yedek_bilgisi(self.dosya)
        self.assertEqual(bilgi["olusturma_tarihi"], "2026-08-19 13:32:05 UTC")
        self.assertEqual(bilgi["kaynak_db"], "nobet_db")

    @patch("yedekleme.services.yedek_servisi.subprocess.run")
    def test_basarisiz_donus_kodu_hata_verir(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout=b"", stderr=b"bozuk dosya"
        )
        with self.assertRaises(yedek_servisi.YedekHatasi):
            yedek_servisi.yedek_bilgisi(self.dosya)


class MevcutDbTabloSayimlariTestCase(TestCase):
    def test_bilinen_tablo_dogru_sayilir_bilinmeyen_atlanir(self):
        Group.objects.create(name="test-grubu-1")
        Group.objects.create(name="test-grubu-2")
        sayimlar = yedek_servisi.mevcut_db_tablo_sayimlari(["auth_group", "olmayan_tablo"])
        self.assertEqual(sayimlar["auth_group"], Group.objects.count())
        self.assertNotIn("olmayan_tablo", sayimlar)


class YedekRaporuTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.dosya = self.gecici_dizin / "ornek.dump"
        self.dosya.write_bytes(yedek_servisi.PG_DUMP_IMZASI + b"-sahte-icerik")
        Group.objects.create(name="mevcut-grup")  # canlı DB'de auth_group'ta 1 satır

    @patch("yedekleme.services.yedek_servisi.subprocess.run")
    def test_farkli_tablo_yakalanir_ayni_olan_sayilir(self, mock_run):
        # Test DB adı ayara göre değişebilir (örn. TestCase'in kullandığı paylaşımlı
        # bellek içi sqlite takma adı); yedek_raporu()'nun karşılaştırdığı değerle
        # birebir aynı olsun diye doğrudan settings'ten okunuyor.
        canli_db_adi = settings.DATABASES["default"]["NAME"]
        toc_ciktisi = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=f";\n; Archive created at 2026-08-19 13:32:05 UTC\n;     dbname: {canli_db_adi}\n".encode(),
            stderr=b"",
        )
        # Yedekte auth_group'ta 3 satır var, canlı DB'de (setUp) 1 satır — fark yakalanmalı.
        # okul_bilgi/egitim_ogretim_yili de eklenerek okul adı ve aktif yıl çıkarımı
        # gerçek bir rapor akışında da doğrulanıyor.
        veri_ciktisi = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=(
                b"COPY public.auth_group (id, name) FROM stdin;\n1\tA\n2\tB\n3\tC\n\\.\n"
                b"COPY public.okul_bilgi (id, okul_adi, okul_egtyil_id) FROM stdin;\n"
                b"1\tOrnek Lisesi\t2\n\\.\n"
                b"COPY public.egitim_ogretim_yili (id, egitim_yili) FROM stdin;\n"
                b"1\t2025-2026\n2\t2026-2027\n\\.\n"
            ),
            stderr=b"",
        )
        mock_run.side_effect = [toc_ciktisi, veri_ciktisi]

        rapor = yedek_servisi.yedek_raporu(self.dosya)

        self.assertEqual(rapor.olusturma_tarihi, "2026-08-19 13:32:05 UTC")
        self.assertTrue(rapor.kaynak_db_eslesiyor)  # test DB adı ":memory:" ile eşleşiyor
        self.assertEqual(rapor.okul_adi, "Ornek Lisesi")
        self.assertEqual(rapor.aktif_egitim_yili, "2026-2027")
        # 3 tablo da (auth_group, okul_bilgi, egitim_ogretim_yili) yedekte veri
        # taşıyor, canlı test DB'sinde ise (setUp'taki tek auth_group kaydı hariç)
        # boş — hepsi "farklı" sayılır.
        self.assertEqual(rapor.toplam_tablo, 3)
        self.assertEqual(rapor.ayni_tablo_sayisi, 0)
        self.assertEqual({f.tablo for f in rapor.farkli_tablolar}, {"auth_group", "okul_bilgi", "egitim_ogretim_yili"})
        auth_group_farki = next(f for f in rapor.farkli_tablolar if f.tablo == "auth_group")
        self.assertEqual(auth_group_farki.canli, 1)
        self.assertEqual(auth_group_farki.yedek, 3)
        self.assertEqual(auth_group_farki.fark, 2)

    @patch("yedekleme.services.yedek_servisi.subprocess.run")
    def test_farkli_kaynak_db_isaretlenir(self, mock_run):
        toc_ciktisi = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=b";\n; Archive created at 2026-08-19 13:32:05 UTC\n;     dbname: baska_okul_db\n",
            stderr=b"",
        )
        veri_ciktisi = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=b"", stderr=b""
        )
        mock_run.side_effect = [toc_ciktisi, veri_ciktisi]

        rapor = yedek_servisi.yedek_raporu(self.dosya)
        self.assertFalse(rapor.kaynak_db_eslesiyor)


class GeriYuklemeOnayFormTestCase(TestCase):
    # Onay alanı, veritabanının adını değil, seçilen yedek dosyasının adını
    # bekler — böylece kullanıcı yanlış bir yedeği geri yüklemeye çalışırsa
    # (örn. listedeki başka bir dosyayı seçip yanlışlıkla onaylarsa değil, ama
    # en azından hangi dosyayı seçtiğini bilinçli şekilde teyit etmeden) devam
    # edemez.
    def test_yedek_dosya_adi_dogru_yazilinca_gecerli(self):
        form = GeriYuklemeOnayForm(
            {
                "dosya_adi": "nobet_db_web_20260101_000000.dump",
                "dogrulama": "nobet_db_web_20260101_000000.dump",
                "onay": "on",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_yanlis_yazilinca_reddedilir(self):
        form = GeriYuklemeOnayForm(
            {
                "dosya_adi": "nobet_db_web_20260101_000000.dump",
                "dogrulama": "baska_bir_dosya.dump",
                "onay": "on",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("dogrulama", form.errors)

    def test_onay_kutusu_isaretlenmezse_reddedilir(self):
        form = GeriYuklemeOnayForm(
            {
                "dosya_adi": "nobet_db_web_20260101_000000.dump",
                "dogrulama": "nobet_db_web_20260101_000000.dump",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("onay", form.errors)


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

    def test_yukleme_yetkisiz_kullanici_reddedilir(self):
        self.client.login(username="ogretmen", password="test-pass-123")
        yanit = self.client.post("/yedekleme/yukle/")
        self.assertEqual(yanit.status_code, 403)

    def test_yukleme_dump_olmayan_uzanti_form_hatasi_verir(self):
        self.client.login(username="mudur", password="test-pass-123")
        dosya = SimpleUploadedFile("sahte.txt", b"PGDMP-icerik")
        yanit = self.client.post("/yedekleme/yukle/", {"dosya": dosya}, follow=True)
        mesajlar = [str(m) for m in yanit.context["messages"]]
        self.assertTrue(any(".dump" in m for m in mesajlar))


class GdriveAktifMiTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.token_yolu = self.gecici_dizin / "token.json"

    def test_ucu_de_tanimli_ve_token_varken_aktif(self):
        self.token_yolu.write_text("{}")
        with patch.dict(
            "os.environ",
            {
                "YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": "/tmp/istemci.json",
                "YEDEKLEME_GDRIVE_TOKEN": str(self.token_yolu),
                "YEDEKLEME_GDRIVE_KLASOR_ID": "abc",
            },
            clear=True,
        ):
            self.assertTrue(gdrive_servisi.aktif_mi())

    def test_token_dosyasi_henuz_yoksa_pasif(self):
        # .env'de üç değişken de tanımlı ama henüz gdrive_yetkilendir hiç
        # çalıştırılmamış (token dosyası oluşmamış) — yapılandırma tamam
        # görünse de tarayıcı tabanlı ilk adım atlanmışsa aktif sayılmamalı.
        with patch.dict(
            "os.environ",
            {
                "YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": "/tmp/istemci.json",
                "YEDEKLEME_GDRIVE_TOKEN": str(self.token_yolu),
                "YEDEKLEME_GDRIVE_KLASOR_ID": "abc",
            },
            clear=True,
        ):
            self.assertFalse(gdrive_servisi.aktif_mi())

    def test_biri_eksikken_pasif(self):
        self.token_yolu.write_text("{}")
        with patch.dict(
            "os.environ",
            {"YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": "/tmp/istemci.json", "YEDEKLEME_GDRIVE_TOKEN": str(self.token_yolu)},
            clear=True,
        ):
            self.assertFalse(gdrive_servisi.aktif_mi())

    def test_ucu_de_yokken_pasif(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(gdrive_servisi.aktif_mi())


class GdriveOauthYetkilendirTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.istemci_yolu = self.gecici_dizin / "client_secret.json"
        self.istemci_yolu.write_text("{}")
        self.token_yolu = self.gecici_dizin / "token.json"
        self._env_patch = patch.dict(
            "os.environ",
            {
                "YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": str(self.istemci_yolu),
                "YEDEKLEME_GDRIVE_TOKEN": str(self.token_yolu),
            },
            clear=True,
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def test_istemci_dosyasi_yoksa_hata_verir(self):
        with patch.dict("os.environ", {"YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": "/olmayan/yol.json"}):
            with self.assertRaises(yedek_servisi.YedekHatasi):
                gdrive_servisi.oauth_yetkilendir()

    @patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file")
    def test_basarili_akista_token_dosyaya_yazilir(self, mock_from_client_secrets):
        sahte_akis = MagicMock()
        sahte_kimlik = MagicMock()
        sahte_kimlik.to_json.return_value = '{"token": "sahte"}'
        sahte_akis.run_local_server.return_value = sahte_kimlik
        mock_from_client_secrets.return_value = sahte_akis

        sonuc_yolu = gdrive_servisi.oauth_yetkilendir()

        self.assertEqual(sonuc_yolu, self.token_yolu)
        self.assertEqual(self.token_yolu.read_text(), '{"token": "sahte"}')
        self.assertEqual(oct(self.token_yolu.stat().st_mode)[-3:], "600")


class GdriveYedekYukleTestCase(TestCase):
    def setUp(self):
        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.dosya = self.gecici_dizin / "ornek.dump"
        self.dosya.write_bytes(b"PGDMP-sahte-icerik")
        self.token_yolu = self.gecici_dizin / "token.json"
        self.token_yolu.write_text("{}")
        self._env_patch = patch.dict(
            "os.environ",
            {
                "YEDEKLEME_GDRIVE_OAUTH_ISTEMCI": str(self.gecici_dizin / "sahte-istemci.json"),
                "YEDEKLEME_GDRIVE_TOKEN": str(self.token_yolu),
                "YEDEKLEME_GDRIVE_KLASOR_ID": "klasor-123",
            },
            clear=True,
        )
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

    def test_yapilandirilmamisken_hata_verir(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(yedek_servisi.YedekHatasi):
                gdrive_servisi.yedek_yukle(self.dosya)

    def test_dosya_yoksa_hata_verir(self):
        with self.assertRaises(yedek_servisi.YedekHatasi):
            gdrive_servisi.yedek_yukle(self.gecici_dizin / "olmayan.dump")

    @patch("yedekleme.services.gdrive_servisi._servis_olustur")
    def test_ayni_adli_dosya_yoksa_yeni_olusturulur(self, mock_servis_olustur):
        servis = MagicMock()
        mock_servis_olustur.return_value = servis
        servis.files().list().execute.return_value = {"files": []}
        servis.files().create().execute.return_value = {"id": "yeni-dosya-id"}

        sonuc = gdrive_servisi.yedek_yukle(self.dosya)

        self.assertEqual(sonuc, "yeni-dosya-id")
        servis.files().create.assert_called()
        servis.files().update.assert_not_called()

    @patch("yedekleme.services.gdrive_servisi._servis_olustur")
    def test_ayni_adli_dosya_varsa_uzerine_yazilir(self, mock_servis_olustur):
        servis = MagicMock()
        mock_servis_olustur.return_value = servis
        servis.files().list().execute.return_value = {"files": [{"id": "eski-dosya-id"}]}
        servis.files().update().execute.return_value = {"id": "eski-dosya-id"}

        sonuc = gdrive_servisi.yedek_yukle(self.dosya)

        self.assertEqual(sonuc, "eski-dosya-id")
        servis.files().update.assert_called()
        servis.files().create.assert_not_called()

    @patch("yedekleme.services.gdrive_servisi._servis_olustur")
    def test_http_hatasi_yedekhatasina_cevrilir(self, mock_servis_olustur):
        from googleapiclient.errors import HttpError

        servis = MagicMock()
        mock_servis_olustur.return_value = servis
        servis.files().list().execute.return_value = {"files": []}
        sahte_yanit = MagicMock(status=403, reason="Forbidden")
        servis.files().create().execute.side_effect = HttpError(sahte_yanit, b"yetkisiz")

        with self.assertRaises(yedek_servisi.YedekHatasi):
            gdrive_servisi.yedek_yukle(self.dosya)


class YedekOlusturGdriveEntegrasyonuTestCase(TestCase):
    """yedek_olustur view'ının, gdrive aktifse otomatik yüklemeyi tetiklediğini
    (ve gdrive hatasının yerel yedek başarısını geçersiz kılmadığını) doğrular —
    gerçek pg_dump/Drive çağrısı yapılmaz, ikisi de mock'lanır."""

    def setUp(self):
        self.client = Client()
        self.mudur_yardimcisi = User.objects.create_user("mudur-gdrive", password="test-pass-123")
        grup, _ = Group.objects.get_or_create(name="mudur_yardimcisi")
        self.mudur_yardimcisi.groups.add(grup)
        self.client.login(username="mudur-gdrive", password="test-pass-123")

        self.gecici_dizin = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self._orijinal_backup_dir = yedek_servisi.BACKUP_DIR
        yedek_servisi.BACKUP_DIR = self.gecici_dizin

    def tearDown(self):
        yedek_servisi.BACKUP_DIR = self._orijinal_backup_dir

    @patch("yedekleme.views.gdrive_servisi.yedek_yukle")
    @patch("yedekleme.views.gdrive_servisi.aktif_mi", return_value=True)
    @patch("yedekleme.views.yedek_servisi.yedek_olustur")
    def test_gdrive_aktifken_otomatik_yuklenir(self, mock_yedek_olustur, mock_aktif_mi, mock_gdrive_yukle):
        sahte_yol = self.gecici_dizin / "sahte.dump"
        sahte_yol.write_bytes(b"PGDMP")
        mock_yedek_olustur.return_value = sahte_yol

        yanit = self.client.post("/yedekleme/olustur/", follow=True)

        mock_gdrive_yukle.assert_called_once_with(sahte_yol)
        mesajlar = [str(m) for m in yanit.context["messages"]]
        self.assertTrue(any("Drive" in m for m in mesajlar))

    @patch("yedekleme.views.gdrive_servisi.yedek_yukle")
    @patch("yedekleme.views.gdrive_servisi.aktif_mi", return_value=True)
    @patch("yedekleme.views.yedek_servisi.yedek_olustur")
    def test_gdrive_hatasi_yerel_yedegi_gecersiz_kilmaz(
        self, mock_yedek_olustur, mock_aktif_mi, mock_gdrive_yukle
    ):
        sahte_yol = self.gecici_dizin / "sahte.dump"
        sahte_yol.write_bytes(b"PGDMP")
        mock_yedek_olustur.return_value = sahte_yol
        mock_gdrive_yukle.side_effect = yedek_servisi.YedekHatasi("ağ hatası")

        yanit = self.client.post("/yedekleme/olustur/", follow=True)

        mesajlar = [str(m) for m in yanit.context["messages"]]
        self.assertTrue(any("Yedek oluşturuldu" in m for m in mesajlar))
        self.assertTrue(any("yüklenemedi" in m for m in mesajlar))

    @patch("yedekleme.views.gdrive_servisi.aktif_mi", return_value=False)
    def test_gdrive_pasifken_hic_cagrilmaz(self, mock_aktif_mi):
        sahte_yol = self.gecici_dizin / "sahte.dump"
        sahte_yol.write_bytes(b"PGDMP")
        with patch("yedekleme.views.yedek_servisi.yedek_olustur", return_value=sahte_yol):
            with patch("yedekleme.views.gdrive_servisi.yedek_yukle") as mock_gdrive_yukle:
                self.client.post("/yedekleme/olustur/")
                mock_gdrive_yukle.assert_not_called()
