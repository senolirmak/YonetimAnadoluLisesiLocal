"""AdvancedNobetDagitim (ders doldurma dağıtımı) testleri.

Bkz. utility/services/nobet_dagitimi_service.py — problem en düşük maliyetli akışla
kesin çözülür: önce en fazla ders doldurulur, sonra dönem boyu yük dengelenir.
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
        """Regresyon: calculate_penalty teacher_counts sözlüğüne sıfır-kayıt eklememeli."""
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=20, devamsiz_sayisi=5)
        solver = AdvancedNobetDagitim(max_shifts=2)
        solver.set_teacher_statistics(stats)
        solver.optimize(available, absent)
        cozum = solver._akis_ile_coz()
        ilk_boyut = len(cozum["teacher_counts"])

        for _ in range(10):
            solver.calculate_penalty(cozum)

        self.assertEqual(len(cozum["teacher_counts"]), ilk_boyut)

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

        self.assertLess(sure, 25, f"Dağıtım {sure:.1f} saniye sürdü — timeout riski")


def _nobetci(t_id, dolu=()):
    return {"ogretmen_id": t_id, "adi_soyadi": f"N{t_id}", "dersleri": {h: "x" for h in dolu}}


def _bos_ders(t_id, **saat_sinif):
    return {"ogretmen_id": t_id, "adi_soyadi": f"D{t_id}", "dersleri": saat_sinif}


def _dagit(nobetciler, bos, toplamlar=None, max_shifts=2, son_yer=None):
    solver = AdvancedNobetDagitim(max_shifts=max_shifts)
    solver.set_teacher_statistics({
        t: {"toplam_nobet": n, "son_nobet_yeri": (son_yer or {}).get(t)}
        for t, n in (toplamlar or {}).items()
    })
    return solver.optimize(nobetciler, bos)


class AdilDagitimTestCase(SimpleTestCase):
    def test_ders_donem_toplami_en_az_olana_gider(self):
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2), _nobetci(3)],
            [{"ogretmen_id": 9, "dersleri": {3: "9/A"}}],
            toplamlar={1: 7, 2: 2, 3: 5},
        )
        self.assertEqual([a["teacher_id"] for a in sonuc["assignments"]], [2])

    def test_toplami_cok_dusuk_olan_ayni_gun_iki_ders_alir(self):
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2)],
            [{"ogretmen_id": 9, "dersleri": {1: "9/A", 2: "9/B"}}],
            toplamlar={1: 0, 2: 10},
        )
        self.assertEqual(sonuc["teacher_counts"], {1: 2})

    def test_toplamlar_esitse_gunluk_is_paylastirilir(self):
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2)],
            [{"ogretmen_id": 9, "dersleri": {1: "9/A", 2: "9/B"}}],
            toplamlar={1: 4, 2: 4},
        )
        self.assertEqual(sonuc["teacher_counts"], {1: 1, 2: 1})

    def test_mumkun_olan_en_fazla_ders_doldurulur(self):
        """Toplamı az olan 1, 1. saati alırsa 2. saat boş kalır; doğru çözüm 1'e 2. saati,
        2'ye 1. saati vermektir (2 yalnızca 1. saatte boş)."""
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2, dolu=range(2, 9))],
            [{"ogretmen_id": 9, "dersleri": {1: "9/A", 2: "9/B"}}],
            toplamlar={1: 0, 2: 30},
            max_shifts=1,
        )
        self.assertEqual(sonuc["unassigned"], [])
        self.assertEqual(
            sorted((a["teacher_id"], a["hour"]) for a in sonuc["assignments"]), [(1, 2), (2, 1)]
        )

    def test_esitlikte_son_doldurdugu_sinif_tekrar_verilmez(self):
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2)],
            [{"ogretmen_id": 9, "dersleri": {3: "9/A"}}],
            toplamlar={1: 3, 2: 3},
            son_yer={1: "9/A"},
        )
        self.assertEqual([a["teacher_id"] for a in sonuc["assignments"]], [2])

    def test_istatistigi_olmayan_nobetci_sifir_toplamli_sayilir(self):
        sonuc = _dagit(
            [_nobetci(1), _nobetci(2)],
            [{"ogretmen_id": 9, "dersleri": {3: "9/A"}}],
            toplamlar={1: 2},
        )
        self.assertEqual([a["teacher_id"] for a in sonuc["assignments"]], [2])

    def test_ayni_veride_ayni_sonuc(self):
        available, absent, stats = _sentetik_veri(ogretmen_sayisi=30, devamsiz_sayisi=8)
        sonuclar = []
        for _ in range(2):
            solver = AdvancedNobetDagitim(max_shifts=2)
            solver.set_teacher_statistics(stats)
            sonuclar.append(solver.optimize(available, absent)["assignments"])
        self.assertEqual(sonuclar[0], sonuclar[1])
