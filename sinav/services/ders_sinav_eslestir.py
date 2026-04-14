# -*- coding: utf-8 -*-
"""
Öğretmen Ders-Sınav Eşleştirme Servisi
=======================================

OturmaPlani-first mantığı:
  1. Aktif sınav takvimindeki tüm OturmaPlani slotları taranır.
  2. Her slot için dp_saat = sınav_saati + dp_offset_dk hesaplanır.
  3. DersProgrami'nde (gun=tarih.weekday, saat=dp_saat, sinif_sube=salon_sinif_sube)
     eşleşen öğretmen varsa ve o slotta gözetmen değilse slot listeye eklenir.

Çağrı örnekleri:
  # Sınıf Listesi PDF: ders saati + 50dk = sınav saati
  ders_sinav_eslestir(personel, ogretmen_adi, aktif_uretim, dp_offset_dk=-50, ...)

  # Kelebek PDF: ders saati == sınav saati
  ders_sinav_eslestir(personel, ogretmen_adi, aktif_uretim, dp_offset_dk=0, ...)

  # Uygulama sınavı Kelebek: ek filtre ile
  ders_sinav_eslestir(personel, ogretmen_adi, aktif_uretim, dp_offset_dk=0,
                      op_filtre={"takvim__ders__ders_adi__icontains": "(Uygulama)"}, ...)
"""

from __future__ import annotations

from datetime import date as _date, datetime as _dt, timedelta as _td
from typing import Any

from sinav.models import OturmaPlani
from sinav.utils import onceki_ders_saati, salon_goster


