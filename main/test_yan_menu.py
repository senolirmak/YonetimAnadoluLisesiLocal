"""Kalıcı sol menüler (main.context_processors.yan_menu): Görevlerim ve Devamsızlık ve Nöbet."""

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from okul.testing import aktif_egitim_yili_olustur, kullanici_olustur, personel_olustur
from sosyalkulup.models import KulupDanisman, SosyalKulup

MENU_ISARETI = 'class="gm-menu"'


class GorevMenusuTests(TestCase):
    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")
        self.ogretmen = kullanici_olustur("ogretmen")
        personel = personel_olustur(user=self.ogretmen)
        self.kulup = SosyalKulup.objects.create(ad="Satranç Kulübü")
        KulupDanisman.objects.create(kulup=self.kulup, ogretmen=personel)
        self.kulup_url = reverse("sosyalkulup:kulup_ogrencileri", args=[self.kulup.pk])

    def test_gorev_sayfalarinda_menu_gorunur(self):
        self.client.force_login(self.ogretmen)
        for url in (
            reverse("gorevlerim"),
            reverse("ogretmen_haftalik_nobet"),
            reverse("ogretmen_ders_doldurma"),
            reverse("haftalik_ders_programi"),
            self.kulup_url,
        ):
            with self.subTest(url=url):
                resp = self.client.get(url)
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertContains(resp, reverse("ogretmen_haftalik_nobet"))

    def test_bulunulan_sayfa_menude_isaretlenir(self):
        self.client.force_login(self.ogretmen)
        resp = self.client.get(self.kulup_url)
        self.assertEqual(resp.context["gorev_menu"]["aktif_sayfa"], "sosyalkulup:kulup_ogrencileri")
        self.assertContains(resp, 'class="aktif">Satranç Kulübü — Öğrenci Listesi')

    def test_danisman_olmayanda_kulup_bolumu_yok(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("gorevlerim"))
        self.assertContains(resp, MENU_ISARETI)
        self.assertNotContains(resp, "Sosyal Kulübüm")

    def test_ana_sayfada_gorevlerim_degil_ana_menu(self):
        self.client.force_login(self.ogretmen)
        resp = self.client.get(reverse("index"))
        self.assertNotIn("gorev_menu", resp.context)
        self.assertEqual(resp.context["yan_menu"], "includes/ana_menu.html")

    def test_ust_yoneticide_menu_yok(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("ogretmen_ders_doldurma"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, MENU_ISARETI)

    def test_sorumluluk_gorevleri_sayfasinda_menu_gorunur(self):
        self.client.force_login(self.ogretmen)
        resp = self.client.get(reverse("ogretmen_sorumluluk_gorevleri"))
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "sorumluluk/ogretmen_sorumluluk_gorevleri.html")
        self.assertContains(resp, MENU_ISARETI)

    def test_gozetim_alt_sayfasinda_ust_baglanti_isaretlenir(self):
        self.client.force_login(self.ogretmen)
        resp = self.client.get(reverse("ogretmen_yoklama_raporum"))
        self.assertContains(resp, MENU_ISARETI)
        self.assertEqual(resp.context["gorev_menu"]["aktif_sayfa"], "ogretmen_sinav_gozetim")


class MainUrlCakismaTests(SimpleTestCase):
    """main.urls config/urls.py'de en sona eklendiği için önceki bir app'in aynı
    adresi gölgelemesi bağlantıyı başka sayfaya götürür."""

    def test_main_adresleri_kendi_viewlarina_cozulur(self):
        from django.urls import NoReverseMatch, resolve

        import main.urls

        for desen in main.urls.urlpatterns:
            try:
                url = reverse(desen.name)
            except NoReverseMatch:
                continue  # parametreli adresler
            with self.subTest(url=url):
                self.assertEqual(resolve(url).view_name, desen.name)


