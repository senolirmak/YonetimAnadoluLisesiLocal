"""
Mazeret Sınav Planı — Otomatik Dağıtım Servisi

SinavSalonYoklama(durum="yok") kayıtlarından devamsız öğrencilerin
girdiği (ders, sinav_turu) çiftlerini tespit eder ve MazeretOturum'lara
round-robin ile dağıtır.

Kurallar:
- Sadece en az 1 devamsız öğrenci olan dersler dağıtıma girer
- Yazılı dersler  → sinav_turu='Yazili' olan oturumlara
- Uygulama dersleri → sinav_turu='Uygulama' olan oturumlara
- Round-robin dağıtım: dersler oturumlara sırayla atanır

OturmaPlani.ders_adi formatı: "DERS ADI" veya "DERS ADI (Yazili/Uygulama)"
Bu suffix Takvim.sinav_turu ile eşleştirilerek ders_id çözümlenir.
"""
from __future__ import annotations

import re
from datetime import time, timedelta
from typing import List, Tuple

from django.db.models import Subquery, OuterRef

from ogrenci.models import Ogrenci

from sinav.models import (
    MazeretSinav,
    MazeretGun,
    MazeretOturum,
    MazeretOturumDers,
    MazeretOgrenci,
    TakvimUretim,
    Takvim,
    OturmaPlani,
    SinavSalonYoklama,
)

_SINAV_TURU_RE = re.compile(r'^(.*?)\s+\((Yazili|Uygulama)\)$')


# Varsayılan oturum başlangıç saatleri (AlgoritmaParametreleri yoksa kullanılır)
VARSAYILAN_SAATLER = ["08:50", "10:30", "12:10", "13:35", "14:25"]
# Her oturumun süresi (dakika)
OTURUM_SURESI_DK = 80


def _str_to_time(s: str) -> time:
    h, m = map(int, s.split(":"))
    return time(h, m)


