"""Öğrenci İşleri sayfası için günün kısa özeti."""

from devamsizlik.models import OgrenciDevamsizlik
from ogrenci.models import Ogrenci
from ogrencinobet.models import OgrenciNobetGorevi


def ogrenci_ozeti(tarih) -> dict:
    """Aktif öğrenci sayısı; `tarih` günü yoklamada devamsız ve nöbetçi öğrenci sayıları."""
    return {
        "tarih": tarih,
        "aktif_ogrenci": Ogrenci.objects.filter(aktif=True).count(),
        "devamsiz_ogrenci": (
            OgrenciDevamsizlik.objects.filter(tarih=tarih).values("ogrenci").distinct().count()
        ),
        "nobetci_ogrenci": OgrenciNobetGorevi.objects.filter(tarih=tarih).count(),
    }
