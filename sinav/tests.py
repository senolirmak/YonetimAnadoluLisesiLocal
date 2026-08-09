"""Kelebek takvim GA motoru (ortaksinav_engine.services.takvim.TakvimService)
icin saf mantik testleri.

ortaksinav_engine INSTALLED_APPS'te ayri bir Django app'i degildir (bkz.
CLAUDE.md: "Ortak sınav motoru (Kelebek) — sinav + ortaksinav_engine"), bu
yuzden testleri kavramsal olarak ait oldugu sinav app'i altinda tutuyoruz.

_phase1/_phase2 artik ILP degil GA kullanir (bkz. takvim.py docstring'i).
Testler DB gerektirmez: TakvimService dogrudan config dict + no-op log/cancel
ile olusturulup _build_graph ile uretilen sentetik G/DERSLER/SUBE_DERS_MAP
uzerinde calistirilir.
"""

import random
import time

import pandas as pd
from django.test import SimpleTestCase

from ortaksinav_engine.services.oturma import OturmaPlanService
from ortaksinav_engine.services.takvim import TakvimService

_EMPTY_KEY = ("__EMPTY__", None)


def _service(**config_overrides):
    config = {
        "OTURUM_SAYISI_GUN": 3,
        "MAX_SINAV_PER_GUN": 2,
        "TIME_LIMIT_PHASE1": 20,
        "TIME_LIMIT_PHASE2": 20,
        "MAX_EXTRA_DAYS": 10,
    }
    config.update(config_overrides)
    return TakvimService(config, log_fn=lambda m: None, cancel_fn=lambda: False)


def _graph(sube_dersler: dict):
    """sube_dersler = {"9/A": ["MAT", "FIZ"], ...} → (G, DERSLER, SUBE_DERS_MAP).

    TakvimService._build_graph'in gercek kodda kullandigi bicimle birebir
    ayni sekilde uretir (DataFrame → networkx Graph)."""
    rows = [
        {"Ders": ders, "Sube": sube}
        for sube, dersler in sube_dersler.items()
        for ders in dersler
    ]
    return TakvimService._build_graph(pd.DataFrame(rows))


