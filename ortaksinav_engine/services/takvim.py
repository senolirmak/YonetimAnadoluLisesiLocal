# -*- coding: utf-8 -*-
"""
TakvimService – Adim 4

Genetik algoritma (kisit-duyarli yapici yerlesim + mutasyonla iyilestirme) ile
catismasiz sinav takvimi olusturur. SubeDers tablosunu okur; Takvim tablosuna
yazar ve takvim.xlsx uretir.

Ozel metodlar:
  _nth_business_day   – takvim hesabi icin is gunu bulur
  _build_graph        – sube bazli catisma grafi
  _greedy_upper_bound – greedy boyama ile slot ust siniri (GA icin baslangic K'si)
  _day_slots_dict     – gun -> slot listesi eslestirmesi
  _phase1             – Faz-1 GA (minimum/kompakt slot sayisini bulan yapici arama)
  _phase2             – Faz-2 GA (Kelebek amac fonksiyonlu populasyon evrimi)
  _ga_build_context   – ders bazli kisitlari 'birim' (union-find ile eslesmis
                        ders gruplari) bazina indirger
  _ga_construct       – kisit-duyarli DSATUR-benzeri yapici yerlesim
  _ga_mutate          – sert kisitlari koruyarak bireyi mutasyona ugratir
  _ga_fitness         – yumusak amaclari (erken slot, yuk dengesi, cesitlilik) puanlar
"""

import copy
import itertools
import random
import time
from collections import defaultdict
from datetime import datetime, timedelta
from math import ceil

import networkx as nx
import pandas as pd

from ortaksinav_engine.config import CIFT_OTURUMLU_DERSLER as _DEFAULT_CIFT_OTURUMLU
from ortaksinav_engine.services.base import BaseService

# GA parametreleri
_GA_POPULATION_SIZE = 40
_GA_GENERATIONS = 120
_GA_MAX_STAGNATION = 25
_GA_CONSTRUCT_ATTEMPTS = 50  # bir K icin feasible birey aramak icin deneme sayisi


