"""ekders yetki testleri. Ek ders hesapları maaşa yansır: ekranlar yalnızca üst yöneticiye açık."""

from django.test import TestCase
from django.urls import reverse

from okul.testing import yetki_dogrula

YASAK = ("ogretmen", "rehber_ogretmen", "disiplin_kurulu")
IZINLI = ("mudur_yardimcisi", "okul_muduru")


class EkdersYetkiTestCase(TestCase):
    def test_get_ekranlari(self):
        urller = [reverse("ekders:donem_listesi"), reverse("ekders:donem_olustur"),
                  reverse("ekders:donem_detay", args=[999]), reverse("ekders:donem_duzenle", args=[999]),
                  reverse("ekders:hafta_duzenle", args=[999, 1]), reverse("ekders:tatil_listesi")]
        yetki_dogrula(self, urller, YASAK, IZINLI)

    def test_post_islemleri(self):
        urller = [reverse("ekders:donem_hesapla", args=[999]), reverse("ekders:donem_onayla", args=[999]),
                  reverse("ekders:tatil_sil", args=[999])]
        yetki_dogrula(self, urller, YASAK, IZINLI, method="post")
