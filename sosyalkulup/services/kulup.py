"""Kulüp, danışman ve üye listeleri (okuma)."""

from django.db.models import Count, Prefetch, Q

from ..models import KulupDanisman, KulupUyelik, SosyalKulup


def _personel(user):
    try:
        return user.personel
    except Exception:
        return None


def ogretmen_kulupleri(user, egitim_yili):
    """Kullanıcının `egitim_yili`'nda danışmanı olduğu kulüpler."""
    personel = _personel(user)
    if personel is None or egitim_yili is None:
        return SosyalKulup.objects.none()
    return SosyalKulup.objects.filter(
        danismanlar__ogretmen=personel, danismanlar__egitim_yili=egitim_yili
    ).order_by("ad")


def kulup_danismani_mi(user, kulup, egitim_yili):
    personel = _personel(user)
    return (
        personel is not None
        and egitim_yili is not None
        and KulupDanisman.objects.filter(
            ogretmen=personel, kulup=kulup, egitim_yili=egitim_yili
        ).exists()
    )


def kulup_danismanlari(kulup, egitim_yili):
    return (
        KulupDanisman.objects.filter(kulup=kulup, egitim_yili=egitim_yili)
        .select_related("ogretmen")
        .order_by("ogretmen__adi_soyadi")
    )


def kulup_uyeleri(kulup, egitim_yili):
    """Kulübün `egitim_yili` üyesi olan aktif öğrenciler (sınıf/şube/no sırasıyla)."""
    return (
        KulupUyelik.objects.filter(kulup=kulup, egitim_yili=egitim_yili, ogrenci__aktif=True)
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )


def kulup_ozetleri(egitim_yili):
    """Tüm kulüpler + `egitim_yili` danışmanları ve aktif üye sayısı."""
    return (
        SosyalKulup.objects.annotate(
            uye_sayisi=Count(
                "uyelikler",
                filter=Q(uyelikler__egitim_yili=egitim_yili, uyelikler__ogrenci__aktif=True),
            )
        )
        .prefetch_related(
            Prefetch(
                "danismanlar",
                queryset=KulupDanisman.objects.filter(egitim_yili=egitim_yili)
                .select_related("ogretmen")
                .order_by("ogretmen__adi_soyadi"),
                to_attr="yil_danismanlari",
            )
        )
        .order_by("-aktif", "ad")
    )
