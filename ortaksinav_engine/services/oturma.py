# -*- coding: utf-8 -*-
"""
OturmaPlanService – Adim 5

Takvim ve Ogrenci tablolarindan bir oturumun ogrencilerini alarak
Kelebek karisik oturma duzeni olusturur, OturmaPlani tablosuna kaydeder
ve Excel ciktisi uretir.

Ozel metodlar:
  _build_layout   – 6x6 matris icin backtracking + greedy yerlesim
  _place_matrix   – 6x6 matrisi 3 blok x 6 sira x 2 koltuk yapisina donusturur
  _write_excel    – oturma plani Excel dosyasini olusturur
  generate_oturum – tek oturum icin plani uretir
  generate_all    – takvimdeki tum oturumlar icin calistirir
"""

import re
import random
from datetime import datetime

import pandas as pd
from django.db.models import F

from ortaksinav_engine.services.base import BaseService
from ortaksinav_engine.utils import normalize_sube_cell


class OturmaPlanService(BaseService):
    """Kelebek oturma plani olusturan servis."""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate_all(self):
        from sinav.models import Takvim, SinavBilgisi, TakvimUretim

        self.log("\nAdim 5: Tum oturumlar icin oturma plani olusturuluyor...\n")
        aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
        aktif_uretim = (
            TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
            if aktif_sinav else None
        )
        unique_sessions = (
            Takvim.objects
            .filter(uretim=aktif_uretim)
            .values_list("tarih", "saat", "oturum")
            .distinct()
            .order_by("tarih", "saat", "oturum")
        )
        if not unique_sessions.exists():
            self.log("DB'de takvim yok. Once Adim 4'u calistirin.")
            return

        self.log(f"Toplam {unique_sessions.count()} oturum bulundu.\n")
        for tarih, saat, oturum in unique_sessions:
            try:
                self.log("────────────────────────────────────────────")
                self.log(f"{tarih} {saat} (Oturum {oturum}) isleniyor...")
                self.generate_oturum(str(tarih), str(saat), int(oturum), aktif_sinav, aktif_uretim)
            except Exception as e:
                self.log(f"HATA {tarih} {saat} (Oturum {oturum}): {e}")

        self.log("\nTum oturumlar icin oturma plani tamamlandi.\n")

    def generate_selected(self, sessions: list):
        """Yalnızca verilen oturumlar için oturma planı oluşturur.

        sessions: [{"tarih": "YYYY-MM-DD", "saat": "HH:MM", "oturum": int}, ...]
        """
        from sinav.models import SinavBilgisi, TakvimUretim

        aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
        aktif_uretim = (
            TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
            if aktif_sinav else None
        )
        self.log(f"\nSecili {len(sessions)} oturum icin oturma plani olusturuluyor...\n")
        for s in sessions:
            tarih  = s.get("tarih", "")
            saat   = s.get("saat", "")
            oturum = int(s.get("oturum", 1))
            try:
                self.log("────────────────────────────────────────────")
                self.log(f"{tarih} {saat} (Oturum {oturum}) isleniyor...")
                self.generate_oturum(tarih, saat, oturum, aktif_sinav, aktif_uretim)
            except Exception as e:
                self.log(f"HATA {tarih} {saat} (Oturum {oturum}): {e}")
        self.log("\nSecili oturumlar tamamlandi.\n")

    def generate_oturum(self, tarih: str, saat: str, oturum: int, aktif_sinav=None, aktif_uretim=None):
        from ogrenci.models import Ogrenci as OgrenciModel
        from sinav.models import Takvim, OturmaPlani

        self.log(f"\nOturum yerlesimi: {tarih} {saat} (Oturum {oturum})")
        baslik = f"{tarih} {saat} (Oturum {oturum})"

        if aktif_uretim is not None:
            takvim_qs = Takvim.objects.filter(tarih=tarih, saat=saat, uretim=aktif_uretim)
        else:
            takvim_qs = Takvim.objects.filter(tarih=tarih, saat=saat, sinav=aktif_sinav)
        if not takvim_qs.exists():
            self.log("Belirtilen tarih/saat icin takvim verisi bulunamadi.")
            return

        subeler = sorted(set(
            s for t in takvim_qs for s in normalize_sube_cell(t.subeler)
        ))
        if not subeler:
            self.log("Bu oturumda sube bulunamadi.")
            return

        salon_adlari = [f"Salon-{s.replace('/', '_')}" for s in subeler]
        sube_to_ders = {
            s: (t.ders_adi or (t.ders.ders_adi if t.ders else ""))
            for t in takvim_qs.select_related("ders")
            for s in normalize_sube_cell(t.subeler)
        }

        df_o = pd.DataFrame(OgrenciModel.objects.values(
            "okulno", "adi", "soyadi", "cinsiyet", "sinif", "sube",
        ))
        if not df_o.empty:
            df_o["sinifsube"] = df_o["sinif"].astype(str) + "/" + df_o["sube"].astype(str)
        if df_o.empty:
            self.log("DB'de ogrenci yok. Adim 1'i calistirin.")
            return

        df_o["sinifsube"] = df_o["sinifsube"].astype(str).str.upper().str.replace(" ", "")
        df_o["ders"] = df_o["sinifsube"].map(sube_to_ders).fillna("Diger")
        df_o = df_o[df_o["ders"] != "Diger"].copy()
        if df_o.empty:
            self.log("Bu oturumda sinava girecek ogrenci bulunamadi.")
            return

        ogr = df_o.sample(frac=1, random_state=42).reset_index(drop=True)
        salon_map = {name: [] for name in salon_adlari}
        for i, (_, row) in enumerate(ogr.iterrows()):
            salon_map[salon_adlari[i % len(salon_adlari)]].append(row.to_dict())

        salon_grids = {}
        for salon, lst in salon_map.items():
            df_salon = pd.DataFrame(lst)
            for col in ("ders", "sinif"):
                if col not in df_salon.columns:
                    df_salon[col] = ""
            salon_grids[salon] = self._place_matrix(df_salon)

        # DB kaydet
        tarih_date = datetime.strptime(tarih, "%Y-%m-%d").date()
        OturmaPlani.objects.filter(
            tarih=tarih_date, saat=saat, oturum=oturum, uretim=aktif_uretim
        ).delete()

        # OturmaUretim kaydı: bu oturum için üretim tarihi ve TakvimUretim FK
        if aktif_uretim is not None:
            from sinav.models import OturmaUretim as _OU
            _OU.objects.filter(
                takvim_uretim=aktif_uretim, tarih=tarih_date, saat=saat, oturum=oturum
            ).delete()
            _OU.objects.create(
                takvim_uretim=aktif_uretim, tarih=tarih_date, saat=saat, oturum=oturum
            )

        op_records = []
        for salon, grid in salon_grids.items():
            seat_number = 1
            for block in grid:
                for row_cells in block:
                    for s in row_cells:
                        if isinstance(s, dict):
                            adi = str(s.get("adi") or s.get("ad") or "")
                            soyadi = str(s.get("soyadi") or s.get("soyad") or "")
                            op_records.append(OturmaPlani(
                                sinav=aktif_sinav,
                                uretim=aktif_uretim,
                                tarih=tarih_date, saat=saat, oturum=oturum,
                                salon=salon, sira_no=seat_number,
                                okulno=str(s.get("okulno") or ""),
                                sinifsube=str(s.get("sinifsube") or ""),
                                adi_soyadi=f"{adi} {soyadi}".strip(),
                                ders_adi=str(s.get("ders") or ""),
                            ))
                        seat_number += 1
        OturmaPlani.objects.bulk_create(op_records)

        toplam = len(df_o)
        salon_sayisi = len(salon_adlari)
        ortalama = round(toplam / salon_sayisi, 1) if salon_sayisi else 0
        self.log(f"{tarih} {saat} – {salon_sayisi} salon, {toplam} ogrenci ({ortalama} ort.)")

    # ------------------------------------------------------------------
    # Ozel yardimci metodlar
    # ------------------------------------------------------------------

    def _place_matrix(self, df_students):
        ROWS, COLS_PER_BLOCK, BLOCKS = 6, 2, 3
        TOTAL_COLS = COLS_PER_BLOCK * BLOCKS

        def get_level(ogr):
            seviye = ogr.get("sinif", None)
            if seviye not in (None, ""):
                try:
                    return int(seviye)
                except Exception:
                    pass
            sinifsube = str(ogr.get("sinifsube", "") or "")
            m = re.search(r"(\d+)", sinifsube)
            if m:
                try:
                    return int(m.group(1))
                except Exception:
                    pass
            return None

        groups = {}
        for _, row in df_students.iterrows():
            ogr = row.to_dict()
            k = (ogr.get("ders", "") or "", get_level(ogr))
            groups.setdefault(k, []).append(ogr)

        exam_counts = {k: len(v) for k, v in groups.items()}
        layout = self._build_layout(exam_counts, rows=ROWS, cols=TOTAL_COLS)

        exam_positions = {k: [] for k in groups.keys()}
        for r in range(ROWS):
            for c in range(TOTAL_COLS):
                ek = layout[r][c]
                if ek in exam_positions:
                    exam_positions[ek].append((r, c))

        seat_owner = [[None for _ in range(TOTAL_COLS)] for _ in range(ROWS)]
        for ek, ogr_list in groups.items():
            pos_list = exam_positions.get(ek, [])
            random.shuffle(ogr_list)
            for ogr, (r, c) in zip(ogr_list, pos_list):
                seat_owner[r][c] = ogr

        grid = [
            [[None for _ in range(COLS_PER_BLOCK)] for _ in range(ROWS)]
            for _ in range(BLOCKS)
        ]
        for r in range(ROWS):
            for c in range(TOTAL_COLS):
                ogr = seat_owner[r][c]
                if ogr is None:
                    continue
                block = c // COLS_PER_BLOCK
                col_in_block = c % COLS_PER_BLOCK
                grid[block][r][col_in_block] = ogr
        return grid

    @staticmethod
    def _build_layout(exam_counts, rows=6, cols=6, max_bt_tries=0):
        EMPTY_KEY = ("__EMPTY__", None)
        total_students = sum(exam_counts.values())
        TOTAL_SLOTS = rows * cols

        if total_students < TOTAL_SLOTS:
            exam_counts = exam_counts.copy()
            exam_counts[EMPTY_KEY] = TOTAL_SLOTS - total_students

        exam_list = sorted(exam_counts.items(), key=lambda kv: -kv[1])
        exam_keys = [k for k, _ in exam_list]
        positions = [(r, c) for r in range(rows) for c in range(cols)]

        def is_adjacent_forbidden(layout, r, c, exam_key):
            if exam_key == EMPTY_KEY:
                return False
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < cols and (c // 2) == (nc // 2):
                    if layout[r][nc] == exam_key:
                        return True
            for dr in (-1, 1):
                nr = r + dr
                if 0 <= nr < rows:
                    if layout[nr][c] == exam_key:
                        return True
            return False

        # Backtracking
        for _ in range(max_bt_tries):
            layout = [[None] * cols for _ in range(rows)]
            remaining = dict(exam_counts)
            local_keys = exam_keys[:]
            random.shuffle(local_keys)
            local_positions = positions[:]
            random.shuffle(local_positions)

            def backtrack(pos_idx):
                if pos_idx >= len(local_positions):
                    return all(v == 0 for v in remaining.values())
                r, c = local_positions[pos_idx]
                for ek in local_keys:
                    if remaining[ek] <= 0:
                        continue
                    if is_adjacent_forbidden(layout, r, c, ek):
                        continue
                    layout[r][c] = ek
                    remaining[ek] -= 1
                    if backtrack(pos_idx + 1):
                        return True
                    layout[r][c] = None
                    remaining[ek] += 1
                return False

            if backtrack(0):
                return layout

        # Greedy fallback
        layout = [[None] * cols for _ in range(rows)]
        remaining = dict(exam_counts)

        def conflict_score(layout, r, c, exam_key):
            if exam_key == EMPTY_KEY:
                return 0
            score = 0
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < cols and (c // 2) == (nc // 2):
                    if layout[r][nc] == exam_key:
                        score += 1
            for dr in (-1, 1):
                nr = r + dr
                if 0 <= nr < rows:
                    if layout[nr][c] == exam_key:
                        score += 1
            return score

        shuffled = positions[:]
        random.shuffle(shuffled)
        for r, c in shuffled:
            best_key, best_score = None, None
            for ek in exam_keys:
                if remaining.get(ek, 0) <= 0:
                    continue
                score = conflict_score(layout, r, c, ek)
                if best_score is None or score < best_score:
                    best_score = score
                    best_key = ek
                    if best_score == 0:
                        break
            if best_key is None:
                best_key = EMPTY_KEY
            layout[r][c] = best_key
            remaining[best_key] = remaining.get(best_key, 0) - 1

        return layout

