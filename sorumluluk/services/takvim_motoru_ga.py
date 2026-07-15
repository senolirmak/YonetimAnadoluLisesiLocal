import random
from collections import defaultdict
from datetime import timedelta

from sorumluluk.models import SALON_KAPASITESI, SALON_SAYISI
from sorumluluk.services.takvim_motoru import DjangoSinavTakvimiMotoru


class DjangoSinavTakvimiMotoruGA(DjangoSinavTakvimiMotoru):
    """Genetik algoritma tabanlı sınav takvimi motoru.

    Veri yükleme, çakışma grafiği, ceza/puan fonksiyonları ve DB'ye kaydetme
    DjangoSinavTakvimiMotoru'dan aynen miras alınır (drop-in değişim).
    Sadece `optimize_edilmis_takvim` metodu, rastgele-yeniden-başlatma yerine
    gerçek bir GA (seçilim + çaprazlama + mutasyon + elitizm) ile değiştirilir.

    Kromozom: dersleri (cid) temsil eden bir permütasyon. Yerleştirme (decode),
    orijinal motordaki aç gözlü slot-doldurma mantığının aynısını kullanır;
    fark, aynı öğrenci-sayısına sahip dersler arasındaki öncelik sırasının artık
    set/hash sırasına değil, kromozomun kendisine bağlı olmasıdır — böylece
    çaprazlama/mutasyon sonucu gerçekten farklı takvimler üretilebilir.
    """

    def _decode(self, courses_order, max_daily_exams, slot_max_ders):
        order_index = {c: i for i, c in enumerate(courses_order)}
        neighbor_map = {c: set(self._conflict_graph.neighbors(c)) for c in courses_order}

        schedule = defaultdict(lambda: defaultdict(list))
        unscheduled = set(courses_order)
        cur_date = self._next_valid_exam_day(self.baslangic_tarihi)

        while unscheduled:
            day_str = cur_date.strftime("%Y-%m-%d")
            daily_counts = defaultdict(int)

            for slot in self.TIME_SLOTS:
                candidates = sorted(
                    unscheduled,
                    key=lambda c: (self.ders_bilgileri[c]["OgrenciSayisi"], -order_index[c]),
                    reverse=True,
                )

                for course in candidates:
                    if slot_max_ders is not None:
                        current_count = sum(
                            len(self.ders_bilgileri[sc].get("MergedComponents", [1]))
                            for sc in schedule[day_str][slot]
                        )
                        new_count = len(self.ders_bilgileri[course].get("MergedComponents", [1]))
                        if current_count + new_count > slot_max_ders:
                            continue

                    if any(other in neighbor_map[course] for other in schedule[day_str][slot]):
                        continue

                    c_info = self.ders_bilgileri[course]
                    is_uygulama = (c_info.get("PartType") == "P1")

                    if len(schedule[day_str][slot]) > 0:
                        first_c_info = self.ders_bilgileri[schedule[day_str][slot][0]]
                        if is_uygulama != (first_c_info.get("PartType") == "P1"):
                            continue

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

                    if is_uygulama:
                        gercek_ders_students = defaultdict(int)
                        for sc in schedule[day_str][slot]:
                            gercek_ders_students[self.ders_bilgileri[sc]["GercekDersAdi"]] += self.ders_bilgileri[sc]["OgrenciSayisi"]
                        gercek_ders_students[self.ders_bilgileri[course]["GercekDersAdi"]] += self.ders_bilgileri[course]["OgrenciSayisi"]

                        total_salons = 0
                        for count in gercek_ders_students.values():
                            total_salons += (count + self._SALON_KAPASITESI - 1) // self._SALON_KAPASITESI
                        if total_salons > self._SALON_SAYISI:
                            continue
                    else:
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
                return None

            cur_date = self._next_valid_exam_day(cur_date + timedelta(days=1))

        return {d: dict(t) for d, t in schedule.items()}

    def _fitness(self, schedule, max_daily_exams):
        """Küçük olan daha iyi. (gün sayısı, ceza, -puan) sözlüksel sırayla karşılaştırılır."""
        if schedule is None:
            return (float("inf"), float("inf"), float("inf"))
        days = len(schedule)
        penalty = self._schedule_penalty(schedule, max_daily_exams=max_daily_exams)
        score = self._schedule_score(schedule)
        return (days, penalty, -score)

    @staticmethod
    def _order_crossover(parent1, parent2):
        """OX1: permütasyonlar için sıra çaprazlaması."""
        size = len(parent1)
        a, b = sorted(random.sample(range(size), 2))
        child = [None] * size
        segment = parent1[a:b]
        child[a:b] = segment
        segment_set = set(segment)

        fill_genes = [g for g in parent2 if g not in segment_set]
        idx = 0
        for i in list(range(b, size)) + list(range(0, a)):
            child[i] = fill_genes[idx]
            idx += 1
        return child

    @staticmethod
    def _swap_mutate(chromosome, mutation_rate):
        chromosome = chromosome[:]
        if random.random() < mutation_rate:
            n_swaps = random.randint(1, 3)
            size = len(chromosome)
            for _ in range(n_swaps):
                i, j = random.sample(range(size), 2)
                chromosome[i], chromosome[j] = chromosome[j], chromosome[i]
        return chromosome

    @staticmethod
    def _tournament_select(population, fitnesses, tournament_size):
        contenders = random.sample(range(len(population)), min(tournament_size, len(population)))
        best_idx = min(contenders, key=lambda i: fitnesses[i])
        return population[best_idx]

    def optimize_edilmis_takvim(
        self, max_iter=800, max_daily_exams=2, slot_max_ders=6,
        population_size=40, elite_ratio=0.1, mutation_rate=0.25, tournament_size=3,
    ):
        """Genetik algoritma: Initialize Population -> Evaluate Fitness -> Selection
        -> Crossover -> Mutation -> Elitism -> Repeat until convergence/max generations.

        `max_iter`, orijinal motorla aynı arayüzü korumak için toplam decode
        (uygunluk değerlendirmesi) bütçesini belirler: generations ~= max_iter / population_size.
        """
        self._conflict_graph = self.cakisma_grafigi_olustur()
        courses_all = list(self._conflict_graph.nodes())
        if not courses_all:
            raise RuntimeError("Öğrencilere atanmış hiçbir ders bulunamadı.")

        self._SALON_KAPASITESI = SALON_KAPASITESI
        self._SALON_SAYISI = SALON_SAYISI

        base_order = sorted(
            courses_all,
            key=lambda c: (self._conflict_graph.degree(c), self.ders_bilgileri[c]["OgrenciSayisi"]),
            reverse=True,
        )

        generations = max(15, max_iter // max(1, population_size))
        elite_count = max(1, int(population_size * elite_ratio))

        population = [base_order[:]]
        while len(population) < population_size:
            perm = courses_all[:]
            random.shuffle(perm)
            population.append(perm)

        best_schedule = None
        best_fitness = (float("inf"), float("inf"), float("inf"))

        for _generation in range(generations):
            decoded = [self._decode(chromo, max_daily_exams, slot_max_ders) for chromo in population]
            fitnesses = [self._fitness(sch, max_daily_exams) for sch in decoded]

            for sch, fit in zip(decoded, fitnesses):
                if fit < best_fitness:
                    best_fitness = fit
                    best_schedule = sch

            ranked = sorted(range(len(population)), key=lambda i: fitnesses[i])
            next_population = [population[i][:] for i in ranked[:elite_count]]

            while len(next_population) < population_size:
                parent1 = self._tournament_select(population, fitnesses, tournament_size)
                parent2 = self._tournament_select(population, fitnesses, tournament_size)
                child = self._order_crossover(parent1, parent2)
                child = self._swap_mutate(child, mutation_rate)
                next_population.append(child)

            population = next_population

        if best_schedule is None:
            raise RuntimeError("Uygun takvim bulunamadı. Kısıtlamaları esnetmeyi deneyin.")

        return best_schedule
