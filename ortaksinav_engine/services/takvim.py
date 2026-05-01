# -*- coding: utf-8 -*-
"""
TakvimService – Adim 4

ILP (PuLP + NetworkX) ile catismasiz sinav takvimi olusturur.
SubeDers tablosunu okur; Takvim tablosuna yazar ve takvim.xlsx uretir.

Ozel metodlar:
  _nth_business_day  – takvim hesabi icin is gunu bulur
  _build_graph       – sube bazli catisma grafi
  _greedy_upper_bound – greedy boyama ile slot ust siniri
  _day_slots_dict    – gun -> slot listesi eslestirmesi
  _phase1            – Faz-1 ILP (minimum slot sayisi)
  _phase2            – Faz-2 ILP (Kelebek amac fonksiyonlu optimizasyon)
"""

import itertools
from datetime import datetime, timedelta
from math import ceil

import pandas as pd
import networkx as nx
from pulp import (
    LpProblem, LpVariable, LpBinary, lpSum,
    LpMinimize, PULP_CBC_CMD, value, LpStatusOptimal,
)

from ortaksinav_engine.config import CIFT_OTURUMLU_DERSLER as _DEFAULT_CIFT_OTURUMLU
from ortaksinav_engine.services.base import BaseService


class TakvimService(BaseService):
    """ILP tabanli sinav takvimi olusturan servis."""

    def takvimolustur(self):
        self.log("\nILP ile sinav takvimi olusturuluyor...")
        from sinav.models import SubeDers, SinavBilgisi

        from django.db.models import F as _F
        aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
        # FK alanlar için string değerler: ders__ders_adi, sube__sube (harf)
        records = list(
            SubeDers.objects
            .exclude(ders__isnull=True)
            .exclude(sube__isnull=True)
            .values(
                ders_adi=_F("ders__ders_adi"),
                sinif_seviye=_F("seviye"),
                sube_harf=_F("sube__sube"),
            )
        )
        if not records:
            raise RuntimeError("Adim 4: DB'de sube/ders yok. Once Adim 3'u calistirin.")

        df = (
            pd.DataFrame(records)
            .rename(columns={"ders_adi": "Ders", "sinif_seviye": "Seviye", "sube_harf": "Sube"})
        )
        df["Ders"] = df["Ders"].astype(str).str.strip()
        df["Sube"] = df["Sube"].astype(str).str.strip()
        df["Seviye"] = df["Seviye"].astype(int)
        df["Sube"] = df["Seviye"].astype(str) + "/" + df["Sube"]

        from okul.models import DersHavuzu as _DH
        _db_cift = list(_DH.objects.filter(cift_oturum=1).values_list("ders_adi", flat=True))
        CIFT_OTURUMLU_DERSLER = _db_cift or self.config.get("CIFT_OTURUMLU_DERSLER") or _DEFAULT_CIFT_OTURUMLU

        # Cift oturumlu dersleri ikiye ayir
        rows = []
        for _, r in df.iterrows():
            if r["Ders"] in CIFT_OTURUMLU_DERSLER:
                for tip in [" (Uygulama)", " (Yazili)"]:
                    rr = r.copy()
                    rr["Ders"] = r["Ders"] + tip
                    rows.append(rr)
            else:
                rows.append(r)
        dfE = pd.DataFrame(rows)

        G, DERSLER, SUBE_DERS_MAP = self._build_graph(dfE)

        # Seviye bazli catisma gruplari: ayni gruptaki dersler ayni seviyede
        # ayni slota duşemez → G'ye ek kenar ekle
        catisma_gruplari = self.config.get("SEVIYE_CATISMA_GRUPLARI") or []
        kenар_sayisi = 0
        for grup in catisma_gruplari:
            # Her dersin hangi seviyelerde bulundugunu bul
            ders_seviye: dict[str, set] = {}
            for d in grup:
                if d not in DERSLER:
                    continue
                for sube, dlist in SUBE_DERS_MAP.items():
                    if d in set(dlist):
                        sev = sube.split("/")[0]
                        ders_seviye.setdefault(d, set()).add(sev)
            # Ortak seviyesi olan her ders cifti icin kenar ekle
            ders_listesi = [d for d in grup if d in ders_seviye]
            for i, d1 in enumerate(ders_listesi):
                for d2 in ders_listesi[i + 1:]:
                    if ders_seviye[d1] & ders_seviye[d2] and not G.has_edge(d1, d2):
                        G.add_edge(d1, d2)
                        kenар_sayisi += 1
        if kenар_sayisi:
            self.log(f"  Seviye catisma kisiti: {kenар_sayisi} yeni kenar G'ye eklendi.")

        # Catisma grubundaki dersler icin sube bazli gun kisiti:
        # ayni gruptaki derslerden bir sube'nin ayni gunde en fazla 1 sinavi olabilir.
        catisma_gun_kisitlari: list[tuple[str, frozenset]] = []
        for grup in catisma_gruplari:
            grup_dersler = set(grup) & set(DERSLER)
            for sube, dlist in SUBE_DERS_MAP.items():
                dset = grup_dersler & set(dlist)
                if len(dset) >= 2:
                    catisma_gun_kisitlari.append((sube, frozenset(dset)))
        if catisma_gun_kisitlari:
            self.log(f"  Catisma gun kisiti: {len(catisma_gun_kisitlari)} "
                     f"sube/grup kombinasyonu icin gun basina <= 1 aktif.")

        # Uygulama sinavlari exclusive slot: ayni slotta baska hicbir sinav olamaz.
        # Her (Uygulama) dersi ile diger tum dersler arasina G'ye kenar eklenir;
        # ILP bu kenarlar icin x[d1,t] + x[d2,t] <= 1 kisitini zaten uygular.
        uygulama_dersler = [d for d in DERSLER if d.endswith(" (Uygulama)")]
        if uygulama_dersler:
            uyg_kenar = 0
            for d_uyg in uygulama_dersler:
                for d_other in DERSLER:
                    if d_other != d_uyg and not G.has_edge(d_uyg, d_other):
                        G.add_edge(d_uyg, d_other)
                        uyg_kenar += 1
            self.log(f"  Uygulama exclusive kisiti: {len(uygulama_dersler)} uyg. dersi, "
                     f"{uyg_kenar} yeni kenar G'ye eklendi.")

        DERS_WEIGHT = {
            d: dfE[dfE["Ders"] == d]["Sube"].nunique()
            for d in DERSLER
        }

        min_days_needed = max(
            (ceil(len(set(dlist)) / 2) for dlist in SUBE_DERS_MAP.values()),
            default=0,
        )

        # OTURUM_SAATLERI autoritatif kaynak: gun basina slot sayisi her zaman
        # liste uzunlugundan turetilir; OTURUM_SAYISI_GUN ile uyumsuzluk engellenir.
        OTURUM_SAYISI_GUN = len(self.config["OTURUM_SAATLERI"])
        K_upper = self._greedy_upper_bound(G, DERSLER)
        K_upper = max(K_upper, min_days_needed * OTURUM_SAYISI_GUN)
        extra_days_used = 0

        # Sabit sinavlari slot endeksine donustur
        fixed_slots: dict[str, int] = {}
        sabit_list = self.config.get("SABIT_SINAVLAR") or []
        if sabit_list:
            from datetime import date as _date
            oturum_saatleri = self.config["OTURUM_SAATLERI"]
            baslangic = self.config["BASLANGIC_TARIH"]
            holidays  = self.config["HOLIDAYS"]
            for ss in sabit_list:
                ders_adi  = ss["ders"]
                seviyeler = ss.get("seviyeler") or []  # [] → tüm seviyeler

                # Çift oturumlu dersler ILP'de "(Yazılı)" ve "(Uygulama)" olarak
                # ikiye bölündüğünden, sabit atama "(Yazılı)" varyantına yapılır.
                if ders_adi in CIFT_OTURUMLU_DERSLER:
                    ilp_ders_adi = ders_adi + " (Yazili)"
                    self.log(f"  [Sabit] '{ders_adi}' çift oturumlu → Yazili oturumu sabitlenecek.")
                else:
                    ilp_ders_adi = ders_adi

                try:
                    tarih = _date.fromisoformat(ss["tarih"])
                    saat  = ss["saat"]
                    slot_in_day = oturum_saatleri.index(saat)
                except (ValueError, IndexError) as exc:
                    self.log(f"  [Sabit] '{ders_adi}' slot hesaplanamadı: {exc}")
                    continue

                day_index = self._date_to_day_index(tarih, baslangic, holidays)
                t_fixed = day_index * OTURUM_SAYISI_GUN + slot_in_day

                # Seviye filtresi: belirtilmişse yalnızca o seviyelerde var olan dersler için uygula.
                # SUBE_DERS_MAP anahtarları "9/A" biçiminde; ham ders_adi kullanılarak kontrol edilir.
                # ILP'de SUBE_DERS_MAP değerleri dfE'den gelir: çift oturumlu dersler
                # orada "(Yazılı)"/"(Uygulama)" olarak genişletilmiştir.
                # Bu yüzden varlık/seviye kontrolü ilp_ders_adi ile yapılmalı.
                if ilp_ders_adi not in DERSLER:
                    self.log(f"  [Sabit] '{ilp_ders_adi}' DERSLER'de yok, atlanıyor.")
                    continue

                if seviyeler:
                    sev_strs = {str(s) for s in seviyeler}
                    mevcut = any(
                        sube.split("/")[0] in sev_strs and ilp_ders_adi in set(dlist)
                        for sube, dlist in SUBE_DERS_MAP.items()
                    )
                    if not mevcut:
                        self.log(f"  [Sabit] '{ilp_ders_adi}' belirlenen seviyelerde yok, atlanıyor.")
                        continue
                    sev_str = ",".join(str(s) for s in seviyeler)
                    self.log(f"  [Sabit] {ilp_ders_adi} (seviye:{sev_str}) → gün {day_index+1}, slot {slot_in_day+1} (t={t_fixed})")
                else:
                    self.log(f"  [Sabit] {ilp_ders_adi} → gün {day_index+1}, slot {slot_in_day+1} (t={t_fixed})")

                fixed_slots[ilp_ders_adi] = t_fixed

            # K_upper en az tüm sabit slotları kapsayacak kadar büyük olmalı
            if fixed_slots:
                K_upper = max(K_upper, max(fixed_slots.values()) + 1)

        # Cift oturumlu ciftleri onceden hesapla – Faz-1 ve Faz-2'de kullanilir
        pairs = [
            (base + " (Uygulama)", base + " (Yazili)")
            for base in CIFT_OTURUMLU_DERSLER
            if base + " (Uygulama)" in DERSLER and base + " (Yazili)" in DERSLER
        ]
        if pairs:
            self.log(f"  Cift oturumlu ayni-gun kisiti: {len(pairs)} cift (Faz-1 ve Faz-2).")

        # Faz-1
        while True:
            if self.is_cancelled():
                raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")
            DAY_SLOTS = self._day_slots_dict(K_upper, OTURUM_SAYISI_GUN)
            min_slots, ders_to_slot_p1, _ = self._phase1(
                K_upper, G, DERSLER, SUBE_DERS_MAP, DAY_SLOTS, fixed_slots,
                catisma_gun_kisitlari, pairs,
            )
            if min_slots is not None:
                break
            extra_days_used += 1
            if extra_days_used > self.config["MAX_EXTRA_DAYS"]:
                raise RuntimeError("Faz-1: Feasible bulunamadi; gun alt sinirini artirin.")
            K_upper += OTURUM_SAYISI_GUN
            self.log(f"Gun artirildi: K_upper={K_upper}")

        self.log(f"Faz-1 tamamlandi: {min_slots} slot, K_upper={K_upper}")

        if self.is_cancelled():
            raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")

        # Her ders icin hangi sinif seviyelerini (9,10,11,12) kapsadigini hesapla
        ders_seviye_map: dict[str, set[int]] = {}
        for d in DERSLER:
            sevs: set[int] = set()
            for sube, dlist in SUBE_DERS_MAP.items():
                if d in set(dlist):
                    try:
                        sevs.add(int(sube.split("/")[0]))
                    except (ValueError, IndexError):
                        pass
            ders_seviye_map[d] = sevs

        # Faz-2: min_slots slotu kullan; sabit sinavlar icin K buyutulabilir
        K_phase2 = max(min_slots, max(fixed_slots.values()) + 1) if fixed_slots else min_slots
        ders_to_slot = self._phase2(
            K_phase2, G, DERSLER, SUBE_DERS_MAP, pairs, DERS_WEIGHT, OTURUM_SAYISI_GUN,
            ders_seviye_map, fixed_slots, catisma_gun_kisitlari,
        )
        if ders_to_slot is None:
            self.log("Faz-2 cozum bulamadi; Faz-1 sonucu kullaniliyor.")
            ders_to_slot = ders_to_slot_p1

        rows_out = []
        for d, t in sorted(ders_to_slot.items(), key=lambda kv: (kv[1], kv[0])):
            day_index = t // OTURUM_SAYISI_GUN
            slot_in_day = t % OTURUM_SAYISI_GUN
            tarih = self._nth_business_day(
                self.config["BASLANGIC_TARIH"], day_index, self.config["HOLIDAYS"]
            )
            saat = self.config["OTURUM_SAATLERI"][slot_in_day]
            subeler = dfE.loc[dfE["Ders"] == d, "Sube"].unique()
            rows_out.append({
                "Tarih": tarih.strftime("%Y-%m-%d"),
                "Saat": saat,
                "Oturum": t,          # gecici; asagida yeniden numaralandirilacak
                "GunIdx": day_index,
                "Ders": d,
                "Subeler": ", ".join(sorted(subeler)),
            })

        # Oturum numaralarini GUN BAZINDA 1'den baslayarak yeniden ver:
        # Ayni (Tarih, Saat) → ayni oturum numarasi; her gun icin 1'den baslar.
        slot_to_oturum: dict[tuple, int] = {}
        gun_oturum_no: dict[str, int] = {}
        for row in sorted(rows_out, key=lambda r: (r["Tarih"], r["Saat"])):
            key = (row["Tarih"], row["Saat"])
            if key not in slot_to_oturum:
                tarih = row["Tarih"]
                gun_oturum_no.setdefault(tarih, 1)
                slot_to_oturum[key] = gun_oturum_no[tarih]
                gun_oturum_no[tarih] += 1
        for row in rows_out:
            row["Oturum"] = slot_to_oturum[(row["Tarih"], row["Saat"])]

        df_out = pd.DataFrame(rows_out)

        # Kural kontrolu
        _max_per_gun = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        tmp = df_out.copy()
        tmp["Subeler"] = tmp["Subeler"].str.split(", ")
        tmp = tmp.explode("Subeler").rename(columns={"Subeler": "Sube"})
        gcount = tmp.groupby(["GunIdx", "Sube"]).size().reset_index(name="Adet")
        viol = gcount[gcount["Adet"] > _max_per_gun]
        if not viol.empty:
            for _, row in viol.iterrows():
                self.log(f"  IHLAL: {row['Sube']} - Gun {int(row['GunIdx'])+1} - {int(row['Adet'])} sinav")
            self.log(f"IHLAL: {len(viol)} sube/gun kombinasyonunda > {_max_per_gun} sinav var!")
        else:
            self.log(f"Kural saglandi: Her sube icin her gunde <= {_max_per_gun} sinav.")

        # Catisma grubu gun kisiti dogrulama
        if catisma_gun_kisitlari:
            ihlal_cg = 0
            for _sube, dset_cg in catisma_gun_kisitlari:
                gun_sayim = {}
                for d in dset_cg:
                    if d in ders_to_slot:
                        gi = ders_to_slot[d] // OTURUM_SAYISI_GUN
                        gun_sayim[gi] = gun_sayim.get(gi, 0) + 1
                for gi, cnt in gun_sayim.items():
                    if cnt > 1:
                        ihlal_cg += 1
            if ihlal_cg:
                self.log(f"IHLAL: Catisma grubu gun kisiti {ihlal_cg} kombinasyonda asildi!")
            else:
                self.log("Catisma grubu gun kisiti saglandi: her sube/gunde <= 1.")

        # Kelebek karisimi raporu: slot basina kac farkli seviye var?
        tmp2 = df_out.copy()
        tmp2["Subeler"] = tmp2["Subeler"].str.split(", ")
        tmp2 = tmp2.explode("Subeler")
        tmp2["Seviye"] = tmp2["Subeler"].str.split("/").str[0]
        slot_seviye = tmp2.groupby(["Tarih", "Oturum"])["Seviye"].nunique()
        ort = slot_seviye.mean()
        maks = slot_seviye.max()
        self.log(f"Kelebek karisimi: ortalama {ort:.1f} seviye/oturum, max {maks} seviye/oturum.")

        # DB'ye kaydetme YOK – önizleme için instance değişkenine yaz, view kaydeder
        kayitlar = df_out.drop(columns=["GunIdx"]).to_dict(orient="records")
        for r in kayitlar:
            r["Tarih"] = str(r["Tarih"])  # date → str
        self._onizleme_kayitlar = kayitlar
        self.log(f"{len(kayitlar)} kayitlik onizleme hazırlandi.")
        self.log("Takvimi kontrol edip onaylayabilirsiniz.")

    # ------------------------------------------------------------------
    # Ozel yardimci metodlar
    # ------------------------------------------------------------------

    @staticmethod
    def _date_to_day_index(tarih, baslangic: datetime, holidays: set) -> int:
        """Verilen tarihin is-gunu endeksini hesaplar (baslangic=0)."""
        from datetime import date as _date
        # Baslangic gununun tarihini bul (tatil/hafta sonu atlayarak)
        cur = baslangic
        while cur.weekday() >= 5 or cur.date() in holidays:
            cur += timedelta(days=1)
        if cur.date() == tarih:
            return 0
        idx = 0
        while cur.date() < tarih:
            cur += timedelta(days=1)
            if cur.weekday() < 5 and cur.date() not in holidays:
                idx += 1
        return idx

    @staticmethod
    def _nth_business_day(start_date: datetime, n: int, holidays: set) -> datetime:
        d = start_date
        while d.weekday() >= 5 or d.date() in holidays:
            d += timedelta(days=1)
        added = 0
        while added < n:
            d += timedelta(days=1)
            if d.weekday() < 5 and d.date() not in holidays:
                added += 1
        return d

    @staticmethod
    def _build_graph(df_expanded: pd.DataFrame):
        dersler = sorted(df_expanded["Ders"].unique())
        G = nx.Graph()
        G.add_nodes_from(dersler)
        sube_ders_map = df_expanded.groupby("Sube")["Ders"].unique().to_dict()
        for sube, dlist in sube_ders_map.items():
            for d1, d2 in itertools.combinations(set(dlist), 2):
                G.add_edge(d1, d2)
        return G, dersler, sube_ders_map

    @staticmethod
    def _greedy_upper_bound(G, dersler):
        if not dersler:
            return 0
        greedy = nx.coloring.greedy_color(G, strategy="DSATUR")
        K_upper = max(greedy.values()) + 1 if greedy else 1
        K_upper += max(3, ceil(len(dersler) / 12))
        return K_upper

    @staticmethod
    def _day_slots_dict(K_upper, per_day):
        return {
            g: list(range(g * per_day, min((g + 1) * per_day, K_upper)))
            for g in range(ceil(max(K_upper, 1) / per_day))
        }

    def _phase1(self, K_upper, G, DERSLER, SUBE_DERS_MAP, DAY_SLOTS,
                fixed_slots=None, catisma_gun_kisitlari=None, pairs=None):
        MAX_SINAV_PER_GUN = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        DAYS = list(DAY_SLOTS.keys())
        model = LpProblem("MinSlot_Phase1", LpMinimize)
        x = {
            (d, t): LpVariable(f"x_{i}_{t}", cat=LpBinary)
            for i, d in enumerate(DERSLER)
            for t in range(K_upper)
        }
        y = {t: LpVariable(f"y_{t}", cat=LpBinary) for t in range(K_upper)}

        for d in DERSLER:
            model += lpSum(x[(d, t)] for t in range(K_upper)) == 1

        # Sabit sınav kısıtları: bu dersler yalnızca belirlenen slota atanabilir
        for d, t_fixed in (fixed_slots or {}).items():
            if d in DERSLER and t_fixed < K_upper:
                model += x[(d, t_fixed)] == 1

        for d1, d2 in G.edges():
            for t in range(K_upper):
                model += x[(d1, t)] + x[(d2, t)] <= 1

        for t in range(K_upper):
            for d in DERSLER:
                model += x[(d, t)] <= y[t]
            if t < K_upper - 1:
                model += y[t] >= y[t + 1]

        for sube, dlist in SUBE_DERS_MAP.items():
            dset = set(dlist)
            for g, slots in DAY_SLOTS.items():
                model += lpSum(x[(d, t)] for d in dset for t in slots if (d, t) in x) <= MAX_SINAV_PER_GUN

        # Catisma grubundaki dersler: ayni sube icin ayni gunde en fazla 1 sinav
        for _sube, dset_cg in (catisma_gun_kisitlari or []):
            for g, slots in DAY_SLOTS.items():
                model += lpSum(x[(d, t)] for d in dset_cg for t in slots if (d, t) in x) <= 1

        # Cift oturumlu dersler AYNI GUNDE OLMALI – Faz-1'de de hard kisit
        if pairs:
            u1 = {
                (d, g): LpVariable(f"u1_{DERSLER.index(d)}_{g}", cat=LpBinary)
                for d in DERSLER
                for g in DAYS
            }
            for d in DERSLER:
                for g, slots in DAY_SLOTS.items():
                    model += u1[(d, g)] <= lpSum(x[(d, t)] for t in slots if (d, t) in x)
                model += lpSum(u1[(d, g)] for g in DAYS) == 1
            for dL, dK in pairs:
                for g in DAYS:
                    model += u1[(dL, g)] == u1[(dK, g)]

        model += lpSum(y[t] for t in range(K_upper))
        model.solve(PULP_CBC_CMD(msg=False, timeLimit=self.config["TIME_LIMIT_PHASE1"],
                                 gapRel=0.0, threads=0))

        if model.status not in (LpStatusOptimal, 1):
            return None, None, None

        ders_to_slot = {}
        for d in DERSLER:
            for t in range(K_upper):
                if value(x[(d, t)]) > 0.5:
                    ders_to_slot[d] = t
                    break
        used_slots = sorted(set(ders_to_slot.values()))
        return len(used_slots), ders_to_slot, used_slots

    def _phase2(self, min_slots, G, DERSLER, SUBE_DERS_MAP, pairs, DERS_WEIGHT,
                oturum_sayisi_gun, ders_seviye_map=None, fixed_slots=None,
                catisma_gun_kisitlari=None):
        MAX_SINAV_PER_GUN = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        """
        Faz-2: Exactly min_slots sloti kullanir (K = min_slots).
        Tum y[t]=1 olacagindan y degiskenleri kaldirilir.
        Hedef:
          1. Cift oturumlu dersleri ayni gune koy.
          2. Her oturumda farkli sinif seviyelerinden ders olsun (Kelebek karisimi).
          3. Erken slotlari tercih et.
        """
        K = min_slots
        DAY_SLOTS = self._day_slots_dict(K, oturum_sayisi_gun)
        DAYS = list(DAY_SLOTS.keys())

        model = LpProblem("SameDay_Phase2", LpMinimize)

        x = {
            (d, t): LpVariable(f"x_{i}_{t}", cat=LpBinary)
            for i, d in enumerate(DERSLER)
            for t in range(K)
        }

        # Her ders tam olarak 1 slota atanir
        for d in DERSLER:
            model += lpSum(x[(d, t)] for t in range(K)) == 1

        # Sabit sınav kısıtları
        for d, t_fixed in (fixed_slots or {}).items():
            if d in DERSLER and t_fixed < K:
                model += x[(d, t_fixed)] == 1

        # Catisan dersler ayni slotta olamaz
        for d1, d2 in G.edges():
            for t in range(K):
                model += x[(d1, t)] + x[(d2, t)] <= 1

        # Sube/gun <= MAX_SINAV_PER_GUN sinavi
        for sube, dlist in SUBE_DERS_MAP.items():
            dset = set(dlist)
            for g, slots in DAY_SLOTS.items():
                model += lpSum(x[(d, t)] for d in dset for t in slots if (d, t) in x) <= MAX_SINAV_PER_GUN

        # Catisma grubundaki dersler: ayni sube icin ayni gunde en fazla 1 sinav
        for _sube, dset_cg in (catisma_gun_kisitlari or []):
            for g, slots in DAY_SLOTS.items():
                model += lpSum(x[(d, t)] for d in dset_cg for t in slots if (d, t) in x) <= 1

        # Ders-gun ikili degiskeni (cift oturum icin)
        u = {
            (d, g): LpVariable(f"u_{DERSLER.index(d)}_{g}", cat=LpBinary)
            for d in DERSLER
            for g in DAYS
        }
        for d in DERSLER:
            for g, slots in DAY_SLOTS.items():
                model += u[(d, g)] <= lpSum(x[(d, t)] for t in slots if (d, t) in x)
            model += lpSum(u[(d, g)] for g in DAYS) == 1

        # Cift oturumlu dersler AYNI GUNDE OLMALI – hard kisit
        # u[(dL,g)] == u[(dK,g)] her g icin: ya ikisi birden o gunde ya da ikisi de degil.
        for dL, dK in pairs:
            for g in DAYS:
                model += u[(dL, g)] == u[(dK, g)]

        # Erken slotlari tercih et (slot numarasi kucuk olsun)
        slot_usage = lpSum(
            x[(d, t)] * (t % oturum_sayisi_gun)
            for d in DERSLER
            for t in range(K)
            if (d, t) in x
        )

        # Agir dersleri ayri slotlara dag (max grup buyuklugunu minimize et)
        M = {t: LpVariable(f"M_{t}", lowBound=0) for t in range(K)}
        for t in range(K):
            for d in DERSLER:
                w_d = DERS_WEIGHT.get(d, 1)
                model += M[t] >= w_d * x[(d, t)]

        # Ayni slot eslemesi: cakisma yoksa ayni slotta olmasi tercih edilir (soft)
        esleme_ciftleri = self.config.get("AYNI_SLOT_ESLEME") or []
        esleme_term = 0
        esleme_aktif = 0
        for idx, (d1, d2) in enumerate(esleme_ciftleri):
            if d1 not in DERSLER or d2 not in DERSLER:
                continue
            if G.has_edge(d1, d2):
                self.log(f"  [Esleme] '{d1}' ↔ '{d2}' çakışıyor; ayni slot atanamaz, atlanıyor.")
                continue
            for t in range(K):
                z = LpVariable(f"zes_{idx}_{t}", cat=LpBinary)
                model += z <= x[(d1, t)]
                model += z <= x[(d2, t)]
                esleme_term += z
            esleme_aktif += 1
        if esleme_aktif:
            self.log(f"  Ayni slot esleme: {esleme_aktif} cift, soft kisit olarak eklendi.")

        # Kelebek karisimi: her slotta farkli sinif seviyelerinden ders olsun
        # lev[s,t] = 1 ise slot t'de seviye s'den en az bir ders var
        diversity_term = 0
        if ders_seviye_map:
            SEVIYELER = sorted({s for sevs in ders_seviye_map.values() for s in sevs})
            if SEVIYELER:
                lev = {
                    (sv, t): LpVariable(f"lev_{sv}_{t}", cat=LpBinary)
                    for sv in SEVIYELER
                    for t in range(K)
                }
                for sv in SEVIYELER:
                    dersler_sv = [d for d in DERSLER if sv in ders_seviye_map.get(d, set())]
                    for t in range(K):
                        if dersler_sv:
                            model += lev[(sv, t)] <= lpSum(
                                x[(d, t)] for d in dersler_sv if (d, t) in x
                            )
                        else:
                            model += lev[(sv, t)] == 0
                # Maksimize etmek icin minimizasyona negatif eklenir
                diversity_term = -0.5 * lpSum(lev[(sv, t)] for sv in SEVIYELER for t in range(K))

        model += (
            0.01 * slot_usage
            + 0.01 * lpSum(M[t] for t in range(K))
            + diversity_term
            - 0.4 * esleme_term
        )

        model.solve(PULP_CBC_CMD(msg=False, timeLimit=self.config["TIME_LIMIT_PHASE2"],
                                 gapRel=0.05, threads=0))

        if model.status not in (LpStatusOptimal, 1):
            return None

        ders_to_slot = {}
        for d in DERSLER:
            for t in range(K):
                if value(x[(d, t)]) > 0.5:
                    ders_to_slot[d] = t
                    break
        return ders_to_slot
