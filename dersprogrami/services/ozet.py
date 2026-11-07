"""Ders Programı İşlemleri sayfası için aktif ders programının kısa özeti."""

from dersprogrami.models import DersProgrami
from okul.utils import get_aktif_dp_tarihi


def ders_programi_ozeti() -> dict:
    """Aktif ders programının tarihi, öğretmen / sınıf-şube / haftalık ders saati sayıları."""
    aktif = DersProgrami.objects.aktif()
    return {
        "uygulama_tarihi": get_aktif_dp_tarihi(),
        "ogretmen_sayisi": aktif.values("ogretmen").distinct().count(),
        "sinif_sube_sayisi": aktif.values("sinif_sube").distinct().count(),
        "ders_saati_sayisi": aktif.count(),
    }
