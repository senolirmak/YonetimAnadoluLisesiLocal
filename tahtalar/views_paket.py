"""Kurulum paketi sayfası: üst yönetici tahtalara kurulacak akal-eta-yonetim
.deb paketini indirir
ya da tahtada `wget` ile çekilecek süreli bir link üretir."""

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from okul.auth import ust_yonetici_required
from tahtalar.models import Tahta
from tahtalar.services import kurulum_paketi


def _paket_yaniti(sunucu):
    icerik = kurulum_paketi.paket_olustur(sunucu)
    yanit = HttpResponse(icerik, content_type="application/vnd.debian.binary-package")
    yanit["Content-Disposition"] = f'attachment; filename="{kurulum_paketi.paket_dosya_adi()}"'
    yanit["Cache-Control"] = "no-store"
    return yanit


def _varsayilan_sunucu(request):
    return request.build_absolute_uri("/").rstrip("/")


@ust_yonetici_required
def paket_sayfasi(request):
    surum = kurulum_paketi.uygulama_surumu()
    kaynak = request.POST if request.method == "POST" else request.GET
    sunucu_girdi = kaynak.get("sunucu") or _varsayilan_sunucu(request)
    baglam = {
        "title": "akal-eta-yonetim Kurulum Paketi",
        "surum": surum,
        "dosya_adi": kurulum_paketi.paket_dosya_adi(),
        "sunucu": sunucu_girdi,
        "ca_var": kurulum_paketi.ca_sertifikasi() is not None,
        "link_saat": kurulum_paketi.LINK_GECERLILIK_SN // 3600,
        "eski_surumlu": Tahta.objects.filter(aktif=True)
        .exclude(ajan_surumu__in=["", surum])
        .order_by("ad"),
    }
    try:
        kurulum_paketi.kayit_anahtari()
        sunucu = kurulum_paketi.sunucu_adresini_dogrula(sunucu_girdi)
    except kurulum_paketi.PaketHatasi as hata:
        baglam["hata"] = str(hata)
        return render(request, "tahtalar/paket.html", baglam)

    baglam["sunucu"] = sunucu
    baglam["ca_gomulu"] = baglam["ca_var"] and sunucu.startswith("https://")
    if request.method == "POST":
        if request.POST.get("islem") == "indir":
            return _paket_yaniti(sunucu)
        token = kurulum_paketi.indirme_tokeni_uret(sunucu)
        baglam["link"] = sunucu + reverse("tahtalar:paket_link", args=[token])
    return render(request, "tahtalar/paket.html", baglam)


def paket_link(request, token):
    """Tahtanın `wget` ile çektiği süreli link. Oturum gerektirmez; imza ve süre
    kontrolü yetkidir (link, üst yöneticinin ürettiği imzalı token'ı taşır)."""
    sunucu = kurulum_paketi.indirme_tokenini_coz(token)
    if not sunucu:
        raise Http404("Link geçersiz ya da süresi dolmuş.")
    try:
        return _paket_yaniti(sunucu)
    except kurulum_paketi.PaketHatasi:
        raise Http404("Paket şu an üretilemiyor.") from None
