from django.db.models import Q

from dersprogrami.models import DersProgrami

REHBERLIK_DERS_ADI = "REHBERLİK VE YÖNLENDİRME"


def rehberlik_dersi_q(alan="ders__ders_adi"):
    """Rehberlik dersini adının yazımından bağımsız eşleyen filtre.

    `iexact` büyük/küçük harf dönüşümünü veritabanının locale'ine bırakır: Türkçe
    olmayan bir locale'de "i" → "I" olur, "İ" ile eşleşmez. Bu yüzden ad hem noktalı
    büyük İ ile ("REHBERLİK VE YÖNLENDİRME") hem de noktasız i ile
    ("Rehberlik ve Yönlendirme") aranır.
    """
    return Q(**{f"{alan}__iexact": REHBERLIK_DERS_ADI}) | Q(
        **{f"{alan}__iexact": "rehberlik ve yönlendirme"}
    )


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
        .filter(rehberlik_dersi_q(), ogretmen=personel)
        .select_related("sinif_sube", "ders")
        .first()
    )
    return ders.sinif_sube if ders else None


def sinif_rehber_ogretmeni(sinif_sube):
    """`sinif_sube`'nin sınıf rehber öğretmeni (Personel); yoksa None."""
    ders = (
        DersProgrami.objects.aktif()
        .filter(rehberlik_dersi_q(), sinif_sube=sinif_sube)
        .select_related("ogretmen")
        .first()
    )
    return ders.ogretmen if ders else None
