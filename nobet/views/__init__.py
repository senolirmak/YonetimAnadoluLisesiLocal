# nobet/views/__init__.py
# Geriye dönük uyumluluk: tüm public isimler buradan erişilebilir.

from .dagitim import (
    _get_report_header_info,
    _gun_adi_tr,
    manuel_dagitim,
    nobet_dagitim,
)
from .ders_doldurma import (
    NobetPDFReport,
    _generate_pdf_bytes,
    download_ders_doldurma_pdf,
    download_ders_doldurma_png,
    download_ders_doldurma_xlsx,
    nobet_ders_doldurma,
)
from .gunun_nobetcileri import (
    devamsizlik_sinif_pdf,
    download_gunun_nobetcileri_png,
    download_unassigned_ders_png,
    gunun_nobetcileri,
)
from .permissions import (
    TARIH_DEGISTIREBILIR_GRUPLAR,
    YONETICI_GRUPLAR,
    MudurYardimcisiMixin,
    is_mudur_yardimcisi,
    is_tarih_degistirebilir,
    is_yonetici,
    mudur_required,
    mudur_yardimcisi_required,
    yonetici_required,
)

__all__ = [
    # permissions
    "YONETICI_GRUPLAR",
    "TARIH_DEGISTIREBILIR_GRUPLAR",
    "is_mudur_yardimcisi",
    "is_yonetici",
    "is_tarih_degistirebilir",
    "mudur_required",
    "mudur_yardimcisi_required",
    "yonetici_required",
    "MudurYardimcisiMixin",
    # dagitim
    "_get_report_header_info",
    "_gun_adi_tr",
    "nobet_dagitim",
    "manuel_dagitim",
    # ders_doldurma
    "NobetPDFReport",
    "_generate_pdf_bytes",
    "nobet_ders_doldurma",
    "download_ders_doldurma_pdf",
    "download_ders_doldurma_png",
    "download_ders_doldurma_xlsx",
    # gunun_nobetcileri
    "gunun_nobetcileri",
    "download_gunun_nobetcileri_png",
    "download_unassigned_ders_png",
    "devamsizlik_sinif_pdf",
]
