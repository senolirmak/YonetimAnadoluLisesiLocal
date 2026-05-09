"""
Mazeret Sınav ILP Planlama Servisi

MazeretOgrenci (belge_teslim=True, uygun) kayıtlarından çakışmasız mazeret
takvimi üretir. Çakışma kuralı: aynı öğrencinin iki sınavı aynı slotta olamaz.
Uygulama dersleri exclusive slot alır (başka hiçbir ders aynı slotta olamaz).

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
                    ogrenci__okulno__in=_mo_okulno_ints
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

        # Öğrenci-paylaşan alt graf: günlük çakışma için minimum gün sayısını belirler
        G_student = nx.Graph()
        G_student.add_nodes_from(range(N))
        for ia, ib in student_pairs:
            G_student.add_edge(ia, ib)
        student_greedy = nx.coloring.greedy_color(G_student, strategy="largest_first")
        min_days_ogrenci = (max(student_greedy.values()) + 1) if student_greedy else 1

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

        # Öğrenci bazlı günlük çakışma kısıtı:
        # Ortak öğrencisi olan iki dersin aynı güne atanması engellenir.
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

        for ia, ib in student_pairs:
            for d in range(num_days):
                prob += u_gun[(ia, d)] + u_gun[(ib, d)] <= 1

        if student_pairs:
            self.log(
                f"  Günlük çakışma kısıtı: {len(student_pairs)} öğrenci-paylaşan ders çifti, "
                f"{num_days} gün × çift = {len(student_pairs) * num_days} kısıt eklendi."
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

        # Kullanılan slotları sıralı konumlara sıkıştır
        kullanilan = sorted(set(ders_to_slot.values()))
        slot_konum = {t: idx for idx, t in enumerate(kullanilan)}
        ders_to_konum = {i: slot_konum[ders_to_slot[i]] for i in range(N)}

        toplam_oturum = len(kullanilan)
        toplam_gun = (toplam_oturum - 1) // K_gun + 1

        self.log(
            f"ILP tamamlandı: {toplam_oturum} oturum → {toplam_gun} gün."
        )

        # ──────────────────────────────────────────────
        # DB kayıtları: mevcut günleri sil, yeniden oluştur
        # ──────────────────────────────────────────────
        mazeret_sinav.gunler.all().delete()

        gun_objects: dict[int, MazeretGun] = {}
        slot_to_oturum: dict[int, MazeretOturum] = {}
        oturum_sayaci: dict[int, int] = {}  # day_idx → oturum_no

        for konum in range(toplam_oturum):
            day_idx = konum // K_gun
            slot_in_day = konum % K_gun

            if day_idx not in gun_objects:
                tarih = _nth_is_gunu(baslangic_tarih, day_idx, tatil)
                gun_objects[day_idx] = MazeretGun.objects.create(
                    mazeret_sinav=mazeret_sinav,
                    tarih=tarih,
                )
                oturum_sayaci[day_idx] = 0

            gun = gun_objects[day_idx]
            oturum_sayaci[day_idx] += 1

            # Bu konumdaki derslerin sinav_turu'nu belirle
            ders_in_konum = [DERSLER[i] for i, k in ders_to_konum.items() if k == konum]
            sinav_turu = (
                "Uygulama"
                if any(d[1] == "Uygulama" for d in ders_in_konum)
                else "Yazili"
            )

            saat_bas = _str_to_time(saatler[slot_in_day])
            saat_bit = _time_add_dk(saat_bas, OTURUM_SURESI_DK)

            slot_to_oturum[konum] = MazeretOturum.objects.create(
                gun=gun,
                oturum_no=oturum_sayaci[day_idx],
                saat_baslangic=saat_bas,
                saat_bitis=saat_bit,
                sinav_turu=sinav_turu,
            )

        # MazeretOturumDers
        atamalar = [
            MazeretOturumDers(
                oturum=slot_to_oturum[ders_to_konum[i]],
                ders_id=ders_key_to_id[DERSLER[i]],
                sinav_turu=DERSLER[i][1],
            )
            for i in range(N)
        ]
        MazeretOturumDers.objects.bulk_create(atamalar, ignore_conflicts=True)

        return True, (
            f"{N} ders, {toplam_oturum} oturum ({toplam_gun} gün) — çakışmasız dağıtıldı."
        )
