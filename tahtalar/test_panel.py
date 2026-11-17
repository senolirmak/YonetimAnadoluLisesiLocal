"""tahtalar — /tahtalar/ sayfası, toplu komut ve Okul Yönetimi kartı."""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from okul.testing import kullanici_olustur
from tahtalar.models import Tahta, TahtaEnvanteri, TahtaKomutu


def _tahta(ad, **kw):
    kw.setdefault("makine_kimligi", f"m-{ad}")
    kw.setdefault("token_ozeti", f"t-{ad}")
    return Tahta.objects.create(ad=ad, **kw)


class TahtaSayfasiTestCase(TestCase):
    def setUp(self):
        self.acik = _tahta(
            "K101",
            son_gorulme=timezone.now(),
            ahenk_servisi=Tahta.AHENK_CALISIYOR,
            meb_kayitli=True,
        )
        self.kapali = _tahta("K102", ahenk_servisi=Tahta.AHENK_DURMUS, meb_kayitli=False)
        self.pasif = _tahta("ESKI", aktif=False)
        TahtaEnvanteri.objects.create(lider_id=9, mac_adresi="aa:bb:cc:00:00:09", sube_adi="Z001")
        self.url = reverse("tahtalar:liste")
        self.komut_url = reverse("tahtalar:komut_ver")

    def _giris(self, *gruplar):
        self.client.force_login(kullanici_olustur(*gruplar))

    def test_mudur_yardimcisi_ve_okul_muduru_gorur(self):
        for grup in ("mudur_yardimcisi", "okul_muduru"):
            with self.subTest(grup=grup):
                self._giris(grup)
                yanit = self.client.get(self.url)
                self.assertEqual(yanit.status_code, 200)
                self.assertContains(yanit, "K101")
                self.assertContains(yanit, "Z001")  # ajanı kurulmamış envanter
                self.assertNotContains(yanit, "ESKI")  # pasif tahta listelenmez

    def test_ogretmen_ve_diger_yoneticiler_giremez(self):
        for grup in ("ogretmen", "rehber_ogretmen", "disiplin_kurulu"):
            with self.subTest(grup=grup):
                self._giris(grup)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.client.post(self.komut_url, {"komut": "kapat", "tahta": [self.acik.pk]})
        self.assertFalse(TahtaKomutu.objects.exists())

    def test_girissiz_kullanici_yonlendirilir(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_filtreler(self):
        self._giris("mudur_yardimcisi")
        beklenen = {
            "cevrimici": ("K101", "K102"),
            "cevrimdisi": ("K102", "K101"),
            "ahenk_sorunlu": ("K102", "K101"),
            "meb_kayitsiz": ("K102", "K101"),
        }
        for filtre, (var, yok) in beklenen.items():
            with self.subTest(filtre=filtre):
                yanit = self.client.get(self.url, {"filtre": filtre})
                adlar = [t.ad for t in yanit.context["tahtalar"]]
                self.assertIn(var, adlar)
                self.assertNotIn(yok, adlar)
        yanit = self.client.get(self.url, {"filtre": "uydurma"})
        self.assertEqual(len(yanit.context["tahtalar"]), 2)

    def test_toplu_komut(self):
        self._giris("okul_muduru")
        yanit = self.client.post(
            self.komut_url,
            {
                "komut": "yeniden_baslat",
                "tahta": [self.acik.pk, self.kapali.pk],
                "filtre": "cevrimici",
            },
        )
        self.assertRedirects(yanit, f"{self.url}?filtre=cevrimici", fetch_redirect_response=False)
        komutlar = TahtaKomutu.objects.all()
        self.assertEqual(
            {(k.tahta_id, k.komut) for k in komutlar},
            {(self.acik.pk, "yeniden_baslat"), (self.kapali.pk, "yeniden_baslat")},
        )
        self.assertTrue(
            all(k.olusturan.groups.filter(name="okul_muduru").exists() for k in komutlar)
        )

    def test_pasif_tahtaya_ve_gecersiz_komut_verilmez(self):
        self._giris("mudur_yardimcisi")
        self.client.post(self.komut_url, {"komut": "kapat", "tahta": [self.pasif.pk]})
        self.client.post(self.komut_url, {"komut": "sil", "tahta": [self.acik.pk]})
        self.client.post(self.komut_url, {"komut": "kapat", "tahta": ["abc"]})
        self.assertFalse(TahtaKomutu.objects.exists())

    def test_get_ile_komut_verilemez(self):
        self._giris("mudur_yardimcisi")
        yanit = self.client.get(self.komut_url, {"komut": "kapat", "tahta": [self.acik.pk]})
        self.assertEqual(yanit.status_code, 405)

    def test_son_komut_listede_gorunur(self):
        TahtaKomutu.objects.create(tahta=self.acik, komut=TahtaKomutu.KAPAT)
        self._giris("mudur_yardimcisi")
        yanit = self.client.get(self.url)
        acik = next(t for t in yanit.context["tahtalar"] if t.pk == self.acik.pk)
        self.assertEqual(acik.son_komut.komut, TahtaKomutu.KAPAT)

    def test_okul_yonetimi_karti(self):
        self._giris("okul_muduru")
        yanit = self.client.get(reverse("okul:yonetim_index"))
        self.assertContains(yanit, "Etkileşimli Tahtalar")
        self.assertContains(yanit, self.url)
        self.assertEqual(yanit.context["tahta_ozeti"]["toplam"], 2)
        self.assertEqual(yanit.context["tahta_ozeti"]["cevrimici"], 1)
        self.assertEqual(yanit.context["tahta_ozeti"]["ajansiz"], 1)

    def test_sol_menu_yonetim_menusu(self):
        self._giris("okul_muduru")
        yanit = self.client.get(self.url)
        self.assertEqual(yanit.context["yan_menu"], "includes/yonetim_menu.html")
