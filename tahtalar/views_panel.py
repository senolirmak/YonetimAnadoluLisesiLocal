"""Tahtalar sayfası: müdür yardımcısı ve okul müdürü tahtaların durumunu görür,
seçili tahtalara toplu kapat / yeniden başlat komutu verir."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from okul.auth import ust_yonetici_required
from tahtalar.models import KOMUT_GECERLILIK, Tahta, TahtaKomutu
from tahtalar.services import ajan_api, panel


@ust_yonetici_required
def tahta_listesi(request):
    filtre = request.GET.get("filtre")
    if filtre not in panel.FILTRELER:
        filtre = None
    return render(
        request,
        "tahtalar/liste.html",
        {
            "title": "Etkileşimli Tahtalar",
            "ozet": panel.ozet(),
            "tahtalar": panel.tahta_listesi(filtre),
            "filtre": filtre,
            "filtre_etiketi": panel.FILTRELER[filtre][0] if filtre else "",
            "ajansiz": panel.ajansiz_envanter(),
            "son_komutlar": panel.son_komutlar(),
            "komut_secenekleri": TahtaKomutu.PANEL_KOMUTLARI,
            "gecerlilik_dk": int(KOMUT_GECERLILIK.total_seconds() // 60),
        },
    )


@ust_yonetici_required
@require_POST
def komut_ver(request):
    komut = request.POST.get("komut")
    etiketler = dict(TahtaKomutu.PANEL_KOMUTLARI)
    secilen = [i for i in request.POST.getlist("tahta") if i.isdigit()]
    tahtalar = list(Tahta.objects.filter(pk__in=secilen, aktif=True))
    filtre = request.POST.get("filtre")
    geri = redirect(reverse("tahtalar:liste"))
    if filtre in panel.FILTRELER:
        geri = redirect(f"{reverse('tahtalar:liste')}?filtre={filtre}")

    if komut not in etiketler:
        messages.error(request, "Geçersiz komut.")
        return geri
    if not tahtalar:
        messages.error(request, "Önce en az bir tahta seçin.")
        return geri

    sayi = ajan_api.komut_olustur(tahtalar, komut, request.user)
    messages.success(
        request,
        f"{sayi} tahtaya “{etiketler[komut]}” komutu verildi. Tahtalar bir dakika içinde uygular.",
    )
    cevrimdisi = [t.ad for t in tahtalar if not t.cevrimici]
    if cevrimdisi:
        dakika = int(KOMUT_GECERLILIK.total_seconds() // 60)
        messages.info(
            request,
            f"Çevrimdışı: {', '.join(cevrimdisi)}. "
            f"Bu tahtalar {dakika} dakika içinde açılmazsa komut iptal olur.",
        )
    return geri
