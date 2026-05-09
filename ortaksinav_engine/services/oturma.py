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

import hashlib
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
                import traceback as _tb
                self.log(f"HATA {tarih} {saat} (Oturum {oturum}): {e}")
                self.log(_tb.format_exc())
        self.log("\nSecili oturumlar tamamlandi.\n")

    def generate_oturum(self, tarih: str, saat: str, oturum: int, aktif_sinav=None, aktif_uretim=None):
        from ogrenci.models import Ogrenci as OgrenciModel, OgrenciMuaf
        from sinav.models import Takvim, OturmaPlani

        self.log(f"\nOturum yerlesimi: {tarih} {saat} (Oturum {oturum})")
        baslik = f"{tarih} {saat} (Oturum {oturum})"

        # Yeniden üretimde eski kayıtları temizle (aynı uretim + tarih + saat + oturum)
        if aktif_uretim is not None:
            silinen, _ = OturmaPlani.objects.filter(
                uretim=aktif_uretim, tarih=tarih, saat=saat, oturum=oturum
            ).delete()
            if silinen:
                self.log(f"Önceki üretimden {silinen} kayıt silindi.")
            takvim_qs = Takvim.objects.filter(tarih=tarih, saat=saat, uretim=aktif_uretim).select_related("ders_saati")
        else:
            takvim_qs = Takvim.objects.filter(tarih=tarih, saat=saat, sinav=aktif_sinav).select_related("ders_saati")
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
            s: t.ders_tam_adi
            for t in takvim_qs.select_related("ders")
            for s in normalize_sube_cell(t.subeler)
        }

        # Özel durum 1: Sürekli devamsız öğrencileri hiçbir sınavda oturma planına alma
        sureksiz_set = set(
            OgrenciModel.objects.filter(sureksiz_devamsiz=True)
            .values_list("okulno", flat=True)
        )

        df_o = pd.DataFrame(OgrenciModel.objects.values(
            "okulno", "adi", "soyadi", "cinsiyet", "sinif", "sube",
        ))
        if not df_o.empty:
            df_o["sinifsube"] = df_o["sinif"].astype(str) + "/" + df_o["sube"].astype(str)
        if df_o.empty:
            self.log("DB'de ogrenci yok. Adim 1'i calistirin.")
            return

        # Sürekli devamsız filtresi
        if sureksiz_set:
            onceki = len(df_o)
            df_o = df_o[~df_o["okulno"].isin(sureksiz_set)].copy()
            hariç_sureksiz = onceki - len(df_o)
            if hariç_sureksiz:
                self.log(f"  Özel durum: {hariç_sureksiz} sürekli devamsız öğrenci hariç tutuldu.")

        df_o["sinifsube"] = df_o["sinifsube"].astype(str).str.upper().str.replace(" ", "")
        df_o["ders"] = df_o["sinifsube"].map(sube_to_ders).fillna("Diger")
        df_o = df_o[df_o["ders"] != "Diger"].copy()
        if df_o.empty:
            self.log("Bu oturumda sinava girecek ogrenci bulunamadi.")
            return

        # Özel durum 2: Muaf öğrencileri bu oturumun dersi için hariç tut
        # ders_tam_adi → base_adi (suffix'i çıkar): "Matematik (Yazili)" → "Matematik"
        _sfx_re = re.compile(r'^(.*?)\s+\((Yazili|Uygulama)\)$')

        def _base_ders(adi: str) -> str:
            m = _sfx_re.match(adi or "")
            return m.group(1).strip() if m else (adi or "")

        oturum_base_ders = {_base_ders(v) for v in sube_to_ders.values()}
        muaf_pairs: set[tuple] = set(
            OgrenciMuaf.objects.filter(ders__ders_adi__in=oturum_base_ders)
            .values_list("ogrenci__okulno", "ders__ders_adi")
        )
        if muaf_pairs:
            df_o["_ders_base"] = df_o["ders"].apply(_base_ders)
            onceki = len(df_o)
            df_o = df_o[
                ~df_o.apply(
                    lambda r: (r["okulno"], r["_ders_base"]) in muaf_pairs,
                    axis=1,
                )
            ].copy()
            df_o = df_o.drop(columns=["_ders_base"])
            hariç_muaf = onceki - len(df_o)
            if hariç_muaf:
                self.log(f"  Özel durum: {hariç_muaf} muaf öğrenci bu oturum için hariç tutuldu.")

        if df_o.empty:
            self.log("Bu oturumda sinava girecek ogrenci bulunamadi (ozel durumlar sonrasi).")
            return

        kelebek = self.config.get("KELEBEK_DAGITIM", True)
        _seed = int(hashlib.md5(f"{tarih}{saat}{oturum}".encode()).hexdigest(), 16) % (2 ** 31)
        ogr = df_o.sample(frac=1, random_state=_seed).reset_index(drop=True)
        salon_map = {name: [] for name in salon_adlari}
        n_salons = len(salon_adlari)
        SALON_KAPASITE = 36  # 3 blok × 6 sıra × 2 koltuk

        if kelebek:
            # Kademe 2: Her sınav grubu kendi içinde salonlara orantılı dağıtılır.
            # Round-robin (tüm öğrenci karışık) yerine per-grup round-robin:
            # her salona her gruptan floor ya da ceil kadar düşer → garantili denge.
            groups_by_ders: dict[str, list] = {}
            for _, row in ogr.iterrows():
                groups_by_ders.setdefault(row["ders"], []).append(row.to_dict())

            for students in groups_by_ders.values():
                for i, student in enumerate(students):
                    salon_map[salon_adlari[i % n_salons]].append(student)

            for salon, lst in salon_map.items():
                bos = SALON_KAPASITE - len(lst)
                self.log(
                    f"  {salon}: {len(lst)} öğrenci, {bos} boş koltuk "
                    f"(doluluk %{100 * len(lst) // SALON_KAPASITE})"
                )
        else:
            # Kelebek yok: her öğrenci kendi şube salonuna gider.
            self.log("Kelebek dağılımı kapalı: her sınıf kendi salonunda.")
            for _, row in ogr.iterrows():
                sinifsube = str(row.get("sinifsube", "")).upper().replace(" ", "")
                salon_key = f"Salon-{sinifsube.replace('/', '_')}"
                if salon_key in salon_map:
                    salon_map[salon_key].append(row.to_dict())

        salon_grids = {}
        for salon, lst in salon_map.items():
            if not lst:
                continue
            if kelebek:
                df_salon = pd.DataFrame(lst)
                for col in ("ders", "sinif"):
                    if col not in df_salon.columns:
                        df_salon[col] = ""
                salon_grids[salon] = self._place_matrix(df_salon)
            else:
                salon_grids[salon] = self._simple_grid(lst)

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

        # Salon → gözetmen: sınav saatinde o salonun ders programındaki öğretmen
        from okul.models import SinifSube as _SS
        from ortaksinav_engine.utils import salon_gozetmen_bul
        ss_map = {}
        for sube_str in subeler:
            parts = sube_str.split("/")
            if len(parts) == 2:
                try:
                    ss = _SS.objects.filter(sinif=int(parts[0]), sube=parts[1]).first()
                except (ValueError, TypeError):
                    ss = None
                if ss:
                    ss_map[f"Salon-{sube_str.replace('/', '_')}"] = ss
        ders_saati_obj = takvim_qs.first().ders_saati
        salon_gozetmen = salon_gozetmen_bul(tarih_date, ders_saati_obj or saat, ss_map)

        # Sıra numaralandırması: pdf_rapor.oturum_plani_pdf ile birebir aynı seat_map
        # Grup 1→1-12, Grup 2→13-24, Grup 3→25-36
        # Çift satır sol→sağ, tek satır sağ→sol (S-şekli)
        COLS_PER_BLOCK = 2

        op_records = []
        for salon, grid in salon_grids.items():
            gozetmen_obj = salon_gozetmen.get(salon)
            salon_ss = ss_map.get(salon)
            n_blocks   = len(grid)
            n_rows_blk = len(grid[0]) if grid else 6

            seat_map = {}
            sn = 1
            for b in range(n_blocks):
                for r in range(n_rows_blk):
                    for c in ([0, 1] if r % 2 == 0 else [1, 0]):
                        seat_map[(b, r, c)] = sn
                        sn += 1

            for block_idx, block in enumerate(grid):
                for row_idx, row_cells in enumerate(block):
                    for col_idx, s in enumerate(row_cells):
                        seat_number = seat_map[(block_idx, row_idx, col_idx)]
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
                                gozetmen_fk=gozetmen_obj,
                                salon_sinif_sube=salon_ss,
                            ))
        OturmaPlani.objects.bulk_create(op_records)

        toplam = len(df_o)
        salon_sayisi = len(salon_adlari)
        ortalama = round(toplam / salon_sayisi, 1) if salon_sayisi else 0
        self.log(f"{tarih} {saat} – {salon_sayisi} salon, {toplam} ogrenci ({ortalama} ort.)")

    # ------------------------------------------------------------------
    # Ozel yardimci metodlar
    # ------------------------------------------------------------------

    def _simple_grid(self, lst: list) -> list:
        """Kelebek olmayan mod: öğrencileri sıra sıra, blok blok yerleştirir."""
        ROWS, COLS_PER_BLOCK, BLOCKS = 6, 2, 3
        grid = [
            [[None] * COLS_PER_BLOCK for _ in range(ROWS)]
            for _ in range(BLOCKS)
        ]
        idx = 0
        for b in range(BLOCKS):
            for r in range(ROWS):
                for c in range(COLS_PER_BLOCK):
                    if idx < len(lst):
                        grid[b][r][c] = lst[idx] if isinstance(lst[idx], dict) else lst[idx].to_dict()
                        idx += 1
        return grid

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
    def _build_layout(exam_counts, rows=6, cols=6):
        """
        Üç fazlı yerleşim algoritması.

        Faz 1 (Stride deseni):
            Boş koltuklar grid'e düzenli aralıklarla yayılır; tampon görevi görür.

        Faz 2 (MRV greedy):
            En kısıtlı konuma önce ata (Minimum Remaining Values).
            exam_key = (ders, seviye) → aynı ders+seviye komşu olamaz.
            Çakışmasız seçenek yoksa en az çakışan grup atanır.

        Faz 3 (Takas onarımı):
            Kalan komşu çakışmalarını yerel ikili takasla gider.
        """
        EMPTY_KEY = ("__EMPTY__", None)
        total_students = sum(exam_counts.values())
        TOTAL_SLOTS = rows * cols

        if total_students == 0:
            return [[EMPTY_KEY] * cols for _ in range(rows)]

        # ── Faz 1: Stride tabanlı dolu konum belirleme ──────────────────────
        if total_students >= TOTAL_SLOTS:
            occupied_indices = list(range(TOTAL_SLOTS))
        else:
            occupied_indices = [
                i * TOTAL_SLOTS // total_students for i in range(total_students)
            ]

        all_positions = [(r, c) for r in range(rows) for c in range(cols)]
        occupied_list = [all_positions[idx] for idx in occupied_indices]
        occupied_set  = set(occupied_list)

        # Komşuluk haritası — sadece dolu konumlar arası
        def occ_neighbors(r, c):
            result = []
            for dc in (-1, 1):
                nc = c + dc
                if 0 <= nc < cols and (c // 2) == (nc // 2) and (r, nc) in occupied_set:
                    result.append((r, nc))
            for dr in (-1, 1):
                nr = r + dr
                if 0 <= nr < rows and (nr, c) in occupied_set:
                    result.append((nr, c))
            return result

        adj = {pos: occ_neighbors(*pos) for pos in occupied_set}

        # ── Faz 2: MRV greedy ───────────────────────────────────────────────
        layout     = [[EMPTY_KEY] * cols for _ in range(rows)]
        assignment: dict = {}
        remaining  = dict(exam_counts)
        keys_desc  = sorted(exam_counts, key=lambda k: -exam_counts[k])

        def valid_keys(pos):
            forbidden = {assignment.get(n) for n in adj[pos]} - {None}
            return [k for k in keys_desc if remaining.get(k, 0) > 0 and k not in forbidden]

        unassigned = set(occupied_set)

        while unassigned:
            # En kısıtlı konum: geçerli seçenek sayısı az, komşu sayısı fazla
            best = min(unassigned, key=lambda p: (len(valid_keys(p)), -len(adj[p]), p))
            vk = valid_keys(best)
            if vk:
                chosen = vk[0]              # geçerliler içinde en büyük grup
            else:
                available = [k for k in keys_desc if remaining.get(k, 0) > 0]
                if not available:
                    unassigned.discard(best)
                    continue
                # Çakışmasız seçenek yok → en az çakışan grubu ata
                chosen = min(
                    available,
                    key=lambda k: sum(1 for n in adj[best] if assignment.get(n) == k),
                )
            r, c = best
            layout[r][c]   = chosen
            assignment[best] = chosen
            remaining[chosen] -= 1
            unassigned.discard(best)

        # ── Faz 3: Takas onarımı ────────────────────────────────────────────
        # Kalan komşu çakışmalarını yerel ikili takasla azalt (max 5 geçiş)
        for _ in range(5):
            improved = False
            for pos in occupied_set:
                key_here = assignment.get(pos)
                if key_here is None:
                    continue
                conflict_n = [n for n in adj[pos] if assignment.get(n) == key_here]
                if not conflict_n:
                    continue
                old_here = len(conflict_n)

                for pos2 in occupied_set:
                    if pos2 == pos:
                        continue
                    key2 = assignment.get(pos2)
                    if key2 is None or key2 == key_here:
                        continue
                    # Takas sonrası çakışma sayılarını hesapla
                    new_here = sum(
                        1 for n in adj[pos]  if assignment.get(n) == key2 and n != pos2
                    )
                    old_p2 = sum(
                        1 for n in adj[pos2] if assignment.get(n) == key2 and n != pos
                    )
                    new_p2 = sum(
                        1 for n in adj[pos2] if assignment.get(n) == key_here and n != pos
                    )
                    if new_here + new_p2 < old_here + old_p2:
                        # Takas faydalı
                        r,  c  = pos
                        r2, c2 = pos2
                        layout[r][c]   = key2
                        layout[r2][c2] = key_here
                        assignment[pos]  = key2
                        assignment[pos2] = key_here
                        improved = True
                        break
            if not improved:
                break

        return layout

