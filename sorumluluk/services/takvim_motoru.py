import random
from itertools import combinations
from collections import defaultdict
from datetime import datetime, timedelta, date
from typing import Optional

import networkx as nx
from django.db import transaction

from sorumluluk.models import (
    SALON_KAPASITESI,
    SALON_SAYISI,
    SorumluSinav,
    SorumluTakvim,
    SorumluOgrenci,
    SorumluDersHavuzu,
)


class DjangoSinavTakvimiMotoru:
    """
    Django veritabanındaki kayıtları kullanarak çakışmasız sınav takvimi üreten motor.
    """
    def __init__(
        self,
        sinav: SorumluSinav,
        baslangic_tarihi: date,
        time_slots: list,
        tatil_tarihleri: Optional[list] = None,
        exclude_weekends: bool = True,
        seed: int = 42,
        cift_oturumlu_dersler: Optional[list] = None,
    ):
        self.sinav = sinav
        self.TIME_SLOTS = time_slots  # Örn: [1, 2, 3, 4] (Oturum Numaraları)
        self.baslangic_tarihi = baslangic_tarihi
        self.tatil_tarihleri = set(tatil_tarihleri or [])
        self.exclude_weekends = exclude_weekends
        self.cift_oturumlu_dersler = cift_oturumlu_dersler or []
        self.seed = seed
        random.seed(self.seed)

        self.verileri_yukle()

    def _is_valid_exam_day(self, d: date) -> bool:
        if d in self.tatil_tarihleri:
            return False
        if self.exclude_weekends and d.weekday() >= 5:
            return False
        return True

    def _next_valid_exam_day(self, d: date) -> date:
        x = d
        while not self._is_valid_exam_day(x):
            x += timedelta(days=1)
        return x

    def verileri_yukle(self):
        self.max_kapasite = SALON_KAPASITESI * SALON_SAYISI
        self.ogrenci_ders_dict = defaultdict(list)
        self.ders_ogrenci_dict = defaultdict(list)
        self.ders_bilgileri = {}

        # Sınava ait havuzdaki tüm dersleri al
        havuz = SorumluDersHavuzu.objects.filter(sinav=self.sinav)
        for hd in havuz:
            # Sınıf seviyesini ders adına ekleyerek farklı sınıfların aynı isimli derslerini benzersiz yapıyoruz
            ders_ek = f" ({hd.onceki_sinif}. Sınıf)" if hd.onceki_sinif else ""
            ders_baslik = f"{hd.ders_adi}{ders_ek}"
            
            base_info = {
                "Sinif": hd.onceki_sinif or 0,
                "Ders": ders_baslik,
                "GercekDersAdi": hd.ders_adi,
                "OgrenciSayisi": 0,
            }
            cid = str(hd.id)
            if hd.id in self.cift_oturumlu_dersler:
                self.ders_bilgileri[f"{cid}_P1"] = {
                    **base_info, "Ders": f"{ders_baslik} (Uygulama)", "BaseCid": cid, "PartType": "P1"
                }
                self.ders_bilgileri[f"{cid}_P2"] = {
                    **base_info, "Ders": f"{ders_baslik} (Yazılı)", "BaseCid": cid, "PartType": "P2"
                }
            else:
                self.ders_bilgileri[cid] = {**base_info, "BaseCid": cid, "PartType": None}

        # Aktif öğrencileri ve sorumlu oldukları dersleri al
        ogrenciler = SorumluOgrenci.objects.filter(
            sinav=self.sinav, aktif=True
        ).prefetch_related("dersler").order_by("sinif", "sube", "adi_soyadi")

        temp_ders_ogrenci = defaultdict(list)
        for ogr in ogrenciler:
            for d in ogr.dersler.all():
                cid = str(d.havuz_dersi_id)
                if d.havuz_dersi_id in self.cift_oturumlu_dersler:
                    temp_ders_ogrenci[f"{cid}_P1"].append(ogr.okulno)
                    temp_ders_ogrenci[f"{cid}_P2"].append(ogr.okulno)
                else:
                    temp_ders_ogrenci[cid].append(ogr.okulno)

        for cid, ogrenci_list in temp_ders_ogrenci.items():
            base_info = self.ders_bilgileri.get(cid)
            if not base_info:
                continue
                
            # Öğrenci sayısı kapasiteyi aşıyorsa dersi eşit gruplara böl
            if len(ogrenci_list) > self.max_kapasite:
                num_groups = (len(ogrenci_list) + self.max_kapasite - 1) // self.max_kapasite
                chunk_size = (len(ogrenci_list) + num_groups - 1) // num_groups

                for i in range(num_groups):
                    new_cid = f"{cid}_G{i+1}"
                    chunk = ogrenci_list[i*chunk_size : (i+1)*chunk_size]
                    
                    ders_ismi = base_info['Ders']
                    if ders_ismi.endswith("(Uygulama)"):
                        ders_ismi = ders_ismi.replace(" (Uygulama)", f" (Grup {i+1}) (Uygulama)")
                    elif ders_ismi.endswith("(Yazılı)"):
                        ders_ismi = ders_ismi.replace(" (Yazılı)", f" (Grup {i+1}) (Yazılı)")
                    else:
                        ders_ismi = f"{ders_ismi} (Grup {i+1})"
                    
                    self.ders_bilgileri[new_cid] = {
                        "Sinif": base_info["Sinif"],
                        "Ders": ders_ismi,
                        "GercekDersAdi": base_info["GercekDersAdi"],
                        "OgrenciSayisi": len(chunk),
                        "BaseCid": base_info.get("BaseCid", cid),
                        "PartType": base_info.get("PartType"),
                    }
                    self.ders_ogrenci_dict[new_cid].extend(chunk)
                    for okulno in chunk:
                        self.ogrenci_ders_dict[okulno].append(new_cid)
                
                del self.ders_bilgileri[cid]
            else:
                self.ders_bilgileri[cid]["OgrenciSayisi"] = len(ogrenci_list)
                self.ders_ogrenci_dict[cid].extend(ogrenci_list)
                for okulno in ogrenci_list:
                    self.ogrenci_ders_dict[okulno].append(cid)
                    
        # Sadece öğrencisi olan dersleri bırak
        self.ders_bilgileri = {k: v for k, v in self.ders_bilgileri.items() if v["OgrenciSayisi"] > 0}

        # Aynı ders adı + farklı sınıf seviyesi → toplam ≤ SALON_KAPASITESI ise birleştir
        self._birlesim_olustur()

    def _birlesim_olustur(self):
        """Aynı ders adı, farklı sınıf seviyesi için iki kural:

        - Toplam öğrenci ≤ SALON_KAPASITESI → aynı slota zorla (sanal cid ile birleştir)
        - Toplam öğrenci > SALON_KAPASITESI → farklı slota zorla (çakışma grafiğine kenar)

        Çift oturumlu dersler (P1/P2) da aynı gruplamayı kullanır:
        birleşebilen seviyelerin Uygulama'ları da, Yazılı'ları da birleşir.
        Birleşik P1+P2 çiftleri ortak BaseCid alarak aynı-gün yasağı korunur.
        """
        havuz_gruplari: dict = defaultdict(list)
        for hd in SorumluDersHavuzu.objects.filter(sinav=self.sinav):
            havuz_gruplari[hd.ders_adi].append(hd.id)

        # Çakışma grafiğine eklenecek "kesinlikle farklı slot" çiftleri
        self._zorunlu_cakisma: list = []

        for ders_adi, havuz_ids in havuz_gruplari.items():
            if len(havuz_ids) < 2:
                continue

            # Öğrenci sayısı: normal cid'den al, çift-oturumlu ise P1'den al
            def ogrenci_sayisi(hid: int) -> int:
                cid = str(hid)
                if cid in self.ders_bilgileri:
                    return self.ders_bilgileri[cid]["OgrenciSayisi"]
                p1 = f"{cid}_P1"
                if p1 in self.ders_bilgileri:
                    return self.ders_bilgileri[p1]["OgrenciSayisi"]
                return 0

            # Grupların öğrenci listelerini bulmak için yardımcı fonksiyon
            def get_students(hid: int) -> set:
                cid = str(hid)
                if cid in self.ders_bilgileri:
                    return set(self.ders_ogrenci_dict.get(cid, []))
                p1 = f"{cid}_P1"
                if p1 in self.ders_bilgileri:
                    return set(self.ders_ogrenci_dict.get(p1, []))
                return set()

            # Açgözlü merge planı: havuz_id düzeyinde grupla
            remaining = sorted(havuz_ids, key=ogrenci_sayisi)
            merge_groups: list = []   # birleştirilecek gruplar (≥2 havuz_id)
            solo_ids: list = []       # tek kalan havuz_id'ler

            while remaining:
                anchor = remaining.pop(0)
                group = [anchor]
                total = ogrenci_sayisi(anchor)
                group_students = get_students(anchor)

                leftovers = []
                for hid in remaining:
                    count = ogrenci_sayisi(hid)
                    hid_students = get_students(hid)

                    # Aynı öğrenci her iki sınıfta da bu dersten sorumluysa birleştirme (çakışmayı önle)
                    if not group_students.isdisjoint(hid_students):
                        leftovers.append(hid)
                        continue

                    if total + count <= SALON_KAPASITESI:
                        group.append(hid)
                        total += count
                        group_students.update(hid_students)
                    else:
                        leftovers.append(hid)
                remaining = leftovers

                if len(group) >= 2:
                    merge_groups.append(group)
                else:
                    solo_ids.append(anchor)

            # Her merge grubu için paylaşılan BaseCid (P1+P2 aynı-gün yasağını korur)
            group_base = {
                tuple(sorted(g)): "mergebase_" + "_".join(str(h) for h in sorted(g))
                for g in merge_groups
            }

            # Normal, P1, P2 sırасıyla işle
            for part_type, suffix, label in [
                (None, "",    ""),
                ("P1", "_P1", " (Uygulama)"),
                ("P2", "_P2", " (Yazılı)"),
            ]:
                part_cids: list = []   # bu parttaki tüm sonuç cid'ler (çakışma kontrolü için)

                for group in merge_groups:
                    base_cid = group_base[tuple(sorted(group))]
                    cids = [f"{hid}{suffix}" for hid in group if f"{hid}{suffix}" in self.ders_bilgileri]

                    if len(cids) < 2:
                        part_cids.extend(cids)
                        continue

                    merged_cid = f"merge{suffix}_" + "_".join(str(h) for h in sorted(group))

                    seen: set = set()
                    students: list = []
                    for c in cids:
                        for okulno in self.ders_ogrenci_dict[c]:
                            if okulno not in seen:
                                seen.add(okulno)
                                students.append(okulno)

                    self.ders_bilgileri[merged_cid] = {
                        "Sinif": 0,
                        "Ders": f"{ders_adi}{label}",
                        "GercekDersAdi": ders_adi,
                        "OgrenciSayisi": len(students),
                        "BaseCid": base_cid,
                        "PartType": part_type,
                        "MergedComponents": {c: dict(self.ders_bilgileri[c]) for c in cids},
                    }
                    self.ders_ogrenci_dict[merged_cid] = students

                    for okulno in students:
                        updated = [cx for cx in self.ogrenci_ders_dict[okulno] if cx not in cids]
                        if merged_cid not in updated:
                            updated.append(merged_cid)
                        self.ogrenci_ders_dict[okulno] = updated

                    for old_cid in cids:
                        self.ders_bilgileri.pop(old_cid, None)
                        self.ders_ogrenci_dict.pop(old_cid, None)

                    part_cids.append(merged_cid)

                # Solo havuz_id'lerin cid'lerini de ekle
                for hid in solo_ids:
                    cid = f"{hid}{suffix}"
                    if cid in self.ders_bilgileri:
                        part_cids.append(cid)

                # Birden fazla sonuç cid varsa → kesinlikle farklı slotta olmalı
                for c1, c2 in combinations(part_cids, 2):
                    self._zorunlu_cakisma.append((c1, c2))

    def cakisma_grafigi_olustur(self):
        G = nx.Graph()
        all_courses = set().union(*self.ogrenci_ders_dict.values()) if self.ogrenci_ders_dict else set()
        G.add_nodes_from(all_courses)

        for courses in self.ogrenci_ders_dict.values():
            for c1, c2 in combinations(courses, 2):
                if G.has_edge(c1, c2):
                    G[c1][c2]["weight"] += 1
                else:
                    G.add_edge(c1, c2, weight=1)
                    
        # Gruplara bölünen aynı dersin alt gruplarının çakışmasını (aynı oturuma düşmesini) engelle
        base_to_groups = defaultdict(list)
        for cid, info in self.ders_bilgileri.items():
            if "BaseCid" in info:
                base_to_groups[info["BaseCid"]].append(cid)
        for groups in base_to_groups.values():
            for c1, c2 in combinations(groups, 2):
                G.add_edge(c1, c2, weight=999)

        # Birleştirilemeyecek kadar büyük aynı-isim farklı-seviye dersleri farklı slota zorla
        for c1, c2 in getattr(self, "_zorunlu_cakisma", []):
            if G.has_node(c1) and G.has_node(c2):
                G.add_edge(c1, c2, weight=999)

        return G

    def _schedule_penalty(self, schedule, max_daily_exams=2):
        student_day_count = defaultdict(lambda: defaultdict(int))
        day_exam_count = defaultdict(int)

        for day, times in schedule.items():
            for t in self.TIME_SLOTS:
                for course in times.get(t, []):
                    day_exam_count[day] += 1
                    for s in self.ders_ogrenci_dict.get(course, []):
                        student_day_count[s][day] += 1

        penalty = 0.0
        for _, days in student_day_count.items():
            for _, cnt in days.items():
                if cnt > max_daily_exams:
                    penalty += (cnt - max_daily_exams) * 1000

        if day_exam_count:
            avg = sum(day_exam_count.values()) / max(1, len(day_exam_count))
            for _, cnt in day_exam_count.items():
                penalty += abs(cnt - avg) * 2

        return penalty

    def _schedule_score(self, schedule):
        def parse_date(s): return datetime.strptime(s, "%Y-%m-%d").date()
        days_sorted = sorted(schedule.keys(), key=parse_date)
        w = {d: 1.0 / (i ** 0.5) for i, d in enumerate(days_sorted, start=1)}

        total = 0.0
        for day, times in schedule.items():
            for t in self.TIME_SLOTS:
                for course in times.get(t, []):
                    total += self.ders_bilgileri[course]["OgrenciSayisi"] * w.get(day, 1.0)
        return total

    def optimize_edilmis_takvim(self, max_iter=800, max_daily_exams=2, slot_max_ders=6):
        conflict_graph = self.cakisma_grafigi_olustur()
        courses_all = list(conflict_graph.nodes())
        if not courses_all:
            raise RuntimeError("Öğrencilere atanmış hiçbir ders bulunamadı.")

        neighbor_map = {c: set(conflict_graph.neighbors(c)) for c in courses_all}
        base_order = sorted(
            courses_all,
            key=lambda c: (conflict_graph.degree(c), self.ders_bilgileri[c]["OgrenciSayisi"]),
            reverse=True,
        )

        best_schedule = None
        best_days = float("inf")
        best_penalty = float("inf")
        best_score = float("-inf")

        for _ in range(max_iter):
            courses = base_order[:]
            random.shuffle(courses)

            schedule = defaultdict(lambda: defaultdict(list))
            unscheduled = set(courses)
            cur_date = self._next_valid_exam_day(self.baslangic_tarihi)

            while unscheduled:
                day_str = cur_date.strftime("%Y-%m-%d")
                daily_counts = defaultdict(int)

                for slot in self.TIME_SLOTS:
                    candidates = sorted(
                        list(unscheduled),
                        key=lambda c: self.ders_bilgileri[c]["OgrenciSayisi"],
                        reverse=True,
                    )

                    for course in candidates:
                        if slot_max_ders is not None:
                            # Mevcut slotta ve yeni eklenecek blokta toplam kaç GERÇEK alt ders var hesapla
                            current_count = sum(len(self.ders_bilgileri[sc].get("MergedComponents", [1])) for sc in schedule[day_str][slot])
                            new_count = len(self.ders_bilgileri[course].get("MergedComponents", [1]))
                            # Eğer bu dersi eklediğimizde ayarlanan limiti aşıyorsak, atla (daha küçük bir ders arayabilir)
                            if current_count + new_count > slot_max_ders:
                                continue

                        if any(other in neighbor_map[course] for other in schedule[day_str][slot]):
                            continue
                            
                        c_info = self.ders_bilgileri[course]
                        is_uygulama = (c_info.get("PartType") == "P1")
                        
                        # Uygulama sınavları diğer sınav türleriyle aynı oturuma (saate) planlanamaz
                        if len(schedule[day_str][slot]) > 0:
                            first_c_info = self.ders_bilgileri[schedule[day_str][slot][0]]
                            if is_uygulama != (first_c_info.get("PartType") == "P1"):
                                continue

                        # Uygulama ve Yazılı oturumlarını kesinlikle farklı günlere ayır
                        c_info = self.ders_bilgileri[course]
                        if c_info.get("PartType"):
                            same_day_conflict = False
                            for slt in self.TIME_SLOTS:
                                for sc in schedule[day_str][slt]:
                                    sc_info = self.ders_bilgileri[sc]
                                    if sc_info.get("BaseCid") == c_info["BaseCid"] and \
                                       sc_info.get("PartType") and \
                                       sc_info["PartType"] != c_info["PartType"]:
                                        same_day_conflict = True
                                        break
                                if same_day_conflict:
                                    break
                            if same_day_conflict:
                                continue

                        # Kapasite ve Salon kontrolü
                        if is_uygulama:
                            # Uygulama sınavları farklı salonlara yerleştirilir; toplam salon ihtiyacı SALON_SAYISI'nı aşamaz
                            gercek_ders_students = defaultdict(int)
                            for sc in schedule[day_str][slot]:
                                gercek_ders_students[self.ders_bilgileri[sc]["GercekDersAdi"]] += self.ders_bilgileri[sc]["OgrenciSayisi"]
                            gercek_ders_students[self.ders_bilgileri[course]["GercekDersAdi"]] += self.ders_bilgileri[course]["OgrenciSayisi"]
                            
                            total_salons = 0
                            for count in gercek_ders_students.values():
                                total_salons += (count + SALON_KAPASITESI - 1) // SALON_KAPASITESI
                            if total_salons > SALON_SAYISI:
                                continue
                        else:
                            # Normal ve Yazılı sınavlar için global kapasite (Örn: max 60 kişi S1 ve S2'ye dağılır)
                            current_students = sum(self.ders_bilgileri[c]["OgrenciSayisi"] for c in schedule[day_str][slot])
                            if current_students + self.ders_bilgileri[course]["OgrenciSayisi"] > self.max_kapasite:
                                continue

                        ok = True
                        for s in self.ders_ogrenci_dict.get(course, []):
                            if daily_counts[s] >= max_daily_exams:
                                ok = False
                                break
                            if any(d in schedule[day_str][slot] for d in self.ogrenci_ders_dict.get(s, [])):
                                ok = False
                                break
                        if not ok:
                            continue

                        schedule[day_str][slot].append(course)
                        unscheduled.remove(course)

                        for s in self.ders_ogrenci_dict.get(course, []):
                            daily_counts[s] += 1

                if all(len(schedule[day_str].get(sl, [])) == 0 for sl in self.TIME_SLOTS):
                    schedule = None
                    break

                cur_date = self._next_valid_exam_day(cur_date + timedelta(days=1))

            if schedule is None:
                continue

            days_count = len(schedule)
            penalty = self._schedule_penalty(schedule, max_daily_exams=max_daily_exams)
            score = self._schedule_score(schedule)

            if (days_count < best_days) or \
               (days_count == best_days and penalty < best_penalty) or \
               (days_count == best_days and penalty == best_penalty and score > best_score):
                best_schedule = {d: dict(t) for d, t in schedule.items()}
                best_days = days_count
                best_penalty = penalty
                best_score = score

        if best_schedule is None:
            raise RuntimeError("Uygun takvim bulunamadı. Kısıtlamaları esnetmeyi deneyin.")

        return best_schedule

    @transaction.atomic
    def veritabanina_kaydet(self, schedule, saatler_dict):
        """Üretilen takvimi SorumluTakvim (düz yapı) olarak kaydeder."""
        SorumluTakvim.objects.filter(sinav=self.sinav).delete()

        yeni_rows = []
        for day_str in sorted(schedule.keys()):
            tarih_obj = datetime.strptime(day_str, "%Y-%m-%d").date()
            for slot_no, courses in schedule[day_str].items():
                if not courses:
                    continue
                bas_str, bit_str = saatler_dict.get(slot_no, ("00:00", "00:00"))
                bas = datetime.strptime(bas_str, "%H:%M").time()
                bit = datetime.strptime(bit_str, "%H:%M").time()
                for cid in courses:
                    info = self.ders_bilgileri[cid]
                    merged = info.get("MergedComponents")
                    if merged:
                        # Birleşik kayıt → her orijinal bileşen için ayrı satır
                        for comp_info in merged.values():
                            part = comp_info.get("PartType")
                            sinav_turu = "Uygulama" if part == "P1" else ("Yazili" if part == "P2" else "")
                            yeni_rows.append(SorumluTakvim(
                                sinav=self.sinav,
                                tarih=tarih_obj,
                                oturum_no=slot_no,
                                saat_baslangic=bas,
                                saat_bitis=bit,
                                sinav_turu=sinav_turu,
                                ders_adi=comp_info["Ders"],
                            ))
                    else:
                        part = info.get("PartType")
                        sinav_turu = "Uygulama" if part == "P1" else ("Yazili" if part == "P2" else "")
                        yeni_rows.append(SorumluTakvim(
                            sinav=self.sinav,
                            tarih=tarih_obj,
                            oturum_no=slot_no,
                            saat_baslangic=bas,
                            saat_bitis=bit,
                            sinav_turu=sinav_turu,
                            ders_adi=info["Ders"],
                        ))
        SorumluTakvim.objects.bulk_create(yeni_rows, ignore_conflicts=True)