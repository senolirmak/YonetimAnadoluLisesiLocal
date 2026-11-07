"""nobet view'larının yetki adları — mantık yok, hepsi okul.auth'tan gelir.

Bu modül, nobet.views.* ve `nobet.views` paketinin eski adlarla içe aktardığı
yetki yardımcılarını korumak için durur. Yeni kodda doğrudan `okul.auth`
kullanın.
"""

from okul.auth import (
    UST_YONETIM_GRUPLARI,
    YONETICI_GRUPLARI,
    MudurYardimcisiMixin,
    is_mudur_yardimcisi,
    is_ust_yonetici,
    is_yonetici,
    mudur_yardimcisi_required,
    ust_yonetici_required,
    yonetici_required,
)

# Eski adlar
YONETICI_GRUPLAR = YONETICI_GRUPLARI
TARIH_DEGISTIREBILIR_GRUPLAR = UST_YONETIM_GRUPLARI
is_tarih_degistirebilir = is_ust_yonetici
mudur_required = ust_yonetici_required

__all__ = [
    "YONETICI_GRUPLAR",
    "TARIH_DEGISTIREBILIR_GRUPLAR",
    "MudurYardimcisiMixin",
    "is_mudur_yardimcisi",
    "is_tarih_degistirebilir",
    "is_ust_yonetici",
    "is_yonetici",
    "mudur_required",
    "mudur_yardimcisi_required",
    "ust_yonetici_required",
    "yonetici_required",
]
