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


def sinif_kulup_gruplari(sinif, sube, egitim_yili):
    """Sınıftaki aktif öğrencileri kulüplerine göre gruplar.

    Dönüş: (gruplar, kulupsuzler)
      gruplar    = [(SosyalKulup, [(Ogrenci, KulupUyelik), ...]), ...]  kulüp adına göre
      kulupsuzler = [Ogrenci, ...]  kulüp seçilmemiş öğrenciler
    Her grupta öğrenciler okul no sırasındadır.
    """
    uyelikler = sinif_uyelikleri(sinif, sube, egitim_yili)
    gruplar, kulupsuzler = {}, []
    for ogr in sinif_ogrencileri(sinif, sube):  # okulno sıralı
        u = uyelikler.get(ogr.pk)
        if u is None:
            kulupsuzler.append(ogr)
        else:
            gruplar.setdefault(u.kulup, []).append((ogr, u))
    sirali = sorted(gruplar.items(), key=lambda kv: (kv[0].ad, kv[0].pk))
    return sirali, kulupsuzler


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


class KulupGorevHatasi(ValueError):
    pass


@transaction.atomic
def kulup_gorevlerini_kaydet(kulup, egitim_yili, secimler):
    """Kulüp üyelerinin görevlerini toplu kaydeder. `secimler` = {uyelik_id: gorev}.

    Yalnızca bu kulübün `egitim_yili` üyelikleri (aktif öğrenciler) işlenir; başka
    üyelik id'leri yok sayılır. "Üye" dışındaki her görev kulüpte en fazla bir öğrencide
    olabilir. Hata varsa `KulupGorevHatasi` fırlatılır ve hiçbir şey kaydedilmez.
    Dönüş: değişen kayıt sayısı.
    """
    gecerli = dict(KulupUyelik.GOREV_CHOICES)
    uyelikler = {
        u.pk: u
        for u in KulupUyelik.objects.filter(
            kulup=kulup, egitim_yili=egitim_yili, ogrenci__aktif=True
        ).select_related("ogrenci")
    }

    yeni = {pk: u.gorev for pk, u in uyelikler.items()}
    for uyelik_id, gorev in secimler.items():
        if uyelik_id not in uyelikler:
            continue
        if gorev not in gecerli:
            raise KulupGorevHatasi("Geçersiz görev seçimi.")
        yeni[uyelik_id] = gorev

    sahipler = {}
    for pk, gorev in yeni.items():
        if gorev == KulupUyelik.GOREV_UYE:
            continue
        if gorev in sahipler:
            raise KulupGorevHatasi(
                f"'{gecerli[gorev]}' görevi yalnızca bir öğrenciye verilebilir "
                f"({uyelikler[sahipler[gorev]].ogrenci} ve {uyelikler[pk].ogrenci})."
            )
        sahipler[gorev] = pk

    degisen = 0
    for pk, gorev in yeni.items():
        u = uyelikler[pk]
        if u.gorev != gorev:
            u.gorev = gorev
            u.save(update_fields=["gorev"])
            degisen += 1
    return degisen