class NobetMenusuTests(TestCase):
    def setUp(self):
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")
        self.sayfa_url = reverse("devamsizlik_nobet_islemleri")

    def test_mudur_yardimcisi_sayfayi_menuyle_gorur(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        self.assertContains(resp, reverse("devamsizlik_list"))
        self.assertContains(resp, reverse("nobetci_ders_doldurma_istatistik"))

    def test_okul_mudurunde_yetkisiz_baglantilar_yok(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, reverse("devamsizlik_list"))
        self.assertNotContains(resp, reverse("nobetci_ders_doldurma_istatistik"))

    def test_ogretmen_sayfaya_giremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.sayfa_url).status_code, 403)

    def test_alt_sayfalarda_menu_var_adim_dugmeleri_yok(self):
        self.client.force_login(self.mudur_yrd)
        for ad in ("devamsizlik_list", "nobet_dagitim", "gunun_nobetcileri", "nobet_ders_doldurma"):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["nobet_menu"]["aktif_sayfa"], ad)
                self.assertNotContains(resp, "1. Devamsızlık</a>")

    def test_form_sayfasinda_ust_baglanti_isaretlenir(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("devamsizlik_create"))
        self.assertEqual(resp.context["nobet_menu"]["aktif_sayfa"], "devamsizlik_list")

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "Ders Doldurma Listesi</a>")

    def test_ogretmen_ana_sayfasi_degismez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("index"))
        self.assertNotContains(resp, self.sayfa_url)
        self.assertContains(resp, reverse("ogretmen_haftalik_nobet"))
        self.assertContains(resp, reverse("ogretmen_gunun_nobetcileri"))


class GunlukOzetTests(TestCase):
    def test_sayilar(self):
        import datetime

        from nobet.models import NobetAtanamayan, NobetGecmisi
        from nobet.services.gunluk_ozet import gunluk_ozet
        from okul.testing import devamsizlik_olustur, nobet_ogretmen_olustur

        bugun = datetime.date(2025, 10, 15)
        an = timezone.make_aware(datetime.datetime(2025, 10, 15, 10, 0))
        ogr1, ogr2, ogr3 = (nobet_ogretmen_olustur() for _ in range(3))
        devamsizlik_olustur(ogr1, datetime.date(2025, 10, 14), sure=3)  # 14-16: dahil
        devamsizlik_olustur(ogr2, bugun)  # yalnızca bugün: dahil
        devamsizlik_olustur(ogr3, datetime.date(2025, 10, 10), sure=2)  # bitmiş: hariç
        # Aynı gün iki kez kaydedilmiş: yalnızca sonraki (ekranda görünen) sayılır
        once = an - datetime.timedelta(hours=1)
        NobetGecmisi.objects.create(ogretmen=ogr1, saat=1, sinif="9A", tarih=once)
        NobetGecmisi.objects.create(ogretmen=ogr1, saat=2, sinif="9A", tarih=once)
        NobetGecmisi.objects.create(ogretmen=ogr1, saat=1, sinif="9A", tarih=an)
        NobetAtanamayan.objects.create(ogretmen=ogr2, saat=3, sinif="10B", tarih=an)

        ozet = gunluk_ozet(bugun)
        self.assertEqual(ozet["devamsiz_personel"], 2)
        self.assertEqual(ozet["atanan_ders"], 1)
        self.assertEqual(ozet["atanamayan_ders"], 1)


class DersProgramiMenusuTests(TestCase):
    def setUp(self):
        self.sayfa_url = reverse("ders_programi_islemleri")

    def test_mudur_yardimcisi_sayfayi_menuyle_gorur(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        self.assertContains(resp, reverse("fet_kopru"))
        self.assertContains(resp, reverse("sinif_program"))

    def test_rehber_ogretmende_ust_yonetici_baglantilari_yok(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("dersprogrami_listesi"))
        self.assertNotContains(resp, reverse("fet_kopru"))
        self.assertNotContains(resp, reverse("sinif_program"))

    def test_ogretmen_sayfaya_giremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.sayfa_url).status_code, 403)

    def test_alt_sayfalarda_menu_var(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        for ad in (
            "dersprogrami_listesi",
            "ogretmen_program",
            "sinif_ogretmenleri",
            "haftalik_ders_programi",
            "rehber_ogretmenler",
            "dersdefteri:ders_listesi",
            "sosyalkulup:danisman_ogretmenler",
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["ders_programi_menu"]["aktif_sayfa"], ad)

    def test_ders_defteri_alt_sayfasinda_ust_baglanti_isaretlenir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("dersdefteri:gecmis_listesi"))
        self.assertEqual(
            resp.context["ders_programi_menu"]["aktif_sayfa"], "dersdefteri:ders_listesi"
        )

    def test_ogretmen_rolundekinde_ortak_sayfada_gorevlerim_menusu(self):
        rehber = kullanici_olustur("rehber_ogretmen")
        self.client.force_login(rehber)
        resp = self.client.get(reverse("haftalik_ders_programi"))
        self.assertIn("gorev_menu", resp.context)
        self.assertNotIn("ders_programi_menu", resp.context)
        resp = self.client.get(reverse("dersprogrami_listesi"))
        self.assertIn("ders_programi_menu", resp.context)

    def test_salt_ogretmende_ders_defterinde_ana_menu(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("dersdefteri:ders_listesi"))
        self.assertNotIn("ders_programi_menu", resp.context)
        self.assertEqual(resp.context["yan_menu"], "includes/ana_menu.html")

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "FET Köprüsü</a>")


