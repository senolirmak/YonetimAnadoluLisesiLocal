"""Öğrencinin `aktif` bayrağını, onu pasife alan kayıtlara göre günceller.

Bir öğrenci şu kayıtlardan herhangi biri varken pasif kalır:
  - okuldan ayrılma kaydı (`OgrenciAyrilma`)
  - tasdikname kaydı (`secmelidersler.OgrenciTasdikname`)
  - uygulanmış sene sonu geçişinde mezun durumu (`senesonu.SeneSonuOgrenciGecisi`)

İkinci sınıf tekrarı hem tasdikname hem ayrılma kaydı açar (bkz.
secmelidersler/services/sinif_tekrari.py); bu yüzden kayıtlardan biri silindiğinde
öğrenci doğrudan aktif yapılmamalı, bu modül kullanılmalı.
"""


def pasif_sebepleri(ogrenci) -> list[str]:
    from secmelidersler.models import OgrenciTasdikname
    from senesonu.models import SeneSonuOgrenciGecisi

    from ..models import OgrenciAyrilma

    sebepler = []
    if OgrenciAyrilma.objects.filter(ogrenci=ogrenci).exists():
        sebepler.append("okuldan ayrılma kaydı")
    if OgrenciTasdikname.objects.filter(ogrenci=ogrenci).exists():
        sebepler.append("tasdikname kaydı")
    if SeneSonuOgrenciGecisi.objects.filter(
        ogrenci=ogrenci, durum="mezun", gecis__uygulandi=True
    ).exists():
        sebepler.append("mezuniyet")
    return sebepler


def aktifligi_guncelle(ogrenci) -> list[str]:
    """Pasif sebebi kalmadıysa öğrenciyi aktif, varsa pasif yapar.
    Kalan sebepleri döner (boş liste → öğrenci aktif)."""
    sebepler = pasif_sebepleri(ogrenci)
    yeni = not sebepler
    if ogrenci.aktif != yeni:
        ogrenci.aktif = yeni
        ogrenci.save(update_fields=["aktif"])
    return sebepler