class TakvimServiceGATestCase(SimpleTestCase):
    """_phase1 (yapici GA) + _phase2 (evrimsel GA) icin sert kisit regresyonlari."""

    def _run_full(self, sube_dersler, svc=None, pairs=None, fixed_slots=None,
                  catisma_gun_kisitlari=None, esleme_gercek=None):
        """Faz-1 + Faz-2'yi ardisik calistirir (takvimolustur() ile ayni akis,
        K_upper yetersizse buyuten disi dongu dahil), (ders_to_slot,
        oturum_sayisi_gun, G) doner."""
        svc = svc or _service()
        oturum_sayisi_gun = svc.config["OTURUM_SAYISI_GUN"]
        G, DERSLER, SUBE_DERS_MAP = _graph(sube_dersler)
        DERS_WEIGHT = {
            d: sum(1 for dl in sube_dersler.values() if d in dl) for d in DERSLER
        }
        K_upper = svc._greedy_upper_bound(G, DERSLER)

        # takvimolustur()'daki Faz-1 disi dongusunun aynisi: _greedy_upper_bound
        # yalnizca catisma grafigini hesaba katar, gun kotasini degil — bu yuzden
        # yetersiz kalirsa gun ekleyerek tekrar denenir.
        min_slots = None
        extra_days = 0
        while min_slots is None:
            DAY_SLOTS = svc._day_slots_dict(K_upper, oturum_sayisi_gun)
            min_slots, ders_to_slot_p1, _used = svc._phase1(
                K_upper, G, DERSLER, SUBE_DERS_MAP, DAY_SLOTS,
                fixed_slots=fixed_slots, catisma_gun_kisitlari=catisma_gun_kisitlari,
                pairs=pairs, esleme_gercek=esleme_gercek,
            )
            if min_slots is not None:
                break
            extra_days += 1
            self.assertLessEqual(
                extra_days, svc.config["MAX_EXTRA_DAYS"], "Faz-1 feasible cozum bulamadi",
            )
            K_upper += oturum_sayisi_gun

        ders_to_slot = svc._phase2(
            min_slots, G, DERSLER, SUBE_DERS_MAP, pairs or [], DERS_WEIGHT,
            oturum_sayisi_gun, ders_seviye_map=None, fixed_slots=fixed_slots,
            catisma_gun_kisitlari=catisma_gun_kisitlari, esleme_gercek=esleme_gercek,
        )
        # takvimolustur() ile ayni fallback: Faz-2 basarisiz olursa Faz-1 sonucu kullanilir.
        if ders_to_slot is None:
            ders_to_slot = ders_to_slot_p1
        return ders_to_slot, oturum_sayisi_gun, G

    def test_catisan_dersler_farkli_slota_duser(self):
        ders_to_slot, _gun, G = self._run_full({
            "9/A": ["MAT", "FIZ"],
            "9/B": ["MAT", "KIMYA"],
        })
        for d1, d2 in G.edges():
            self.assertNotEqual(
                ders_to_slot[d1], ders_to_slot[d2],
                f"Catisan dersler ayni slota dustu: {d1} / {d2}",
            )

    def test_gun_basina_sube_kotasi_asilmaz(self):
        # 5 slots/gun ama sube kotasi 2 → gun basina en fazla 2 sinav, kotayi
        # zorlamak icin slot/gun kapasitesini bilerek genis tuttuk.
        svc = _service(OTURUM_SAYISI_GUN=5, MAX_SINAV_PER_GUN=2)
        sube_dersler = {"9/A": [f"DERS{i}" for i in range(5)]}
        ders_to_slot, oturum_sayisi_gun, _G = self._run_full(sube_dersler, svc=svc)

        gun_sayim: dict[int, int] = {}
        for _d, t in ders_to_slot.items():
            gun = t // oturum_sayisi_gun
            gun_sayim[gun] = gun_sayim.get(gun, 0) + 1
        for gun, adet in gun_sayim.items():
            self.assertLessEqual(adet, 2, f"Gun {gun}: {adet} sinav (kota=2)")

    def test_sabit_slot_uygulanir(self):
        ders_to_slot, _gun, _G = self._run_full(
            {"9/A": ["MAT", "FIZ"], "9/B": ["KIMYA"]},
            fixed_slots={"MAT": 0},
        )
        self.assertEqual(ders_to_slot["MAT"], 0)

    def test_esleme_ayni_slota_duser(self):
        ders_to_slot, _gun, _G = self._run_full(
            {"9/A": ["MAT", "FIZ"], "9/B": ["TARIH", "COGRAFYA"]},
            esleme_gercek=[("MAT", "TARIH")],
        )
        self.assertEqual(ders_to_slot["MAT"], ders_to_slot["TARIH"])

    def test_cift_oturum_ayni_gunde_ve_ayri_slotta(self):
        # Uygulama-exclusive kisiti _run_full/_graph tarafindan otomatik
        # eklenmedigi icin (bu, takvimolustur()'da ayri bir asama) burada
        # G'yi elle kurup dogrudan _phase1/_phase2 cagiriyoruz.
        svc = _service(OTURUM_SAYISI_GUN=3)
        sube_dersler = {
            "9/A": ["DIL (Uygulama)", "DIL (Yazili)", "MAT"],
            "9/B": ["FIZ"],
        }
        oturum_sayisi_gun = svc.config["OTURUM_SAYISI_GUN"]
        G, DERSLER, SUBE_DERS_MAP = _graph(sube_dersler)
        # Gercek kodda oldugu gibi: Uygulama sinavi tum diger derslerle exclusive.
        for d in DERSLER:
            if d != "DIL (Uygulama)" and not G.has_edge("DIL (Uygulama)", d):
                G.add_edge("DIL (Uygulama)", d)

        pairs = [("DIL (Uygulama)", "DIL (Yazili)")]
        DERS_WEIGHT = {d: 1 for d in DERSLER}
        K_upper = svc._greedy_upper_bound(G, DERSLER)
        DAY_SLOTS = svc._day_slots_dict(K_upper, oturum_sayisi_gun)
        min_slots, ders_to_slot_p1, _used = svc._phase1(
            K_upper, G, DERSLER, SUBE_DERS_MAP, DAY_SLOTS, pairs=pairs,
        )
        self.assertIsNotNone(min_slots)
        ders_to_slot = svc._phase2(
            min_slots, G, DERSLER, SUBE_DERS_MAP, pairs, DERS_WEIGHT, oturum_sayisi_gun,
        ) or ders_to_slot_p1

        gun = oturum_sayisi_gun
        self.assertEqual(
            ders_to_slot["DIL (Uygulama)"] // gun,
            ders_to_slot["DIL (Yazili)"] // gun,
            "Cift oturumlu dersler ayni gunde olmali",
        )
        self.assertNotEqual(
            ders_to_slot["DIL (Uygulama)"], ders_to_slot["DIL (Yazili)"],
            "Uygulama exclusive slotta olmali (Yazili ile ayni slot olamaz)",
        )

    def test_catisma_grubu_gun_kisiti(self):
        svc = _service(OTURUM_SAYISI_GUN=2, MAX_SINAV_PER_GUN=2)
        sube_dersler = {"9/A": ["EDEBIYAT", "TARIH", "COGRAFYA", "FIZ", "KIMYA", "BIYO"]}
        catisma_gun_kisitlari = [("9/A", frozenset({"EDEBIYAT", "TARIH", "COGRAFYA"}))]
        ders_to_slot, oturum_sayisi_gun, _G = self._run_full(
            sube_dersler, svc=svc, catisma_gun_kisitlari=catisma_gun_kisitlari,
        )

        gun_sayim: dict[int, int] = {}
        for d in ("EDEBIYAT", "TARIH", "COGRAFYA"):
            g = ders_to_slot[d] // oturum_sayisi_gun
            gun_sayim[g] = gun_sayim.get(g, 0) + 1
        for g, adet in gun_sayim.items():
            self.assertLessEqual(adet, 1, f"Catisma grubu gun {g}'de {adet} ders (kota=1)")

    def test_makul_olcekte_tum_dersler_yerlesir_ve_hizli_biter(self):
        """Regresyon: gercekci-ish olcekte (12 sube, sube basina 8 ders) GA
        makul surede (<20sn) tum derslere kisitsiz bir yerlesim bulmali."""
        rnd = random.Random(11)
        havuz = [f"DERS{i}" for i in range(18)]
        sube_dersler = {
            f"{sev}/{sub}": rnd.sample(havuz, k=8)
            for sev in (9, 10, 11, 12)
            for sub in "ABC"
        }
        svc = _service(OTURUM_SAYISI_GUN=5, MAX_SINAV_PER_GUN=2)

        baslangic = time.perf_counter()
        ders_to_slot, _gun, G = self._run_full(sube_dersler, svc=svc)
        sure = time.perf_counter() - baslangic

        self.assertEqual(set(ders_to_slot.keys()), set(havuz))
        for d1, d2 in G.edges():
            self.assertNotEqual(ders_to_slot[d1], ders_to_slot[d2])
        self.assertLess(sure, 20, f"GA {sure:.1f} saniye surdu")