class DersProgramiOzetiTests(TestCase):
    def test_sayilar(self):
        from dersprogrami.services.ozet import ders_programi_ozeti
        from okul.testing import ders_programi_olustur, sinif_sube_olustur

        p1, p2 = personel_olustur(), personel_olustur()
        ders_programi_olustur(p1, 1, sinif_sube_olustur(9, "A"))
        ders_programi_olustur(p1, 2, sinif_sube_olustur(9, "B"))
        ders_programi_olustur(p2, 3, sinif_sube_olustur(9, "A"))

        ozet = ders_programi_ozeti()
        self.assertEqual(ozet["ogretmen_sayisi"], 2)
        self.assertEqual(ozet["sinif_sube_sayisi"], 2)
        self.assertEqual(ozet["ders_saati_sayisi"], 3)


class OgrenciMenusuTests(TestCase):
    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")
        self.sayfa_url = reverse("ogrenci_islemleri")

    def test_ogretmen_sayfayi_menuyle_gorur_yonetici_baglantilari_yok(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        # Rehberlik sınıfı olmayan öğretmene açılmayan sayfalar gösterilmez
        self.assertNotContains(resp, f'href="{reverse("ogrenci:ogrenci_liste")}"')
        self.assertNotContains(resp, reverse("sosyalkulup:ogrenci_kulup_belirle"))
        self.assertContains(resp, reverse("sinif_oturma_plani"))
        self.assertNotContains(resp, reverse("ogrenci:ayrilma_listesi"))
        self.assertNotContains(resp, reverse("ogrencinobet:nobetci_form"))

    def test_mudur_yardimcisi_tum_baglantilari_gorur(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(self.sayfa_url)
        for ad in (
            "ogrenci:ayrilma_listesi",
            "sosyalkulup:kulup_listesi",
            "ogrencinobet:nobetci_form",
            "devamsizlik:ogrenci_devamsizlik_pdf",
        ):
            self.assertContains(resp, reverse(ad))

    def test_giris_yapmamis_yonlendirilir(self):
        self.assertEqual(self.client.get(self.sayfa_url).status_code, 302)

    def test_alt_sayfalarda_menu_var(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        for ad in (
            "ogrenci:ogrenci_liste",
            "ogrenci:sureksiz_devamsiz_listesi",
            "ogrenci:ayrilma_listesi",
            "sosyalkulup:ogrenci_kulup_belirle",
            "sosyalkulup:kulup_listesi",
            "ogrencinobet:nobetci_form",
            "devamsizlik:ogrenci_devamsizlik_listesi",
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["ogrenci_menu"]["aktif_sayfa"], ad)

    def test_alt_sayfada_ust_baglanti_isaretlenir(self):
        from okul.testing import ogrenci_olustur

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("ogrenci:ogrenci_detay_duzenle", args=[ogrenci_olustur().pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["ogrenci_menu"]["aktif_sayfa"], "ogrenci:ogrenci_liste")

    def test_kulup_ogrencileri_iki_menude_farkli_isaretlenir(self):
        kulup = SosyalKulup.objects.create(ad="Tiyatro Kulübü")
        url = reverse("sosyalkulup:kulup_ogrencileri", args=[kulup.pk])
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(url)
        self.assertEqual(resp.context["ogrenci_menu"]["aktif_sayfa"], "sosyalkulup:kulup_listesi")

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "Öğrenci Sosyal Kulübünü Belirle</a>")

    def test_faaliyetler_ogrenci_isleri_menusunde(self):
        ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=ogretmen)  # faaliyet sayfaları personel kaydı ister
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("index"))
        self.assertNotContains(resp, "Faaliyetlerim</a>")

        resp = self.client.get(self.sayfa_url)
        self.assertContains(resp, reverse("faaliyet:faaliyet_liste"))
        self.assertContains(resp, reverse("faaliyet:faaliyet_olustur"))

        for ad in ("faaliyet:faaliyet_liste", "faaliyet:faaliyet_olustur"):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["ogrenci_menu"]["aktif_sayfa"], ad)


