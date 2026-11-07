"""okul.auth — merkezi rol kuralları (rol_bayraklari ve ondan türeyen kontroller)."""

from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse

from okul import auth
from okul.models import OkulYonetici
from okul.testing import aktif_egitim_yili_olustur, kullanici_olustur, personel_olustur

BAYRAKLAR = ("mudur_yardimcisi", "ust_yonetici", "yonetici", "rehber_ogretmen",
             "disiplin_kurulu", "salt_ogretmen", "ogretmen_menu")


def _kullanici(*gruplar, pasif=None, **kw):
    u = kullanici_olustur(*gruplar, **kw)
    personel_olustur(user=u)
    if pasif:
        OkulYonetici.objects.create(user=u, unvan=pasif, aktif=False)
    return u


class RolBayraklariTests(TestCase):
    def _bekle(self, user, *dogrular):
        b = auth.rol_bayraklari(user)
        self.assertEqual({k for k in BAYRAKLAR if b[k]}, set(dogrular))

    def test_roller(self):
        self._bekle(AnonymousUser())
        self._bekle(_kullanici())
        self._bekle(_kullanici("ogretmen"), "salt_ogretmen", "ogretmen_menu")
        self._bekle(_kullanici("rehber_ogretmen"), "yonetici", "rehber_ogretmen", "ogretmen_menu")
        self._bekle(_kullanici("disiplin_kurulu"), "yonetici", "disiplin_kurulu", "ogretmen_menu")
        self._bekle(_kullanici("mudur_yardimcisi"), "mudur_yardimcisi", "ust_yonetici", "yonetici")
        self._bekle(_kullanici("okul_muduru"), "ust_yonetici", "yonetici")
        self._bekle(_kullanici(superuser=True), "mudur_yardimcisi", "ust_yonetici", "yonetici",
                    "rehber_ogretmen", "disiplin_kurulu")
        self._bekle(_kullanici(is_staff=True))

    def test_pasif_profil_ust_yonetim_yetkisini_kaybeder_yonetici_kalir(self):
        self._bekle(_kullanici("mudur_yardimcisi", pasif="mudur_yardimcisi"), "yonetici")
        self._bekle(_kullanici("okul_muduru", pasif="okul_muduru"), "yonetici")

    def test_ogretmen_ve_ust_yonetici_birlikte_ise_ogretmen_menusu_yok(self):
        self._bekle(_kullanici("ogretmen", "mudur_yardimcisi"),
                    "mudur_yardimcisi", "ust_yonetici", "yonetici")

    def test_tekil_kontroller_bayraklarla_ayni(self):
        u = _kullanici("rehber_ogretmen")
        b = auth.rol_bayraklari(u)
        self.assertEqual(auth.is_yonetici(u), b["yonetici"])
        self.assertEqual(auth.is_rehber_ogretmen(u), b["rehber_ogretmen"])
        self.assertEqual(auth.is_ogretmen_menu(u), b["ogretmen_menu"])
        self.assertEqual(auth.is_ust_yonetici(u), b["ust_yonetici"])

    def test_sablon_bayraklari_ayni_kurallari_kullanir(self):
        from django.test import RequestFactory

        from main.context_processors import kullanici_rol

        istek = RequestFactory().get("/")
        istek.user = _kullanici("mudur_yardimcisi", pasif="mudur_yardimcisi")
        ctx = kullanici_rol(istek)
        self.assertFalse(ctx["is_mudur_yardimcisi"])
        self.assertFalse(ctx["is_tarih_degistirebilir"])
        self.assertTrue(ctx["is_yonetici"])


class PasifProfilErisimTests(TestCase):
    """Satır içi kopyaların açık bıraktığı sayfalar pasif profile de kapalıdır."""

    def setUp(self):
        aktif_egitim_yili_olustur("2025-2026")

    def test_pasif_mudur_yardimcisi(self):
        self.client.force_login(_kullanici("mudur_yardimcisi", pasif="mudur_yardimcisi"))
        for ad in ("ogretmen_haftalik_nobet", "ogretmen_gunun_nobetcileri",
                   "ogretmen_ders_doldurma", "nobetci_ders_doldurma_istatistik"):
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 403)
        self.assertEqual(
            self.client.get(reverse("devamsizlik:ogrenci_devamsizlik_pdf")).status_code, 302
        )

    def test_pasif_okul_muduru(self):
        self.client.force_login(_kullanici("okul_muduru", pasif="okul_muduru"))
        self.assertEqual(self.client.get(reverse("ogrenci:sureksiz_devamsiz_listesi")).status_code, 403)

    def test_aktif_mudur_yardimcisi_girer(self):
        self.client.force_login(_kullanici("mudur_yardimcisi"))
        for ad in ("ogretmen_haftalik_nobet", "ogrenci:sureksiz_devamsiz_listesi"):
            with self.subTest(sayfa=ad):
                self.assertEqual(self.client.get(reverse(ad)).status_code, 200)

    def test_rehberlik_ve_disiplin_erisimi_degismedi(self):
        """KVKK: rehberlik/disiplin kayıtlarına yalnızca ilgili kurul/rehber ve müdür yardımcısı."""
        for grup, rehberlik, disiplin in (
            ("ogretmen", 302, 302),
            ("rehber_ogretmen", 200, 302),
            ("disiplin_kurulu", 302, 200),
            ("okul_muduru", 302, 302),
            ("mudur_yardimcisi", 200, 200),
        ):
            with self.subTest(grup=grup):
                self.client.force_login(_kullanici(grup))
                self.assertEqual(self.client.get(reverse("rehberlik:gorusme_liste")).status_code, rehberlik)
                self.assertEqual(self.client.get(reverse("disiplin:gorusme_liste")).status_code, disiplin)