def ders_sinav_eslestir(
    personel,
    ogretmen_adi: str,
    aktif_uretim,
    *,
    dp_offset_dk: int = 0,
    bugun: _date | None = None,
    simdi_str: str = "",
    op_filtre: dict[str, Any] | None = None,
) -> list[dict]:
    """
    Öğretmenin ders programıyla aktif sınavın OturmaPlani'nı eşleştirir.

    Parametreler
    ------------
    personel      : DersProgrami.ogretmen FK değeri (okul.Personel)
    ogretmen_adi  : Gözetmen karşılaştırması için ad-soyad string
    aktif_uretim  : TakvimUretim instance (aktif=True)
    dp_offset_dk  : Sınav saatine eklenen dakika farkı (negatif = önceki ders)
                    0  → ders_saat == sinav_saat          (Kelebek PDF)
                    -50 → ders_saat == sinav_saat - 50dk  (Sınıf Listesi PDF)
    bugun         : Aktiflik kontrolü için bugünün tarihi (varsayılan: date.today())
    simdi_str     : "HH:MM" formatında şu anki saat (aktiflik için)
    op_filtre     : OturmaPlani sorgusuna eklenecek ek filtre kwargs
                    örn. {"takvim__ders__ders_adi__icontains": "(Uygulama)"}

    Dönen liste elemanları
    ----------------------
    {
        "tarih"      : date,
        "saat"       : str "HH:MM",
        "oturum"     : int,
        "sinifsube"  : str "10/B",
        "salonlar"   : [{"ham": "Salon-10_B", "ad": "Salon 10/B"}, ...],
        "onceki_saat": str | None,
        "aktif"      : bool,
    }
    """
    from dersprogrami.models import DersProgrami

    if not (personel and ogretmen_adi and aktif_uretim):
        return []

    bugun = bugun or _date.today()

    # ── 1. Öğretmenin DersProgrami → (gun, ders_saat_str, sinif_sube_id) seti ──
    dp_rows = (
        DersProgrami.objects
        .filter(ogretmen=personel, sinif_sube__isnull=False, ders_saati__isnull=False)
        .values("gun", "sinif_sube_id", "ders_saati__derssaati_baslangic")
        .distinct()
    )
    dp_set: set[tuple] = set()
    sinif_sube_ids: set[int] = set()
    for r in dp_rows:
        saat_str = r["ders_saati__derssaati_baslangic"].strftime("%H:%M")
        dp_set.add((r["gun"], saat_str, r["sinif_sube_id"]))
        sinif_sube_ids.add(r["sinif_sube_id"])

    if not sinif_sube_ids:
        return []

    # ── 2. OturmaPlani: öğretmenin sınıflarının sınav odası olduğu slotlar ────
    op_qs = (
        OturmaPlani.objects
        .filter(uretim=aktif_uretim, salon_sinif_sube_id__in=sinif_sube_ids)
        .values(
            "tarih", "saat", "oturum", "salon",
            "salon_sinif_sube_id",
            "salon_sinif_sube__sinif",
            "salon_sinif_sube__sube",
        )
        .distinct()
        .order_by("tarih", "saat", "oturum")
    )
    if op_filtre:
        op_qs = op_qs.filter(**op_filtre)

    # ── 3. Offset uygula ve DersProgrami seti ile eşleştir ───────────────────
    # key: (tarih, saat, oturum, sinif_sube_id, sinif, sube)  →  [salon_kodu, ...]
    slot_salon_map: dict[tuple, list[str]] = {}

    for row in op_qs:
        tarih = row["tarih"]
        saat  = row["saat"]
        sid   = row["salon_sinif_sube_id"]
        if not sid:
            continue

        dp_gun = tarih.strftime("%A")

        if dp_offset_dk == 0:
            dp_saat = saat
        else:
            t = _dt.strptime(saat, "%H:%M")
            dp_saat = (
                _dt.combine(_date.today(), t.time()) + _td(minutes=dp_offset_dk)
            ).strftime("%H:%M")

        if (dp_gun, dp_saat, sid) not in dp_set:
            continue

        key = (
            tarih, saat, row["oturum"], sid,
            row["salon_sinif_sube__sinif"],
            row["salon_sinif_sube__sube"],
        )
        salon = row.get("salon", "") or ""
        slot_salon_map.setdefault(key, [])
        if salon and salon not in slot_salon_map[key]:
            slot_salon_map[key].append(salon)

    # ── 4. Sonuçları formatla ─────────────────────────────────────────────────
    result: list[dict] = []
    for key, salonlar_raw in slot_salon_map.items():
        tarih, saat, oturum, _sid, sinif, sube = key
        onceki = onceki_ders_saati(saat)
        result.append({
            "tarih":       tarih,
            "saat":        saat,
            "oturum":      oturum,
            "sinifsube":   f"{sinif}/{sube}" if sinif and sube else "",
            "salonlar":    [{"ham": s, "ad": salon_goster(s)} for s in salonlar_raw],
            "onceki_saat": onceki,
            "aktif": (
                tarih == bugun
                and onceki is not None
                and simdi_str >= onceki
            ),
        })

    result.sort(key=lambda x: (x["tarih"], x["saat"], x["oturum"]))
    return result


