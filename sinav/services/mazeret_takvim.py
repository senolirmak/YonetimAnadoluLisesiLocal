"""
Mazeret Sınav Oturma Planı Üretim Servisi

MazeretOturumDers kayıtlarından (ders → oturum ataması) yola çıkarak
uygun öğrencileri MazeretSinav.salon_config'de tanımlı salonlara yerleştirir.

Kurallar:
- Uygun öğrenci: belge_teslim=True, sureksiz_devamsiz=False, muaf değil
- Salon kapasiteleri MazeretSinav.efektif_salon_config'den okunur
- Varsayılan: {"Mazeret 1": 36, "Mazeret 2": 36}
- Sıralama: sinifsube → adi_soyadi (alfabetik)
- Toplam öğrenci toplam kapasiteyi aşarsa fazlalar son salona eklenir (uyarı)
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sinav.models import MazeretSinav


def oturma_plani_olustur(mazeret: "MazeretSinav") -> dict:
    """
    Mazeret sınavı için MazeretOturmaPlani kayıtları üretir.
    Mevcut plan silinip yeniden oluşturulur.

    Returns: {
        "toplam": int,
        "salonlar": {salon_adi: ogrenci_sayisi},
        "uyari": str,
    }
    """
    from ogrenci.models import Ogrenci, OgrenciMuaf
    from sinav.models import (
        MazeretOturumDers, MazeretOgrenci, MazeretOturmaPlani,
    )

    # Salon adı → kapasite
    salon_config: dict[str, int] = mazeret.efektif_salon_config
    salonlar = list(salon_config.keys())
    toplam_kapasite = sum(salon_config.values())

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

    # Oturumları sıralı işle
    oturumlar = list(
        MazeretOturumDers.objects
        .filter(oturum__gun__mazeret_sinav=mazeret)
        .select_related("oturum__gun", "ders")
        .order_by("oturum__gun__tarih", "oturum__oturum_no", "ders__ders_adi")
    )

    # oturum_id → [(okulno, adi_soyadi, sinifsube, ders_adi, sinav_turu), ...]
    oturum_ogrenci_map: dict[int, list[tuple]] = {}
    for od in oturumlar:
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
                oturum_ogrenci_map.setdefault(od.oturum_id, []).append(
                    (okulno, adi_soyadi, sinifsube, od.ders.ders_adi, od.sinav_turu)
                )

    # Kayıt oluştur
    yeni_kayitlar = []
    salon_sayilari: dict[str, int] = {s: 0 for s in salonlar}
    toplam = 0
    uyari = ""

    for oturum_id, ogrenci_listesi in oturum_ogrenci_map.items():
        # Aynı öğrencinin aynı oturumda birden fazla dersi → tekil tut
        goruldu: set[str] = set()
        tekil = []
        for satir in ogrenci_listesi:
            if satir[0] not in goruldu:
                goruldu.add(satir[0])
                tekil.append(satir)

        if len(tekil) > toplam_kapasite:
            uyari = (
                f"Bazı oturumlarda salon kapasitesi ({toplam_kapasite}) aşıldı "
                f"({len(tekil)} öğrenci). Fazla öğrenciler son salona eklendi."
            )

        # Öğrencileri salonlara dağıt: her salon dolduktan sonra sıradaki salona geç
        kapasite_listesi = [salon_config[s] for s in salonlar]
        salon_idx = 0          # hangi salondayız
        salon_ici_sira = 0     # bu salonda kaçıncı öğrenciyiz (0-indexed)

        for okulno, adi_soyadi, sinifsube, ders_adi, sinav_turu in tekil:
            # Mevcut salon doldu mu?
            if (salon_idx < len(salonlar) - 1 and
                    salon_ici_sira >= kapasite_listesi[salon_idx]):
                salon_idx += 1
                salon_ici_sira = 0

            salon = salonlar[min(salon_idx, len(salonlar) - 1)]
            sira_no = salon_ici_sira + 1

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
            salon_ici_sira += 1
            toplam += 1

    MazeretOturmaPlani.objects.bulk_create(yeni_kayitlar, ignore_conflicts=True)
    return {"toplam": toplam, "salonlar": salon_sayilari, "uyari": uyari}
