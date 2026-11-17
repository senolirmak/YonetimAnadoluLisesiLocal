"""Tahtalar sayfası (/tahtalar/) ve Okul Yönetimi kartı için sorgular."""

import datetime

from django.db.models import Prefetch

from tahtalar.models import Tahta, TahtaEnvanteri, TahtaKomutu

FILTRELER = {
    "cevrimici": ("Çevrimiçi", lambda qs: qs.cevrimici()),
    "cevrimdisi": ("Çevrimdışı", lambda qs: qs.cevrimdisi()),
    "ahenk_sorunlu": (
        "Ahenk çalışmıyor",
        lambda qs: qs.exclude(ahenk_servisi=Tahta.AHENK_CALISIYOR),
    ),
    "meb_kayitsiz": ("MEB'e kayıtsız", lambda qs: qs.exclude(meb_kayitli=True)),
    "guncelleme": (
        "Güncelleniyor / sorunlu güncelleme",
        lambda qs: qs.filter(
            guncelleme_durumu__in=[
                Tahta.GUNCELLEME_SURUYOR,
                Tahta.GUNCELLEME_BASARISIZ,
                Tahta.GUNCELLEME_YARIDA_KALDI,
            ]
        ),
    ),
}


def ozet():
    tahtalar = Tahta.objects.filter(aktif=True)
    return {
        "toplam": tahtalar.count(),
        "cevrimici": tahtalar.cevrimici().count(),
        "ahenk_sorunlu": tahtalar.exclude(ahenk_servisi=Tahta.AHENK_CALISIYOR).count(),
        "meb_kayitsiz": tahtalar.exclude(meb_kayitli=True).count(),
        "ajansiz": ajansiz_envanter().count(),
        "guncelleme": FILTRELER["guncelleme"][1](tahtalar).count(),
    }


def tahta_listesi(filtre=None):
    son_komut = TahtaKomutu.objects.order_by("-olusturma")
    qs = (
        Tahta.objects.filter(aktif=True)
        .select_related("envanter")
        .prefetch_related(Prefetch("komutlar", queryset=son_komut, to_attr="komut_gecmisi"))
        .order_by("konum", "ad")
    )
    if filtre in FILTRELER:
        qs = FILTRELER[filtre][1](qs)
    tahtalar = list(qs)
    for tahta in tahtalar:
        tahta.son_komut = tahta.komut_gecmisi[0] if tahta.komut_gecmisi else None
        tahta.ekran_oturumu = _gosterim(tahta.aktif_oturum)
        tahta.diger_oturum_sayisi = (
            len(tahta.oturumlar) - (1 if tahta.ekran_oturumu else 0) if tahta.cevrimici else 0
        )
    return tahtalar


def _gosterim(oturum):
    if not oturum:
        return None
    baslangic = oturum.get("baslangic")
    return {
        **oturum,
        "baslangic": (
            datetime.datetime.fromtimestamp(baslangic, tz=datetime.UTC) if baslangic else None
        ),
    }


def ajansiz_envanter():
    """MEB Lider listesinde olan ama ajanı henüz bağlanmamış tahtalar."""
    return TahtaEnvanteri.objects.filter(tahta__isnull=True).order_by("sube_adi")


def son_komutlar(adet=15):
    return TahtaKomutu.objects.select_related("tahta", "olusturan")[:adet]
