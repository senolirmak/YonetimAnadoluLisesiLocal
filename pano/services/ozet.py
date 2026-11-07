"""Bilgi Panosu giriş sayfası için pano içeriklerinin kısa özeti."""

from django.utils import timezone

from pano.models import Duyuru, Etkinlik, KioskAyar, MedyaIcerik


def pano_ozeti() -> dict:
    """Şu an yayındaki duyuru, bugünkü/sonraki etkinlik ve aktif medya sayıları,
    aktif kiosk ayarı (yoksa None)."""
    simdi = timezone.now()
    bugun = timezone.localdate()
    return {
        "yayindaki_duyuru": sum(1 for d in Duyuru.objects.filter(aktif=True) if d.yayinda_mi(simdi)),
        "yaklasan_etkinlik": Etkinlik.objects.filter(aktif=True, baslangic__date__gte=bugun).count(),
        "aktif_medya": MedyaIcerik.objects.filter(aktif=True).count(),
        "kiosk": KioskAyar.objects.filter(aktif=True).first(),
    }
