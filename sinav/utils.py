# -*- coding: utf-8 -*-
"""
sinav app yardımcı fonksiyonları.
"""


def onceki_ders_saati(saat: str) -> str | None:
    """
    'HH:MM' formatındaki saatten 50 dakika çıkarır.
    Sonuç negatif olursa None döner.
    """
    h, m = map(int, saat.split(":"))
    total = h * 60 + m - 50
    if total < 0:
        return None
    return f"{total // 60:02d}:{total % 60:02d}"


def saat_offset(saat: str, dakika: int) -> str:
    """'HH:MM' formatına dakika ekler/çıkarır. Sonucu 'HH:MM' döner (negatif → '00:00')."""
    h, m = map(int, saat.split(":"))
    total = max(0, h * 60 + m + dakika)
    return f"{total // 60:02d}:{total % 60:02d}"


def slot_aktif_mi(tarih, saat: str, bugun, simdi_str: str,
                  baslangic_dk: int = -30, bitis_dk: int = 120) -> bool:
    """Slot'un buton erişimine açık olup olmadığını döner."""
    if tarih != bugun:
        return False
    return saat_offset(saat, baslangic_dk) <= simdi_str <= saat_offset(saat, bitis_dk)


# ── Sınav slot erişim kuralları ──────────────────────────────────────────────
# Her slot türü için geçerli saat penceresi (dakika cinsinden, sınav saatine göre).
# Değiştirmek istediğinizde yalnızca bu sözlüğü güncellemek yeterlidir.
SLOT_ERISIM_KURALLARI: dict[str, dict] = {
    "gozetim":      {"baslangic_dk":  -5, "bitis_dk":  35},  # Yoklama / Medya (sınav 40 dk)
    "siniflistesi": {"baslangic_dk": -50, "bitis_dk": -10},  # Sınıf Listesi PDF (sınav -50dk → -10dk)
}


def slot_listesi_aktif_isle(slotlar: list, tur: str, bugun, simdi_str: str) -> None:
    """
    Slot listesini yerinde (in-place) işler; her slota 'aktif' bayrağı ekler.

    Parametreler
    ------------
    slotlar   : [{"tarih": date, "saat": str, ...}, ...]
    tur       : SLOT_ERISIM_KURALLARI'ndaki anahtar ("gozetim" | "siniflistesi")
    bugun     : datetime.date — bugünün tarihi
    simdi_str : "HH:MM" — şu anki saat
    """
    kural = SLOT_ERISIM_KURALLARI[tur]
    for s in slotlar:
        s["aktif"] = slot_aktif_mi(
            s["tarih"], s["saat"], bugun, simdi_str,
            baslangic_dk=kural["baslangic_dk"],
            bitis_dk=kural["bitis_dk"],
        )


def salon_goster(salon_kodu: str) -> str:
    """'Salon-10_B' → 'Salon 10/B' formatına çevirir."""
    return salon_kodu.replace("-", " ", 1).replace("_", "/")


class AdminOverride:
    """
    Yönetici için sınav saati koşulunu oturum süresince bypass eden mekanizma.

    Kullanım:
        force = AdminOverride.is_active(request)  # view'da tek satır
        AdminOverride.toggle(request)              # toggle endpoint'te
    """

    _KEY = "sinav_admin_force_aktif"

    @classmethod
    def is_active(cls, request) -> bool:
        """Yalnızca superuser ise ve oturumda açık ise True döner."""
        if not request.user.is_superuser:
            return False
        return bool(request.session.get(cls._KEY, False))

    @classmethod
    def enable(cls, request) -> None:
        request.session[cls._KEY] = True

    @classmethod
    def disable(cls, request) -> None:
        request.session[cls._KEY] = False

    @classmethod
    def toggle(cls, request) -> bool:
        """Toggle yapar, yeni durumu (True/False) döner."""
        if cls.is_active(request):
            cls.disable(request)
            return False
        else:
            cls.enable(request)
            return True


def gozetmen_bul(aktif_sinav, tarih, saat: str, sinifsube: str) -> str | None:
    """
    Verilen (tarih, saat, sinifsube) için gözetmen öğretmenini döndürür.

    Kural: saat - 50 dakikada aynı sınıfta dersi olan öğretmen gözetmendir.
    Eşleşme bulunamazsa None döner.
    """
    from datetime import time as dt_time
    from dersprogrami.models import DersProgrami

    onceki_saat = onceki_ders_saati(saat)
    if not onceki_saat:
        return None

    gun = tarih.strftime("%A")  # "Monday", "Tuesday", ...

    # sinifsube "9/A" → sinif=9, sube="A"
    try:
        sinif_str, sube = sinifsube.split("/")
        sinif = int(sinif_str)
    except (ValueError, AttributeError):
        return None

    h, m = map(int, onceki_saat.split(":"))
    giris = dt_time(h, m)

    dp = (
        DersProgrami.objects
        .filter(
            gun=gun,
            ders_saati__derssaati_baslangic=giris,
            sinif_sube__sinif=sinif,
            sinif_sube__sube=sube,
            uygulama_tarihi__lte=tarih,
        )
        .order_by("-uygulama_tarihi")
        .select_related("ogretmen")
        .first()
    )

    return dp.ogretmen.adi_soyadi if dp else None