class OgrenciOzetiTests(TestCase):
    def test_sayilar(self):
        import datetime

        from devamsizlik.models import OgrenciDevamsizlik
        from ogrenci.services.ozet import ogrenci_ozeti
        from ogrencinobet.models import OgrenciNobetGorevi
        from okul.testing import ders_saati_olustur, ogrenci_olustur

        bugun = datetime.date(2025, 10, 15)
        o1, o2 = ogrenci_olustur(), ogrenci_olustur()
        ogrenci_olustur(aktif=False)
        OgrenciDevamsizlik.objects.create(ogrenci=o1, tarih=bugun, ders_saati=ders_saati_olustur(1))
        OgrenciDevamsizlik.objects.create(ogrenci=o1, tarih=bugun, ders_saati=ders_saati_olustur(2))
        OgrenciDevamsizlik.objects.create(ogrenci=o2, tarih=bugun - datetime.timedelta(days=1), ders_saati=ders_saati_olustur(1))
        OgrenciNobetGorevi.objects.create(ogrenci=o2, tarih=bugun)

        ozet = ogrenci_ozeti(bugun)
        self.assertEqual(ozet["aktif_ogrenci"], 2)
        self.assertEqual(ozet["devamsiz_ogrenci"], 1)
        self.assertEqual(ozet["nobetci_ogrenci"], 1)


