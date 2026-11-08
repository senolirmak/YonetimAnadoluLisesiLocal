"""Kurul toplantıları: liste, toplantı sayfası (gündem, katılım, kararlar, durum), PDF'ler ve takvim."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from kurul.forms import KararForm, ToplantiForm
from kurul.models import GundemMaddesi, Karar, Katilim, Kurul, Toplanti
from kurul.services import toplanti as ts
from kurul.services.toplanti_pdf import duyuru_pdf, karar_defteri_pdf, tutanak_pdf
from okul.auth import mudur_yardimcisi_required
from okul.utils import get_aktif_egitim_yili


def _kurul_yetkisi(request, kurul, yonetim=False):
    izin = ts.toplanti_yonetebilir(request.user, kurul) if yonetim else ts.toplanti_gorebilir(request.user, kurul)
    if not izin:
        raise PermissionDenied


def _okul_bilgisi():
    from okul.models import OkulBilgi

    bilgi = OkulBilgi.get()
    return (bilgi.okul_adi or ""), (bilgi.okul_muduru or "")


def _pdf(icerik, ad):
    yanit = HttpResponse(icerik, content_type="application/pdf")
    yanit["Content-Disposition"] = f'inline; filename="{ad}.pdf"'
    return yanit


@login_required
def toplantilar(request, pk):
    kurul = get_object_or_404(Kurul.objects.select_related("tur", "egitim_yili"), pk=pk)
    _kurul_yetkisi(request, kurul)
    yonetebilir = ts.toplanti_yonetebilir(request.user, kurul)
    form = ToplantiForm(initial={"tarih": timezone.localdate()})
    if request.method == "POST":
        if not yonetebilir:
            raise PermissionDenied
        form = ToplantiForm(request.POST)
        if form.is_valid():
            toplanti = ts.toplanti_olustur(kurul, olusturan=request.user, **form.cleaned_data)
            messages.success(request, f"{toplanti.no}. toplantı oluşturuldu; gündemi ve katılım listesi hazırlandı.")
            return redirect("kurul:toplanti_detay", pk=toplanti.pk)
    return render(request, "kurul/toplantilar.html", {
        "title": f"{kurul.ad} — Toplantılar",
        "kurul": kurul,
        "toplantilar": kurul.toplantilar.order_by("-tarih", "-saat"),
        "form": form,
        "yonetebilir": yonetebilir,
    })


@login_required
def toplanti_detay(request, pk):
    toplanti = get_object_or_404(
        Toplanti.objects.select_related("kurul__tur", "kurul__egitim_yili", "kurul__sinif_sube", "kurul__brans"),
        pk=pk,
    )
    kurul = toplanti.kurul
    _kurul_yetkisi(request, kurul)
    yonetebilir = ts.toplanti_yonetebilir(request.user, kurul)
    onaylayabilir = ts.onaylayabilir(request.user)
    bilgi_formu = ToplantiForm(instance=toplanti)
    karar_formu = KararForm(toplanti)

    if request.method == "POST":
        islem = request.POST.get("islem", "")
        if islem in ("onayla", "onayi_kaldir"):
            if not onaylayabilir:
                raise PermissionDenied
        elif not yonetebilir:
            raise PermissionDenied
        try:
            sonuc = _islem_uygula(request, toplanti, islem)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
            return redirect("kurul:toplanti_detay", pk=toplanti.pk)
        if isinstance(sonuc, (ToplantiForm, KararForm)):
            if isinstance(sonuc, ToplantiForm):
                bilgi_formu = sonuc
            else:
                karar_formu = sonuc
        else:
            return redirect("kurul:toplanti_detay", pk=toplanti.pk)

    onceki = ts.onceki_toplanti(toplanti)
    return render(request, "kurul/toplanti_detay.html", {
        "title": f"{kurul.ad} — {toplanti.no}. Toplantı",
        "toplanti": toplanti,
        "kurul": kurul,
        "gizli": kurul.tur.gizli,
        "gundem": toplanti.gundem.all(),
        "katilimlar": toplanti.katilimlar.all(),
        "kararlar": toplanti.kararlar.select_related("sorumlu", "gundem_maddesi"),
        "onceki": onceki,
        "onceki_kararlar": onceki.kararlar.all() if onceki else [],
        "oneriler": ts.gundem_onerileri(toplanti),
        "bilgi_formu": bilgi_formu,
        "karar_formu": karar_formu,
        "katilim_durumlari": Katilim.DURUM_CHOICES,
        "takip_durumlari": Karar.TAKIP_CHOICES,
        "yonetebilir": yonetebilir and toplanti.duzenlenebilir,
        "takip_edebilir": yonetebilir,
        "onaylayabilir": onaylayabilir,
    })


def _islem_uygula(request, toplanti, islem):
    """Toplantı sayfasındaki POST işlemleri. Hatalı form dönerse sayfa yeniden çizilir."""
    p = request.POST
    if islem == "bilgi":
        if not toplanti.duzenlenebilir:
            raise ValidationError("Onaylanmış ya da iptal edilmiş toplantı düzenlenemez.")
        form = ToplantiForm(p, instance=toplanti)
        if not form.is_valid():
            return form
        form.save()
        messages.success(request, "Toplantı bilgileri kaydedildi.")
    elif islem == "gundem_ekle":
        basliklar = p.getlist("oneri") + [p.get("baslik", "")]
        n = ts.gundem_ekle(toplanti, basliklar)
        messages.success(request, f"{n} gündem maddesi eklendi.")
    elif islem in ("gundem_yukari", "gundem_asagi", "gundem_sil"):
        madde = get_object_or_404(GundemMaddesi, pk=p.get("madde"), toplanti=toplanti)
        if islem == "gundem_sil":
            ts.gundem_sil(madde)
        else:
            ts.gundem_tasi(madde, -1 if islem == "gundem_yukari" else 1)
    elif islem == "gorusme":
        ozetler = {int(k[8:]): v.strip() for k, v in p.items() if k.startswith("gorusme_") and k[8:].isdigit()}
        ts.gorusmeleri_kaydet(toplanti, ozetler)
        messages.success(request, "Görüşme özetleri kaydedildi.")
    elif islem == "katilim":
        durumlar = {
            int(k[6:]): (v, p.get(f"aciklama_{k[6:]}", ""))
            for k, v in p.items() if k.startswith("durum_") and k[6:].isdigit()
        }
        ts.katilimi_kaydet(toplanti, durumlar)
        messages.success(request, "Katılım kaydedildi.")
    elif islem == "katilim_esitle":
        n = ts.katilimi_esitle(toplanti)
        messages.success(request, f"Katılım listesine {n} yeni üye eklendi.")
    elif islem == "karar_ekle":
        form = KararForm(toplanti, p)
        if not form.is_valid():
            return form
        ts.karar_ekle(toplanti, **form.cleaned_data)
        messages.success(request, "Karar eklendi.")
    elif islem == "karar_sil":
        ts.karar_sil(get_object_or_404(Karar, pk=p.get("karar"), toplanti=toplanti))
        messages.success(request, "Karar silindi.")
    elif islem == "karar_takip":
        karar = get_object_or_404(Karar, pk=p.get("karar"), toplanti=toplanti)
        ts.karar_takibi(karar, p.get("takip_durumu"), p.get("takip_notu", ""))
        messages.success(request, f"{karar.no}. kararın takip durumu güncellendi.")
    elif islem in ("duyur", "yapildi", "onayla", "onayi_kaldir", "iptal"):
        ts.durum_degistir(toplanti, islem, request.user)
        messages.success(request, f"Toplantı durumu: {toplanti.get_durum_display()}.")
        if islem == "duyur" and toplanti.duyuru_suresi_yetersiz:
            messages.warning(request, f"Duyuru toplantıdan {toplanti.duyuru_gun_farki} gün önce yapıldı; "
                                      "olağan toplantılar en az 5 gün önceden duyurulmalıdır.")
    else:
        raise ValidationError("Geçersiz işlem.")
    return None


@login_required
def toplanti_duyuru_pdf(request, pk):
    toplanti = get_object_or_404(Toplanti.objects.select_related("kurul__tur", "kurul__egitim_yili"), pk=pk)
    _kurul_yetkisi(request, toplanti.kurul)
    okul_adi, _ = _okul_bilgisi()
    return _pdf(duyuru_pdf(toplanti, okul_adi), f"toplanti-{toplanti.pk}-duyuru")


@login_required
def toplanti_tutanak_pdf(request, pk):
    toplanti = get_object_or_404(Toplanti.objects.select_related("kurul__tur", "kurul__egitim_yili"), pk=pk)
    _kurul_yetkisi(request, toplanti.kurul)
    okul_adi, mudur = _okul_bilgisi()
    return _pdf(tutanak_pdf(toplanti, okul_adi, mudur), f"toplanti-{toplanti.pk}-tutanak")


@login_required
def karar_defteri(request, pk):
    kurul = get_object_or_404(Kurul.objects.select_related("tur", "egitim_yili"), pk=pk)
    _kurul_yetkisi(request, kurul)
    okul_adi, _ = _okul_bilgisi()
    return _pdf(karar_defteri_pdf(kurul, okul_adi), f"kurul-{kurul.pk}-karar-defteri")


@mudur_yardimcisi_required
def toplanti_takvimi(request):
    """Yılın bütün kurul toplantıları; yaklaşanlar ve onay bekleyenler öne çıkar."""
    yil = get_aktif_egitim_yili()
    toplantilar = (
        Toplanti.objects.filter(kurul__egitim_yili=yil)
        .select_related("kurul__tur", "kurul__sinif_sube", "kurul__brans").order_by("tarih", "saat")
        if yil else Toplanti.objects.none()
    )
    bugun = timezone.localdate()
    return render(request, "kurul/toplanti_takvimi.html", {
        "title": "Kurul Toplantı Takvimi",
        "egitim_yili": yil,
        "yaklasan": [t for t in toplantilar if t.tarih >= bugun and t.durum != Toplanti.DURUM_IPTAL],
        "onay_bekleyen": [t for t in toplantilar if t.durum == Toplanti.DURUM_YAPILDI],
        "gecmis": [t for t in toplantilar if t.tarih < bugun or t.durum == Toplanti.DURUM_IPTAL][::-1],
    })
