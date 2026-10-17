# -*- coding: utf-8 -*-
"""
OturmaPlanService – Adim 5

Takvim ve SinavOgrenci tablolarindan bir oturumun ogrencilerini alarak
Kelebek karisik oturma duzeni olusturur ve OturmaPlani tablosuna kaydeder.

Ozel metodlar:
  _build_layout       – 6x6 matris icin stride bosluk + GA tabanli yerlesim
  _ga_seat_assignment – komsu-cakisma sayisini minimize eden permutasyon GA'si
  _place_matrix       – 6x6 matrisi 3 blok x 6 sira x 2 koltuk yapisina donusturur
  _simple_grid        – kelebek kapaliyken ogrencileri sirayla yerlestirir
  generate_oturum     – tek oturum icin plani uretir
  generate_all        – takvimdeki tum oturumlar icin calistirir
  generate_selected   – yalnizca secilen oturumlar icin calistirir
"""

import hashlib
import random
import re
from datetime import datetime
from operator import eq, itemgetter

import pandas as pd

from ortaksinav_engine.services.base import BaseService
from ortaksinav_engine.utils import normalize_sube_cell


def anlik_goruntu_garanti_et(sinav):
    """Bu sınav için `SinavOgrenci`/`SinavOgrenciMuaf` anlık görüntüsü daha önce
    alınmamışsa, o anki CANLI `ogrenci.Ogrenci`/`OgrenciMuaf` verisinden bir kere
    oluşturur; zaten varsa hiçbir şey yapmaz (idempotent) — bkz.
    `sinav.models.SinavOgrenci` docstring'i.

    `generate_oturum`'un TEK çağrı noktası: bir sınav için "Oturma Üret" ilk kez
    ne zaman çalışırsa, öğrenci listesi o an için dondurulur; sınav dönemi geçtikten
    sonra (yeni eğitim yılına geçilip roster değiştikten sonra) yeniden üretilirse
    bile aynı donmuş liste kullanılmaya devam eder."""
    from ogrenci.models import Ogrenci as OgrenciModel
    from ogrenci.models import OgrenciMuaf
    from okul.utils import get_aktif_egitim_yili
    from sinav.models import SinavOgrenci, SinavOgrenciMuaf

    if sinav is None or SinavOgrenci.objects.filter(sinav=sinav).exists():
        return

    SinavOgrenci.objects.bulk_create([
        SinavOgrenci(
            sinav=sinav, okulno=o.okulno, adi=o.adi, soyadi=o.soyadi,
            cinsiyet=o.cinsiyet, sinif=o.sinif, sube=o.sube,
            sureksiz_devamsiz=o.sureksiz_devamsiz,
        )
        for o in OgrenciModel.objects.filter(aktif=True)
    ], ignore_conflicts=True)

    SinavOgrenciMuaf.objects.bulk_create([
        SinavOgrenciMuaf(sinav=sinav, okulno=okulno, ders_adi=ders_adi)
        for okulno, ders_adi in OgrenciMuaf.objects.filter(
            egitim_yili=get_aktif_egitim_yili()
        ).values_list("ogrenci__okulno", "ders__ders_adi")
    ], ignore_conflicts=True)


