"""Ajan paketi sayfası: üst yönetici tahtalara kurulacak .deb paketini indirir
ya da tahtada `wget` ile çekilecek süreli bir link üretir."""

from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.urls import reverse

from okul.auth import ust_yonetici_required
from tahtalar.models import Tahta
from tahtalar.services import ajan_paketi


def _paket_yaniti(sunucu):
    icerik = ajan_paketi.paket_olustur(sunucu)
    yanit = HttpResponse(icerik, content_type="application/vnd.debian.binary-package")
    yanit["Content-Disposition"] = f'attachment; filename="{ajan_paketi.paket_dosya_adi()}"'
    yanit["Cache-Control"] = "no-store"
    return yanit


def _varsayilan_sunucu(request):
    return request.build_absolute_uri("/").rstrip("/")


@ust_yonetici_required
def paket_sayfasi(request):
    surum = ajan_paketi.ajan_surumu()
    kaynak = request.POST if request.method == "POST" else request.GET
    sunucu_girdi = kaynak.get("sunucu") or _varsayilan_sunucu(request)
    baglam = {
        "title": "Tahta Ajanı Paketi",
        "surum": surum,
        "dosya_adi": ajan_paketi.paket_dosya_adi(),
        "sunucu": sunucu_girdi,
        "ca_var": ajan_paketi.ca_sertifikasi() is not None,
        "link_saat": ajan_paketi.LINK_GECERLILIK_SN // 3600,
        "eski_surumlu": Tahta.objects.filter(aktif=True)
        .exclude(ajan_surumu__in=["", surum])
        .order_by("ad"),
    }
    try:
        ajan_paketi.kayit_anahtari()
        sunucu = ajan_paketi.sunucu_adresini_dogrula(sunucu_girdi)
    except ajan_paketi.PaketHatasi as hata:
        baglam["hata"] = str(hata)
        return render(request, "tahtalar/paket.html", baglam)

    baglam["sunucu"] = sunucu
    baglam["ca_gomulu"] = baglam["ca_var"] and sunucu.startswith("https://")
    if request.method == "POST":
        if request.POST.get("islem") == "indir":
            return _paket_yaniti(sunucu)
        token = ajan_paketi.indirme_tokeni_uret(sunucu)
        baglam["link"] = sunucu + reverse("tahtalar:paket_link", args=[token])
    return render(request, "tahtalar/paket.html", baglam)


def paket_link(request, token):
    """Tahtanın `wget` ile çektiği süreli link. Oturum gerektirmez; imza ve süre
    kontrolü yetkidir (link, üst yöneticinin ürettiği imzalı token'ı taşır)."""
    sunucu = ajan_paketi.indirme_tokenini_coz(token)
    if not sunucu:
        raise Http404("Link geçersiz ya da süresi dolmuş.")
    try:
        return _paket_yaniti(sunucu)
    except ajan_paketi.PaketHatasi:
        raise Http404("Paket şu an üretilemiyor.") from None
