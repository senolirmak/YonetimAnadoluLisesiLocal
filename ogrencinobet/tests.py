from django.test import TestCase
from django.urls import reverse

from okul.testing import yetki_dogrula


class OgrenciNobetYetkiTestCase(TestCase):
    def test_nobetci_formu_yalnizca_ust_yoneticiye_acik(self):
        yetki_dogrula(
            self, [reverse("ogrencinobet:nobetci_form")],
            ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"), ("mudur_yardimcisi", "okul_muduru"),
        )
