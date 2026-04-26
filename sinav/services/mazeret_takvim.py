"""
Mazeret Sınav Oturma Planı Üretim Servisi

MazeretOturumDers kayıtlarından (ders → oturum ataması) yola çıkarak
uygun öğrencileri iki salona (Mazeret1, Mazeret2) yerleştirir.

Kurallar:
- Uygun öğrenci: belge_teslim=True, sureksiz_devamsiz=False, muaf değil
- Her salonun kapasitesi 40 öğrenci
- Sıralama: sinifsube → adi_soyadi (alfabetik)
- Aynı oturumda birden fazla ders varsa öğrenciler kendi derslerine göre sırayla yerleşir
- Toplam > 80 ise fazla öğrenciler son salona eklenir (uyarı)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sinav.models import MazeretSinav

SALON_KAPASITESI = 40
SALONLAR = ["Mazeret1", "Mazeret2"]


def oturma_plani_olustur(mazeret: "MazeretSinav") -> dict:
    """
    Mazeret sınavı için MazeretOturmaPlani kayıtları üretir.
    Mevcut plan silinip yeniden oluşturulur.

    Returns: {"toplam": int, "salonlar": {"Mazeret1": int, "Mazeret2": int}, "uyari": str}
    """
    from ogrenci.models import Ogrenci, OgrenciMuaf
    from sinav.models import (
        MazeretOturumDers, MazeretOgrenci, MazeretOturmaPlani,
    )

    # Mevcut planı temizle
    MazeretOturmaPlani.objects.filter(mazeret_sinav=mazeret).delete()

    # Sürekli devamsız okulno'lar
    sureksiz = set(
        Ogrenci.objects.filter(sureksiz_devamsiz=True)
        .values_list("okulno", flat=True)
    )

    # Muaf (okulno, ders_adi) çiftleri
    muaf_pairs: set[tuple[str, str]] = set(
        OgrenciMuaf.objects.filter(
            ogrenci__okulno__in=MazeretOgrenci.objects.filter(
                mazeret_sinav=mazeret
            ).values("okulno")
        ).values_list("ogrenci__okulno", "ders__ders_adi")
    )

    # Oturumlara göre işle
    oturumlar = list(
        MazeretOturumDers.objects
        .filter(oturum__gun__mazeret_sinav=mazeret)
        .select_related("oturum__gun", "ders")
        .order_by("oturum__gun__tarih", "oturum__oturum_no", "ders__ders_adi")
    )

    # (oturum_id) → [(okulno, adi_soyadi, sinifsube, ders_adi, sinav_turu), ...]
    oturum_ogrenci_map: dict[int, list[tuple]] = {}
    for od in oturumlar:
        oturum_id = od.oturum_id
        ogrs = list(
            MazeretOgrenci.objects.filter(
                mazeret_sinav=mazeret,
                ders_adi=od.ders.ders_adi,
                sinav_turu=od.sinav_turu,
                belge_teslim=True,
            )
            .exclude(okulno__in=sureksiz)
            .order_by("sinifsube", "adi_soyadi")
            .values_list("okulno", "adi_soyadi", "sinifsube")
        )
        for okulno, adi_soyadi, sinifsube in ogrs:
            if (okulno, od.ders.ders_adi) not in muaf_pairs:
                oturum_ogrenci_map.setdefault(oturum_id, []).append(
                    (okulno, adi_soyadi, sinifsube, od.ders.ders_adi, od.sinav_turu)
                )

    # Kayıt oluştur
    yeni_kayitlar = []
    salon_sayilari: dict[str, int] = {s: 0 for s in SALONLAR}
    toplam = 0
    uyari = ""

    for oturum_id, ogrenci_listesi in oturum_ogrenci_map.items():
        # Aynı oturumda aynı öğrenci birden fazla derste olabilir — tekil tut
        goruldu: set[str] = set()
        tekil = []
        for satir in ogrenci_listesi:
            if satir[0] not in goruldu:
                goruldu.add(satir[0])
                tekil.append(satir)

        if len(tekil) > len(SALONLAR) * SALON_KAPASITESI:
            uyari = (
                f"Bazı oturumlarda {len(SALONLAR) * SALON_KAPASITESI} üzeri öğrenci "
                f"var ({len(tekil)}). Fazla öğrenciler son salona yerleştirildi."
            )

        for sira_genel, (okulno, adi_soyadi, sinifsube, ders_adi, sinav_turu) in enumerate(tekil, start=1):
            salon_idx = min((sira_genel - 1) // SALON_KAPASITESI, len(SALONLAR) - 1)
            salon = SALONLAR[salon_idx]
            sira_no = (sira_genel - 1) % SALON_KAPASITESI + 1

            yeni_kayitlar.append(MazeretOturmaPlani(
                mazeret_sinav=mazeret,
                oturum_id=oturum_id,
                salon=salon,
                sira_no=sira_no,
                okulno=okulno,
                adi_soyadi=adi_soyadi,
                sinifsube=sinifsube,
                ders_adi=ders_adi,
                sinav_turu=sinav_turu,
            ))
            salon_sayilari[salon] = salon_sayilari.get(salon, 0) + 1
            toplam += 1

    MazeretOturmaPlani.objects.bulk_create(yeni_kayitlar, ignore_conflicts=True)
    return {"toplam": toplam, "salonlar": salon_sayilari, "uyari": uyari}
