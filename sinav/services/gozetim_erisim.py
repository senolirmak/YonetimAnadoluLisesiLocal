"""Öğretmenin sınav günü gözetim / sınıf listesi sayfalarına erişim kuralları.

Gözetim ekranı (sinav/views_ogretmen.py: ogretmen_sinav_gozetim) düğmeleri yalnızca
öğretmene atanmış slotlar için ve SLOT_ERISIM_KURALLARI'ndaki saat penceresinde
gösterir. Bu modül aynı kuralı düğmenin açtığı sayfaların kendisinde de uygular;
aksi hâlde adresi bilen bir öğretmen bu sayfaları her saatte açabilirdi.

  - Salon yoklaması: öğretmen o salona gözetmen atanmış (ya da nöbet devriyle
    üstlenmiş) olmalı; "gozetim" penceresi (sınavdan 8 dk önce → 40 dk sonra).
  - Sınıf listesi: öğretmen sınavdan önceki son derste o sınıfta olmalı
    (bkz. ders_sinav_eslestir.tum_siniflistesi_eslestir); "siniflistesi" penceresi.

Müdür yardımcısı, okul müdürü, staff ve superuser bu kontrollerden muaftır.
"""

from django.utils import timezone

from sinav.utils import slot_listesi_aktif_isle


def kontrolden_muaf_mi(user) -> bool:
    from okul.auth import is_ust_yonetici

    return user.is_superuser or user.is_staff or is_ust_yonetici(user)


def _simdi(bugun, simdi_str):
    if bugun is None or simdi_str is None:
        now = timezone.localtime()
        bugun = bugun or now.date()
        simdi_str = simdi_str or now.strftime("%H:%M")
    return bugun, simdi_str


def salon_gozetim_erisimi(personel, aktif_uretim, tarih, saat, salon,
                          bugun=None, simdi_str=None) -> bool:
    from sinav.models import OturmaPlani

    if not (personel and aktif_uretim and tarih and saat and salon):
        return False

    atanmis = OturmaPlani.objects.filter(
        uretim=aktif_uretim, tarih=tarih, saat=saat, salon=salon, gozetmen_fk=personel
    ).exists() or any(
        s["tarih"] == tarih and s["saat"] == saat and any(x["ham"] == salon for x in s["salonlar"])
        for s in nobetci_gozetim_slotlari(personel, aktif_uretim)
    )
    if not atanmis:
        return False

    bugun, simdi_str = _simdi(bugun, simdi_str)
    slot = {"tarih": tarih, "saat": saat}
    slot_listesi_aktif_isle([slot], "gozetim", bugun, simdi_str)
    return slot["aktif"]


def sinif_listesi_erisimi(personel, aktif_uretim, tarih, saat, sinifsube, oturum=None,
                          bugun=None, simdi_str=None) -> bool:
    from sinav.services.ders_sinav_eslestir import tum_siniflistesi_eslestir

    if not (personel and aktif_uretim and tarih and saat and sinifsube):
        return False

    eslesen = [
        dict(s)
        for s in tum_siniflistesi_eslestir(aktif_uretim).get(personel.pk, [])
        if s["tarih"] == tarih and s["saat"] == saat and s["sinifsube"] == sinifsube
        and (oturum is None or s["oturum"] == oturum)
    ]
    bugun, simdi_str = _simdi(bugun, simdi_str)
    slot_listesi_aktif_isle(eslesen, "siniflistesi", bugun, simdi_str)
    return any(s["aktif"] for s in eslesen)


def nobetci_gozetim_slotlari(personel, aktif_uretim):
    """
    Devamsız öğretmen yerine sınıfa giren nöbetçi öğretmenin
    üstlendiği sınav gözetim slotlarını döndürür.
    """
    from nobet.models import NobetGecmisi
    from sinav.models import OturmaPlani, Takvim
    from sinav.utils import salon_goster

    if not (personel and aktif_uretim):
        return []

    try:
        nobet_ogr = personel.ogretmen
    except Exception:
        return []

    gecmisler = list(
        NobetGecmisi.objects
        .filter(ogretmen=nobet_ogr, atandi=1, sinif__isnull=False)
        .values("tarih", "saat", "sinif")
    )
    if not gecmisler:
        return []

    sinav_tarihler = set(
        OturmaPlani.objects
        .filter(uretim=aktif_uretim)
        .values_list("tarih", flat=True)
        .distinct()
    )

    slotlar = []
    seen = set()

    for g in gecmisler:
        tarih = g["tarih"].date() if hasattr(g["tarih"], "date") else g["tarih"]
        if tarih not in sinav_tarihler:
            continue

        sinif_str = (g["sinif"] or "").strip()
        parts = sinif_str.split("/")
        if len(parts) != 2:
            continue
        try:
            sinif_no = int(parts[0])
        except ValueError:
            continue
        sube_str = parts[1].strip()

        ders_no = g["saat"]
        if ders_no:
            sinav_saatleri = set(
                Takvim.objects
                .filter(uretim=aktif_uretim, tarih=tarih,
                        ders_saati__derssaati_no=ders_no)
                .values_list("saat", flat=True)
                .distinct()
            )
        else:
            sinav_saatleri = None

        op_filtre = dict(
            uretim=aktif_uretim,
            tarih=tarih,
            salon_sinif_sube__sinif=sinif_no,
            salon_sinif_sube__sube=sube_str,
        )
        if sinav_saatleri is not None:
            op_filtre["saat__in"] = sinav_saatleri

        op_qs = (
            OturmaPlani.objects
            .filter(**op_filtre)
            .values(
                "tarih", "saat", "oturum", "salon",
                "salon_sinif_sube__sinif",
                "salon_sinif_sube__sube",
            )
            .distinct()
            .order_by("tarih", "saat", "oturum")
        )

        for row in op_qs:
            key = (row["tarih"], row["saat"], row["oturum"])
            if key in seen:
                continue
            seen.add(key)
            sinif = row["salon_sinif_sube__sinif"]
            sube  = row["salon_sinif_sube__sube"]
            salon = row["salon"] or ""
            slotlar.append({
                "tarih":      row["tarih"],
                "saat":       row["saat"],
                "oturum":     row["oturum"],
                "salonlar":   [{"ham": salon, "ad": salon_goster(salon)}] if salon else [],
                "sinifsube":  f"{sinif}/{sube}" if sinif and sube else sinif_str,
                "nobet_devir": True,
            })

    return sorted(slotlar, key=lambda x: (x["tarih"], x["saat"], x["oturum"]))
