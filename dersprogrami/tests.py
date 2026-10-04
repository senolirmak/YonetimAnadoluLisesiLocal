import datetime
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from io import BytesIO
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from dersprogrami.models import GUNLER, DersProgrami
from dersprogrami.services.fet_kopru import (
    FetKopruHatasi,
    fet_disa_aktar,
    fet_iceri_aktar,
    programi_aktif_yap,
)
from okul.models import AktifVeriKonfigurasyonu, DersHavuzu, DersSaatleri, Personel, SinifSube

ESKI_TARIH = datetime.date(2026, 9, 28)
YENI_TARIH = datetime.date(2026, 10, 5)


def _yerlestir(fet_xml: bytes) -> bytes:
    """FET'in yaptığını taklit eder: her etkinliğe, dışa aktarılan programdaki mevcut
    sırasına göre çakışmasız bir başlangıç zamanı kısıtı ekler (gün gün, saat saat)."""
    kok = ET.fromstring(fet_xml)
    gunler = [d.findtext("Name") for d in kok.findall("Days_List/Day")]
    saatler = [h.findtext("Name") for h in kok.findall("Hours_List/Hour")]
    zaman = kok.find("Time_Constraints_List")
    # Her etkinliği kendi gününe koymak için basit bir sayaç; testteki veri buna sığar.
    for i, e in enumerate(kok.findall("Activities_List/Activity")):
        k = ET.SubElement(zaman, "ConstraintActivityPreferredStartingTime")
        for etiket, deger in [
            ("Weight_Percentage", "100"),
            ("Activity_Id", e.findtext("Id")),
            ("Preferred_Day", gunler[i % len(gunler)]),
            ("Preferred_Hour", saatler[(i // len(gunler)) * 2]),
            ("Permanently_Locked", "false"),
            ("Active", "true"),
        ]:
            ET.SubElement(k, etiket).text = deger
    return ET.tostring(kok, encoding="utf-8")


def _uclu_saatleri(qs):
    return Counter(
        (d.ogretmen.adi_soyadi, f"{d.sinif_sube.sinif}/{d.sinif_sube.sube}", d.ders.ders_adi)
        for d in qs.select_related("ogretmen", "sinif_sube", "ders")
    )


class FetKopruTestCase(TestCase):
    def setUp(self):
        DersSaatleri.objects.all().delete()
        self.saat = {
            n: DersSaatleri.objects.create(
                derssaati_no=n,
                derssaati_baslangic=datetime.time(7 + n),
                derssaati_bitis=datetime.time(7 + n, 40),
            )
            for n in range(1, 9)
        }
        SinifSube.objects.all().delete()
        self.a = SinifSube.objects.create(sinif=9, sube="A")
        self.b = SinifSube.objects.create(sinif=9, sube="B")
        self.mat_ogr = Personel.objects.create(kimlikno="1", adi_soyadi="MAT HOCA")
        self.dil1 = Personel.objects.create(kimlikno="2", adi_soyadi="ALMANCA HOCA")
        self.dil2 = Personel.objects.create(kimlikno="3", adi_soyadi="FRANSIZCA HOCA")
        self.mat = DersHavuzu.objects.create(ders_adi="MATEMATİK T")
        self.almanca = DersHavuzu.objects.create(ders_adi="ALMANCA T")
        self.fransizca = DersHavuzu.objects.create(ders_adi="FRANSIZCA T")

        def ekle(ogretmen, sube, ders, gun, saat):
            DersProgrami.objects.create(
                ogretmen=ogretmen, sinif_sube=sube, ders=ders, gun=gun,
                ders_saati=self.saat[saat], uygulama_tarihi=ESKI_TARIH,
            )

        # 9/A matematik: Pazartesi 1-2 (blok) + Çarşamba 3 → 2+1
        ekle(self.mat_ogr, self.a, self.mat, "Monday", 1)
        ekle(self.mat_ogr, self.a, self.mat, "Monday", 2)
        ekle(self.mat_ogr, self.a, self.mat, "Wednesday", 3)
        # Paralel seçmeli: 9/A ikiye bölünür, aynı saatte Almanca + Fransızca (Salı 5)
        ekle(self.dil1, self.a, self.almanca, "Tuesday", 5)
        ekle(self.dil2, self.a, self.fransizca, "Tuesday", 5)
        # Birleştirilmiş ders: Almanca hocası 9/A ve 9/B'ye aynı anda (Perşembe 6)
        ekle(self.dil1, self.a, self.almanca, "Thursday", 6)
        ekle(self.dil1, self.b, self.almanca, "Thursday", 6)
        AktifVeriKonfigurasyonu.objects.update_or_create(
            veri_turu="ders_programi", defaults={"uygulama_tarihi": ESKI_TARIH}
        )

    def _etkinlikler(self):
        kok = ET.fromstring(fet_disa_aktar())
        return kok, kok.findall("Activities_List/Activity")

    def test_disa_aktarma_bloklari_ve_ortak_etkinlikler(self):
        kok, etkinlikler = self._etkinlikler()
        self.assertEqual([d.findtext("Name") for d in kok.findall("Days_List/Day")],
                         [tr for _, tr in GUNLER[:5]])
        self.assertEqual(len(kok.findall("Hours_List/Hour")), 8)

        mat = [e for e in etkinlikler if e.findtext("Subject") == "MATEMATİK T"]
        self.assertEqual(sorted(int(e.findtext("Duration")) for e in mat), [1, 2])
        self.assertEqual({e.findtext("Total_Duration") for e in mat}, {"3"})
        self.assertEqual(len({e.findtext("Activity_Group_Id") for e in mat}), 1)
        self.assertEqual(len(kok.findall("Time_Constraints_List/ConstraintMinDaysBetweenActivities")), 1)

        paralel = [e for e in etkinlikler if e.findtext("Subject", "").startswith("Blok: ")]
        self.assertEqual(len(paralel), 1)
        self.assertEqual(sorted(t.text for t in paralel[0].findall("Teacher")),
                         ["ALMANCA HOCA", "FRANSIZCA HOCA"])

        birlesik = [e for e in etkinlikler if len(e.findall("Students")) == 2]
        self.assertEqual(len(birlesik), 1)
        self.assertEqual([s.text for s in birlesik[0].findall("Students")], ["9/A", "9/B"])

    def test_gidis_donus_saatleri_korur(self):
        sonuc = _yerlestir(fet_disa_aktar())
        ozet = fet_iceri_aktar(BytesIO(sonuc), YENI_TARIH)
        self.assertEqual(ozet["uyarilar"], [])
        self.assertEqual(
            _uclu_saatleri(DersProgrami.objects.filter(uygulama_tarihi=YENI_TARIH)),
            _uclu_saatleri(DersProgrami.objects.filter(uygulama_tarihi=ESKI_TARIH)),
        )
        # Yeni sürüm otomatik aktif olmaz.
        self.assertEqual(DersProgrami.objects.aktif().filter(uygulama_tarihi=ESKI_TARIH).count(), 7)
        self.assertFalse(DersProgrami.objects.aktif().filter(uygulama_tarihi=YENI_TARIH).exists())

    def test_ayni_tarihte_program_varsa_reddeder(self):
        with self.assertRaises(FetKopruHatasi):
            fet_iceri_aktar(BytesIO(_yerlestir(fet_disa_aktar())), ESKI_TARIH)

    def test_yerlestirilmemis_dosya_reddedilir(self):
        with self.assertRaises(FetKopruHatasi):
            fet_iceri_aktar(BytesIO(fet_disa_aktar()), YENI_TARIH)

    def test_aktif_yap(self):
        fet_iceri_aktar(BytesIO(_yerlestir(fet_disa_aktar())), YENI_TARIH)
        programi_aktif_yap(YENI_TARIH)
        self.assertEqual(DersProgrami.objects.aktif().count(), 7)
        self.assertFalse(DersProgrami.objects.aktif().filter(uygulama_tarihi=ESKI_TARIH).exists())

    def test_yetki(self):
        ogretmen = User.objects.create_user("ogr", password="x")
        ogretmen.groups.add(Group.objects.get_or_create(name="ogretmen")[0])
        self.client.force_login(ogretmen)
        self.assertNotEqual(self.client.get(reverse("fet_indir")).status_code, 200)

        self.client.force_login(User.objects.create_superuser("admin", "a@a.a", "x"))
        r = self.client.get(reverse("fet_indir"))
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"<Activities_List>", r.content)

        r = self.client.post(reverse("fet_kopru"), {
            "uygulama_tarihi": YENI_TARIH.isoformat(),
            "dosya": SimpleUploadedFile("okul_data_and_timetable.fet", _yerlestir(r.content)),
        })
        self.assertRedirects(r, reverse("fet_kopru"))
        self.assertEqual(DersProgrami.objects.filter(uygulama_tarihi=YENI_TARIH).count(), 7)

    @skipUnless(shutil.which("fet-cl"), "fet-cl kurulu değil")
    def test_gercek_fet_ile_uretim(self):
        with tempfile.TemporaryDirectory() as dizin:
            girdi = Path(dizin) / "okul.fet"
            girdi.write_bytes(fet_disa_aktar())
            subprocess.run(
                ["fet-cl", f"--inputfile={girdi}", f"--outputdir={dizin}/out", "--timelimitseconds=60"],
                check=True, capture_output=True, timeout=120,
            )
            sonuc = Path(dizin) / "out" / "timetables" / "okul" / "okul_data_and_timetable.fet"
            ozet = fet_iceri_aktar(BytesIO(sonuc.read_bytes()), YENI_TARIH)
        self.assertEqual(ozet["uyarilar"], [])
        self.assertEqual(
            _uclu_saatleri(DersProgrami.objects.filter(uygulama_tarihi=YENI_TARIH)),
            _uclu_saatleri(DersProgrami.objects.filter(uygulama_tarihi=ESKI_TARIH)),
        )
