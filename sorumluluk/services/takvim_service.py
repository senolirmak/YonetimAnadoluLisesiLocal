import re
from datetime import time as _time
from itertools import groupby

from django.db import transaction
from django.db.models import Max

from sorumluluk.models import (
    SALON_KAPASITESI,
    SorumluGozetmen,
    SorumluKomisyonUyesi,
    SorumluOgrenci,
    SorumluOturmaPlani,
    SorumlulukSalon,
    SorumluSinav,
    SorumluTakvim,
)


def oturma_plani_olustur(sinav: SorumluSinav) -> None:
    """Sınav için tüm oturumlarda oturma planı oluşturur.

    SorumluTakvim'den oturum/ders bilgisini okur; her oturumda sorumlu
    öğrencileri sınıf/şube + ad soyad sırasına göre salonlara dağıtır.
    """
    salon_listesi = list(SorumlulukSalon.objects.filter(aktif=True).order_by("sira"))
    if not salon_listesi:
        raise ValueError(
            "Oturma planı oluşturulamadı: en az bir aktif salon tanımlı olmalı "
            "(bkz. Sorumluluk → Salonlar)."
        )
    salon_sayisi = len(salon_listesi)

    SorumluOturmaPlani.objects.filter(sinav=sinav).delete()

    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    yeni_kayitlar = []
    MAX_KAPASITE = SALON_KAPASITESI * salon_sayisi

    for (tarih, oturum_no), rows in groupby(takvim_rows, key=lambda r: (r.tarih, r.oturum_no)):
        rows = list(rows)
        saat_baslangic = rows[0].saat_baslangic
        saat_bitis     = rows[0].saat_bitis
        ders_adlari    = [r.ders_adi for r in rows]

        session_students = []

        for d_adi in ders_adlari:
            if " (Grup " in d_adi:
                base_adi = d_adi.split(" (Grup ")[0]
                m_grup   = re.search(r"\(Grup (\d+)\)", d_adi)
                grup_no  = int(m_grup.group(1)) if m_grup else 1
            else:
                base_adi = d_adi
                grup_no  = 1

            base_adi = (
                base_adi
                .replace(" (1. Oturum)", "")
                .replace(" (2. Oturum)", "")
                .replace(" (Uygulama)", "")
                .replace(" (Yazılı)", "")
            )

            # Takvim motoru ders_adi'na "(X. Sınıf)" eki koyar; havuzda sadece saf ders adı var.
            m_sinif = re.search(r" \((\d+)\. Sınıf\)$", base_adi)
            if m_sinif:
                query_ders_adi = base_adi[: m_sinif.start()]
                query_sinif    = int(m_sinif.group(1))
            else:
                query_ders_adi = base_adi
                query_sinif    = None

            ogr_filter = {
                "sinav": sinav,
                "aktif": True,
                "dersler__havuz_dersi__ders_adi": query_ders_adi,
            }
            if query_sinif is not None:
                ogr_filter["dersler__havuz_dersi__onceki_sinif"] = query_sinif

            course_students = list(
                SorumluOgrenci.objects
                .filter(**ogr_filter)
                .prefetch_related("dersler__havuz_dersi")
                .order_by("sinif", "sube", "adi_soyadi")
                .distinct()
            )

            if len(course_students) > MAX_KAPASITE:
                num_groups = (len(course_students) + MAX_KAPASITE - 1) // MAX_KAPASITE
                chunk_size = (len(course_students) + num_groups - 1) // num_groups
                start_idx  = (grup_no - 1) * chunk_size
                chunk      = course_students[start_idx : start_idx + chunk_size]
            else:
                chunk = course_students

            for ogr in chunk:
                ogr._display_ders_adi = d_adi
                session_students.append(ogr)

        # Tekilleştir; Uygulama oturumlarında ders sırası bozulmadan korunur
        is_uygulama_session = any("(Uygulama)" in d for d in ders_adlari)
        seen = set()
        unique_students = []
        if not is_uygulama_session:
            session_students.sort(key=lambda o: (o.sinif, o.sube, o.adi_soyadi))
        for ogr in session_students:
            if ogr.okulno not in seen:
                seen.add(ogr.okulno)
                unique_students.append(ogr)

        # Salon/sıra ataması: Uygulama → her ders ardışık salonlara; normal → sıralı
        if is_uygulama_session:
            ders_gruplar: dict = {}
            for ogr in unique_students:
                d_key = getattr(ogr, "_display_ders_adi", "")
                ders_gruplar.setdefault(d_key, []).append(ogr)
            atamalar = []
            current_salon_idx = 0  # her ders bir öncekinin bittiği salondan devam eder
            for _, grup in ders_gruplar.items():
                for i, ogr in enumerate(grup):
                    s_idx   = current_salon_idx + (i // SALON_KAPASITESI)
                    salon   = salon_listesi[min(s_idx, salon_sayisi - 1)].kod
                    sira_no = i % SALON_KAPASITESI + 1
                    atamalar.append((salon, sira_no, ogr))
                # Bu ders kaç salon kapladı?
                current_salon_idx += (len(grup) + SALON_KAPASITESI - 1) // SALON_KAPASITESI
        else:
            atamalar = []
            for i, ogr in enumerate(unique_students):
                salon_idx = i // SALON_KAPASITESI
                salon     = salon_listesi[min(salon_idx, salon_sayisi - 1)].kod
                atamalar.append((salon, i % SALON_KAPASITESI + 1, ogr))

        for salon, sira_no, ogr in atamalar:
            display_adi = getattr(ogr, "_display_ders_adi", "")
            base_adi    = display_adi.split(" (Grup ")[0] if " (Grup " in display_adi else display_adi
            base_adi    = (
                base_adi
                .replace(" (1. Oturum)", "")
                .replace(" (2. Oturum)", "")
                .replace(" (Uygulama)", "")
                .replace(" (Yazılı)", "")
            )

            m = re.search(r" \((\d+)\. Sınıf\)$", base_adi)
            if m:
                gercek_ders_adi = base_adi[: m.start()]
                sinif_seviyesi  = int(m.group(1))
            else:
                gercek_ders_adi = base_adi
                sinif_seviyesi  = None

            ogr_dersler = [
                d for d in ogr.dersler.all()
                if d.havuz_dersi.ders_adi == gercek_ders_adi
                and (d.havuz_dersi.onceki_sinif == sinif_seviyesi if sinif_seviyesi else True)
            ]
            onceki_sinif = ogr_dersler[0].havuz_dersi.onceki_sinif if ogr_dersler else None

            yeni_kayitlar.append(SorumluOturmaPlani(
                sinav=sinav,
                tarih=tarih,
                oturum_no=oturum_no,
                saat_baslangic=saat_baslangic,
                saat_bitis=saat_bitis,
                salon=salon,
                sira_no=sira_no,
                okulno=ogr.okulno,
                adi_soyadi=ogr.adi_soyadi,
                sinifsube=ogr.sinifsube,
                ders_adi=display_adi,
                onceki_sinif=onceki_sinif,
            ))

    SorumluOturmaPlani.objects.bulk_create(yeni_kayitlar, ignore_conflicts=True)


def oturumlar_verisini_hazirla(sinav: SorumluSinav) -> list[dict]:
    """Sınava ait takvim ve oturma planı kayıtlarını birleştirerek görünümler için
    ortak veri yapısı üretir."""
    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    oturma_dict = {}
    for op in SorumluOturmaPlani.objects.filter(sinav=sinav).order_by("salon", "sira_no"):
        oturma_dict.setdefault((op.tarih, op.oturum_no), []).append(op)

    # Tüm salonlar (pasif olanlar dahil) — pdf_service.py'deki salon_keys de aynı
    # sıralamayla (SorumlulukSalon.sira) üretilir, "salonN" pozisyonları eşleşmeli.
    # Pasif bir salon daha önce kullanılmışsa geçmiş sınavın verisi kaybolmasın diye
    # dahil edilir.
    salonlar = list(SorumlulukSalon.objects.order_by("sira"))

    oturumlar_veri = []
    for (tarih, oturum_no), rows in groupby(takvim_rows, key=lambda r: (r.tarih, r.oturum_no)):
        rows = list(rows)
        kayitlar = oturma_dict.get((tarih, oturum_no), [])
        veri = {
            "tarih":          tarih,
            "oturum_no":      oturum_no,
            "saat_baslangic": rows[0].saat_baslangic,
            "saat_bitis":     rows[0].saat_bitis,
            "dersler":        [r.ders_adi for r in rows],
            "ders_sayisi":    len(rows),
            # Şablonların salon sayısından bağımsız döngü kurabilmesi için:
            "salonlar":       [],
        }
        for i, salon in enumerate(salonlar, start=1):
            bu_salon = [k for k in kayitlar if k.salon == salon.kod]
            veri[f"salon{i}"] = bu_salon  # pdf_service.py: geriye dönük "salonN" erişimi
            veri["salonlar"].append({"ad": salon.ad, "kayitlar": bu_salon})
        veri["dolu_salon_var"] = any(s["kayitlar"] for s in veri["salonlar"])
        oturumlar_veri.append(veri)
    return oturumlar_veri


def ayni_dersin_ogrencilerini_grupla(sinav: SorumluSinav) -> None:
    """Oturma planı oluşturulduktan sonra aynı dersin öğrencilerini aynı salonda
    toplamak için salon/sıra numaralarını yeniden düzenler."""
    planlar = list(
        SorumluOturmaPlani.objects.filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi", "sinifsube", "adi_soyadi")
    )
    salon_isimleri = [s.kod for s in SorumlulukSalon.objects.filter(aktif=True).order_by("sira")]
    if not salon_isimleri:
        raise ValueError(
            "Öğrenciler salonlara göre gruplanamadı: en az bir aktif salon tanımlı olmalı "
            "(bkz. Sorumluluk → Salonlar)."
        )

    for (tarih, oturum_no), group in groupby(planlar, key=lambda x: (x.tarih, x.oturum_no)):
        oturum_planlari = list(group)

        is_uygulama_session = any("(Uygulama)" in op.ders_adi for op in oturum_planlari)

        if is_uygulama_session:
            def get_gercek_ders_adi(d_adi):
                base = d_adi.split(" (Grup ")[0] if " (Grup " in d_adi else d_adi
                base = base.replace(" (Uygulama)", "").replace(" (Yazılı)", "")
                m = re.search(r" \(\d+\. Sınıf\)$", base)
                if m:
                    return base[:m.start()].strip()
                return base.strip()

            oturum_planlari.sort(key=lambda op: get_gercek_ders_adi(op.ders_adi))
            courses = [list(c_group) for _, c_group in groupby(oturum_planlari, key=lambda op: get_gercek_ders_adi(op.ders_adi))]
        else:
            courses = [list(c_group) for _, c_group in groupby(oturum_planlari, key=lambda x: x.ders_adi)]

        salon_counts = {s: 0 for s in salon_isimleri}
        current_salon_idx = 0

        for c_students in courses:
            c_len = len(c_students)

            # Uygulama sınavlarında her farklı ders yeni bir salonda başlamalı
            if is_uygulama_session and salon_counts[salon_isimleri[current_salon_idx]] > 0:
                if current_salon_idx + 1 < len(salon_isimleri):
                    current_salon_idx += 1

            current_salon = salon_isimleri[current_salon_idx]

            if salon_counts[current_salon] + c_len <= SALON_KAPASITESI:
                # Dersi tamamen mevcut salona sığdır
                for op in c_students:
                    op.salon = current_salon
                    salon_counts[current_salon] += 1
                    op.sira_no = salon_counts[current_salon]
            else:
                # Mevcut salona sığmıyorsa, bir sonraki salona geçmeyi dene
                next_salon_idx = current_salon_idx + 1
                if next_salon_idx < len(salon_isimleri) and c_len <= SALON_KAPASITESI:
                    current_salon_idx = next_salon_idx
                    current_salon = salon_isimleri[current_salon_idx]
                    for op in c_students:
                        op.salon = current_salon
                        salon_counts[current_salon] += 1
                        op.sira_no = salon_counts[current_salon]
                else:
                    # Diğer salona da sığmıyorsa veya tek salondan büyükse, mecburen bölerek doldur
                    for op in c_students:
                        if salon_counts[current_salon] >= SALON_KAPASITESI and current_salon_idx + 1 < len(salon_isimleri):
                            current_salon_idx += 1
                            current_salon = salon_isimleri[current_salon_idx]
                        op.salon = current_salon
                        salon_counts[current_salon] += 1
                        op.sira_no = salon_counts[current_salon]

    if planlar:
        # Güncelleme sırasında oluşan "unique constraint" (tekil kısıtlama) hatasını
        # önlemek için mevcut kayıtları silip yeniden toplu olarak ekliyoruz.
        SorumluOturmaPlani.objects.filter(sinav=sinav).delete()
        for op in planlar:
            op.pk = None
        SorumluOturmaPlani.objects.bulk_create(planlar)


def oturumu_tasi(
    sinav: SorumluSinav,
    eski_tarih,
    yeni_tarih,
    oturum_no: int,
    yeni_bas: _time | None = None,
    yeni_bit: _time | None = None,
) -> bool:
    """Bir sınav oturumunu (takvim + komisyon + gözetmen + oturma planı) başka bir
    tarihe/saate taşır. Çakışma kontrolü çağıran tarafından yapılmış olmalıdır.

    Döndürülen bool, hedef slotta zaten kayıt olup olmadığını (birleştirme modu)
    belirtir.
    """
    hedef_dersler = set(
        SorumluTakvim.objects
        .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
        .values_list("ders_adi", flat=True)
    )
    hedef_var = bool(hedef_dersler)

    with transaction.atomic():
        SorumluTakvim.objects.filter(
            sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
        ).update(tarih=yeni_tarih)
        SorumluKomisyonUyesi.objects.filter(
            sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
        ).update(tarih=yeni_tarih)

        if hedef_var:
            # Gozetmen: hedefte zaten atanmış salonları atla
            hedef_salonlar = set(
                SorumluGozetmen.objects
                .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
                .values_list("salon", flat=True)
            )
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no,
                salon__in=hedef_salonlar,
            ).delete()
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)

            # OturmaPlani: hedef salon max sira_no'dan devam et
            salon_max = dict(
                SorumluOturmaPlani.objects
                .filter(sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no)
                .values("salon")
                .annotate(m=Max("sira_no"))
                .values_list("salon", "m")
            )
            to_move = list(
                SorumluOturmaPlani.objects
                .filter(sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no)
                .order_by("salon", "sira_no")
            )
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).delete()
            counters: dict = dict(salon_max)
            for op in to_move:
                counters[op.salon] = counters.get(op.salon, 0) + 1
                op.pk      = None
                op.tarih   = yeni_tarih
                op.sira_no = counters[op.salon]
            if to_move:
                SorumluOturmaPlani.objects.bulk_create(to_move)
        else:
            SorumluGozetmen.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=eski_tarih, oturum_no=oturum_no
            ).update(tarih=yeni_tarih)

    # Saat güncelleme — tarih işlemlerinden bağımsız, yeni_tarih üzerinden uygula
    saat_guncelleme = {}
    if yeni_bas is not None:
        saat_guncelleme["saat_baslangic"] = yeni_bas
    if yeni_bit is not None:
        saat_guncelleme["saat_bitis"] = yeni_bit

    if saat_guncelleme:
        with transaction.atomic():
            SorumluTakvim.objects.filter(
                sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no
            ).update(**saat_guncelleme)
            SorumluOturmaPlani.objects.filter(
                sinav=sinav, tarih=yeni_tarih, oturum_no=oturum_no
            ).update(**saat_guncelleme)

    return hedef_var
