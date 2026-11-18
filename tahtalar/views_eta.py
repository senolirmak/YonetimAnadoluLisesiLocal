"""ETA envanter kaydı sayfası: üst yönetici tahtaların ETA (eta-register)
kayıt durumunu görür, seçili tahtalara okul kodu ve birim adıyla kayıt /
güncelleme komutu verir. İstek MEB'in ETA sunucusuna tahtadaki akal-eta-yonetim'den gider."""

from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse

from okul.auth import ust_yonetici_required
from okul.models import OkulBilgi
from tahtalar.models import KOMUT_GECERLILIK, Tahta, TahtaKomutu
from tahtalar.services import ajan_api


def _son_eta_komutlari(tahtalar):
    son = {}
    for komut in TahtaKomutu.objects.filter(
        tahta__in=tahtalar, komut=TahtaKomutu.ETA_KAYDET
    ).order_by("-olusturma"):
        son.setdefault(komut.tahta_id, komut)
    return son


@ust_yonetici_required
def eta_sayfasi(request):
    tahtalar = list(Tahta.objects.filter(aktif=True).select_related("envanter").order_by("ad"))
    if request.method == "POST":
        return _komut_ver(request, tahtalar)

    ajan_api.suresi_dolanlari_iptal_et()
    son_komutlar = _son_eta_komutlari(tahtalar)
    okul_kodu = OkulBilgi.get().okul_kodu
    for t in tahtalar:
        t.birim_onerisi = ajan_api.eta_birim_onerisi(t)
        t.son_eta_komutu = son_komutlar.get(t.pk)
        t.baska_okulda = bool(
            t.eta_kayitli and okul_kodu and t.eta_okul_kodu and t.eta_okul_kodu != okul_kodu
        )
    return render(
        request,
        "tahtalar/eta.html",
        {
            "title": "ETA Kaydı",
            "tahtalar": tahtalar,
            "okul_kodu": okul_kodu,
            "kayitli": sum(1 for t in tahtalar if t.eta_kayitli),
            "kayitsiz": sum(1 for t in tahtalar if t.eta_kayitli is False),
            "bilinmiyor": sum(1 for t in tahtalar if t.eta_kayitli is None),
            "gecerlilik_dk": int(KOMUT_GECERLILIK.total_seconds() // 60),
            "birim_en_az": ajan_api.ETA_BIRIM_EN_AZ,
            "birim_en_cok": ajan_api.ETA_BIRIM_EN_COK,
        },
    )


def _komut_ver(request, tahtalar):
    geri = redirect(reverse("tahtalar:eta"))
    try:
        okul_kodu = ajan_api.eta_okul_kodu_dogrula(request.POST.get("okul_kodu"))
    except ValueError as hata:
        messages.error(request, str(hata))
        return geri

    secilen = set(request.POST.getlist("tahta"))
    tahta_birimleri, hatalar = [], []
    for tahta in tahtalar:
        if str(tahta.pk) not in secilen:
            continue
        try:
            birim = ajan_api.eta_birim_adi_dogrula(request.POST.get(f"birim_{tahta.pk}"))
        except ValueError as hata:
            hatalar.append(f"{tahta.ad}: {hata}")
            continue
        tahta_birimleri.append((tahta, birim))

    if hatalar:
        messages.error(request, "Komut verilmedi. " + " ".join(hatalar))
        return geri
    if not tahta_birimleri:
        messages.error(request, "Önce en az bir tahta seçin.")
        return geri

    sayi = ajan_api.eta_kayit_komutu_olustur(tahta_birimleri, okul_kodu, request.user)
    messages.success(
        request,
        f"{sayi} tahtaya ETA kayıt komutu verildi (okul kodu {okul_kodu}). "
        "Tahtalar bir dakika içinde uygular; sonuç bu sayfada görünür.",
    )
    cevrimdisi = [t.ad for t, _ in tahta_birimleri if not t.cevrimici]
    if cevrimdisi:
        dakika = int(KOMUT_GECERLILIK.total_seconds() // 60)
        messages.info(
            request,
            f"Çevrimdışı: {', '.join(cevrimdisi)}. "
            f"Bu tahtalar {dakika} dakika içinde açılmazsa komut iptal olur.",
        )
    return geri