def _time_add_minutes(t: time, minutes: int) -> time:
    dt = timedelta(hours=t.hour, minutes=t.minute) + timedelta(minutes=minutes)
    total = int(dt.total_seconds())
    return time(total // 3600, (total % 3600) // 60)


def oturumlari_olustur(mazeret_sinav: MazeretSinav, oturum_saatleri_str: str | None = None) -> None:
    """
    Mazeret sınavının her günü için oturumları oluşturur.
    Daha önce oluşturulmuş oturumları siler ve yeniden üretir.

    oturum_saatleri_str: virgülle ayrılmış saat listesi, örn. "08:50,10:30,12:10,13:35"
    Belirtilmezse AlgoritmaParametreleri veya varsayılan saatler kullanılır.
    """
    # Oturum saatlerini belirle
    if oturum_saatleri_str:
        saatler = [s.strip() for s in oturum_saatleri_str.split(",") if s.strip()]
    else:
        try:
            params = mazeret_sinav.sinav.parametreler
            saatler = [s.strip() for s in params.oturum_saatleri.split(",") if s.strip()]
        except Exception:
            saatler = VARSAYILAN_SAATLER

    # En az 4 oturum garantisi
    if len(saatler) < 4:
        saatler = VARSAYILAN_SAATLER

    # Aktif TakvimUretim'den Uygulama ders sayısını bul
    aktif_uretim = TakvimUretim.objects.filter(
        sinav=mazeret_sinav.sinav, aktif=True
    ).first()

    uygulama_sayisi = 0
    if aktif_uretim:
        uygulama_sayisi = (
            Takvim.objects.filter(uretim=aktif_uretim, sinav_turu="Uygulama")
            .values("ders_id")
            .distinct()
            .count()
        )

    # Kaç Uygulama slotu gerekiyor?
    # Uygulama oturumları en sona yerleştirilir, her biri ayrı zaman diliminde
    uygulama_slot_sayisi = uygulama_sayisi  # her Uygulama dersi ayrı slot
    yazili_slot_sayisi = max(4, len(saatler)) - uygulama_slot_sayisi
    if yazili_slot_sayisi < 1:
        yazili_slot_sayisi = 1

    # Toplam slot sayısına göre saatleri düzenle
    toplam_slot = yazili_slot_sayisi + uygulama_slot_sayisi
    # Yeterli saat yoksa ekle
    while len(saatler) < toplam_slot:
        son = _str_to_time(saatler[-1])
        yeni = _time_add_minutes(son, OTURUM_SURESI_DK + 10)
        saatler.append(f"{yeni.hour:02d}:{yeni.minute:02d}")

    for gun in mazeret_sinav.gunler.all():
        # Mevcut oturumları temizle
        gun.oturumlar.all().delete()

        oturum_no = 1
        # Yazılı oturumlar
        for i in range(yazili_slot_sayisi):
            bas = _str_to_time(saatler[i])
            bit = _time_add_minutes(bas, OTURUM_SURESI_DK)
            MazeretOturum.objects.create(
                gun=gun,
                oturum_no=oturum_no,
                saat_baslangic=bas,
                saat_bitis=bit,
                sinav_turu="Yazili",
            )
            oturum_no += 1

        # Uygulama oturumları (sonraki slotlarda, tekil)
        for j in range(uygulama_slot_sayisi):
            idx = yazili_slot_sayisi + j
            bas = _str_to_time(saatler[idx])
            bit = _time_add_minutes(bas, OTURUM_SURESI_DK)
            MazeretOturum.objects.create(
                gun=gun,
                oturum_no=oturum_no,
                saat_baslangic=bas,
                saat_bitis=bit,
                sinav_turu="Uygulama",
            )
            oturum_no += 1


def populate_ogrenciler(mazeret_sinav: MazeretSinav) -> int:
    """
    SinavSalonYoklama(durum="yok") kayıtlarından MazeretOgrenci tablosunu doldurur.
    Mevcut belge_teslim değerlerini korur; yeni kayıtlar için belge_teslim=False.

    Returns: eklenen kayıt sayısı
    """
    aktif_uretim = TakvimUretim.objects.filter(
        sinav=mazeret_sinav.sinav, aktif=True
    ).first()
    if not aktif_uretim:
        return 0

    ders_adi_subq = OturmaPlani.objects.filter(
        uretim=aktif_uretim,
        okulno=OuterRef("okulno"),
        tarih=OuterRef("tarih"),
        saat=OuterRef("saat"),
        salon=OuterRef("salon"),
    ).values("ders_adi")[:1]

    absent_rows = list(
        SinavSalonYoklama.objects.filter(uretim=aktif_uretim, durum="yok")
        .annotate(ders_adi_full=Subquery(ders_adi_subq))
        .values("okulno", "adi_soyadi", "sinifsube", "ders_adi_full")
        .distinct()
    )

    # Mevcut kayıtları koru (belge_teslim değeri kaybolmasın)
    mevcut = {
        (r.okulno, r.ders_adi, r.sinav_turu)
        for r in MazeretOgrenci.objects.filter(mazeret_sinav=mazeret_sinav)
        .only("okulno", "ders_adi", "sinav_turu")
    }

    yeni = []
    for row in absent_rows:
        ders_adi_full = (row.get("ders_adi_full") or "").strip()
        if not ders_adi_full:
            continue
        m = _SINAV_TURU_RE.match(ders_adi_full)
        ders_adi  = m.group(1).strip() if m else ders_adi_full
        sinav_turu = m.group(2) if m else ""
        key = (row["okulno"], ders_adi, sinav_turu)
        if key not in mevcut:
            yeni.append(MazeretOgrenci(
                mazeret_sinav=mazeret_sinav,
                okulno=row["okulno"],
                adi_soyadi=row["adi_soyadi"],
                sinifsube=row["sinifsube"],
                ders_adi=ders_adi,
                sinav_turu=sinav_turu,
                belge_teslim=False,
            ))

    if yeni:
        MazeretOgrenci.objects.bulk_create(yeni, ignore_conflicts=True)
    return len(yeni)


def _absent_ders_listesi(aktif_uretim) -> list[dict]:
    """
    SinavSalonYoklama(durum="yok") → OturmaPlani → Takvim zinciri ile
    en az 1 devamsız öğrenci olan (ders_id, sinav_turu) çiftlerini döner.

    OturmaPlani.ders_adi alanı "DERS ADI" veya "DERS ADI (Yazili/Uygulama)"
    formatında olabilir; suffix ayrıştırılarak Takvim ile eşleştirilir.
    """
    # Adım 1: devamsız öğrencilerin OturmaPlani.ders_adi → subquery ile al
    ders_adi_subq = OturmaPlani.objects.filter(
        uretim=aktif_uretim,
        okulno=OuterRef("okulno"),
        tarih=OuterRef("tarih"),
        saat=OuterRef("saat"),
        salon=OuterRef("salon"),
    ).values("ders_adi")[:1]

    absent_ders_adileri = set(
        SinavSalonYoklama.objects.filter(uretim=aktif_uretim, durum="yok")
        .annotate(ders_adi=Subquery(ders_adi_subq))
        .values_list("ders_adi", flat=True)
        .distinct()
    ) - {None, ""}

    # Adım 2: "DERS ADI (Yazili)" formatını ayrıştır → (base_adi, sinav_turu) seti
    parsed: set[tuple[str, str]] = set()
    for ders_adi_full in absent_ders_adileri:
        m = _SINAV_TURU_RE.match(ders_adi_full)
        if m:
            parsed.add((m.group(1).strip(), m.group(2)))
        else:
            parsed.add((ders_adi_full, ""))

    # Adım 3: Takvim üzerinden ders_id çözümle
    result = []
    for base_adi, sinav_turu in parsed:
        qs = Takvim.objects.filter(
            uretim=aktif_uretim,
            ders__ders_adi=base_adi,
            sinav_turu=sinav_turu,
        ).values("ders_id", "sinav_turu").distinct()
        result.extend(qs)

    # Tekrarları kaldır, sırala
    seen = set()
    unique = []
    for r in result:
        key = (r["ders_id"], r["sinav_turu"])
        if key not in seen:
            seen.add(key)
            unique.append(r)
    unique.sort(key=lambda r: (r["sinav_turu"], r["ders_id"]))
    return unique


def dagit(mazeret_sinav: MazeretSinav) -> Tuple[bool, str]:
    """
    Belge teslim etmiş VE sürekli devamsız olmayan öğrencilerin derslerini
    MazeretOturum'lara round-robin ile dağıtır.
    Mevcut MazeretOturumDers kayıtlarını siler ve yeniden oluşturur.

    Returns: (basarili: bool, mesaj: str)
    """
    # Önce mevcut atamaları temizle
    MazeretOturumDers.objects.filter(
        oturum__gun__mazeret_sinav=mazeret_sinav
    ).delete()

    # Aktif TakvimUretim
    aktif_uretim = TakvimUretim.objects.filter(
        sinav=mazeret_sinav.sinav, aktif=True
    ).first()
    if not aktif_uretim:
        return False, "Aktif takvim üretimi bulunamadı. Önce bir takvim üretimi aktif yapın."

    # Sürekli devamsız veya muaf öğrencilerin okul numaraları → dağıtımdan hariç
    hariç_okulnolari = set(
        Ogrenci.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
    ) | set(
        Ogrenci.objects.filter(muaf=True).values_list("okulno", flat=True)
    )

    # Belge teslim etmiş VE hariç listesinde olmayan → uygun (ders_adi, sinav_turu) çiftleri
    uygun_qs = (
        MazeretOgrenci.objects
        .filter(mazeret_sinav=mazeret_sinav, belge_teslim=True)
        .exclude(okulno__in=hariç_okulnolari)
        .values("ders_adi", "sinav_turu")
        .distinct()
    )
    uygun_ders_adileri: set[tuple[str, str]] = {
        (r["ders_adi"], r["sinav_turu"]) for r in uygun_qs
    }

    if not uygun_ders_adileri:
        return False, (
            "Belge teslim etmiş uygun öğrenci bulunamadı. "
            "Önce öğrencilerin belge teslim durumunu güncelleyin."
        )

    # (ders_adi, sinav_turu) → (ders_id, sinav_turu) çözümle
    takvim_kayitlar = []
    seen: set[tuple] = set()
    for ders_adi, sinav_turu in uygun_ders_adileri:
        tk = Takvim.objects.filter(
            uretim=aktif_uretim,
            ders__ders_adi=ders_adi,
            sinav_turu=sinav_turu,
        ).values("ders_id", "sinav_turu").first()
        if tk:
            key = (tk["ders_id"], tk["sinav_turu"])
            if key not in seen:
                seen.add(key)
                takvim_kayitlar.append(tk)

    takvim_kayitlar.sort(key=lambda r: (r["sinav_turu"], r["ders_id"]))

    if not takvim_kayitlar:
        return False, "Uygun dersler takvimde bulunamadı."

    yazili_dersler = [r for r in takvim_kayitlar if r["sinav_turu"] != "Uygulama"]
    uygulama_dersler = [r for r in takvim_kayitlar if r["sinav_turu"] == "Uygulama"]

    # Oturumları al
    yazili_oturumlar: List[MazeretOturum] = list(
        MazeretOturum.objects.filter(
            gun__mazeret_sinav=mazeret_sinav, sinav_turu="Yazili"
        ).order_by("gun__tarih", "oturum_no")
    )
    uygulama_oturumlar: List[MazeretOturum] = list(
        MazeretOturum.objects.filter(
            gun__mazeret_sinav=mazeret_sinav, sinav_turu="Uygulama"
        ).order_by("gun__tarih", "oturum_no")
    )

    hatalar = []
    if not yazili_oturumlar and yazili_dersler:
        hatalar.append("Yazılı sınav için Yazılı oturum tanımlanmamış.")
    if not uygulama_oturumlar and uygulama_dersler:
        hatalar.append("Uygulama sınavı için Uygulama oturumu tanımlanmamış.")
    if hatalar:
        return False, " ".join(hatalar)

    atamalar = []

    # Yazılı dağıtım — round-robin
    for i, ders_info in enumerate(yazili_dersler):
        oturum = yazili_oturumlar[i % len(yazili_oturumlar)]
        atamalar.append(MazeretOturumDers(
            oturum=oturum,
            ders_id=ders_info["ders_id"],
            sinav_turu=ders_info["sinav_turu"],
        ))

    # Uygulama dağıtım — round-robin
    for i, ders_info in enumerate(uygulama_dersler):
        oturum = uygulama_oturumlar[i % len(uygulama_oturumlar)]
        atamalar.append(MazeretOturumDers(
            oturum=oturum,
            ders_id=ders_info["ders_id"],
            sinav_turu=ders_info["sinav_turu"],
        ))

    MazeretOturumDers.objects.bulk_create(atamalar, ignore_conflicts=True)

    return True, (
        f"Devamsız öğrencisi olan {len(yazili_dersler)} Yazılı ve "
        f"{len(uygulama_dersler)} Uygulama dersi "
        f"toplam {len(yazili_oturumlar) + len(uygulama_oturumlar)} oturuma dağıtıldı."
    )
