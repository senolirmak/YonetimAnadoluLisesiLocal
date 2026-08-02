"""
Mazeret Sınav Oturma Planı Üretim Servisi

MazeretOturumDers kayıtlarından (ders → oturum ataması) yola çıkarak
uygun öğrencileri MazeretSinav.salon_config'de tanımlı salonlara yerleştirir.

Kurallar:
- Uygun öğrenci: belge_teslim=True, sureksiz_devamsiz=False, muaf değil
- Salon kapasiteleri MazeretSinav.efektif_salon_config'den okunur (herhangi sayıda salon olabilir)
- Varsayılan: {"Mazeret 1": 36, "Mazeret 2": 36}
- Kelebek dağılım: her ders grubu kendi içinde tüm salonlara round-robin dağıtılır
  (ana sınavın OturmaPlanService'i ile aynı mantık), böylece bir salonda yan yana
  oturan öğrenciler farklı derslerden olur.
- Toplam öğrenci toplam kapasiteyi aşarsa uyarı verilir.
"""
from __future__ import annotations

import hashlib
import random
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
    from django.db.models import Q

    from ogrenci.models import Ogrenci, OgrenciMuaf
    from okul.utils import get_aktif_egitim_yili
    from sinav.models import (
        MazeretOgrenci,
        MazeretOturmaPlani,
        MazeretOturumDers,
    )

    # Salon adı → kapasite
    salon_config: dict[str, int] = mazeret.efektif_salon_config
    salonlar = list(salon_config.keys())
    toplam_kapasite = sum(salon_config.values())

    # Mevcut planı temizle
    MazeretOturmaPlani.objects.filter(mazeret_sinav=mazeret).delete()

    # Sürekli devamsız okulno'lar — Ogrenci.okulno int; MazeretOgrenci.okulno CharField → str
    sureksiz_strs = {
        str(x) for x in
        Ogrenci.objects.filter(
            Q(sureksiz_devamsiz=True) | Q(aktif=False)
        ).values_list("okulno", flat=True)
    }

    # Muaf (okulno, ders_adi) çiftleri — subquery yerine Python listesi (int↔varchar tip uyumu)
    _mo_okulno_ints = [
        int(x) for x in
        MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
        .values_list("okulno", flat=True).distinct() if x
    ]
    muaf_pairs: set[tuple[str, str]] = (
        {
            (str(ok), ders)
            for ok, ders in OgrenciMuaf.objects.filter(
                ogrenci__okulno__in=_mo_okulno_ints,
                egitim_yili=get_aktif_egitim_yili(),
            ).values_list("ogrenci__okulno", "ders__ders_adi")
        }
        if _mo_okulno_ints else set()
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
            .exclude(okulno__in=sureksiz_strs)
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
                f"({len(tekil)} öğrenci)."
            )

        # Kelebek dağılım: dersi paylaşan öğrenciler karıştırılıp her ders grubu
        # kendi içinde tüm salonlara round-robin dağıtılır. Böylece bir salonda
        # yan yana oturan öğrenciler mümkün olduğunca farklı derslerden olur.
        _seed = int(hashlib.md5(str(oturum_id).encode()).hexdigest(), 16) % (2 ** 31)
        karisik = list(tekil)
        random.Random(_seed).shuffle(karisik)

        groups_by_ders: dict[str, list] = {}
        for satir in karisik:
            groups_by_ders.setdefault(satir[3], []).append(satir)  # satir[3] = ders_adi

        salon_map: dict[str, list] = {s: [] for s in salonlar}
        n_salons = len(salonlar)
        for students in groups_by_ders.values():
            for i, satir in enumerate(students):
                salon_map[salonlar[i % n_salons]].append(satir)

        # Salon içi sıra numarası da derse göre round-robin harmanlanır: aynı
        # salonda ard arda oturan (sira_no'su ardışık) öğrenciler farklı ders
        # gruplarından gelir, tek bir dersin öğrencileri art arda sıralanmaz.
        for salon, satirlar in salon_map.items():
            salon_ders_map: dict[str, list] = {}
            for satir in satirlar:
                salon_ders_map.setdefault(satir[3], []).append(satir)
            harmanli = []
            while any(salon_ders_map.values()):
                for grup in salon_ders_map.values():
                    if grup:
                        harmanli.append(grup.pop(0))
            salon_map[salon] = harmanli

        for salon, satirlar in salon_map.items():
            for sira_no, (okulno, adi_soyadi, sinifsube, ders_adi, sinav_turu) in enumerate(satirlar, start=1):
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


def mazeret_salon_gruplari(mazeret: "MazeretSinav", kayitlar: list) -> list[dict]:
    """
    kayitlar listesini (MazeretOturmaPlani) salon adına göre gruplar.
    Sıralama önce mazeret.efektif_salon_config'deki salon adlarını, sonra kayıtlarda
    olup config'de olmayan (elle düzenlenmiş) salon adlarını takip eder.
    """
    salon_adlari = list(mazeret.efektif_salon_config.keys())
    for k in kayitlar:
        if k.salon not in salon_adlari:
            salon_adlari.append(k.salon)
    return [
        {"ad": ad, "kayitlar": [k for k in kayitlar if k.salon == ad]}
        for ad in salon_adlari
    ]
