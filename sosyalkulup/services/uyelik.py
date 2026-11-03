"""Sınıf bazında öğrenci kulüp üyeliklerini okuma ve kaydetme."""

from django.db import transaction
from django.db.models import Q

from ogrenci.models import Ogrenci

from ..models import KulupUyelik, SosyalKulup


def sinif_ogrencileri(sinif, sube):
    """Sınıf/şubedeki aktif öğrenciler (okul no sırasıyla)."""
    return Ogrenci.objects.filter(sinif=sinif, sube__iexact=sube, aktif=True).order_by("okulno")


def sinif_uyelikleri(sinif, sube, egitim_yili):
    """Sınıftaki aktif öğrencilerin `egitim_yili` üyeliklerini {ogrenci_id: KulupUyelik} olarak döner."""
    return {
        u.ogrenci_id: u
        for u in KulupUyelik.objects.filter(
            egitim_yili=egitim_yili, ogrenci__in=sinif_ogrencileri(sinif, sube)
        ).select_related("kulup")
    }


def secilebilir_kulupler(mevcut_kulup_idleri=()):
    """Aktif kulüpler + öğrencinin zaten üye olduğu (sonradan pasife alınmış) kulüpler."""
    return SosyalKulup.objects.filter(Q(aktif=True) | Q(pk__in=list(mevcut_kulup_idleri)))


@transaction.atomic
def sinif_kuluplerini_kaydet(sinif, sube, secimler, egitim_yili):
    """`secimler` = {ogrenci_id: kulup_id veya None}. Yalnızca bu sınıfın aktif öğrencileri
    işlenir; başka sınıftan gelen id'ler sessizce yok sayılır.

    - kulup_id None → öğrencinin bu yılki üyeliği silinir.
    - Kulüp değişirse üyelik yeni kulübe taşınır ve görev "Üye"ye döner.
    - Kulüp aynıysa (görev dahil) hiçbir şey değişmez.

    Geçersiz/pasif kulüp seçimi `ValueError` fırlatır (öğrencinin zaten üye olduğu pasif
    kulüp aynen korunabilir). Dönüş: (eklenen, guncellenen, silinen) sayıları.
    """
    ogrenci_idleri = set(sinif_ogrencileri(sinif, sube).values_list("pk", flat=True))
    mevcut = sinif_uyelikleri(sinif, sube, egitim_yili)
    aktif_kulupler = set(SosyalKulup.objects.filter(aktif=True).values_list("pk", flat=True))

    eklenen = guncellenen = silinen = 0
    for ogrenci_id, kulup_id in secimler.items():
        if ogrenci_id not in ogrenci_idleri:
            continue
        uyelik = mevcut.get(ogrenci_id)
        if kulup_id is None:
            if uyelik:
                uyelik.delete()
                silinen += 1
            continue
        # Pasif kulübe yeni üye alınmaz; zaten üye olan öğrenci kalabilir.
        ayni_kulup = uyelik is not None and uyelik.kulup_id == kulup_id
        if kulup_id not in aktif_kulupler and not ayni_kulup:
            raise ValueError("Geçersiz kulüp seçimi.")
        if uyelik is None:
            KulupUyelik.objects.create(
                ogrenci_id=ogrenci_id, kulup_id=kulup_id, egitim_yili=egitim_yili
            )
            eklenen += 1
        elif uyelik.kulup_id != kulup_id:
            uyelik.kulup_id = kulup_id
            uyelik.gorev = KulupUyelik.GOREV_UYE
            uyelik.save(update_fields=["kulup", "gorev"])
            guncellenen += 1
    return eklenen, guncellenen, silinen
