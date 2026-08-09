"""AdvancedNobetDagitim (nöbet dağıtım GA motoru) için regresyon testleri.

Bkz. utility/services/nobet_dagitimi_service.py. Buradaki testler özellikle iki
regresyonu yakalamak için var:
  1. GA'nın gerçekçi ölçekte gunicorn worker timeout'una takılacak kadar
     yavaşlaması (eski varsayılanlar population_size=600, generations=200,
     erken durdurma yok — bu senaryo ~95 saniye sürüyordu).
  2. calculate_penalty içindeki defaultdict yan-etkisi (solution["teacher_counts"][t_id]
     ile okuma yaparken sözlüğe sıfır-kayıt ekleniyordu).
"""

import random
import time

from django.test import SimpleTestCase

from utility.services.nobet_dagitimi_service import AdvancedNobetDagitim


def _sentetik_veri(ogretmen_sayisi, devamsiz_sayisi, tohum=42):
    """Gerçekçi ölçekte, tekrarlanabilir (sabit tohumlu) sentetik veri üretir."""
    rnd = random.Random(tohum)

    available_teachers = []
    for i in range(ogretmen_sayisi):
        busy_hours = set(rnd.sample(range(1, 9), k=rnd.randint(2, 5)))
        dersleri = {h: f"11/{h}-A" for h in busy_hours}
        available_teachers.append(
            {"ogretmen_id": i, "adi_soyadi": f"Ogretmen{i}", "dersleri": dersleri}
        )

    absent_teachers = []
    for i in range(ogretmen_sayisi, ogretmen_sayisi + devamsiz_sayisi):
        hours = rnd.sample(range(1, 9), k=rnd.randint(2, 4))
        dersleri = {
            h: f"{rnd.choice(['9', '10', '11', '12'])}/{h}-{rnd.choice('ABC')}"
            for h in hours
        }
        absent_teachers.append(
            {"ogretmen_id": i, "adi_soyadi": f"Devamsiz{i}", "dersleri": dersleri}
        )

    stats = {
        t["ogretmen_id"]: {
            "haftalik_ortalama": rnd.uniform(0.5, 3),
            "agirlikli_puan": rnd.uniform(0, 10),
            "toplam_nobet": rnd.randint(0, 20),
            "hafta_sayisi": rnd.randint(1, 10),
            "son_nobet_tarihi": None,
            "son_nobet_yeri": None,
        }
        for t in available_teachers
    }
    return available_teachers, absent_teachers, stats


class AdvancedNobetDagitimTestCase(SimpleTestCase):
    """Veritabanı gerektirmeyen saf iş mantığı testleri (SimpleTestCase)."""

    def test_feasible_senaryoda_tum_dersler_atanir(self):
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=20, devamsiz_sayisi=6)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)

        result = solver.optimize(available, absent)

        toplam_ders = sum(len(t["dersleri"]) for t in absent)
        self.assertEqual(len(result["unassigned"]), 0)
        self.assertEqual(len(result["assignments"]), toplam_ders)

    def test_hicbir_ogretmen_max_shifts_asmaz(self):
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=20, devamsiz_sayisi=6)
        max_shifts = 2
        solver = AdvancedNobetDagitim(max_shifts=max_shifts)
        solver.set_teacher_statistics(stats)

        result = solver.optimize(available, absent)

        for count in result["teacher_counts"].values():
            self.assertLessEqual(count, max_shifts)

    def test_hicbir_ogretmen_ayni_saatte_cakismaz(self):
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=20, devamsiz_sayisi=6)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)

        result = solver.optimize(available, absent)

        gorulen_saatler: dict[int, set[int]] = {}
        for a in result["assignments"]:
            saatler = gorulen_saatler.setdefault(a["teacher_id"], set())
            self.assertNotIn(a["hour"], saatler, "Öğretmen aynı saatte iki yere atanmış")
            saatler.add(a["hour"])

    def test_devamsiz_ders_yoksa_ga_calismadan_hemen_doner(self):
        available, _absent, stats = _sentetik_veri(ogretmen_sayisi=10, devamsiz_sayisi=0)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)

        baslangic = time.perf_counter()
        result = solver.optimize(available, [])
        sure = time.perf_counter() - baslangic

        self.assertEqual(result["assignments"], [])
        self.assertEqual(result["unassigned"], [])
        self.assertLess(sure, 0.5, "Devamsız ders yokken GA döngüsü boşuna çalışmamalı")

    def test_uygun_ogretmen_yoksa_tum_dersler_atanamayan_olur(self):
        _available, absent, _stats = _sentetik_veri(ogretmen_sayisi=1, devamsiz_sayisi=5)
        solver = AdvancedNobetDagitim(max_shifts=2)

        baslangic = time.perf_counter()
        result = solver.optimize([], absent)
        sure = time.perf_counter() - baslangic

        toplam_ders = sum(len(t["dersleri"]) for t in absent)
        self.assertEqual(len(result["assignments"]), 0)
        self.assertEqual(len(result["unassigned"]), toplam_ders)
        self.assertLess(sure, 0.5, "Uygun öğretmen yokken GA döngüsü boşuna çalışmamalı")

    def test_calculate_penalty_teacher_counts_uzerinde_yan_etki_birakmaz(self):
        """Regresyon: calculate_penalty tekrar tekrar çağrıldığında
        teacher_counts sözlüğüne sıfır-kayıt eklememeli (bkz. .get() düzeltmesi)."""
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=20, devamsiz_sayisi=5)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)
        solver.availability = solver.prepare_availability(available)
        solver.absent_classes = solver.flatten_absent(absent)
        solver.teachers = available
        solver.teacher_ids = [t["ogretmen_id"] for t in available]

        individual = solver.create_individual()
        ilk_boyut = len(individual["teacher_counts"])

        for _ in range(10):
            solver.calculate_penalty(individual)

        self.assertEqual(len(individual["teacher_counts"]), ilk_boyut)

    def test_gercekci_olcekte_makul_surede_biter(self):
        """Regresyon: eski varsayılanlarla (population_size=600, generations=200,
        erken durdurma yok) bu ölçekteki senaryo ~95 saniye sürüyor ve gunicorn
        worker timeout'una takılıyordu. Yeni varsayılanlarla çok daha hızlı
        bitmeli (yerelde ~8sn ölçüldü; CI için bolca pay bırakılarak 25sn
        sınırı kondu)."""
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=150, devamsiz_sayisi=20)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)

        baslangic = time.perf_counter()
        solver.optimize(available, absent)
        sure = time.perf_counter() - baslangic

        self.assertLess(sure, 25, f"GA {sure:.1f} saniye sürdü — timeout riski")
