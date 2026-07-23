"""Gelecek yıl şube/alan ders paketi hesaplamaları.

`plan_sinif_dagilimi` — sinif_dagilimi view'ından taşındı; öğrencileri
seçmeli ders tercihlerine göre en uygun alana eşleyip kız/erkek dengeli
şubelere dağıtır. Hem `secmelidersler.views.sinif_dagilimi` hem de
`ders_dagilimi_listesi`/`ders_dagilimi_detay` (alan başına şube sayısı için)
bu fonksiyonu kullanır — tek kaynak, iki yer senkron kalır.
"""
import math
from collections import defaultdict

from django.db.models import Max

MAKS_SUBE = 34
HARFLER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _yf(qs, aktif_yil):
    return qs.filter(egitim_yili=aktif_yil) if aktif_yil else qs


def _sube_dagit(ogrs, gelecek_sinif, harf_idx, maks=MAKS_SUBE):
    """Öğrencileri kız/erkek dengesi korunarak şubelere dağıtır."""
    kizlar = sorted([o for o in ogrs if o.cinsiyet == "K"], key=lambda x: x.okulno or 0)
    erkekler = sorted([o for o in ogrs if o.cinsiyet == "E"], key=lambda x: x.okulno or 0)
    toplam = len(kizlar) + len(erkekler)
    if toplam == 0:
        return [], harf_idx

    n_sube = math.ceil(toplam / maks)
    G, B = len(kizlar), len(erkekler)
    kiz_base, kiz_rem = divmod(G, n_sube)
    erk_base, erk_rem = divmod(B, n_sube)

    subeler = []
    kiz_idx = erk_idx = 0
    for i in range(n_sube):
        kiz_al = kiz_base + (1 if i < kiz_rem else 0)
        erk_al = erk_base + (1 if i < erk_rem else 0)
        sube_ogrs = kizlar[kiz_idx:kiz_idx + kiz_al] + erkekler[erk_idx:erk_idx + erk_al]
        sube_ogrs.sort(key=lambda x: x.okulno or 0)
        kiz_idx += kiz_al
        erk_idx += erk_al
        harf = HARFLER[harf_idx] if harf_idx < 26 else str(harf_idx + 1)
        subeler.append({
            "sube": harf,
            "label": f"{gelecek_sinif}/{harf}",
            "ogrenciler": sube_ogrs,
            "kiz_sayi": kiz_al,
            "erkek_sayi": erk_al,
        })
        harf_idx += 1
    return subeler, harf_idx


def plan_sinif_dagilimi(sinif_no, gelecek_sinif, aktif_yil, maks_sube=MAKS_SUBE):
    """Mevcut `sinif_no` öğrencilerini `gelecek_sinif` seviyesi alanlarına/şubelerine dağıtır."""
    from ogrenci.models import Ogrenci
    from ogrencidersleri.models import OgrenciSecmeliDers

    from ..models import Alan, AlanDers, OgrenciSinifTekrari, OgrenciTasdikname

    alanlar = list(
        _yf(Alan.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil)
        .order_by("sira", "adi")
    )
    alan_ders_map = {
        a.pk: set(AlanDers.objects.filter(alan=a).values_list("ders_id", flat=True))
        for a in alanlar
    }

    ogrenciler = list(Ogrenci.objects.filter(sinif=sinif_no).order_by("okulno"))
    ogr_ids = [o.pk for o in ogrenciler]

    sinif_tekrari_ids = set(
        OgrenciSinifTekrari.objects.filter(ogrenci_id__in=ogr_ids).values_list("ogrenci_id", flat=True)
    )
    tasdikname_ids = set(
        OgrenciTasdikname.objects.filter(ogrenci_id__in=ogr_ids).values_list("ogrenci_id", flat=True)
    )

    ogr_secim = defaultdict(set)
    for ogr_id, ders_id in OgrenciSecmeliDers.objects.filter(
        ogrenci_id__in=ogr_ids
    ).values_list("ogrenci_id", "ders_id"):
        ogr_secim[ogr_id].add(ders_id)

    alan_ogr = defaultdict(list)
    alan_yok = []
    sinif_tekrari_liste = []
    tasdikname_liste = []
    for ogr in ogrenciler:
        if ogr.pk in tasdikname_ids:
            tasdikname_liste.append(ogr)
            continue
        if ogr.pk in sinif_tekrari_ids:
            sinif_tekrari_liste.append(ogr)
            continue
        secimler = ogr_secim.get(ogr.pk, set())
        if not secimler:
            alan_yok.append(ogr)
            continue
        en_iyi_pk, en_iyi_skor = None, 0
        for a_pk, d_ids in alan_ders_map.items():
            skor = len(secimler & d_ids)
            if skor > en_iyi_skor:
                en_iyi_skor, en_iyi_pk = skor, a_pk
        (alan_ogr[en_iyi_pk] if en_iyi_pk else alan_yok).append(ogr)

    harf_idx = 0
    alan_gruplari = []
    for a in alanlar:
        ogrs = alan_ogr.get(a.pk, [])
        subeler, harf_idx = _sube_dagit(ogrs, gelecek_sinif, harf_idx, maks_sube)
        toplam_kiz = sum(1 for o in ogrs if o.cinsiyet == "K")
        toplam_erkek = sum(1 for o in ogrs if o.cinsiyet == "E")
        alan_gruplari.append({
            "alan": a,
            "ogrenci_sayisi": len(ogrs),
            "toplam_kiz": toplam_kiz,
            "toplam_erkek": toplam_erkek,
            "sube_sayisi": len(subeler),
            "subeler": subeler,
        })

    return {
        "sinif": sinif_no,
        "gelecek_sinif": gelecek_sinif,
        "alan_gruplari": alan_gruplari,
        "alan_yok": alan_yok,
        "sinif_tekrari": sinif_tekrari_liste,
        "tasdikname": tasdikname_liste,
        "toplam_ogr": sum(g["ogrenci_sayisi"] for g in alan_gruplari),
        "toplam_sube": sum(g["sube_sayisi"] for g in alan_gruplari),
    }


