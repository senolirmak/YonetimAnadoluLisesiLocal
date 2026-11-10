"""Ders doldurma dağıtımı: devamsız öğretmenlerin boş derslerini nöbetçilere atar.

Problem en düşük maliyetli akış (min-cost flow) olarak kesin çözülür:

    kaynak → ders → (nöbetçi, saat) → nöbetçi → nöbetçinin k. görevi → hedef
               └──────────────── atanamadı ────────────────────────────┘

- Her ders tek nöbetçiye, her nöbetçi bir saatte tek derse, günde en fazla
  ``max_shifts`` derse atanır; nöbetçi yalnızca boş (dersi/devamsızlığı olmayan)
  saatlerinde ders alır.
- Öncelik sırası (maliyetlerle kesin olarak sağlanır):
    1. Mümkün olan en fazla ders doldurulur ("atanamadı" kenarı her zaman pahalıdır).
    2. Dönem boyu denge: Σ (geçmiş toplam + bugünkü görev)² en aza indirilir. Ek bir
       görevin maliyeti öğretmenin yüküyle arttığından ders, yükü en az olan uygun
       nöbetçiye gider; yükü eşit olanlar arasında günlük iş paylaştırılır.
    3. Eşitlik bozucu olarak öğretmen, son doldurduğu sınıfa art arda verilmez.
"""

from collections import defaultdict
from typing import Any

import networkx as nx


