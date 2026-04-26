import re
from itertools import groupby

from sorumluluk.models import (
    SALON_KAPASITESI,
    SALON_SAYISI,
    SorumluOgrenci,
    SorumluOturmaPlani,
    SorumluSinav,
    SorumluTakvim,
)


def oturma_plani_olustur(sinav: SorumluSinav) -> None:
    """Sınav için tüm oturumlarda oturma planı oluşturur.

    SorumluTakvim'den oturum/ders bilgisini okur; her oturumda sorumlu
    öğrencileri sınıf/şube + ad soyad sırasına göre salonlara dağıtır.
    """
    SorumluOturmaPlani.objects.filter(sinav=sinav).delete()

    takvim_rows = list(
        SorumluTakvim.objects
        .filter(sinav=sinav)
        .order_by("tarih", "oturum_no", "ders_adi")
    )

    yeni_kayitlar = []
    MAX_KAPASITE = SALON_KAPASITESI * SALON_SAYISI

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
                    salon   = f"Sorumluluk{min(s_idx + 1, SALON_SAYISI)}"
                    sira_no = i % SALON_KAPASITESI + 1
                    atamalar.append((salon, sira_no, ogr))
                # Bu ders kaç salon kapladı?
                current_salon_idx += (len(grup) + SALON_KAPASITESI - 1) // SALON_KAPASITESI
        else:
            atamalar = []
            for i, ogr in enumerate(unique_students):
                salon_idx = i // SALON_KAPASITESI
                salon     = f"Sorumluluk{min(salon_idx + 1, SALON_SAYISI)}"
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
