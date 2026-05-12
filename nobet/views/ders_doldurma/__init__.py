# nobet/views/ders_doldurma/__init__.py
# Geriye dönük uyumluluk: nobet/views/__init__.py aynı import yollarını kullanmaya devam eder.

from ._pdf import (
    generate_pdf_bytes as _generate_pdf_bytes,
    download_ders_doldurma_pdf,
    download_ders_doldurma_png,
)
from .view import nobet_ders_doldurma

__all__ = [
    "nobet_ders_doldurma",
    "_generate_pdf_bytes",
    "download_ders_doldurma_pdf",
    "download_ders_doldurma_png",
]