class AdvancedNobetDagitim:
    """Ders doldurma dağıtımı (bkz. modül açıklaması)."""

    def __init__(self, max_shifts: int = 2) -> None:
        self.penalty_weights = {
            "unassigned": 1_000_000,  # Atanamayan ders (en yüksek öncelik)
            "conflict": 500_000,  # Aynı saatte iki ders (çözücü üretmez; denetim için)
            "overload": 200_000,  # Günlük sınır aşımı (çözücü üretmez; denetim için)
            "denge": 300,  # Dönem boyu denge, bkz. calculate_penalty
            "same_location": 200,  # Aynı sınıfa art arda atama
        }
        self.max_shifts = max_shifts
        self.teacher_stats: dict[int, dict[str, Any]] = {}

    def set_teacher_statistics(self, stats_dict: dict[int, dict[str, Any]] | None) -> None:
        """``{ogretmen_id: {"toplam_nobet": int, "son_nobet_yeri": str, ...}}`` (NobetIstatistik)."""
        self.teacher_stats = stats_dict or {}

    # ======================================================
    # 🔹 Ana fonksiyon
    # ======================================================
    def optimize(
        self,
        available_teachers: list[dict[str, Any]],
        absent_teachers: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """``available_teachers``: ``[{"ogretmen_id", "dersleri": {saat: sınıf}}]`` —
        ``dersleri`` nöbetçinin dolu saatleri. ``absent_teachers``: aynı biçimde,
        ``dersleri`` doldurulacak boş dersler."""
        self.availability = self.prepare_availability(available_teachers)
        self.absent_classes = self.flatten_absent(absent_teachers)
        self.teachers = available_teachers
        self.teacher_ids = [t["ogretmen_id"] for t in available_teachers]
        return self.format_solution(self._akis_ile_coz())

    def _akis_ile_coz(self) -> dict[str, Any]:
        solution: dict[str, Any] = {
            "assignments": [],
            "teacher_counts": defaultdict(int),
            "teacher_schedule": defaultdict(set),
        }
        n = len(self.absent_classes)
        if not n or not self.teacher_ids or self.max_shifts <= 0:
            return solution

        W = self.penalty_weights["denge"]
        S = self.penalty_weights["same_location"]
        gecmis = self._goreli_gecmis()
        en_pahali_gorev = W * (2 * (max(gecmis.values()) + self.max_shifts) - 1) + S
        # Bir dersi daha doldurmak, diğer tüm atamaları en pahalı hâle getirse bile kârlı olmalı
        atanamadi = (n + 1) * (en_pahali_gorev + 1)

        G = nx.DiGraph()
        G.add_node("kaynak", demand=-n)
        G.add_node("hedef", demand=n)
        for i, ders in enumerate(self.absent_classes):
            saat = ders["hour"]
            G.add_edge("kaynak", ("ders", i), capacity=1, weight=0)
            G.add_edge(("ders", i), "hedef", capacity=1, weight=atanamadi)
            for t_id in self.teacher_ids:
                if not self.availability[t_id].get(saat):
                    continue
                son_yer = (self.teacher_stats.get(t_id) or {}).get("son_nobet_yeri")
                G.add_edge(
                    ("ders", i), ("saat", t_id, saat),
                    capacity=1, weight=S if son_yer == ders["class"] else 0,
                )
                G.add_edge(("saat", t_id, saat), ("nobetci", t_id), capacity=1, weight=0)
        for t_id in self.teacher_ids:
            if ("nobetci", t_id) not in G:
                continue
            g = gecmis[t_id]
            for k in range(1, self.max_shifts + 1):
                # k. görevin ek maliyeti: W·((g+k)² − (g+k−1)²) — artan (dışbükey)
                G.add_edge(("nobetci", t_id), ("gorev", t_id, k), capacity=1, weight=W * (2 * (g + k) - 1))
                G.add_edge(("gorev", t_id, k), "hedef", capacity=1, weight=0)

        akis = nx.min_cost_flow(G)

        for i, ders in enumerate(self.absent_classes):
            for hedef, miktar in akis[("ders", i)].items():
                if miktar and hedef != "hedef":
                    _, t_id, saat = hedef
                    solution["assignments"].append(
                        {
                            "hour": saat,
                            "class": ders["class"],
                            "teacher_id": t_id,
                            "absent_teacher_id": ders["absent_teacher_id"],
                        }
                    )
                    solution["teacher_counts"][t_id] += 1
                    solution["teacher_schedule"][t_id].add(saat)
        return solution

    # ======================================================
    # 🔹 Ceza (çözümün değerlendirilmesi; çözücünün en aza indirdiği büyüklük)
    # ======================================================
    def calculate_penalty(self, solution: dict[str, Any]) -> float:
        teacher_counts = solution["teacher_counts"]
        # `.get`: defaultdict'e yan etkili sıfır-kayıt eklenmesin
        counts = [teacher_counts.get(t_id, 0) for t_id in self.teacher_ids]
        penalty = 0

        gecmis = self._goreli_gecmis()
        penalty += self.penalty_weights["denge"] * sum(
            (gecmis[t_id] + c) ** 2 for t_id, c in zip(self.teacher_ids, counts)
        )
        penalty += (len(self.absent_classes) - len(solution["assignments"])) * self.penalty_weights[
            "unassigned"
        ]
        penalty += sum(max(0, c - self.max_shifts) for c in counts) * self.penalty_weights["overload"]

        conflicts = 0
        teacher_hours: dict[int, set] = defaultdict(set)
        for a in solution["assignments"]:
            if a["hour"] in teacher_hours[a["teacher_id"]]:
                conflicts += 1
            teacher_hours[a["teacher_id"]].add(a["hour"])
        penalty += conflicts * self.penalty_weights["conflict"]

        for a in solution["assignments"]:
            stats = self.teacher_stats.get(a["teacher_id"])
            if stats and stats.get("son_nobet_yeri") == a["class"]:
                penalty += self.penalty_weights["same_location"]
        return penalty

    # ======================================================
    # 🔹 Yardımcı fonksiyonlar
    # ======================================================
    def _gecmis_yuk(self, t_id: int) -> int:
        """Öğretmenin bu dönemde (arşivlenmemiş) doldurduğu toplam ders sayısı."""
        stat = self.teacher_stats.get(t_id) or {}
        return int(stat.get("toplam_nobet", stat.get("agirlikli_puan", 0)) or 0)

    def _goreli_gecmis(self) -> dict[int, int]:
        """Geçmiş yükler, bugünkü nöbetçilerin en düşüğüne göre (farklar değişmez, sayılar küçük kalır)."""
        yuk = {t_id: self._gecmis_yuk(t_id) for t_id in self.teacher_ids}
        taban = min(yuk.values(), default=0)
        return {t_id: y - taban for t_id, y in yuk.items()}

    def prepare_availability(self, teachers: list[dict[str, Any]]) -> dict[int, dict[int, bool]]:
        availability: dict[int, dict[int, bool]] = {}
        for t in teachers:
            busy = set(t["dersleri"].keys())
            availability[t["ogretmen_id"]] = {h: (h not in busy) for h in range(1, 9)}
        return availability

    def flatten_absent(self, absent_teachers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {"hour": int(h), "class": c, "absent_teacher_id": t["ogretmen_id"]}
            for t in absent_teachers
            for h, c in t["dersleri"].items()
        ]

    def format_solution(self, solution: dict[str, Any]) -> dict[str, Any]:
        atananlar = {(a["hour"], a["class"], a["absent_teacher_id"]) for a in solution["assignments"]}
        unassigned = [
            {"hour": c["hour"], "class": c["class"], "absent_teacher_id": c["absent_teacher_id"]}
            for c in self.absent_classes
            if (c["hour"], c["class"], c["absent_teacher_id"]) not in atananlar
        ]
        return {
            "assignments": solution["assignments"],
            "unassigned": unassigned,
            "teacher_counts": dict(solution["teacher_counts"]),
            "teacher_schedule": {k: list(v) for k, v in solution["teacher_schedule"].items()},
            "penalty": self.calculate_penalty(solution),
        }
