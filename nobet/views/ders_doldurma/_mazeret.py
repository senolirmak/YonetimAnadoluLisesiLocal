"""
Mazeret salon context — template'e gönderilecek veriyi hazırlar.
"""
from ...models import MazeretSalonGorevi, NobetGorevi, MAZERET_DERSLER


def mazeret_ctx(target_date, gorev_date, day_name_en, absent_teacher_ids):
    """
    Mazeret1 / Mazeret2 salonları için template context'i döner.

    absent_teacher_ids: devamsız personel PK listesi (nöbetçi listesinden hariç tutulur).
    """
    absent_set = set(absent_teacher_ids)

    if gorev_date:
        duty_qs = NobetGorevi.objects.filter(
            uygulama_tarihi=gorev_date, nobet_gun=day_name_en
        ).select_related("ogretmen__personel")
        nobetciler = [
            {"id": r.ogretmen.pk, "adi_soyadi": r.ogretmen.personel.adi_soyadi}
            for r in duty_qs
            if r.ogretmen.personel.pk not in absent_set
        ]
    else:
        nobetciler = []

    mevcut = {}
    for g in MazeretSalonGorevi.objects.filter(tarih=target_date).select_related(
        "ogretmen__personel"
    ):
        mevcut.setdefault(g.salon, {})[g.saat] = {
            "ogretmen_pk": g.ogretmen.pk,
            "adi_soyadi": g.ogretmen.personel.adi_soyadi,
        }

    salonlar = []
    for salon_ad in ("Mazeret1", "Mazeret2"):
        salon_mevcut = mevcut.get(salon_ad, {})
        dersler = [
            {
                "saat": d,
                "ogretmen_pk": salon_mevcut[d]["ogretmen_pk"] if d in salon_mevcut else None,
                "adi_soyadi":  salon_mevcut[d]["adi_soyadi"]  if d in salon_mevcut else None,
            }
            for d in MAZERET_DERSLER
        ]
        salonlar.append({"ad": salon_ad, "acik": bool(salon_mevcut), "dersler": dersler})

    return {"mazeret_salonlar": salonlar, "mazeret_nobetciler": nobetciler}