class SinavMenusuTests(TestCase):
    def setUp(self):
        self.sayfa_url = reverse("sinav_islemleri")
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")

    def test_mudur_yardimcisi_sayfayi_menuyle_gorur(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        for ad in ("sinav:index", "sorumluluk:sinav_liste", "sinav:ogrenci_sinav_yeri"):
            self.assertContains(resp, reverse(ad))
        # Sınav Medya, Ortak Sınav alt menüsüne taşındı
        self.assertNotContains(resp, reverse("sinavmedia:yonetim"))
        self.assertContains(resp, "Aktif sınav seçilmedi")

    def test_aktif_takvim_yokken_rapor_baglantilari_gizli(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(self.sayfa_url)
        self.assertFalse(resp.context["sinav_menu"]["sinav_aktif_var"])
        self.assertNotContains(resp, reverse("sinav:sinav_yoklama_raporu"))

    def test_diger_roller_sayfaya_giremez(self):
        for grup in ("ogretmen", "okul_muduru"):
            with self.subTest(grup=grup):
                self.client.force_login(kullanici_olustur(grup))
                self.assertEqual(self.client.get(self.sayfa_url).status_code, 403)

    def test_tekil_sayfada_menu_var(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("sinav:ogrenci_sinav_yeri"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        self.assertEqual(resp.context["sinav_menu"]["aktif_sayfa"], "sinav:ogrenci_sinav_yeri")

    def test_modul_sayfalarinda_menu_var_modul_isaretlenir(self):
        self.client.force_login(self.mudur_yrd)
        for ad, modul in (
            ("sinav:index", "sinav:index"),
            ("sinav:ders_ayarlari", "sinav:index"),
            ("sinav:mazeret_listesi", "sinav:index"),
            ("sorumluluk:sinav_liste", "sorumluluk:sinav_liste"),
            ("sorumluluk:sinav_olustur", "sorumluluk:sinav_liste"),
            ("sinavmedia:yonetim", "sinav:index"),
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["sinav_menu"]["aktif_sayfa"], modul)

    def test_medya_oynaticida_menu_yok(self):
        from django.test import RequestFactory
        from django.urls import resolve

        from main.context_processors import yan_menu

        istek = RequestFactory().get("/")
        istek.user = self.mudur_yrd
        istek.resolver_match = resolve(reverse("sinavmedia:oynat", args=[1]))
        self.assertEqual(yan_menu(istek), {})

    def test_modul_sayfasinda_ogretmene_menu_yok(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        resp = self.client.get(reverse("sinav:ogrenci_sinav_yeri"))
        self.assertNotIn("sinav_menu", resp.context)

    def test_sinav_medya_ortak_sinav_alt_menusunde(self):
        self.client.force_login(self.mudur_yrd)
        medya_url = reverse("sinavmedia:yonetim")
        resp = self.client.get(reverse("sinav:index"))
        self.assertContains(resp, f'href="{medya_url}" style="--renk:#7c3aed;">Sınav Medya Yönetimi')

        resp = self.client.get(medya_url)
        self.assertContains(resp, 'class="sn-altmenu gm-butonlu"')
        self.assertContains(resp, f'href="{medya_url}" style="--renk:#7c3aed;" class="aktif"')
        self.assertNotContains(resp, '<nav class="sinav-nav">')

    def test_ortak_sinav_menusu_sol_menunun_yaninda(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("sinav:ders_ayarlari"))
        self.assertContains(resp, 'class="sn-altmenu gm-butonlu"')
        self.assertNotContains(resp, '<nav class="sinav-nav">')
        self.assertContains(resp, "Aktif sınav seçilmedi")
        self.assertContains(
            resp, f'href="{reverse("sinav:ders_ayarlari")}" style="--renk:#6366f1;" class="aktif"'
        )

    def test_menusuz_kullanicida_ust_cubuk_kalir(self):
        from django.template.loader import render_to_string

        html = render_to_string("sinav/base.html", {})
        self.assertIn('<nav class="sinav-nav">', html)
        self.assertNotIn('class="sn-altmenu gm-butonlu"', html)

    def test_okul_mudurunde_yoklama_raporunda_menu_yok(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.get(reverse("sinav:sinav_yoklama_raporu"))
        self.assertNotIn("sinav_menu", resp.context)

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "Öğrenci Sınav Yeri Sorgula</a>")


class YonetimMenusuTests(TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        # Gerçek backups/ klasörüne dokunulmaz (bkz. yedekleme/tests.py)
        gecici = tempfile.TemporaryDirectory()
        self.addCleanup(gecici.cleanup)
        yama = patch("yedekleme.services.yedek_servisi.BACKUP_DIR", Path(gecici.name))
        yama.start()
        self.addCleanup(yama.stop)
        self.sayfa_url = reverse("yonetim_paneli")
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")

    def test_mudur_yardimcisi_sayfayi_menuyle_gorur(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        for ad in (
            "okul_ayarlari",
            "okul:yonetim_index",
            "yedekleme:yedek_listesi",
            "senesonu:gecis_listesi",
            "personel_listesi",
            "veriaktar_ana",
            "faaliyet:faaliyet_onay_listesi",
            "faaliyet:faaliyet_yonetim_listesi",
        ):
            self.assertContains(resp, reverse(ad))
        self.assertContains(resp, "Henüz yedek alınmamış")

    def test_diger_roller_sayfaya_giremez(self):
        for grup in ("ogretmen", "okul_muduru"):
            with self.subTest(grup=grup):
                self.client.force_login(kullanici_olustur(grup))
                self.assertEqual(self.client.get(self.sayfa_url).status_code, 403)

    def test_alt_sayfalarda_menu_var_ust_baglanti_isaretlenir(self):
        self.client.force_login(self.mudur_yrd)
        for ad, aktif in (
            ("okul_ayarlari", "okul_ayarlari"),
            ("okul:yonetim_index", "okul:yonetim_index"),
            ("yedekleme:yedek_listesi", "yedekleme:yedek_listesi"),
            ("senesonu:gecis_listesi", "senesonu:gecis_listesi"),
            ("personel_listesi", "personel_listesi"),
            ("veriaktar_ana", "veriaktar_ana"),
            ("faaliyet:faaliyet_onay_listesi", "faaliyet:faaliyet_onay_listesi"),
            ("faaliyet:faaliyet_yonetim_listesi", "faaliyet:faaliyet_yonetim_listesi"),
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["yonetim_menu"]["aktif_sayfa"], aktif)

    def test_ogretmen_faaliyet_sayfalarinda_menu_yok(self):
        from django.test import RequestFactory
        from django.urls import resolve

        from main.context_processors import yan_menu

        for ad in ("faaliyet:faaliyet_liste", "faaliyet:faaliyet_olustur", "okul:ders_havuzu_ayarlari"):
            with self.subTest(sayfa=ad):
                istek = RequestFactory().get("/")
                istek.user = self.mudur_yrd
                istek.resolver_match = resolve(reverse(ad))
                self.assertNotIn("yonetim_menu", yan_menu(istek))

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "Okul Yapılandırması</a>")


class SecmeliMenusuTests(TestCase):
    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")
        self.mudur_yrd = kullanici_olustur("mudur_yardimcisi")

    def test_merkez_sayfada_menu_ve_kartlar(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("secmeli_index"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        self.assertContains(resp, "hub-kart")
        self.assertEqual(resp.context["secmeli_menu"]["aktif_sayfa"], "secmeli_index")
        self.assertNotContains(resp, "Öğrenci Ders Planlaması")

    def test_alt_sayfalarda_ust_baglanti_isaretlenir(self):
        self.client.force_login(self.mudur_yrd)
        for ad, aktif in (
            ("ogrdrs_listesi", "ogrdrs_listesi"),
            ("secmeli_grup_listesi", "secmeli_grup_listesi"),
            ("secmeli_alan_listesi", "secmeli_alan_listesi"),
            ("secmeli_alan_sube_atama", "secmeli_ders_yuku"),
            ("secmeli_ortak_ders_listesi", "secmeli_ortak_ders_listesi"),
            ("ortalama_listesi", "ortalama_listesi"),
            ("tasdikname_listesi", "tasdikname_listesi"),
            ("secmeli_sinif_dagilimi", "secmeli_sinif_dagilimi"),
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertContains(resp, MENU_ISARETI)
                self.assertEqual(resp.context["secmeli_menu"]["aktif_sayfa"], aktif)

    def test_yeni_kayit_sayfasinda_menu(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("ogrenci:yeni_kayit_hub", args=[9]))
        self.assertEqual(resp.context["secmeli_menu"]["aktif_sayfa"], "ogrenci:yeni_kayit_hub")

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(self.mudur_yrd)
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, reverse("secmeli_index"))
        self.assertNotContains(resp, "Öğrenci Seçmeli Dersleri</a>")

    def test_okul_mudurunde_menu_yok(self):
        from django.test import RequestFactory
        from django.urls import resolve

        from main.context_processors import yan_menu

        istek = RequestFactory().get("/")
        istek.user = kullanici_olustur("okul_muduru")
        istek.resolver_match = resolve(reverse("secmeli_index"))
        self.assertEqual(yan_menu(istek), {})


class BilgiPanosuTests(TestCase):
    def setUp(self):
        self.sayfa_url = reverse("bilgi_panosu")

    def test_ust_yonetici_menu_ve_onizleme_gorur(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.get(self.sayfa_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, MENU_ISARETI)
        self.assertContains(resp, f'<iframe src="{reverse("pano:index")}"')
        self.assertContains(resp, reverse("pano:kiosk"))
        # yönetici paneli kısayolları yalnızca is_staff kullanıcılarda
        self.assertNotContains(resp, reverse("admin:pano_duyuru_changelist"))

    def test_etkinlik_onizlemesi_secilir(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(self.sayfa_url, {"goster": "etkinlikler"})
        self.assertContains(resp, f'<iframe src="{reverse("pano:etkinlikler")}"')
        self.assertEqual(resp.context["pano_menu"]["goster"], "etkinlikler")

    def test_gecersiz_secim_panoya_duser(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(self.sayfa_url, {"goster": "javascript:alert(1)"})
        self.assertContains(resp, f'<iframe src="{reverse("pano:index")}"')

    def test_staff_kullanici_icerik_kisayollarini_gorur(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi", is_staff=True))
        resp = self.client.get(self.sayfa_url)
        self.assertContains(resp, reverse("admin:pano_duyuru_changelist"))

    def test_ogretmen_giremez(self):
        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertEqual(self.client.get(self.sayfa_url).status_code, 403)

    def test_pano_onizlemesi_cerceveye_izin_verir(self):
        for ad in ("pano:index", "pano:etkinlikler"):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.headers.get("X-Frame-Options"), "SAMEORIGIN")

    def test_ana_sayfada_tek_dugme(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, self.sayfa_url)
        self.assertNotContains(resp, "Kiosk Modu</a>")


class AnaMenuTests(TestCase):
    """Ana sayfanın sol tarafı menü alanıdır; başlık yok, butonlar role göre süzülür."""

    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")

    def test_ana_sayfa_sol_menude_basliksiz_butonlar(self):
        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, 'aria-label="Ana menü"')
        for ad in ("yonetim_paneli", "devamsizlik_nobet_islemleri", "ders_programi_islemleri",
                   "ogrenci_islemleri", "secmeli_index", "sinav_islemleri", "bilgi_panosu"):
            self.assertContains(resp, reverse(ad))
        for baslik in ("Yönetim Paneli</div>", "Sınav Menüsü</div>", "Duyuru Yönetimi</div>"):
            self.assertNotContains(resp, baslik)
        # Aynı adlı "Görüşme Listesi" butonları ayırt edilebilir adlarla
        self.assertContains(resp, "Müdüriyet Görüşmeleri</a>")
        self.assertContains(resp, "Rehberlik Görüşmeleri</a>")
        self.assertContains(resp, "Disiplin Kurulu Görüşmeleri</a>")

    def test_ogretmen_kendi_butonlarini_gorur(self):
        ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=ogretmen)
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("index"))
        for ad in ("gorevlerim", "ogretmen_haftalik_nobet", "devamsizlik:ogretmen_devamsizlik",
                   "ogrenci_islemleri"):
            self.assertContains(resp, reverse(ad))
        for ad in ("yonetim_paneli", "sinav_islemleri", "bilgi_panosu"):
            self.assertNotContains(resp, reverse(ad))
        self.assertContains(resp, "Yoklama ve Sınıf Defteri elle yazılması")

    def test_sinav_yoklama_butonu_yalnizca_okul_mudurunde(self):
        """Müdür yardımcısı bu rapora Sınav İşlemleri menüsünden ulaşır."""
        from unittest.mock import patch

        from main import utils

        asil = utils.get_ogretmen_gorev_verileri

        def aktif_sinav_var(user, today):
            return {**asil(user, today), "sinav_aktif_var": True}

        rapor = f'href="{reverse("sinav:sinav_yoklama_raporu")}"'
        with patch("main.views.get_ogretmen_gorev_verileri", aktif_sinav_var):
            self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
            self.assertNotContains(self.client.get(reverse("index")), rapor)
            self.client.force_login(kullanici_olustur("okul_muduru"))
            self.assertContains(self.client.get(reverse("index")), rapor)


class DuzeltmeTests(TestCase):
    """Görünen ama rolün açamadığı bağlantıların kaldırılması ve ana menünün yayılması."""

    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")

    def test_rehber_ogretmen_ogrenci_baglantilarini_gorur(self):
        from okul.testing import sinif_rehberi_ata, sinif_sube_olustur

        ogretmen = kullanici_olustur("ogretmen")
        sinif_rehberi_ata(personel_olustur(user=ogretmen), sinif_sube_olustur(10, "A"))
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("ogrenci_islemleri"))
        self.assertContains(resp, reverse("ogrenci:ogrenci_liste"))
        self.assertContains(resp, reverse("sosyalkulup:ogrenci_kulup_belirle"))

    def test_okul_mudurune_ogrenci_yoklama_kayitlari_gosterilmez(self):
        self.client.force_login(kullanici_olustur("okul_muduru"))
        resp = self.client.get(reverse("ogrenci_islemleri"))
        self.assertNotContains(resp, reverse("devamsizlik:ogrenci_devamsizlik_listesi"))
        self.assertContains(resp, reverse("ogrencinobet:nobetci_form"))

    def test_grupsuz_kullaniciya_yonetici_nobet_sayfalari_gosterilmez(self):
        self.client.force_login(kullanici_olustur())
        resp = self.client.get(reverse("index"))
        for ad in ("nobet_dagitim", "gunun_nobetcileri", "nobet_ders_doldurma"):
            self.assertNotContains(resp, f'href="{reverse(ad)}"')

    def test_ogretmen_istatistik_sayfasinda_yonetici_baglantisi_yok(self):
        ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=ogretmen)
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("nobetci_ders_doldurma_istatistik"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, f'href="{reverse("nobet_dagitim")}"')
        # Görevlerim menüsünde, Atanan / Atanamayan Dersler altında
        self.assertEqual(resp.context["gorev_menu"]["aktif_sayfa"], "ogretmen_ders_doldurma")

    def test_rehber_ogretmen_nobet_adim_dugmelerinde_yetkisiz_yok(self):
        self.client.force_login(kullanici_olustur("rehber_ogretmen"))
        resp = self.client.get(reverse("gunun_nobetcileri"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, f'href="{reverse("devamsizlik_list")}"')
        self.assertNotContains(resp, f'href="{reverse("nobet_gorevi_listesi")}"')
        self.assertEqual(resp.context["yan_menu"], "includes/ana_menu.html")

    def test_menusuz_sayfalarda_ana_menu(self):
        mudur_yrd = kullanici_olustur("mudur_yardimcisi")
        self.client.force_login(mudur_yrd)
        for ad, aktif in (
            ("duyuru_listesi", "duyuru_listesi"),
            ("ogretmen_kullanici_listesi", "ogretmen_kullanici_listesi"),
            ("muduriyetcagri:gorusme_liste", "muduriyetcagri:gorusme_liste"),
            ("rehberlik:gorusme_liste", "rehberlik:gorusme_liste"),
            ("disiplin:gorusme_liste", "disiplin:gorusme_liste"),
            ("profil", None),
        ):
            with self.subTest(sayfa=ad):
                resp = self.client.get(reverse(ad))
                self.assertEqual(resp.status_code, 200)
                self.assertEqual(resp.context["yan_menu"], "includes/ana_menu.html")
                self.assertEqual(resp.context["ana_menu_aktif"], aktif)
                self.assertContains(resp, 'aria-label="Ana menü"')

    def test_ogretmen_yoklama_sayfasinda_ana_menu_ve_kendi_butonlari(self):
        ogretmen = kullanici_olustur("ogretmen")
        personel_olustur(user=ogretmen)
        self.client.force_login(ogretmen)
        resp = self.client.get(reverse("devamsizlik:ogretmen_devamsizlik"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'aria-label="Ana menü"')
        # personel_bagli koşulu view'dan değil menü verisinden gelir
        self.assertContains(resp, f'href="{reverse("dersdefteri:ders_listesi")}"')

    def test_menu_sablonlarindan_aciklama_metni_sizmaz(self):
        """Django'nun {# #} açıklaması tek satırlıktır; çok satırlısı sayfaya düz metin basar."""
        from pathlib import Path

        from django.conf import settings

        for yol in sorted((Path(settings.BASE_DIR) / "main/templates/includes").glob("*.html")):
            with self.subTest(sablon=yol.name):
                for satir_no, satir in enumerate(yol.read_text().splitlines(), 1):
                    if "{#" in satir:
                        self.assertIn("#}", satir, f"{yol.name}:{satir_no} çok satırlı {{# #}}")


class AnaSayfaFaaliyetOnayiTests(TestCase):
    def test_bekleyen_faaliyet_onayi_yalnizca_mudur_yardimcisina(self):
        from faaliyet.models import Faaliyet

        aktif_egitim_yili_olustur("2025-2026")
        ogretmen = personel_olustur()
        for i in range(2):
            Faaliyet.objects.create(konu=f"Gezi {i}", tarih=timezone.localdate(), yer="Okul", ogretmen=ogretmen)
        Faaliyet.objects.create(konu="Onaylı", tarih=timezone.localdate(), yer="Okul", ogretmen=ogretmen,
                                durum=Faaliyet.DURUM_ONAYLANDI)

        self.client.force_login(kullanici_olustur("mudur_yardimcisi"))
        resp = self.client.get(reverse("index"))
        self.assertContains(resp, "Bekleyen Faaliyet Onayı")
        self.assertEqual(resp.context["bekleyen_faaliyet_sayisi"], 2)
        self.assertContains(resp, reverse("faaliyet:faaliyet_onay_listesi"))

        self.client.force_login(kullanici_olustur("ogretmen"))
        self.assertNotContains(self.client.get(reverse("index")), "Bekleyen Faaliyet Onayı")