class OturmaPlanServiceGATestCase(SimpleTestCase):
    """OturmaPlanService._build_layout (GA tabanli koltuk atamasi, bkz.
    _ga_seat_assignment) icin saf mantik testleri. Faz-1 (stride bosluk
    yerlesimi) degismedi; sadece Faz-2 (eskiden MRV greedy + takas onarimi)
    GA'ya cevrildi."""

    @staticmethod
    def _adjacency_conflicts(layout, rows, cols):
        conflicts = 0
        for r in range(rows):
            for c in range(cols):
                key = layout[r][c]
                if key == _EMPTY_KEY:
                    continue
                neighbors = []
                for dc in (-1, 1):
                    nc = c + dc
                    if 0 <= nc < cols and (c // 2) == (nc // 2):
                        neighbors.append((r, nc))
                for dr in (-1, 1):
                    nr = r + dr
                    if 0 <= nr < rows:
                        neighbors.append((nr, c))
                for nr, nc in neighbors:
                    if layout[nr][nc] == key:
                        conflicts += 1
        return conflicts // 2

    def test_bos_girdi_tamamen_bos_grid_doner(self):
        layout = OturmaPlanService._build_layout({}, rows=6, cols=6)
        for row in layout:
            for cell in row:
                self.assertEqual(cell, _EMPTY_KEY)

    def test_toplam_ogrenci_sayisi_korunur(self):
        exam_counts = {("MAT", 9): 5, ("FIZ", 10): 4, ("KIMYA", 11): 3}
        layout = OturmaPlanService._build_layout(exam_counts, rows=6, cols=6)
        dolu = sum(1 for row in layout for cell in row if cell != _EMPTY_KEY)
        self.assertEqual(dolu, sum(exam_counts.values()))

    def test_dengeli_dagilimda_komsu_cakismasi_olmaz(self):
        # 6 farkli grup, her biri 6'sar ogrenci = 36 (tam dolu grid). Bu
        # 'komsu-esit-etiket-yok' problemi 6 renkle rahatca cozulebilir
        # oldugundan GA'nin 0 cakismaya ulasmasi beklenir.
        exam_counts = {(f"DERS{i}", 9 + i % 4): 6 for i in range(6)}
        layout = OturmaPlanService._build_layout(exam_counts, rows=6, cols=6)
        conflicts = self._adjacency_conflicts(layout, 6, 6)
        self.assertEqual(conflicts, 0, f"{conflicts} komsu cakismasi bulundu")

    def test_ga_seat_assignment_hizli_biter(self):
        exam_counts = {(f"DERS{i}", 9): 6 for i in range(6)}
        baslangic = time.perf_counter()
        layout = OturmaPlanService._build_layout(exam_counts, rows=6, cols=6)
        sure = time.perf_counter() - baslangic
        self.assertLess(sure, 5, f"GA {sure:.2f} saniye surdu")
        dolu = sum(1 for row in layout for cell in row if cell != _EMPTY_KEY)
        self.assertEqual(dolu, 36)

    def test_asiri_carpik_dagilimda_hata_vermeden_biter(self):
        # Tek bir grup 36 koltugun tamamini kaplarsa sifir cakisma imkansizdir
        # (ayni key'in kendi komsulariyla cakismasi kacinilmaz); GA yine de
        # hatasiz tamamlanmali ve tum koltuklari doldurmali.
        exam_counts = {("TEK_DERS", 9): 36}
        layout = OturmaPlanService._build_layout(exam_counts, rows=6, cols=6)
        dolu = sum(1 for row in layout for cell in row if cell != _EMPTY_KEY)
        self.assertEqual(dolu, 36)