class OturmaPlanService(BaseService):
    """Kelebek oturma plani olusturan servis."""

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate_all(self):
        from sinav.models import SinavBilgisi, Takvim, TakvimUretim

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
            if self.is_cancelled():
                self.log("\nDurduruldu: kalan oturumlar icin oturma plani olusturulmadi.")
                return
            try:
                self.log("────────────────────────────────────────────")
                self.log(f"{tarih} {saat} (Oturum {oturum}) isleniyor...")
                self.generate_oturum(str(tarih), str(saat), int(oturum), aktif_sinav, aktif_uretim)
            except Exception as e:
                self.log(f"HATA {tarih} {saat} (Oturum {oturum}): {e}")

        self.log("\nTum oturumlar icin oturma plani tamamlandi.\n")

    def generate_selected(self, sessions: list) -> list:
        """Yalnızca verilen oturumlar için oturma planı oluşturur.

        sessions: [{"tarih": "YYYY-MM-DD", "saat": "HH:MM", "oturum": int}, ...]
        İptal her oturumdan önce kontrol edilir; yarıdaki oturum yarıda kesilmez.
        Döndürür: hatasız tamamlanan oturumlar (sessions'taki sözlüklerle aynı).
        """
        from sinav.models import SinavBilgisi, TakvimUretim

        aktif_sinav = SinavBilgisi.objects.filter(aktif=True).first()
        aktif_uretim = (
            TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
            if aktif_sinav else None
        )
        self.log(f"\nSecili {len(sessions)} oturum icin oturma plani olusturuluyor...\n")
        tamamlanan = []
        for s in sessions:
            if self.is_cancelled():
                self.log(
                    f"\nDurduruldu: {len(tamamlanan)}/{len(sessions)} oturum tamamlandi, "
                    "kalanlar icin oturma plani olusturulmadi."
                )
                return tamamlanan
            tarih  = s.get("tarih", "")
            saat   = s.get("saat", "")
            oturum = int(s.get("oturum", 1))
            try:
                self.log("────────────────────────────────────────────")
                self.log(f"{tarih} {saat} (Oturum {oturum}) isleniyor...")
                self.generate_oturum(tarih, saat, oturum, aktif_sinav, aktif_uretim)
                tamamlanan.append(s)
            except Exception as e:
                import traceback as _tb
                self.log(f"HATA {tarih} {saat} (Oturum {oturum}): {e}")
                self.log(_tb.format_exc())
        self.log("\nSecili oturumlar tamamlandi.\n")
        return tamamlanan

    def generate_oturum(self, tarih: str, saat: str, oturum: int, aktif_sinav=None, aktif_uretim=None):
        from sinav.models import OturmaPlani, SinavOgrenci, SinavOgrenciMuaf, Takvim

        self.log(f"\nOturum yerlesimi: {tarih} {saat} (Oturum {oturum})")

        # Öğrenci listesi CANLI ogrenci.Ogrenci'den değil, bu sınav için dondurulmuş
        # SinavOgrenci anlık görüntüsünden okunur — bkz. sinav.models.SinavOgrenci
        # docstring'i (2026-2027'nin yeni 9. sınıf öğrencilerinin 2025-2026'ya ait
        # bir sınavda görünmesi olayı). Anlık görüntü bu sınav için daha önce hiç
        # alınmamışsa (ilk üretim), burada o anki canlı veriden bir kere oluşturulur;
        # sonraki her (yeniden) üretim aynı donmuş listeyi kullanır.
        sinav_kapsam = aktif_sinav or (aktif_uretim.sinav if aktif_uretim else None)
        anlik_goruntu_garanti_et(sinav_kapsam)

        # Yeniden üretimde eski kayıtları temizle (aynı uretim + tarih + saat + oturum)
        silinen, _ = OturmaPlani.objects.filter(
            uretim=aktif_uretim, tarih=tarih, saat=saat, oturum=oturum
        ).delete()
        if silinen:
            self.log(f"Önceki üretimden {silinen} kayıt silindi.")

        takvim_filtre = {"uretim": aktif_uretim} if aktif_uretim is not None else {"sinav": aktif_sinav}
        takvimler = list(
            Takvim.objects.filter(tarih=tarih, saat=saat, **takvim_filtre)
            .select_related("ders", "ders_saati")
        )
        if not takvimler:
            self.log("Belirtilen tarih/saat icin takvim verisi bulunamadi.")
            return

        sube_to_ders = {
            s: t.ders_tam_adi
            for t in takvimler
            for s in normalize_sube_cell(t.subeler)
        }
        subeler = sorted(sube_to_ders)
        if not subeler:
            self.log("Bu oturumda sube bulunamadi.")
            return

        salon_adlari = [f"Salon-{s.replace('/', '_')}" for s in subeler]

        df_o = pd.DataFrame(SinavOgrenci.objects.filter(sinav=sinav_kapsam).values(
            "okulno", "adi", "soyadi", "cinsiyet", "sinif", "sube", "sureksiz_devamsiz",
        ))
        if df_o.empty:
            self.log("Bu sinav icin ogrenci anlik goruntusu bulunamadi. Adim 1'i calistirin.")
            return

        # Özel durum 1: Sürekli devamsız öğrencileri hiçbir sınavda oturma planına alma
        # (bu sınavın anlık görüntüsündeki, o anda dondurulmuş hâli)
        hariç_sureksiz = int(df_o["sureksiz_devamsiz"].sum())
        df_o = df_o[~df_o["sureksiz_devamsiz"]].drop(columns=["sureksiz_devamsiz"])
        if hariç_sureksiz:
            self.log(f"  Özel durum: {hariç_sureksiz} sürekli devamsız öğrenci hariç tutuldu.")

        df_o["sinifsube"] = (
            df_o["sinif"].astype(str) + "/" + df_o["sube"].astype(str)
        ).str.upper().str.replace(" ", "")
        df_o["ders"] = df_o["sinifsube"].map(sube_to_ders)
        df_o = df_o[df_o["ders"].notna()].copy()
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
            SinavOgrenciMuaf.objects.filter(
                sinav=sinav_kapsam, ders_adi__in=oturum_base_ders,
            ).values_list("okulno", "ders_adi")
        )
        if muaf_pairs:
            onceki = len(df_o)
            muaf_mi = [
                (okulno, _base_ders(ders)) in muaf_pairs
                for okulno, ders in zip(df_o["okulno"], df_o["ders"])
            ]
            df_o = df_o[[not m for m in muaf_mi]]
            hariç_muaf = onceki - len(df_o)
            if hariç_muaf:
                self.log(f"  Özel durum: {hariç_muaf} muaf öğrenci bu oturum için hariç tutuldu.")

        if df_o.empty:
            self.log("Bu oturumda sinava girecek ogrenci bulunamadi (ozel durumlar sonrasi).")
            return

        kelebek = self.config.get("KELEBEK_DAGITIM", True)
        _seed = int(hashlib.md5(f"{tarih}{saat}{oturum}".encode()).hexdigest(), 16) % (2 ** 31)
        ogr = df_o.sample(frac=1, random_state=_seed).to_dict("records")
        salon_map = {name: [] for name in salon_adlari}
        n_salons = len(salon_adlari)
        SALON_KAPASITE = 36  # 3 blok × 6 sıra × 2 koltuk

        if kelebek:
            # Kademe 2: Her sınav grubu kendi içinde salonlara orantılı dağıtılır.
            # Round-robin (tüm öğrenci karışık) yerine per-grup round-robin:
            # her salona her gruptan floor ya da ceil kadar düşer → garantili denge.
            groups_by_ders: dict[str, list] = {}
            for row in ogr:
                groups_by_ders.setdefault(row["ders"], []).append(row)

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
            for row in ogr:
                salon_key = f"Salon-{row['sinifsube'].replace('/', '_')}"
                if salon_key in salon_map:
                    salon_map[salon_key].append(row)

        salon_grids = {}
        for salon, lst in salon_map.items():
            if not lst:
                continue
            if kelebek:
                salon_grids[salon] = self._place_matrix(lst)
            else:
                salon_grids[salon] = self._simple_grid(lst)

        # DB kaydet
        tarih_date = datetime.strptime(tarih, "%Y-%m-%d").date()

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
        ss_by_key = {(ss.sinif, ss.sube): ss for ss in _SS.objects.all()}
        ss_map = {}
        for sube_str in subeler:
            parts = sube_str.split("/")
            if len(parts) != 2:
                continue
            try:
                ss = ss_by_key.get((int(parts[0]), parts[1]))
            except ValueError:
                ss = None
            if ss:
                ss_map[f"Salon-{sube_str.replace('/', '_')}"] = ss
        ders_saati_obj = takvimler[0].ders_saati
        salon_gozetmen = salon_gozetmen_bul(tarih_date, ders_saati_obj or saat, ss_map)

        # Sıra numaralandırması: pdf_rapor.oturum_plani_pdf ile birebir aynı seat_map
        # Grup 1→1-12, Grup 2→13-24, Grup 3→25-36
        # Çift satır sol→sağ, tek satır sağ→sol (S-şekli)
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
                            adi = str(s.get("adi") or "")
                            soyadi = str(s.get("soyadi") or "")
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
                        grid[b][r][c] = lst[idx]
                        idx += 1
        return grid

    def _place_matrix(self, students: list) -> list:
        """students: öğrenci dict'leri (en az "ders" ve "sinif" anahtarlı)."""
        ROWS, COLS_PER_BLOCK, BLOCKS = 6, 2, 3
        TOTAL_COLS = COLS_PER_BLOCK * BLOCKS

        groups = {}
        for ogr in students:
            k = (ogr["ders"], int(ogr["sinif"]))
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
        İki fazlı yerleşim.

        Faz 1 (Stride deseni):
            Boş koltuklar grid'e düzenli aralıklarla yayılır; tampon görevi görür.

        Faz 2 (Genetik algoritma):
            Dolu konumlara exam_key = (ders, seviye) atamasını, komşu-çakışma
            sayısını (aynı ders+seviye komşu olamaz) minimize edecek şekilde
            permütasyon tabanlı bir GA ile bulur (bkz. _ga_seat_assignment).
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

        # ── Faz 2: GA ile komşu-çakışmasını minimize eden atama ─────────────
        assignment = OturmaPlanService._ga_seat_assignment(occupied_list, adj, exam_counts)

        layout = [[EMPTY_KEY] * cols for _ in range(rows)]
        for (r, c), key in assignment.items():
            layout[r][c] = key
        return layout

    @staticmethod
    def _ga_seat_assignment(occupied_list, adj, exam_counts,
                             population_size=60, generations=150, max_stagnation=30):
        """
        Dolu konum → exam_key atamasını, komşu (aynı ders+seviye) çakışma
        sayısını minimize eden permütasyon tabanlı bir GA ile bulur.

        Birey: occupied_list ile ayni uzunlukta bir exam_key permutasyonu.
        Fitness: komsu ciftler arasindaki ayni-key cakisma sayisi (0 = ideal).
        Mutasyon: rastgele birkac pozisyon ciftinin key'ini takas eder — bu,
        Faz 1'deki eski "takas onarımı" adımının GA mutasyonu icindeki karsiligidir.
        Çaprazlama kullanılmaz (projede AdvancedNobetDagitim/takvim GA'larıyla
        aynı sade desen: elitizm + mutasyon).
        """
        EMPTY_KEY = ("__EMPTY__", None)
        n = len(occupied_list)
        if n == 0:
            return {}

        keys_expanded: list = []
        for k, cnt in exam_counts.items():
            keys_expanded.extend([k] * cnt)
        if len(keys_expanded) < n:
            keys_expanded += [EMPTY_KEY] * (n - len(keys_expanded))
        elif len(keys_expanded) > n:
            keys_expanded = keys_expanded[:n]

        # Tek tür key varsa (örn. salonda tek sınav grubu) her permütasyon aynı
        # çakışmayı verir; GA'nın iyileştirebileceği bir şey yoktur.
        if len(set(keys_expanded)) == 1:
            return dict(zip(occupied_list, keys_expanded))

        # Komşu çiftler bir kez indeks çiftlerine çevrilir (her çift tek sayılır);
        # fitness yalnızca bu çiftlerin key'lerini karşılaştırır.
        index_of = {pos: i for i, pos in enumerate(occupied_list)}
        edges = [
            (index_of[pos], index_of[nb])
            for pos in occupied_list
            for nb in adj[pos]
            if index_of[pos] < index_of[nb]
        ]
        if not edges:
            return dict(zip(occupied_list, keys_expanded))
        sol = [i for i, _ in edges]
        sag = [j for _, j in edges]

        def conflict_count(perm) -> int:
            return sum(map(eq, map(perm.__getitem__, sol), map(perm.__getitem__, sag)))

        rng = random.Random()

        def random_individual():
            perm = list(keys_expanded)
            rng.shuffle(perm)
            return perm

        population = [random_individual() for _ in range(population_size)]
        best_fitness = float("inf")
        stagnation = 0
        swaps_per_mutation = max(1, n // 10)

        for _generation in range(generations):
            # Her bireyin fitness'ı nesil başına bir kez hesaplanır (sıralama kararlı)
            scored = sorted(
                ((conflict_count(p), p) for p in population), key=itemgetter(0)
            )
            population = [p for _, p in scored]
            current_best = scored[0][0]
            if current_best == 0:
                break
            if current_best < best_fitness:
                best_fitness = current_best
                stagnation = 0
            else:
                stagnation += 1
            if stagnation >= max_stagnation:
                break

            parent_pool = population[: max(3, population_size // 4)]
            new_population = [population[0]]  # Elitizm: en iyi bireyi koru
            while len(new_population) < population_size:
                child = list(rng.choice(parent_pool))
                for _ in range(swaps_per_mutation):
                    i, j = rng.randrange(n), rng.randrange(n)
                    child[i], child[j] = child[j], child[i]
                new_population.append(child)
            population = new_population

        best = min(population, key=conflict_count)
        return dict(zip(occupied_list, best))