def alan_ders_paketi(alan, aktif_yil):
    """
    Bir alanın (11-12. sınıf) sabit 40 saatlik ders paketini döndürür:
    [{"tur": "ortak"|"secmeli", "ders": <OrtakDers|SecmeliDers>, "haftalik_saat": int}, ...]
    """
    from ..models import AlanDers, OrtakDers

    paket = []
    for od in _yf(OrtakDers.objects.filter(sinif_seviyesi=alan.sinif_seviyesi), aktif_yil).order_by("sira"):
        paket.append({"tur": "ortak", "ders": od, "haftalik_saat": od.haftalik_saat})
    for ad in AlanDers.objects.filter(alan=alan).select_related("ders").order_by("ders__sira"):
        paket.append({"tur": "secmeli", "ders": ad.ders, "haftalik_saat": ad.secilen_saat})
    return paket


def sube_ders_paketi(mevcut_sinif, sube, gelecek_sinif, aktif_yil):
    """
    9→10 geçişi için: mevcut (mevcut_sinif, sube) öğrencilerinin gelecek yıl
    okuyacağı ders paketini döndürür — OrtakDers(gelecek_sinif) + o şubedeki
    öğrencilerin seçtiği SecmeliDers'lerin (distinct, en yüksek seçilen saat) birleşimi.
    """
    from ogrenci.models import Ogrenci
    from ogrencidersleri.models import OgrenciSecmeliDers

    from ..models import OrtakDers

    paket = []
    for od in _yf(OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil).order_by("sira"):
        paket.append({"tur": "ortak", "ders": od, "haftalik_saat": od.haftalik_saat})

    ogr_ids = Ogrenci.objects.filter(
        sinif=mevcut_sinif, sube=sube, aktif=True
    ).values_list("pk", flat=True)
    secmeli_satirlar = (
        OgrenciSecmeliDers.objects.filter(
            ogrenci_id__in=ogr_ids, ders__grup__sinif_seviyesi=gelecek_sinif
        )
        .values("ders_id", "ders__ders_adi")
        .annotate(saat=Max("secilen_saat"))
        .order_by("ders__sira")
    )
    ders_map = {row["ders_id"]: row for row in secmeli_satirlar}
    if ders_map:
        from ..models import SecmeliDers
        for sd in SecmeliDers.objects.filter(pk__in=ders_map.keys()).order_by("sira"):
            paket.append({"tur": "secmeli", "ders": sd, "haftalik_saat": ders_map[sd.pk]["saat"]})

    return paket
