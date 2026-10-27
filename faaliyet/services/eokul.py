"""Öğrencilerin faaliyet katılımlarının e-Okul'a işlenip işlenmediğinin takibi."""

from django.db import transaction

from ..models import Faaliyet, FaaliyetEokulKaydi


class EokulIsaretHatasi(ValueError):
    pass


def eokul_islenenler(faaliyet_idleri):
    """{(faaliyet_id, ogrenci_id)} — e-Okul'a işlenmiş katılımlar (tek sorgu)."""
    if not faaliyet_idleri:
        return set()
    return set(
        FaaliyetEokulKaydi.objects.filter(faaliyet_id__in=faaliyet_idleri).values_list(
            "faaliyet_id", "ogrenci_id"
        )
    )


def eokul_isaretle(faaliyet_id, ogrenci_id, islendi, isleyen_adi=""):
    """Katılımı e-Okul'a işlendi/işlenmedi olarak işaretler.

    Yalnızca tamamlanmış (onaylanmış + devamsızlığı girilmiş) faaliyetlerde ve
    faaliyete katılan öğrenciler için izin verilir; aksi halde ``EokulIsaretHatasi``.
    """
    faaliyet = Faaliyet.objects.filter(
        pk=faaliyet_id, durum=Faaliyet.DURUM_ONAYLANDI, devamsizlik_girildi=True
    ).first()
    if faaliyet is None:
        raise EokulIsaretHatasi("Faaliyet bulunamadı ya da henüz tamamlanmadı.")
    if not faaliyet.ogrenciler.filter(pk=ogrenci_id).exists():
        raise EokulIsaretHatasi("Öğrenci bu faaliyete katılmamış.")

    if islendi:
        FaaliyetEokulKaydi.objects.get_or_create(
            faaliyet=faaliyet, ogrenci_id=ogrenci_id, defaults={"isleyen_adi": isleyen_adi}
        )
    else:
        FaaliyetEokulKaydi.objects.filter(faaliyet=faaliyet, ogrenci_id=ogrenci_id).delete()
    return islendi


@transaction.atomic
def eokul_toplu_isaretle(faaliyet_idleri, ogrenci_id, islendi, isleyen_adi=""):
    """Öğrencinin birden çok faaliyetini birlikte işaretler; biri geçersizse hiçbiri kaydedilmez."""
    for faaliyet_id in faaliyet_idleri:
        eokul_isaretle(faaliyet_id, ogrenci_id, islendi, isleyen_adi=isleyen_adi)
    return islendi

