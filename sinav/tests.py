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
from datetime import date

import pandas as pd
from django.test import SimpleTestCase, TestCase

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


class SabitSinavSeviyeBolmeTestCase(SimpleTestCase):
    """Aynı ders farklı seviyeler için farklı oturumlara sabitlenebilmeli
    (örn. 10. sınıf TDE 03.11 08:50, 9/11/12 TDE 06.11 10:30)."""

    TDE = "TÜRK DİLİ VE EDEBİYATI"

    def _dfE(self, cift=True):
        rows = []
        for sev in (9, 10, 11, 12):
            sube = f"{sev}/A"
            if cift:
                for sonek in (" (Uygulama)", " (Yazili)"):
                    rows.append({"Ders": self.TDE + sonek, "Seviye": sev, "Sube": sube})
            else:
                rows.append({"Ders": self.TDE, "Seviye": sev, "Sube": sube})
            rows.append({"Ders": "MATEMATİK", "Seviye": sev, "Sube": sube})
        return pd.DataFrame(rows)

    def _sabitler(self):
        return [
            {"ders": self.TDE, "tarih": "2026-11-03", "saat": "08:50", "seviyeler": [10]},
            {"ders": self.TDE, "tarih": "2026-11-06", "saat": "10:30", "seviyeler": [9, 11, 12]},
        ]

    def test_ders_seviyelere_gore_bolunur(self):
        svc = _service()
        dfE, hazir, dugum_ders = svc._sabit_seviye_bol(self._dfE(cift=False), self._sabitler(), [])
        on = f"{self.TDE} [10. sınıf]"
        diger = f"{self.TDE} [9,11,12. sınıf]"
        self.assertEqual([(d, sev) for d, _ss, sev in hazir], [(on, [10]), (diger, [9, 11, 12])])
        self.assertEqual(dugum_ders, {on: self.TDE, diger: self.TDE})
        self.assertEqual(set(dfE.loc[dfE["Ders"] == on, "Sube"]), {"10/A"})
        self.assertNotIn(self.TDE, set(dfE["Ders"]))

    def test_cift_oturumlu_derste_uygulama_da_bolunur(self):
        svc = _service()
        dfE, hazir, dugum_ders = svc._sabit_seviye_bol(self._dfE(), self._sabitler(), [self.TDE])
        self.assertEqual(hazir[0][0], f"{self.TDE} [10. sınıf] (Yazili)")
        self.assertEqual(dugum_ders[f"{self.TDE} [10. sınıf] (Uygulama)"], f"{self.TDE} (Uygulama)")
        self.assertEqual(dugum_ders[f"{self.TDE} [10. sınıf] (Yazili)"], f"{self.TDE} (Yazili)")

    def test_kalan_seviyeler_serbest_kalir(self):
        svc = _service()
        sabit = [self._sabitler()[0]]  # yalnızca 10. sınıf sabit
        dfE, hazir, _ = svc._sabit_seviye_bol(self._dfE(cift=False), sabit, [])
        self.assertEqual(len(hazir), 1)
        self.assertEqual(set(dfE.loc[dfE["Ders"] == self.TDE, "Seviye"]), {9, 11, 12})

    def test_seviyesiz_kayit_kalan_seviyeleri_sabitler(self):
        svc = _service()
        sabit = [self._sabitler()[0], {**self._sabitler()[1], "seviyeler": []}]
        _dfE, hazir, _ = svc._sabit_seviye_bol(self._dfE(cift=False), sabit, [])
        self.assertEqual([(d, sev) for d, _ss, sev in hazir],
                         [(f"{self.TDE} [10. sınıf]", [10]), (self.TDE, [9, 11, 12])])

    def test_bolunmus_dersler_farkli_sabit_slotlara_yerlesir(self):
        svc = _service()
        dfE, hazir, _ = svc._sabit_seviye_bol(self._dfE(), self._sabitler(), [self.TDE])
        sube_dersler = dfE.groupby("Sube")["Ders"].apply(list).to_dict()
        G, DERSLER, _ = _graph(sube_dersler)
        fixed = {hazir[0][0]: 0, hazir[1][0]: 7}
        pairs = [
            (d, d[: -len(" (Uygulama)")] + " (Yazili)")
            for d in DERSLER if d.endswith(" (Uygulama)")
        ]
        self.assertEqual(len(pairs), 2)
        ders_to_slot, gun, _G = TakvimServiceGATestCase._run_full(
            self, sube_dersler, svc=svc, pairs=pairs, fixed_slots=fixed
        )
        self.assertEqual(ders_to_slot[hazir[0][0]], 0)
        self.assertEqual(ders_to_slot[hazir[1][0]], 7)
        for uyg, yaz in pairs:  # Uygulama, Yazılı ile aynı gün
            self.assertEqual(ders_to_slot[uyg] // gun, ders_to_slot[yaz] // gun)


class SabitSinavTakvimUctanUcaTestCase(TestCase):
    """takvimolustur() uçtan uca: seviyeye özel iki sabit TDE sınavı önizlemeye
    doğru tarih/saat ve şubelerle, gerçek ders adıyla yansır."""

    def test_onizleme_satirlari(self):
        from datetime import datetime

        from okul.models import DersHavuzu, SinifSube
        from sinav.models import SubeDers

        tde = DersHavuzu.objects.create(ders_adi="TÜRK DİLİ VE EDEBİYATI", cift_oturum=1)
        mat = DersHavuzu.objects.create(ders_adi="MATEMATİK")
        for sev in (9, 10, 11, 12):
            ss = SinifSube.objects.create(sinif=sev, sube="A")
            for ders in (tde, mat):
                SubeDers.objects.create(ders=ders, seviye=sev, sube=ss)

        svc = _service(
            OTURUM_SAATLERI=["08:50", "10:30", "12:10"],
            BASLANGIC_TARIH=datetime(2026, 11, 2),
            HOLIDAYS=set(),
            SABIT_SINAVLAR=[
                {"ders": tde.ders_adi, "tarih": "2026-11-03", "saat": "08:50", "seviyeler": [10]},
                {"ders": tde.ders_adi, "tarih": "2026-11-06", "saat": "10:30", "seviyeler": [9, 11, 12]},
            ],
        )
        svc.takvimolustur()

        yazili = {
            (r["Tarih"], r["Saat"], r["Subeler"])
            for r in svc._onizleme_kayitlar
            if r["Ders"] == "TÜRK DİLİ VE EDEBİYATI (Yazili)"
        }
        self.assertEqual(yazili, {
            ("2026-11-03", "08:50", "10/A"),
            ("2026-11-06", "10:30", "11/A, 12/A, 9/A"),
        })
        # Düğüm etiketleri ("[10. sınıf]") önizlemeye sızmamalı
        self.assertFalse(any("sınıf]" in r["Ders"] for r in svc._onizleme_kayitlar))


class SabitSinavMutasyonTestCase(SimpleTestCase):
    """Çift oturumlu dersin Uygulama oturumu mutasyona uğrarken sabitlenmiş
    Yazılı eşini başka güne sürüklememeli (sunucuda TDE sabit tarihinin
    ezilmesinin sebebi buydu)."""

    def test_mutasyon_sabit_esi_tasimaz(self):
        svc = _service(OTURUM_SAYISI_GUN=3, MAX_SINAV_PER_GUN=2)
        uyg, yaz = "TDE (Uygulama)", "TDE (Yazili)"
        sube_dersler = {"9/A": [uyg, yaz], "9/B": [uyg, yaz], "10/A": ["MAT"]}
        G, DERSLER, SUBE_DERS_MAP = _graph(sube_dersler)
        fixed = {yaz: 7}  # 3. gün, 2. oturum
        ctx = svc._ga_build_context(G, DERSLER, SUBE_DERS_MAP, fixed, [], [(uyg, yaz)], [])
        K = 15
        rng = random.Random(0)
        placement = svc._ga_construct(ctx, K, 3, 2, rng)
        self.assertIsNotNone(placement)
        for _ in range(200):
            svc._ga_mutate(ctx, placement, K, 3, 2, rng, mutation_rate=1.0)
            self.assertEqual(placement[ctx["course_unit"][yaz]], 7)
            self.assertEqual(placement[ctx["course_unit"][uyg]] // 3, 2)  # aynı gün


class SabitSinavOnKontrolTestCase(TestCase):
    """Sabit sınavlar birbiriyle çelişiyorsa motor onlarca gün eklemeden hemen
    durmalı ve sebebi okunur şekilde loglamalı."""

    def _calistir(self, sabitler, oturumlar=("08:50", "10:30", "12:10")):
        from datetime import datetime

        from okul.models import DersHavuzu, SinifSube
        from sinav.models import SubeDers

        tde = DersHavuzu.objects.create(ders_adi="TÜRK DİLİ VE EDEBİYATI", cift_oturum=1)
        mat = DersHavuzu.objects.create(ders_adi="MATEMATİK")
        for sev in (9, 10):
            ss = SinifSube.objects.create(sinif=sev, sube="A")
            for ders in (tde, mat):
                SubeDers.objects.create(ders=ders, seviye=sev, sube=ss)
        loglar = []
        svc = _service(
            OTURUM_SAATLERI=list(oturumlar), BASLANGIC_TARIH=datetime(2026, 11, 9),
            HOLIDAYS=set(), SABIT_SINAVLAR=sabitler,
        )
        svc._log_fn = loglar.append
        return svc, loglar

    def test_uygulama_sigmazsa_baska_gune_planlanir(self):
        # Sunucudaki durum: 11.11'de 9. sınıfın iki sabit sınavı (TDE Yazılı 08:50,
        # MAT 10:30) var; TDE Uygulama o güne sığmaz (12:10 → günde 3 sınav).
        svc, loglar = self._calistir([
            {"ders": "TÜRK DİLİ VE EDEBİYATI", "tarih": "2026-11-11", "saat": "08:50", "seviyeler": [9]},
            {"ders": "MATEMATİK", "tarih": "2026-11-11", "saat": "10:30", "seviyeler": [9]},
        ])
        svc.takvimolustur()

        uyarilar = [m for m in loglar if "UYARI" in m]
        self.assertEqual(len(uyarilar), 1)
        self.assertIn("TÜRK DİLİ VE EDEBİYATI [9. sınıf] (Uygulama)", uyarilar[0])
        self.assertIn("9/A şubesi o gün günlük sınav sınırını (2) aşıyor", uyarilar[0])
        self.assertFalse(any("Gun artirildi" in m for m in loglar))
        self.assertTrue(any("Sabit sinavlar saglandi" in m for m in loglar))

        satir = {
            (r["Ders"], r["Subeler"]): (r["Tarih"], r["Saat"]) for r in svc._onizleme_kayitlar
        }
        self.assertEqual(satir[("TÜRK DİLİ VE EDEBİYATI (Yazili)", "9/A")], ("2026-11-11", "08:50"))
        self.assertEqual(satir[("MATEMATİK", "9/A")], ("2026-11-11", "10:30"))
        self.assertNotEqual(satir[("TÜRK DİLİ VE EDEBİYATI (Uygulama)", "9/A")][0], "2026-11-11")

    def test_ayni_oturumda_ortak_ogrenci(self):
        svc, loglar = self._calistir([
            {"ders": "MATEMATİK", "tarih": "2026-11-11", "saat": "10:30", "seviyeler": []},
            {"ders": "TÜRK DİLİ VE EDEBİYATI", "tarih": "2026-11-11", "saat": "10:30", "seviyeler": [10]},
        ])
        with self.assertRaises(RuntimeError):
            svc.takvimolustur()
        self.assertTrue(any("11.11.2026 10:30" in m and "ortak öğrencisi" in m for m in loglar))

    def test_uyumlu_sabitlerde_takvim_uretilir(self):
        svc, loglar = self._calistir([
            {"ders": "TÜRK DİLİ VE EDEBİYATI", "tarih": "2026-11-12", "saat": "08:50", "seviyeler": [10]},
            {"ders": "TÜRK DİLİ VE EDEBİYATI", "tarih": "2026-11-11", "saat": "10:30", "seviyeler": [9]},
        ])
        svc.takvimolustur()
        self.assertTrue(any("Sabit sinavlar saglandi" in m for m in loglar))


class SabitSinavEklemeTestCase(SimpleTestCase):
    def test_ayni_ders_farkli_seviyelerle_eklenebilir(self):
        from sinav.services.ders_ayarlari import SabitSinavCakismasi, sabit_sinav_ekle_veya_guncelle

        tde = "TÜRK DİLİ VE EDEBİYATI"
        liste = []
        on = {"ders_adi": tde, "tarih": "2026-11-03", "saat": "08:50", "seviyeler": [10]}
        diger = {"ders_adi": tde, "tarih": "2026-11-06", "saat": "10:30", "seviyeler": [9, 11, 12]}
        self.assertFalse(sabit_sinav_ekle_veya_guncelle(liste, on))
        self.assertFalse(sabit_sinav_ekle_veya_guncelle(liste, diger))
        self.assertEqual(len(liste), 2)

        # Aynı seviyeler → güncelleme
        self.assertTrue(sabit_sinav_ekle_veya_guncelle(liste, {**on, "saat": "10:30"}))
        self.assertEqual(liste[0]["saat"], "10:30")

        # Örtüşen seviye (ya da "tüm sınıflar") → hata, liste değişmez
        with self.assertRaises(SabitSinavCakismasi):
            sabit_sinav_ekle_veya_guncelle(liste, {**on, "seviyeler": [10, 11]})
        with self.assertRaises(SabitSinavCakismasi):
            sabit_sinav_ekle_veya_guncelle(liste, {**on, "seviyeler": []})
        self.assertEqual(len(liste), 2)


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


class OturmaPlanServiceIptalTestCase(TestCase):
    """generate_selected iptal istendiğinde kalan oturumları işlememeli ve
    yalnızca tamamlanan oturumları döndürmeli."""

    SESSIONS = [
        {"tarih": "2026-01-05", "saat": "09:00", "oturum": i} for i in (1, 2, 3)
    ]

    def _calistir(self, iptal_sonrasi):
        from unittest import mock

        islenen = []
        svc = OturmaPlanService(
            {}, log_fn=lambda m: None, cancel_fn=lambda: len(islenen) >= iptal_sonrasi,
        )
        with mock.patch.object(
            svc, "generate_oturum", side_effect=lambda *a, **k: islenen.append(a[2]),
        ):
            tamamlanan = svc.generate_selected(self.SESSIONS)
        return islenen, tamamlanan

    def test_iptal_kalan_oturumlari_atlar(self):
        islenen, tamamlanan = self._calistir(iptal_sonrasi=1)
        self.assertEqual(islenen, [1])
        self.assertEqual(tamamlanan, self.SESSIONS[:1])

    def test_iptal_yoksa_tum_oturumlar_doner(self):
        islenen, tamamlanan = self._calistir(iptal_sonrasi=99)
        self.assertEqual(islenen, [1, 2, 3])
        self.assertEqual(tamamlanan, self.SESSIONS)


class SinavOgrenciAnlikGoruntuTestCase(TestCase):
    """Ortak sınav öğrenci listesi yalnızca aktif öğrencilerden oluşmalı —
    mezun/nakil (aktif=False) öğrenciler salonlara yerleştirilmemeli."""

    def setUp(self):
        from ogrenci.models import Ogrenci
        from sinav.models import SinavBilgisi

        for okulno, aktif in [(1, True), (2, False)]:
            Ogrenci.objects.create(
                okulno=okulno, sinif=9, sube="A", tckimlikno=str(okulno).zfill(11),
                adi="AD", soyadi="SOYAD", dogumtarihi=date(2010, 1, 1), cinsiyet="E",
                aktif=aktif,
            )
        self.sinav = SinavBilgisi.objects.create(
            egitim_ogretim_yili="2026-2027", donem="1", sinav_adi="1",
            sinav_baslangic_tarihi=date(2026, 11, 2), eokul_veri_tarihi=date(2026, 10, 1),
        )

    def test_anlik_goruntu_pasif_ogrenciyi_almaz(self):
        from ortaksinav_engine.services.oturma import anlik_goruntu_garanti_et
        from sinav.models import SinavOgrenci

        anlik_goruntu_garanti_et(self.sinav)

        self.assertEqual(
            list(SinavOgrenci.objects.filter(sinav=self.sinav).values_list("okulno", flat=True)),
            [1],
        )

    def test_senkron_pasif_ogrenciyi_eklemez(self):
        from ogrenci.models import Ogrenci
        from sinav.models import SinavOgrenci
        from sinav.services.ogrenci_senkron import nakil_ogrenci_senkronize_et

        SinavOgrenci.objects.create(
            sinav=self.sinav, okulno=1, adi="AD", soyadi="SOYAD", cinsiyet="E", sinif=9, sube="A",
        )
        Ogrenci.objects.create(
            okulno=3, sinif=9, sube="A", tckimlikno="00000000003", adi="YENİ", soyadi="NAKİL",
            dogumtarihi=date(2010, 1, 1), cinsiyet="E", aktif=False,
        )

        nakil_ogrenci_senkronize_et(self.sinav)

        self.assertEqual(
            set(SinavOgrenci.objects.filter(sinav=self.sinav).values_list("okulno", flat=True)),
            {1},
        )


class SubeDersGuncelleTestCase(TestCase):
    """SubeDers, güncel ders programının birebir yansıması olmalı: arşivlenmiş
    eski programdaki ve bu yıl kapalı şubelerdeki dersler takvime girmemeli."""

    def setUp(self):
        from dersprogrami.models import DersProgrami
        from okul.models import (
            DersHavuzu, EgitimOgretimYili, OkulBilgi, Personel, SinifSube, SinifSubeYil,
        )

        yil = EgitimOgretimYili.objects.create(
            egitim_yili="2026-2027",
            egitim_baslangic=date(2026, 9, 1), egitim_bitis=date(2027, 6, 30),
        )
        okul = OkulBilgi.get()
        okul.okul_egtyil = yil
        okul.save()

        ogretmen = Personel.objects.create(kimlikno="11111111111", adi_soyadi="ÖĞRETMEN")
        mat = DersHavuzu.objects.create(ders_adi="MATEMATİK")
        fiz = DersHavuzu.objects.create(ders_adi="FİZİK")
        self.a = SinifSube.objects.create(sinif=10, sube="A")
        self.g = SinifSube.objects.create(sinif=10, sube="G")
        SinifSubeYil.objects.create(sinif_sube=self.g, egitim_yili=yil, acik=False)

        def dp(ders, ss, tarih, arsiv=False):
            DersProgrami.objects.create(
                gun="Monday", ders=ders, sinif_sube=ss, ogretmen=ogretmen,
                uygulama_tarihi=tarih, arsivlendi=arsiv,
            )

        dp(mat, self.a, date(2026, 10, 4))
        dp(mat, self.g, date(2026, 10, 4))          # kapalı şube
        dp(fiz, self.a, date(2026, 4, 20), arsiv=True)  # geçen yılın programı

    def _subeders(self):
        from sinav.models import SubeDers

        return set(SubeDers.objects.values_list("sube__sinif", "sube__sube", "ders__ders_adi"))

    def test_yalnizca_guncel_program_ve_acik_subeler(self):
        from ortaksinav_engine.services.ders_analiz import DersAnalizService

        DersAnalizService({}, log_fn=lambda m: None).subeders_guncelle()

        self.assertEqual(self._subeders(), {(10, "A", "MATEMATİK")})

    def test_artik_programda_olmayan_kayit_silinir(self):
        from okul.models import DersHavuzu
        from ortaksinav_engine.services.ders_analiz import DersAnalizService
        from sinav.models import SubeDers

        SubeDers.objects.create(ders=DersHavuzu.objects.get(ders_adi="FİZİK"), seviye=10, sube=self.g)

        DersAnalizService({}, log_fn=lambda m: None).subeders_guncelle()

        self.assertEqual(self._subeders(), {(10, "A", "MATEMATİK")})


class DersAyarlariTestCase(TestCase):
    """Ders Ayarları yalnızca bu yılın güncel ders programındaki dersleri
    göstermeli; havuzda kalmış ama bu yıl seçilmeyen dersler görünmemeli."""

    def test_guncel_programda_olmayan_ders_listelenmez(self):
        from django.contrib.auth.models import Group, User
        from django.urls import reverse

        from dersprogrami.models import DersProgrami
        from okul.models import DersHavuzu, Personel, SinifSube

        okutulan = DersHavuzu.objects.create(ders_adi="BEDEN EĞİTİMİ VE SPOR", sinav_yapilmayacak=True)
        DersHavuzu.objects.create(ders_adi="SEÇMELİ SANAT EĞİTİMİ", sinav_yapilmayacak=True)
        DersProgrami.objects.create(
            gun="Monday", ders=okutulan, sinif_sube=SinifSube.objects.create(sinif=9, sube="A"),
            ogretmen=Personel.objects.create(kimlikno="11111111111", adi_soyadi="ÖĞRETMEN"),
            uygulama_tarihi=date(2026, 10, 4),
        )
        user = User.objects.create_superuser("mudur", password="x")
        user.groups.add(Group.objects.get_or_create(name="mudur_yardimcisi")[0])
        self.client.force_login(user)

        yanit = self.client.get(reverse("sinav:ders_ayarlari"))

        self.assertEqual(yanit.status_code, 200)
        self.assertEqual(
            [d.ders_adi for d in yanit.context["yapilmayacak_dersler"]], ["BEDEN EĞİTİMİ VE SPOR"]
        )
        self.assertNotIn("SEÇMELİ SANAT EĞİTİMİ", yanit.context["tum_dersler_sabit"])