class TakvimService(BaseService):
    """Genetik algoritma tabanli sinav takvimi olusturan servis."""

    def takvimolustur(self):
        self.log("\nGA ile sinav takvimi olusturuluyor...")
        from django.db.models import F as _F

        from sinav.models import SinavBilgisi, SubeDers
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
        # GA _ga_slot_valid icinde bu kenarlari komsu-cakisma kisiti olarak okur.
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

                # Çift oturumlu dersler DERSLER listesinde "(Yazılı)" ve "(Uygulama)"
                # olarak ikiye bölündüğünden, sabit atama "(Yazılı)" varyantına yapılır.
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
                # SUBE_DERS_MAP değerleri dfE'den gelir: çift oturumlu dersler orada
                # "(Yazılı)"/"(Uygulama)" olarak genişletilmiştir.
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

        # Eş zamanlı eşleme çiftlerini önceden filtrele: hem DERSLER'de hem çakışmasız olanlar
        esleme_gercek: list[tuple[str, str]] = []
        for d1, d2 in (self.config.get("AYNI_SLOT_ESLEME") or []):
            if d1 not in DERSLER or d2 not in DERSLER:
                continue
            if G.has_edge(d1, d2):
                self.log(
                    f"  [Eş Zamanlı] '{d1}' ↔ '{d2}': ortak öğrenci var (aynı şube), "
                    f"eşleme uygulanamaz — bu iki ders AYRI slotlara atanacak."
                )
                continue
            esleme_gercek.append((d1, d2))
        if esleme_gercek:
            self.log(
                f"  Eş zamanlı eşleme: {len(esleme_gercek)} çift, "
                f"Faz-1 ve Faz-2'de aynı slota hard kısıt olarak uygulanacak."
            )

        # Faz-1
        while True:
            if self.is_cancelled():
                raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")
            DAY_SLOTS = self._day_slots_dict(K_upper, OTURUM_SAYISI_GUN)
            min_slots, ders_to_slot_p1, _ = self._phase1(
                K_upper, G, DERSLER, SUBE_DERS_MAP, DAY_SLOTS, fixed_slots,
                catisma_gun_kisitlari, pairs, esleme_gercek,
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
            ders_seviye_map, fixed_slots, catisma_gun_kisitlari, esleme_gercek,
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
                fixed_slots=None, catisma_gun_kisitlari=None, pairs=None, esleme_gercek=None):
        """
        Faz-1 (GA): K_upper slot ust siniri icinde TUM sert kisitlari saglayan
        kompakt (erken-slot oncelikli) bir yerlesim arar. DAY_SLOTS parametresi
        cagiran kodla imza uyumu icin tutulur, GA gun sayisini oturum_sayisi_gun
        uzerinden kendi hesaplar.
        """
        max_sinav_per_gun = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        oturum_sayisi_gun = self.config["OTURUM_SAYISI_GUN"]
        ctx = self._ga_build_context(
            G, DERSLER, SUBE_DERS_MAP, fixed_slots, catisma_gun_kisitlari, pairs, esleme_gercek,
        )

        rng = random.Random()
        deadline = time.monotonic() + self.config.get("TIME_LIMIT_PHASE1", 300)

        # Once tamamen ac-gozlu (earliest-fit) deneme: kompakt/az-slot kullanan
        # cozume en yakin sonucu verir (ILP'nin min-slot amacinin GA karsiligi).
        placement = self._ga_construct(
            ctx, K_upper, oturum_sayisi_gun, max_sinav_per_gun, rng, earliest_fit=True,
        )
        attempts = 0
        while placement is None and attempts < _GA_CONSTRUCT_ATTEMPTS:
            if self.is_cancelled():
                raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")
            if time.monotonic() > deadline:
                break
            attempts += 1
            placement = self._ga_construct(ctx, K_upper, oturum_sayisi_gun, max_sinav_per_gun, rng)

        if placement is None:
            return None, None, None

        ders_to_slot = self._ga_placement_to_ders(placement, ctx)
        used_slots = sorted(set(ders_to_slot.values()))
        min_slots = (max(used_slots) + 1) if used_slots else 0
        return min_slots, ders_to_slot, used_slots

    def _phase2(self, min_slots, G, DERSLER, SUBE_DERS_MAP, pairs, DERS_WEIGHT,
                oturum_sayisi_gun, ders_seviye_map=None, fixed_slots=None,
                catisma_gun_kisitlari=None, esleme_gercek=None):
        """
        Faz-2 (GA): Tam olarak min_slots slotu kullanan bir populasyon insa edip
        mutasyon + elitizmle yumusak amaclara gore evrimlestirir. Sert kisitlar
        (cakisma, sabit slot, ayni-slot esleme, cift-oturum ayni-gun, gun/sube
        kotasi, catisma-grubu gun kisiti) her bireyde YAPICI ASAMADA garanti
        edilir; mutasyon da yalnizca gecerli tasimalari uygular. Hedef:
          1. Cift oturumlu dersleri ayni gune koy (yapici asamada garanti).
          2. Her oturumda farkli sinif seviyelerinden ders olsun (Kelebek karisimi).
          3. Erken slotlari ve dengeli yuku tercih et.
        """
        max_sinav_per_gun = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        K = min_slots
        ctx = self._ga_build_context(
            G, DERSLER, SUBE_DERS_MAP, fixed_slots, catisma_gun_kisitlari, pairs, esleme_gercek,
        )

        rng = random.Random()
        population = self._ga_build_population(
            ctx, K, oturum_sayisi_gun, max_sinav_per_gun,
            pop_size=_GA_POPULATION_SIZE, rng=rng,
            attempts_budget=_GA_POPULATION_SIZE * 6,
        )
        if not population:
            return None

        def fit(p):
            return self._ga_fitness(p, ctx, DERS_WEIGHT, ders_seviye_map, oturum_sayisi_gun)

        best_penalty = float("inf")
        stagnation = 0
        mutation_rate = 0.25
        deadline = time.monotonic() + self.config.get("TIME_LIMIT_PHASE2", 120)

        for _generation in range(_GA_GENERATIONS):
            if self.is_cancelled():
                raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")
            if time.monotonic() > deadline:
                break

            population.sort(key=fit)
            current_best = fit(population[0])
            if current_best < best_penalty:
                best_penalty = current_best
                stagnation = 0
            else:
                stagnation += 1
            if stagnation >= _GA_MAX_STAGNATION:
                break

            parent_pool = population[: max(3, len(population) // 4)]
            new_population = [population[0]]  # Elitizm: en iyi bireyi koru
            while len(new_population) < len(population):
                parent = copy.deepcopy(rng.choice(parent_pool))
                child = self._ga_mutate(
                    ctx, parent, K, oturum_sayisi_gun, max_sinav_per_gun, rng, mutation_rate,
                )
                new_population.append(child)
            population = new_population

        best = min(population, key=fit)
        return self._ga_placement_to_ders(best, ctx)

    # ------------------------------------------------------------------
    # GA yardimci metodlari
    # ------------------------------------------------------------------

    @staticmethod
    def _ga_build_context(G, DERSLER, SUBE_DERS_MAP, fixed_slots, catisma_gun_kisitlari,
                           pairs, esleme_gercek):
        """
        Ders bazli kisitlari 'birim' (unit) bazina indirger:
          - Ayni-slot eslemesi (esleme_gercek) olan ders ciftleri Union-Find ile
            TEK birim haline getirilir (her zaman ayni slota duserler).
          - Cift oturumlu ciftler (pairs) 'gun bagi' olarak ayrica saklanir
            (ayni GUNDE olmalilar, slot cakismasi zaten G kenariyla saglanir).
        """
        parent = {d: d for d in DERSLER}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for d1, d2 in (esleme_gercek or []):
            if d1 in parent and d2 in parent:
                union(d1, d2)

        unit_courses: dict[str, list[str]] = defaultdict(list)
        course_unit: dict[str, str] = {}
        for d in DERSLER:
            u = find(d)
            unit_courses[u].append(d)
            course_unit[d] = u
        units = list(unit_courses.keys())

        # Birimler arasi catisma komsulugu (G kenarlarindan projekte edilir)
        unit_neighbors: dict[str, set[str]] = {u: set() for u in units}
        for d1, d2 in G.edges():
            u1, u2 = course_unit.get(d1), course_unit.get(d2)
            if u1 and u2 and u1 != u2:
                unit_neighbors[u1].add(u2)
                unit_neighbors[u2].add(u1)

        # Sabit slotlar birim bazina
        fixed_unit_slot: dict[str, int] = {}
        for d, t in (fixed_slots or {}).items():
            u = course_unit.get(d)
            if u is None:
                continue
            if u in fixed_unit_slot and fixed_unit_slot[u] != t:
                continue
            fixed_unit_slot[u] = t

        # Gun bagi ciftleri (cift oturumlu Uygulama/Yazili) birim bazina
        day_partner: dict[str, str] = {}
        for dL, dK in (pairs or []):
            uL, uK = course_unit.get(dL), course_unit.get(dK)
            if uL and uK and uL != uK:
                day_partner[uL] = uK
                day_partner[uK] = uL

        # Birim -> (sube -> o birimdeki, o subeye ait ders sayisi) — gun kotasi icin
        sube_of_course: dict[str, list[str]] = defaultdict(list)
        for sube, dlist in SUBE_DERS_MAP.items():
            for d in dlist:
                sube_of_course[d].append(sube)
        unit_sube_weight: dict[str, dict[str, int]] = defaultdict(dict)
        for u, courses in unit_courses.items():
            w: dict[str, int] = defaultdict(int)
            for d in courses:
                for sube in sube_of_course.get(d, []):
                    w[sube] += 1
            unit_sube_weight[u] = dict(w)

        # Catisma grubu kisitlari: (sube, dset) -> o gruba giren birimler
        unit_catisma_groups: dict[str, list[int]] = defaultdict(list)
        catisma_groups: list[tuple] = []
        for idx, (sube, dset_cg) in enumerate(catisma_gun_kisitlari or []):
            for d in dset_cg:
                u = course_unit.get(d)
                if u is not None:
                    unit_catisma_groups[u].append(idx)
            catisma_groups.append((sube, dset_cg))

        return {
            "units": units,
            "unit_courses": dict(unit_courses),
            "course_unit": course_unit,
            "unit_neighbors": unit_neighbors,
            "fixed_unit_slot": fixed_unit_slot,
            "day_partner": day_partner,
            "unit_sube_weight": dict(unit_sube_weight),
            "unit_catisma_groups": dict(unit_catisma_groups),
        }

    @staticmethod
    def _ga_slot_valid(ctx, placement, day_count, catisma_day_count, unit, t,
                        oturum_sayisi_gun, max_sinav_per_gun):
        """unit'in t slotuna yerlestirilmesi TUM sert kisitlara uyuyor mu?"""
        day = t // oturum_sayisi_gun

        # 1) Cakisma komsulugu: komsu birimlerden biri ayni slotta mi?
        for n in ctx["unit_neighbors"].get(unit, ()):
            if placement.get(n) == t:
                return False

        # 2) Gun bagi: eslesigi (cift oturum) varsa ayni gunde olmali
        partner = ctx["day_partner"].get(unit)
        if partner is not None and partner in placement:
            if placement[partner] // oturum_sayisi_gun != day:
                return False

        # 3) Sube/gun kotasi (MAX_SINAV_PER_GUN)
        for sube, adet in ctx["unit_sube_weight"].get(unit, {}).items():
            if day_count.get((sube, day), 0) + adet > max_sinav_per_gun:
                return False

        # 4) Catisma grubu gun kisiti: (sube, grup) basina gunde <= 1 birim.
        #    (Birim >1 ders icerse bile pratikte esleme nadir oldugundan birim
        #    granularitesinde kontrol yeterlidir.)
        for grup_idx in ctx["unit_catisma_groups"].get(unit, ()):
            if catisma_day_count.get((grup_idx, day), 0) >= 1:
                return False

        return True

    @staticmethod
    def _ga_place(ctx, placement, day_count, catisma_day_count, unit, t, oturum_sayisi_gun):
        placement[unit] = t
        day = t // oturum_sayisi_gun
        for sube, adet in ctx["unit_sube_weight"].get(unit, {}).items():
            day_count[(sube, day)] = day_count.get((sube, day), 0) + adet
        for grup_idx in ctx["unit_catisma_groups"].get(unit, ()):
            catisma_day_count[(grup_idx, day)] = catisma_day_count.get((grup_idx, day), 0) + 1

    @staticmethod
    def _ga_unplace(ctx, placement, day_count, catisma_day_count, unit, oturum_sayisi_gun):
        t = placement.pop(unit, None)
        if t is None:
            return
        day = t // oturum_sayisi_gun
        for sube, adet in ctx["unit_sube_weight"].get(unit, {}).items():
            day_count[(sube, day)] -= adet
        for grup_idx in ctx["unit_catisma_groups"].get(unit, ()):
            catisma_day_count[(grup_idx, day)] -= 1

    @staticmethod
    def _ga_recompute_counts(ctx, placement, oturum_sayisi_gun):
        day_count: dict[tuple, int] = {}
        catisma_day_count: dict[tuple, int] = {}
        for unit, t in placement.items():
            day = t // oturum_sayisi_gun
            for sube, adet in ctx["unit_sube_weight"].get(unit, {}).items():
                day_count[(sube, day)] = day_count.get((sube, day), 0) + adet
            for grup_idx in ctx["unit_catisma_groups"].get(unit, ()):
                catisma_day_count[(grup_idx, day)] = catisma_day_count.get((grup_idx, day), 0) + 1
        return day_count, catisma_day_count

    def _ga_construct(self, ctx, K, oturum_sayisi_gun, max_sinav_per_gun, rng, earliest_fit=False):
        """Kisit-duyarli yapici yerlesim. Basarili olursa {unit: slot} doner, olmazsa None.

        Sira: once sabit-slotlu birimler (hep aynen atanir), sonra en cok komsusu
        olan birimler once (DSATUR benzeri). earliest_fit=True ise her birim icin
        gecerli en kucuk slot secilir (kompakt/az-slot cozum — Faz-1 icin); aksi
        halde gecerli adaylar arasindan erken-slot egilimli rastgele secim yapilir
        (populasyon cesitliligi icin — Faz-2 icin).
        """
        units = ctx["units"]
        unit_neighbors = ctx["unit_neighbors"]
        fixed_unit_slot = ctx["fixed_unit_slot"]

        fixed_first = [u for u in units if u in fixed_unit_slot]
        rest = [u for u in units if u not in fixed_unit_slot]
        rng.shuffle(rest)
        rest.sort(key=lambda u: -len(unit_neighbors.get(u, ())))
        order = fixed_first + rest

        placement: dict[str, int] = {}
        day_count: dict[tuple, int] = {}
        catisma_day_count: dict[tuple, int] = {}

        for unit in order:
            if unit in fixed_unit_slot:
                t = fixed_unit_slot[unit]
                if t >= K or not self._ga_slot_valid(
                    ctx, placement, day_count, catisma_day_count, unit, t,
                    oturum_sayisi_gun, max_sinav_per_gun,
                ):
                    return None
                self._ga_place(ctx, placement, day_count, catisma_day_count, unit, t, oturum_sayisi_gun)
                continue

            candidates = [
                t for t in range(K)
                if self._ga_slot_valid(
                    ctx, placement, day_count, catisma_day_count, unit, t,
                    oturum_sayisi_gun, max_sinav_per_gun,
                )
            ]
            if not candidates:
                return None

            if earliest_fit:
                chosen = candidates[0]
            else:
                # Erken slotlara hafif egilim: adaylarin ilk ucte birinden rastgele sec
                top = candidates[: max(1, len(candidates) // 3)]
                chosen = rng.choice(top)
            self._ga_place(ctx, placement, day_count, catisma_day_count, unit, chosen, oturum_sayisi_gun)

        return placement

    def _ga_build_population(self, ctx, K, oturum_sayisi_gun, max_sinav_per_gun,
                              pop_size, rng, attempts_budget):
        population = []
        attempts = 0
        while len(population) < pop_size and attempts < attempts_budget:
            if self.is_cancelled():
                raise RuntimeError("Adim 4 kullanici tarafindan durduruldu.")
            attempts += 1
            placement = self._ga_construct(ctx, K, oturum_sayisi_gun, max_sinav_per_gun, rng)
            if placement is not None:
                population.append(placement)
        return population

    def _ga_mutate(self, ctx, placement, K, oturum_sayisi_gun, max_sinav_per_gun, rng, mutation_rate):
        """Bireyi yerinde mutasyona ugratir; sert kisitlar HER ZAMAN korunur
        (gecerli bir tasima yoksa o birim degistirilmeden birakilir)."""
        units = ctx["units"]
        day_count, catisma_day_count = self._ga_recompute_counts(ctx, placement, oturum_sayisi_gun)

        for unit in units:
            if unit in ctx["fixed_unit_slot"]:
                continue
            if rng.random() >= mutation_rate:
                continue

            partner = ctx["day_partner"].get(unit)
            old_t = placement[unit]

            if partner is None or partner not in placement:
                self._ga_unplace(ctx, placement, day_count, catisma_day_count, unit, oturum_sayisi_gun)
                candidates = [
                    t for t in range(K)
                    if self._ga_slot_valid(
                        ctx, placement, day_count, catisma_day_count, unit, t,
                        oturum_sayisi_gun, max_sinav_per_gun,
                    )
                ]
                if candidates:
                    new_t = rng.choice(candidates)
                    self._ga_place(ctx, placement, day_count, catisma_day_count, unit, new_t, oturum_sayisi_gun)
                else:
                    self._ga_place(ctx, placement, day_count, catisma_day_count, unit, old_t, oturum_sayisi_gun)
            else:
                # Gun bagli cift: birlikte yeni bir gune tasimayi dene, olmazsa geri al.
                old_partner_t = placement[partner]
                self._ga_unplace(ctx, placement, day_count, catisma_day_count, unit, oturum_sayisi_gun)
                self._ga_unplace(ctx, placement, day_count, catisma_day_count, partner, oturum_sayisi_gun)

                cand_unit = [
                    t for t in range(K)
                    if self._ga_slot_valid(
                        ctx, placement, day_count, catisma_day_count, unit, t,
                        oturum_sayisi_gun, max_sinav_per_gun,
                    )
                ]
                rng.shuffle(cand_unit)
                placed = False
                for t1 in cand_unit:
                    self._ga_place(ctx, placement, day_count, catisma_day_count, unit, t1, oturum_sayisi_gun)
                    cand_partner = [
                        t for t in range(K)
                        if self._ga_slot_valid(
                            ctx, placement, day_count, catisma_day_count, partner, t,
                            oturum_sayisi_gun, max_sinav_per_gun,
                        )
                    ]
                    if cand_partner:
                        t2 = rng.choice(cand_partner)
                        self._ga_place(ctx, placement, day_count, catisma_day_count, partner, t2, oturum_sayisi_gun)
                        placed = True
                        break
                    self._ga_unplace(ctx, placement, day_count, catisma_day_count, unit, oturum_sayisi_gun)
                if not placed:
                    self._ga_place(ctx, placement, day_count, catisma_day_count, unit, old_t, oturum_sayisi_gun)
                    self._ga_place(ctx, placement, day_count, catisma_day_count, partner, old_partner_t, oturum_sayisi_gun)

        return placement

    @staticmethod
    def _ga_placement_to_ders(placement, ctx):
        ders_to_slot: dict[str, int] = {}
        for unit, t in placement.items():
            for d in ctx["unit_courses"][unit]:
                ders_to_slot[d] = t
        return ders_to_slot

    @staticmethod
    def _ga_fitness(placement, ctx, DERS_WEIGHT, ders_seviye_map, oturum_sayisi_gun):
        """Yumusak amaclari puanlar (kucuk = iyi). Sert kisitlar yapici asamada
        zaten garanti edildigi icin burada sadece optimizasyon hedefleri var:
          - erken slot tercihi (kucuk agirlik)
          - agir derslerin (cok sube) slotlara dengeli dagilmasi (kucuk agirlik)
          - Kelebek cesitliligi: her slotta farkli seviyeden ders olmasi (odul)
        """
        slot_usage = 0
        slot_courses: dict[int, list[str]] = defaultdict(list)
        for unit, t in placement.items():
            for d in ctx["unit_courses"][unit]:
                slot_usage += t % oturum_sayisi_gun
                slot_courses[t].append(d)

        max_load_sum = 0
        diversity_sum = 0
        for t, courses in slot_courses.items():
            max_load_sum += max((DERS_WEIGHT.get(d, 1) for d in courses), default=0)
            if ders_seviye_map:
                seviyeler: set = set()
                for d in courses:
                    seviyeler |= ders_seviye_map.get(d, set())
                diversity_sum += len(seviyeler)

        return 0.01 * slot_usage + 0.01 * max_load_sum - 0.5 * diversity_sum
