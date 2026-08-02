"""Ana sınav yoklama raporu (mazeret DEĞİL — asıl sınav yoklaması) için hesaplama."""
import datetime as _dt
from collections import defaultdict

from django.db.models import Q

from sinav.models import OturmaPlani, SinavSalonYoklama, Takvim

_TR_AYLAR = {
    "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4,
    "mayıs": 5, "haziran": 6, "temmuz": 7, "ağustos": 8,
    "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
}


def yoklama_dersleri(aktif_uretim) -> list[dict]:
    """Filtre seçenekleri için Takvim FK üzerinden ders id + adı listesi."""
    if not aktif_uretim:
        return []
    return list(
        Takvim.objects
        .filter(uretim=aktif_uretim, ders__isnull=False)
        .select_related("ders")
        .values("ders_id", "ders__ders_adi")
        .distinct()
        .order_by("ders__ders_adi")
    )


def yoklama_satirlari_hesapla(aktif_uretim, filtre_seviye: str, filtre_ders_adi_base: str | None) -> list[dict]:
    """(seviye, ders_adi, tarih) bazında salon-bağımsız yoklama istatistiklerini hesaplar."""
    if not aktif_uretim:
        return []

    op_q = Q(uretim=aktif_uretim) & ~Q(ders_adi="")
    if filtre_seviye:
        op_q &= Q(sinifsube__startswith=f"{filtre_seviye}/")
    if filtre_ders_adi_base:
        op_q &= Q(ders_adi__istartswith=filtre_ders_adi_base)

    # (seviye, ders_adi, tarih) → okulno seti  (benzersiz öğrenci sayımı için)
    # (seviye, ders_adi, tarih) → set of (saat, salon)  (yoklama linkleri için)
    group_okulno: dict = defaultdict(set)
    group_salonlar: dict = defaultdict(set)
    for r in OturmaPlani.objects.filter(op_q).values(
        "sinifsube", "ders_adi", "tarih", "saat", "salon", "okulno"
    ):
        seviye = r["sinifsube"].split("/")[0] if "/" in r["sinifsube"] else r["sinifsube"]
        grp_key = (seviye, r["ders_adi"], r["tarih"])
        group_okulno[grp_key].add(r["okulno"])
        group_salonlar[grp_key].add((r["saat"], r["salon"]))

    # (tarih, okulno) → (seviye, ders_adi)  — yoklama eşleştirmesi için ters indeks
    okulno_to_group: dict = {}
    for (seviye, ders_adi, tarih), okulno_set in group_okulno.items():
        for okulno in okulno_set:
            okulno_to_group[(tarih, okulno)] = (seviye, ders_adi)

    # (seviye, ders_adi, tarih) → {durum: sayı}
    yoklama_ozet: dict = defaultdict(lambda: defaultdict(int))
    for y in SinavSalonYoklama.objects.filter(uretim=aktif_uretim).values("tarih", "okulno", "durum"):
        grp = okulno_to_group.get((y["tarih"], y["okulno"]))
        if grp:
            seviye, ders_adi = grp
            yoklama_ozet[(seviye, ders_adi, y["tarih"])][y["durum"]] += 1

    satirlar = []
    for key in sorted(group_okulno.keys()):
        seviye, ders_adi, tarih = key
        toplam = len(group_okulno[key])
        yk     = yoklama_ozet.get(key, {})
        mevcut = yk.get("mevcut", 0)
        yok    = yk.get("yok", 0)
        gec    = yk.get("gec", 0)
        satirlar.append({
            "seviye":         seviye,
            "ders_adi":       ders_adi,
            "tarih":          tarih,
            "toplam":         toplam,
            "mevcut":         mevcut,
            "yok":            yok,
            "gec":            gec,
            "yoklama_alindi": bool(yk),
            "eksik":          toplam - (mevcut + yok + gec),
            "salonlar":       sorted(group_salonlar.get(key, [])),
        })
    return satirlar


def yoklama_ogrenci_listesi_hesapla(aktif_uretim, filtre_seviye: str, filtre_ders_adi_base: str | None) -> list[dict]:
    """Her iki filtre de seçiliyse öğrenci bazlı detay listesi döner."""
    if not (aktif_uretim and filtre_seviye and filtre_ders_adi_base):
        return []

    op_rows = list(
        OturmaPlani.objects
        .filter(
            uretim=aktif_uretim,
            sinifsube__startswith=f"{filtre_seviye}/",
            ders_adi__istartswith=filtre_ders_adi_base,
        )
        .values("sinifsube", "okulno", "adi_soyadi")
        .distinct()
        .order_by("sinifsube", "okulno")
    )
    yoklama_durumu = dict(
        SinavSalonYoklama.objects
        .filter(uretim=aktif_uretim)
        .values_list("okulno", "durum")
    )
    return [
        {
            "sinifsube":  r["sinifsube"],
            "okulno":     r["okulno"],
            "adi_soyadi": r["adi_soyadi"],
            "durum":      yoklama_durumu.get(r["okulno"], ""),
        }
        for r in op_rows
    ]


def turkce_tarih_ayristir(tarih_str: str):
    """'10 Nisan 2026' formatındaki metni datetime.date'e çevirir; zaten ISO
    formatındaysa (yıl ile başlıyorsa) olduğu gibi döner; ayrıştırılamazsa None."""
    if not tarih_str or tarih_str[:4].isdigit():
        return tarih_str
    try:
        parcalar = tarih_str.split()
        gun, ay_str, yil = int(parcalar[0]), parcalar[1].lower(), int(parcalar[2])
        return _dt.date(yil, _TR_AYLAR[ay_str], gun)
    except (ValueError, KeyError, IndexError):
        return None


def yok_ogrenciler_gruplu(aktif_uretim, seviye: str, ders_adi: str, tarih) -> list[dict]:
    """Belirli (seviye, ders_adi, tarih) için 'yok' durumundaki öğrencileri şube
    bazında gruplar."""
    if not (aktif_uretim and seviye and ders_adi and tarih):
        return []

    op_q = (
        OturmaPlani.objects
        .filter(
            uretim=aktif_uretim,
            sinifsube__startswith=f"{seviye}/",
            ders_adi=ders_adi,
            tarih=tarih,
        )
        .values("okulno", "adi_soyadi", "sinifsube")
        .distinct()
        .order_by("sinifsube", "okulno")
    )
    okulno_bilgi = {r["okulno"]: r for r in op_q}

    yok_okulnolar = set(
        SinavSalonYoklama.objects
        .filter(
            uretim=aktif_uretim,
            tarih=tarih,
            durum="yok",
            okulno__in=list(okulno_bilgi.keys()),
        )
        .values_list("okulno", flat=True)
        .distinct()
    )

    sube_map: dict = defaultdict(list)
    for okulno, bilgi in sorted(okulno_bilgi.items(), key=lambda x: (x[1]["sinifsube"], x[0])):
        if okulno in yok_okulnolar:
            sube_map[bilgi["sinifsube"]].append({
                "okulno":    okulno,
                "adi_soyadi": bilgi["adi_soyadi"],
            })

    return [
        {"sinifsube": sube, "ogrenciler": ogrenciler}
        for sube, ogrenciler in sorted(sube_map.items())
    ]
