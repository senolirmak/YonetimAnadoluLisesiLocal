from dersprogrami.models import DersProgrami

REHBERLIK_DERS_ADI = "REHBERLİK VE YÖNLENDİRME"


def rehberlik_sinif_sube(user):
    """Kullanıcının sınıf rehber öğretmeni olduğu SinifSube'yi döner; yoksa None.

    Sınıf rehber öğretmeni ayrı bir tabloda tutulmaz: aktif ders programında o sınıfa
    'REHBERLİK VE YÖNLENDİRME' dersini veren öğretmendir.
    """
    try:
        personel = user.personel
    except Exception:
        return None
    if personel is None:
        return None
    ders = (
        DersProgrami.objects.aktif()
        .filter(ogretmen=personel, ders__ders_adi__iexact=REHBERLIK_DERS_ADI)
        .select_related("sinif_sube", "ders")
        .first()
    )
    return ders.sinif_sube if ders else None


def sinif_rehber_ogretmeni(sinif_sube):
    """`sinif_sube`'nin sınıf rehber öğretmeni (Personel); yoksa None."""
    ders = (
        DersProgrami.objects.aktif()
        .filter(sinif_sube=sinif_sube, ders__ders_adi__iexact=REHBERLIK_DERS_ADI)
        .select_related("ogretmen")
        .first()
    )
    return ders.ogretmen if ders else None