def tum_siniflistesi_eslestir(aktif_uretim, **_ignored) -> dict[str, list[dict]]:
    """
    Aktif TakvimUretim'deki her sınav slotu için, o sınav saatinden önce biten
    son dersin öğretmenini bulur ve DersProgrami'nde eşleşen tüm öğretmenleri döndürür.

    Eşleştirme mantığı:
      - Her sınav saati için DersSaatleri.derssaati_bitis < sinav_saati şartını sağlayan
        en geç biten dersin başlangıç saati (derssaati_baslangic) kullanılır.
      - Bu yaklaşım, öğle arası gibi farklı uzunluktaki molalarda da doğru çalışır.
        Örnek: 13:35 sınavı → 6. ders bitis 12:50 < 13:35 → baslangic 12:10 ile eşleşir.

    Döner: { ogretmen_adi_soyadi: [{"tarih", "saat", "oturum", "sinifsube", "salonlar"}, ...] }
    """
    from dersprogrami.models import DersProgrami
    from okul.models import DersSaatleri as _DS

    if not aktif_uretim:
        return {}

    # Ders saatlerini bir kez yükle (küçük liste, ~8 kayıt)
    _ders_saatleri = list(_DS.objects.order_by("derssaati_baslangic"))

    def _onceki_ders_baslangic(sinav_saat_str: str) -> str | None:
        """Sınav saatinden önce biten son dersin başlangıç saatini döner."""
        sinav_t = _dt.strptime(sinav_saat_str, "%H:%M").time()
        onceki = None
        for ds in _ders_saatleri:
            if ds.derssaati_bitis < sinav_t:
                onceki = ds
        return onceki.derssaati_baslangic.strftime("%H:%M") if onceki else None

    # 1. Tüm OturmaPlani slotları: (tarih, saat, oturum, salon, sinif_sube_id, sinif, sube)
    op_rows = list(
        OturmaPlani.objects
        .filter(uretim=aktif_uretim, salon_sinif_sube__isnull=False)
        .values(
            "tarih", "saat", "oturum", "salon",
            "salon_sinif_sube_id",
            "salon_sinif_sube__sinif",
            "salon_sinif_sube__sube",
        )
        .distinct()
        .order_by("tarih", "saat", "oturum")
    )

    # 2. Her slot için sınav öncesi son dersin başlangıç saatini hesapla
    #    (dp_gun, dp_saat, sinif_sube_id) → slot bilgisi
    dp_key_map: dict[tuple, dict] = {}
    for row in op_rows:
        sid = row["salon_sinif_sube_id"]
        if not sid:
            continue
        saat = row["saat"]
        tarih = row["tarih"]
        dp_gun = tarih.strftime("%A")

        dp_saat = _onceki_ders_baslangic(saat)
        if dp_saat is None:
            continue

        dp_key = (dp_gun, dp_saat, sid)
        slot_key = (tarih, saat, row["oturum"], sid,
                    row["salon_sinif_sube__sinif"], row["salon_sinif_sube__sube"])

        if dp_key not in dp_key_map:
            dp_key_map[dp_key] = {
                "slot_key": slot_key,
                "salonlar": set(),
            }
        if row["salon"]:
            dp_key_map[dp_key]["salonlar"].add(row["salon"])

    if not dp_key_map:
        return {}

    # 3. DersProgrami'nde (gun, saat, sinif_sube) üçlüsüne uyan öğretmenleri bul
    from django.db.models import Q
    conditions = Q()
    for (dp_gun, dp_saat, sid) in dp_key_map:
        conditions |= Q(gun=dp_gun, ders_saati__derssaati_baslangic=dp_saat, sinif_sube_id=sid)

    dp_rows = (
        DersProgrami.objects
        .filter(conditions)
        .select_related("ogretmen", "sinif_sube", "ders_saati")
        .values(
            "gun",
            "sinif_sube_id",
            "ders_saati__derssaati_baslangic",
            "ogretmen__adi_soyadi",
        )
        .distinct()
    )

    # 4. Öğretmen → slotlar haritası
    result: dict[str, list[dict]] = {}
    for dp in dp_rows:
        ogr_adi = dp["ogretmen__adi_soyadi"]
        if not ogr_adi:
            continue
        gun      = dp["gun"]
        saat_str = dp["ders_saati__derssaati_baslangic"].strftime("%H:%M")
        sid      = dp["sinif_sube_id"]
        dp_key   = (gun, saat_str, sid)

        bilgi = dp_key_map.get(dp_key)
        if not bilgi:
            continue

        tarih, saat, oturum, _sid, sinif, sube = bilgi["slot_key"]
        salonlar = [{"ham": s, "ad": salon_goster(s)} for s in sorted(bilgi["salonlar"])]
        sinifsube = f"{sinif}/{sube}" if sinif and sube else ""

        result.setdefault(ogr_adi, [])
        # Aynı slot tekrar eklenmesini önle
        mevcut_anahtarlar = {(s["tarih"], s["saat"], s["oturum"]) for s in result[ogr_adi]}
        if (tarih, saat, oturum) not in mevcut_anahtarlar:
            result[ogr_adi].append({
                "tarih":      tarih,
                "saat":       saat,
                "oturum":     oturum,
                "sinifsube":  sinifsube,
                "salonlar":   salonlar,
                "onceki_saat": saat_str,  # gerçek önceki ders başlangıcı (aktivasyon için)
            })

    for slots in result.values():
        slots.sort(key=lambda x: (x["tarih"], x["saat"], x["oturum"]))

    return result
