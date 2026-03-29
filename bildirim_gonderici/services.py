"""
Bildirim gönderim servisi.

Her gönderim ayrı bir arka plan iş parçacığında (thread) çalışır;
bu sayede Django isteği bloklanmaz.
"""
import logging
import threading
import urllib.error
import urllib.request
import json

from django.conf import settings

logger = logging.getLogger(__name__)

# settings.py'de tanımlanabilir; yoksa varsayılan kullanılır
BILDIRIM_TIMEOUT = getattr(settings, "BILDIRIM_TIMEOUT", 4)  # saniye
BILDIRIM_ANAHTAR = getattr(settings, "BILDIRIM_ANAHTAR", "okul-bildirim-2024")


def _gonder_istek(tahta, baslik, mesaj, tur, gonderen_id):
    """Tahta ajanına HTTP POST gönderir; sonucu BildirimLog'a kaydeder."""
    from bildirim_gonderici.models import BildirimLog  # circular import'u önlemek için

    veri = json.dumps(
        {
            "anahtar": BILDIRIM_ANAHTAR,
            "baslik": baslik,
            "mesaj": mesaj,
            "sure_ms": 15000,
        }
    ).encode("utf-8")

    durum = BildirimLog.DURUM_BASARISIZ
    hata = ""

    try:
        req = urllib.request.Request(
            tahta.url,
            data=veri,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=BILDIRIM_TIMEOUT) as resp:
            if resp.status == 200:
                durum = BildirimLog.DURUM_BASARILI
                logger.info("Bildirim gönderildi → %s (%s)", tahta, baslik)
            else:
                hata = f"HTTP {resp.status}"
    except Exception as exc:
        hata = str(exc)
        logger.warning("Bildirim gönderilemedi → %s : %s", tahta, exc)

    from django.contrib.auth.models import User

    gonderen = None
    if gonderen_id:
        try:
            gonderen = User.objects.get(pk=gonderen_id)
        except User.DoesNotExist:
            pass

    BildirimLog.objects.create(
        tahta=tahta,
        tur=tur,
        baslik=baslik,
        mesaj=mesaj,
        gonderen=gonderen,
        durum=durum,
        hata_mesaji=hata,
    )


def tahta_bildirimi_gonder(tahta, baslik, mesaj, tur, gonderen=None):
    """Tek bir tahtaya arka planda bildirim gönderir."""
    if not tahta.aktif:
        return
    gonderen_id = gonderen.pk if gonderen else None
    t = threading.Thread(
        target=_gonder_istek,
        args=(tahta, baslik, mesaj, tur, gonderen_id),
        daemon=True,
    )
    t.start()


def sinif_bildirimi_gonder(sinif_sube, baslik, mesaj, tur, gonderen=None):
    """
    Verilen SinifSube'ye ait aktif tahtaya bildirim gönderir.
    Tahta kaydı yoksa veya pasifse sessizce geçer.
    """
    from bildirim_gonderici.models import SinifTahta

    try:
        tahta = SinifTahta.objects.get(sinif_sube=sinif_sube, aktif=True)
    except SinifTahta.DoesNotExist:
        return

    tahta_bildirimi_gonder(tahta, baslik, mesaj, tur, gonderen)
