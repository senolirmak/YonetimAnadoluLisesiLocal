"""Sınıf oturma düzeni (SinifOturmaDuzeni) iş mantığı.

Giriş yapmış her kullanıcı bir sınıfın oturma planını görebilir; yalnızca o sınıfın
rehber öğretmeni (ve superuser) planı oluşturup değiştirebilir.
"""

from django.db import transaction

from ogrenci.models import Ogrenci, SinifOturmaDuzeni
from ogrenci.services.rehberlik import rehberlik_sinif_sube, sinif_rehber_ogretmeni
from okul.models import SinifSube

# Sınıf yerleşimi: 3 grup × 2 koltuk, 7 sıra
N_GRUP = 3
N_KOLON_PER_GRUP = 2
N_KOLON = N_GRUP * N_KOLON_PER_GRUP
N_SIRA = 7


def rehber_sinifi(user):
    """Kullanıcının rehber öğretmeni olduğu SinifSube; yoksa None."""
    return rehberlik_sinif_sube(user)


def sinif_rehberi(sinif_sube):
    """Sınıfın rehber öğretmeni (Personel); yoksa None."""
    return sinif_rehber_ogretmeni(sinif_sube)


def duzenleyebilir_mi(user, sinif_sube):
    """Kullanıcı bu sınıfın oturma düzenini oluşturup değiştirebilir mi?"""
    if user.is_superuser:
        return True
    rehber = rehber_sinifi(user)
    return rehber is not None and rehber.pk == sinif_sube.pk


def sinif_ogrencileri(sinif_sube):
    return list(
        Ogrenci.objects.filter(sinif=sinif_sube.sinif, sube=sinif_sube.sube, aktif=True)
        .order_by("soyadi", "adi")
    )


def secilebilir_siniflar(egitim_yili):
    """Aktif yılda açık olan sınıf/şubeler ve her biri için planın olup olmadığı."""
    planli = set(
        SinifOturmaDuzeni.objects.filter(egitim_yili=egitim_yili)
        .values_list("sinif_sube_id", flat=True)
        .distinct()
    )
    return [
        {"sinif_sube": ss, "plan_var": ss.pk in planli}
        for ss in SinifSube.objects.order_by("sinif", "sube")
        if ss.acik_mi(egitim_yili)
    ]


def oturma_grid(sinif_sube, egitim_yili):
    """Şablon için sıra → grup → koltuk ızgarası ve yerleşmiş öğrenci pk'leri."""
    mevcut = {
        (d.sira_no, d.kolon_no): d.ogrenci
        for d in SinifOturmaDuzeni.objects.filter(
            sinif_sube=sinif_sube, egitim_yili=egitim_yili
        ).select_related("ogrenci")
    }
    grid = []
    for sira in range(1, N_SIRA + 1):
        satir = []
        for grup in range(1, N_GRUP + 1):
            hucreler = []
            for k in range(1, N_KOLON_PER_GRUP + 1):
                kolon = (grup - 1) * N_KOLON_PER_GRUP + k
                hucreler.append({"ogr": mevcut.get((sira, kolon)), "sira": sira, "kolon": kolon})
            satir.append(hucreler)
        grid.append(satir)
    return grid, {o.pk for o in mevcut.values()}


def koltuklari_oku(veri):
    """POST verisinden {(sira, kolon): ogrenci_pk} sözlüğü çıkarır; boş koltuklar atlanır."""
    koltuklar = {}
    for sira in range(1, N_SIRA + 1):
        for kolon in range(1, N_KOLON + 1):
            deger = (veri.get(f"koltuk_{sira}_{kolon}") or "").strip()
            if not deger:
                continue
            try:
                koltuklar[(sira, kolon)] = int(deger)
            except ValueError as e:
                raise ValueError("Geçersiz öğrenci bilgisi gönderildi.") from e
    return koltuklar


@transaction.atomic
def oturma_duzeni_kaydet(sinif_sube, egitim_yili, user, koltuklar):
    """Sınıfın oturma düzenini verilen koltuk eşleşmesiyle değiştirir.

    Öğrenci o sınıfın aktif öğrencisi değilse ya da aynı öğrenci iki koltuğa
    konmuşsa ValueError fırlatır ve hiçbir şey değiştirmez.
    """
    gecerli_pkler = {o.pk for o in sinif_ogrencileri(sinif_sube)}
    gorulen = set()
    for (sira, kolon), pk in koltuklar.items():
        if not (1 <= sira <= N_SIRA and 1 <= kolon <= N_KOLON):
            raise ValueError("Geçersiz koltuk konumu.")
        if pk not in gecerli_pkler:
            raise ValueError("Bu sınıfa ait olmayan bir öğrenci yerleştirilmeye çalışıldı.")
        if pk in gorulen:
            raise ValueError("Aynı öğrenci birden fazla koltuğa yerleştirilemez.")
        gorulen.add(pk)

    SinifOturmaDuzeni.objects.filter(sinif_sube=sinif_sube, egitim_yili=egitim_yili).delete()
    SinifOturmaDuzeni.objects.bulk_create(
        SinifOturmaDuzeni(
            sinif_sube=sinif_sube,
            ogrenci_id=pk,
            sira_no=sira,
            kolon_no=kolon,
            guncelleyen=user,
            egitim_yili=egitim_yili,
        )
        for (sira, kolon), pk in koltuklar.items()
    )
    return len(koltuklar)
