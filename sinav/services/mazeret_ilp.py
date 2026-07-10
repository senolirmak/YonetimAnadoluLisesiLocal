"""
Mazeret Sınav ILP Planlama Servisi

MazeretOgrenci (belge_teslim=True, uygun) kayıtlarından çakışmasız mazeret
takvimi üretir. Çakışma kuralı: aynı öğrencinin iki sınavı aynı slotta olamaz.
Uygulama dersleri exclusive slot alır (başka hiçbir ders aynı slotta olamaz).
Ayrıca bir öğrenci aynı günde en fazla config["MAX_SINAV_PER_GUN"] (varsayılan 2)
oturuma girebilir.

Çıktı: MazeretGun + MazeretOturum + MazeretOturumDers kayıtları.
"""
from __future__ import annotations

from datetime import date, time, timedelta

import networkx as nx
from pulp import (
    LpProblem, LpVariable, LpBinary, lpSum,
    LpMinimize, PULP_CBC_CMD, value, LpStatusOptimal,
)

from ortaksinav_engine.services.base import BaseService

VARSAYILAN_SAATLER = ["08:50", "10:30", "12:10", "13:35", "14:25"]
OTURUM_SURESI_DK = 40


def _str_to_time(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def _time_add_dk(t: time, dk: int) -> time:
    total = timedelta(hours=t.hour, minutes=t.minute) + timedelta(minutes=dk)
    s = int(total.total_seconds())
    return time(s // 3600, (s % 3600) // 60)


def _parse_tatil(tatil_str: str) -> set[date]:
    sonuc: set[date] = set()
    for tok in tatil_str.replace(",", " ").split():
        try:
            sonuc.add(date.fromisoformat(tok.strip()))
        except ValueError:
            pass
    return sonuc


def _nth_is_gunu(baslangic: date, n: int, tatil: set[date]) -> date:
    """0-indexed: baslangic'tan itibaren n-inci iş günü."""
    count = 0
    gun = baslangic
    while True:
        if gun.weekday() < 5 and gun not in tatil:
            if count == n:
                return gun
            count += 1
        gun += timedelta(days=1)


class MazeretILPService(BaseService):
    """ILP tabanlı mazeret sınav takvimi planlayıcı."""

    def calistir(
        self,
        mazeret_sinav,
        baslangic_tarih: date,
        oturum_saatleri_str: str = "",
        tatil_gunleri_str: str = "",
    ) -> tuple[bool, str]:
        """
        ILP ile mazeret takvimini oluşturur/günceller.
        Mevcut MazeretGun/Oturum/OturumDers kayıtları tamamen silinip yeniden yazılır.
        """
        from sinav.models import (
            MazeretGun, MazeretOturum, MazeretOturumDers, MazeretOgrenci,
            TakvimUretim, Takvim,
        )
        from ogrenci.models import Ogrenci, OgrenciMuaf
        from okul.utils import get_aktif_egitim_yili

        # Oturum saatlerini belirle
        if oturum_saatleri_str:
            saatler = [s.strip() for s in oturum_saatleri_str.split(",") if s.strip()]
        else:
            try:
                saatler = [
                    s.strip()
                    for s in mazeret_sinav.sinav.parametreler.oturum_saatleri.split(",")
                    if s.strip()
                ]
            except Exception:
                saatler = []
        if not saatler:
            saatler = VARSAYILAN_SAATLER
        K_gun = len(saatler)  # oturum/gün

        # Öğrenci başına günlük oturum üst sınırı (varsayılan MazeretSinav.efektif_max_sinav_per_gun)
        max_gun = int(self.config.get("MAX_SINAV_PER_GUN", 2))
        if max_gun < 1:
            max_gun = 1

        # Tatil günlerini topla
        tatil: set[date] = _parse_tatil(tatil_gunleri_str)
        try:
            tatil |= _parse_tatil(mazeret_sinav.sinav.parametreler.tatil_gunleri)
        except Exception:
            pass

        # Aktif TakvimUretim
        aktif_uretim = TakvimUretim.objects.filter(
            sinav=mazeret_sinav.sinav, aktif=True
        ).first()
        if not aktif_uretim:
            return False, "Aktif takvim üretimi bulunamadı."

        # Sürekli devamsız ve muaf filtresi
        # Ogrenci.okulno int; MazeretOgrenci.okulno CharField → str dönüşümü
        sureksiz_strs = {
            str(x) for x in
            Ogrenci.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
        }

        # Subquery yerine Python listesi: int↔varchar tip çakışmasını önle
        _mo_okulno_strs = list(
            MazeretOgrenci.objects.filter(mazeret_sinav=mazeret_sinav)
            .values_list("okulno", flat=True).distinct()
        )
        _mo_okulno_ints = [int(x) for x in _mo_okulno_strs if x]
        muaf_pairs: set[tuple[str, str]] = (
            {
                (str(ok), ders)
                for ok, ders in OgrenciMuaf.objects.filter(
                    ogrenci__okulno__in=_mo_okulno_ints,
                    egitim_yili=get_aktif_egitim_yili(),
                ).values_list("ogrenci__okulno", "ders__ders_adi")
            }
            if _mo_okulno_ints else set()
        )

        uygun = [
            r
            for r in MazeretOgrenci.objects.filter(
                mazeret_sinav=mazeret_sinav, belge_teslim=True
            )
            .exclude(okulno__in=sureksiz_strs)
            .values("okulno", "ders_adi", "sinav_turu")
            if (r["okulno"], r["ders_adi"]) not in muaf_pairs
        ]

        if not uygun:
            return False, (
                "Belge teslim etmiş uygun öğrenci bulunamadı. "
                "Öğrencilerin belge teslim durumunu güncelleyin."
            )

        # (ders_adi, sinav_turu) → ders_id çözümle
        ders_key_to_id: dict[tuple[str, str], int] = {}
        for r in uygun:
            key = (r["ders_adi"], r["sinav_turu"])
            if key not in ders_key_to_id:
                tk = Takvim.objects.filter(
                    uretim=aktif_uretim,
                    ders__ders_adi=r["ders_adi"],
                    sinav_turu=r["sinav_turu"],
                ).values("ders_id").first()
                if tk:
                    ders_key_to_id[key] = tk["ders_id"]

        # Takvimde karşılığı olmayan öğrencileri at
        uygun = [r for r in uygun if (r["ders_adi"], r["sinav_turu"]) in ders_key_to_id]
        if not uygun:
            return False, "Uygun dersler aktif takvimde bulunamadı."

        DERSLER: list[tuple[str, str]] = list(ders_key_to_id.keys())
        N = len(DERSLER)
        ders_idx = {d: i for i, d in enumerate(DERSLER)}

        # Öğrenci → ders seti
        ogr_dersler: dict[str, set[tuple[str, str]]] = {}
        for r in uygun:
            key = (r["ders_adi"], r["sinav_turu"])
            ogr_dersler.setdefault(r["okulno"], set()).add(key)

        # Ders başına uygun öğrenci sayısı (kapasite kısıtı için)
        ogrenci_sayisi: list[int] = [0] * N
        for r in uygun:
            key = (r["ders_adi"], r["sinav_turu"])
            if key in ders_idx:
                ogrenci_sayisi[ders_idx[key]] += 1

        # Salon toplam kapasitesi
        salon_config: dict[str, int] = mazeret_sinav.efektif_salon_config
        toplam_kapasite: int = sum(salon_config.values())

        # ──────────────────────────────────────────────
        # Çakışma grafı:  edge(u,v) → aynı slota atanamaz
        # ──────────────────────────────────────────────
        G = nx.Graph()
        G.add_nodes_from(range(N))

        # Ortak öğrencisi olan ders çiftleri — aynı slot VE aynı gün kısıtı için ayrı kayıt
        student_pairs: set[tuple[int, int]] = set()
        for dersler_seti in ogr_dersler.values():
            dlist = list(dersler_seti)
            for a in range(len(dlist)):
                for b in range(a + 1, len(dlist)):
                    ia = ders_idx[dlist[a]]
                    ib = ders_idx[dlist[b]]
                    G.add_edge(ia, ib)
                    student_pairs.add((min(ia, ib), max(ia, ib)))

        # Uygulama exclusive: diğer tüm derslerle çakışır (yalnızca slot kısıtı)
        for d in DERSLER:
            if d[1] == "Uygulama":
                ui = ders_idx[d]
                for v in range(N):
                    if v != ui:
                        G.add_edge(ui, v)

        # Öğrenci başına gün alt sınırı: bir öğrenci günde en fazla max_gun oturuma girebilir,
        # dolayısıyla en çok dersi olan öğrenci ceil(ders_sayısı / max_gun) gün gerektirir.
        min_days_ogrenci = 1
        if ogr_dersler:
            max_ders_sayisi = max(len(dersler) for dersler in ogr_dersler.values())
            min_days_ogrenci = (max_ders_sayisi + max_gun - 1) // max_gun

        self.log(
            f"Mazeret ILP: {N} ders, "
            f"{G.number_of_edges()} çakışma kenarı, "
            f"{K_gun} oturum/gün, "
            f"toplam kapasite {toplam_kapasite} öğrenci/slot, "
            f"min gün (öğrenci çakışma) = {min_days_ogrenci}"
        )

        # Greedy renklendirme → slot üst sınırı; öğrenci günlük kısıtı için yeterli gün sağla
        greedy = nx.coloring.greedy_color(G, strategy="largest_first")
        K_greedy = (max(greedy.values()) + 1) if greedy else 1
        K = max(K_greedy, min_days_ogrenci * K_gun)

        # ──────────────────────────────────────────────
        # ILP
        # x[i][t] = 1  ⟺  ders i, slot t'ye atandı
        # y[t]    = 1  ⟺  slot t kullanıldı
        # Minimize Σ y[t]
        # ──────────────────────────────────────────────
        prob = LpProblem("mazeret_ilp", LpMinimize)
        x = [
            [LpVariable(f"x_{i}_{t}", cat=LpBinary) for t in range(K)]
            for i in range(N)
        ]
        y = [LpVariable(f"y_{t}", cat=LpBinary) for t in range(K)]

        prob += lpSum(y)

        for i in range(N):
            prob += lpSum(x[i][t] for t in range(K)) == 1

        for u, v in G.edges():
            for t in range(K):
                prob += x[u][t] + x[v][t] <= 1

        # Kapasite kısıtı: bir slottaki toplam öğrenci ≤ salon toplam kapasitesi.
        # Çakışma kısıtı sayesinde aynı slottaki dersler farklı öğrencilere ait,
        # dolayısıyla toplam = Σ ogrenci_sayisi[i] * x[i][t] doğrudan uygulanır.
        for t in range(K):
            prob += (
                lpSum(ogrenci_sayisi[i] * x[i][t] for i in range(N))
                <= toplam_kapasite
            )

        # u_gün[i][d] = 1 ⟺ ders i, gün d'de planlandı
        num_days = (K + K_gun - 1) // K_gun
        u_gun = {
            (i, d): LpVariable(f"ug_{i}_{d}", cat=LpBinary)
            for i in range(N)
            for d in range(num_days)
        }
        for i in range(N):
            for d in range(num_days):
                slots_in_day = [t for t in range(K) if t // K_gun == d]
                prob += u_gun[(i, d)] == lpSum(x[i][t] for t in slots_in_day)

        # Öğrenci bazlı günlük kısıt: bir öğrenci aynı günde en fazla max_gun oturuma girebilir.
        gunluk_kisit_sayisi = 0
        for dersler_seti in ogr_dersler.values():
            ders_idxs = sorted({ders_idx[d] for d in dersler_seti if d in ders_idx})
            if len(ders_idxs) <= max_gun:
                continue
            for d in range(num_days):
                prob += lpSum(u_gun[(i, d)] for i in ders_idxs) <= max_gun
                gunluk_kisit_sayisi += 1

        if gunluk_kisit_sayisi:
            self.log(
                f"  Günlük kısıt: öğrenci başına günde en fazla {max_gun} oturum — "
                f"{gunluk_kisit_sayisi} kısıt eklendi."
            )

        for t in range(K):
            for i in range(N):
                prob += y[t] >= x[i][t]

        # Slotları ardışık kullan: y[t] >= y[t+1]
        # Bu olmadan CBC boşluklu slotlar seçebilir; sıkıştırma sonrası ILP günleri
        # gerçek günlerle örtüşmez ve öğrenci günlük çakışma kısıtı anlamsız kalır.
        for t in range(K - 1):
            prob += y[t] >= y[t + 1]

        status = prob.solve(PULP_CBC_CMD(
            msg=0,
            timeLimit=self.config.get("TIME_LIMIT", 60),
        ))

        if prob.status != LpStatusOptimal:
            return False, f"ILP çözüm bulunamadı (CBC status={prob.status})."

        # Ders → slot atamasını çıkar
        ders_to_slot: dict[int, int] = {}
        for i in range(N):
            for t in range(K):
                if value(x[i][t]) is not None and value(x[i][t]) > 0.5:
                    ders_to_slot[i] = t
                    break

        # Kullanılan slotları GÜN SINIRLARINI KORUYARAK sıkıştır: önce hangi orijinal
        # günlerin kullanıldığını bul (boş günler atlanır), sonra her günün içindeki
        # kullanılan slotları o gün için sıralı oturum konumlarına eşle. Günler arası
        # düz bir sıkıştırma (t → sıra no) günlük kısıtın (öğrenci başına en fazla 2
        # oturum/gün) hesaba kattığı gün sınırlarını bozar — ILP bilerek bir günün
        # slotlarını boş bırakıp dersleri başka güne yaymış olabilir.
        gun_to_slotlar: dict[int, list[int]] = {}
        for t in sorted(set(ders_to_slot.values())):
            gun_to_slotlar.setdefault(t // K_gun, []).append(t)

        kullanilan_gunler = sorted(gun_to_slotlar.keys())
        toplam_gun = len(kullanilan_gunler)
        toplam_oturum = sum(len(v) for v in gun_to_slotlar.values())

        self.log(
            f"ILP tamamlandı: {toplam_oturum} oturum → {toplam_gun} gün."
        )

        # ──────────────────────────────────────────────
        # DB kayıtları: mevcut günleri sil, yeniden oluştur
        # ──────────────────────────────────────────────
        mazeret_sinav.gunler.all().delete()

        slot_to_oturum: dict[int, MazeretOturum] = {}  # orijinal slot t → MazeretOturum

        for day_idx, orijinal_gun in enumerate(kullanilan_gunler):
            tarih = _nth_is_gunu(baslangic_tarih, day_idx, tatil)
            gun = MazeretGun.objects.create(mazeret_sinav=mazeret_sinav, tarih=tarih)

            for oturum_no, t in enumerate(gun_to_slotlar[orijinal_gun], start=1):
                slot_in_day = t % K_gun

                ders_in_slot = [DERSLER[i] for i, tt in ders_to_slot.items() if tt == t]
                sinav_turu = (
                    "Uygulama"
                    if any(d[1] == "Uygulama" for d in ders_in_slot)
                    else "Yazili"
                )

                saat_bas = _str_to_time(saatler[slot_in_day])
                saat_bit = _time_add_dk(saat_bas, OTURUM_SURESI_DK)

                slot_to_oturum[t] = MazeretOturum.objects.create(
                    gun=gun,
                    oturum_no=oturum_no,
                    saat_baslangic=saat_bas,
                    saat_bitis=saat_bit,
                    sinav_turu=sinav_turu,
                )

        # MazeretOturumDers
        atamalar = [
            MazeretOturumDers(
                oturum=slot_to_oturum[ders_to_slot[i]],
                ders_id=ders_key_to_id[DERSLER[i]],
                sinav_turu=DERSLER[i][1],
            )
            for i in range(N)
        ]
        MazeretOturumDers.objects.bulk_create(atamalar, ignore_conflicts=True)

        return True, (
            f"{N} ders, {toplam_oturum} oturum ({toplam_gun} gün) — çakışmasız dağıtıldı."
        )
