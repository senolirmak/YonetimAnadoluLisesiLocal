from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ekders.forms import EkDersDonemiForm, EkDersOnayForm, OgretmenEkDersForm, TatilForm
from ekders.models import EkDersDonemi, EkDersOnay, OgretmenEkDers, Tatil
from ekders.services import donem_hesapla, donem_ozet_listesi, personel_ozet


# ── Dönem Listesi ────────────────────────────────────────────────────────────

@login_required
def donem_listesi(request):
    donemler = EkDersDonemi.objects.select_related("olusturan").all()
    return render(request, "ekders/donem_listesi.html", {"donemler": donemler})


# ── Dönem Oluştur / Düzenle ──────────────────────────────────────────────────

@login_required
def donem_olustur(request):
    if request.method == "POST":
        form = EkDersDonemiForm(request.POST)
        if form.is_valid():
            donem = form.save(commit=False)
            donem.olusturan = request.user
            donem.save()
            messages.success(request, f"'{donem.ad}' dönemi oluşturuldu.")
            return redirect("ekders:donem_detay", pk=donem.pk)
    else:
        form = EkDersDonemiForm()
    return render(request, "ekders/donem_olustur.html", {"form": form, "baslik": "Yeni Dönem"})


@login_required
def donem_duzenle(request, pk):
    donem = get_object_or_404(EkDersDonemi, pk=pk)
    if donem.kapandi:
        messages.error(request, "Kapalı dönem düzenlenemez.")
        return redirect("ekders:donem_detay", pk=pk)
    if request.method == "POST":
        form = EkDersDonemiForm(request.POST, instance=donem)
        if form.is_valid():
            form.save()
            messages.success(request, "Dönem güncellendi.")
            return redirect("ekders:donem_detay", pk=pk)
    else:
        form = EkDersDonemiForm(instance=donem)
    return render(request, "ekders/donem_olustur.html", {"form": form, "baslik": "Dönem Düzenle", "donem": donem})


# ── Dönem Detay ──────────────────────────────────────────────────────────────

@login_required
def donem_detay(request, pk):
    from datetime import date as date_type
    donem = get_object_or_404(EkDersDonemi, pk=pk)

    haftalar = list(
        OgretmenEkDers.objects
        .filter(donem=donem)
        .values_list("hafta_baslangic", flat=True)
        .distinct()
        .order_by("hafta_baslangic")
    )

    secili_hafta = None
    hafta_str = request.GET.get("hafta")
    if hafta_str:
        try:
            secili_hafta = date_type.fromisoformat(hafta_str)
        except ValueError:
            pass
    if secili_hafta not in haftalar:
        secili_hafta = haftalar[0] if haftalar else None

    hafta_kayitlari = []
    if secili_hafta:
        hafta_kayitlari = (
            OgretmenEkDers.objects
            .filter(donem=donem, hafta_baslangic=secili_hafta)
            .select_related("personel", "gorev_tipi")
            .order_by("personel__adi_soyadi")
        )

    onay = getattr(donem, "onay", None)
    return render(request, "ekders/donem_detay.html", {
        "donem": donem,
        "haftalar": haftalar,
        "secili_hafta": secili_hafta,
        "hafta_kayitlari": hafta_kayitlari,
        "onay": onay,
        "onay_form": EkDersOnayForm() if not onay and not donem.kapandi else None,
    })


# ── Otomatik Hesaplama ───────────────────────────────────────────────────────

@require_POST
@login_required
def donem_hesapla_view(request, pk):
    donem = get_object_or_404(EkDersDonemi, pk=pk)
    if donem.kapandi:
        messages.error(request, "Kapalı dönem için hesaplama yapılamaz.")
        return redirect("ekders:donem_detay", pk=pk)
    sayisi = donem_hesapla(donem)
    messages.success(request, f"Hesaplama tamamlandı: {sayisi} haftalık kayıt oluşturuldu/güncellendi.")
    return redirect("ekders:donem_detay", pk=pk)


# ── Haftalık Kayıt Düzenle ───────────────────────────────────────────────────

@login_required
def hafta_duzenle(request, pk, kayit_pk):
    donem = get_object_or_404(EkDersDonemi, pk=pk)
    kayit = get_object_or_404(OgretmenEkDers, pk=kayit_pk, donem=donem)
    if donem.kapandi:
        messages.error(request, "Kapalı dönem düzenlenemez.")
        return redirect("ekders:donem_detay", pk=pk)
    if request.method == "POST":
        form = OgretmenEkDersForm(request.POST, instance=kayit)
        if form.is_valid():
            form.save()
            messages.success(request, f"{kayit.personel} – {kayit.hafta_baslangic:%d.%m.%Y} kaydı güncellendi.")
            hafta_str = request.GET.get("hafta", "")
            url = f"/ekders/{pk}/" + (f"?hafta={hafta_str}" if hafta_str else "")
            return redirect(url)
    else:
        form = OgretmenEkDersForm(instance=kayit)
    return render(request, "ekders/hafta_duzenle.html", {
        "donem": donem,
        "kayit": kayit,
        "form": form,
    })


# ── Onay ─────────────────────────────────────────────────────────────────────

@require_POST
@login_required
def donem_onayla(request, pk):
    donem = get_object_or_404(EkDersDonemi, pk=pk)
    if donem.kapandi:
        messages.error(request, "Bu dönem zaten onaylanmış.")
        return redirect("ekders:donem_detay", pk=pk)
    if not donem.kayitlar.exists():
        messages.error(request, "Onaylamadan önce hesaplama yapın.")
        return redirect("ekders:donem_detay", pk=pk)
    form = EkDersOnayForm(request.POST)
    if form.is_valid():
        onay = form.save(commit=False)
        onay.donem = donem
        onay.onaylayan = request.user
        onay.save()
        donem.kapandi = True
        donem.save(update_fields=["kapandi"])
        messages.success(request, f"'{donem.ad}' dönemi onaylandı ve kapatıldı.")
    return redirect("ekders:donem_detay", pk=pk)


# ── Tatil CRUD ───────────────────────────────────────────────────────────────

@login_required
def tatil_listesi(request):
    tatiller = Tatil.objects.all()
    form = TatilForm()
    if request.method == "POST":
        form = TatilForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tatil eklendi.")
            return redirect("ekders:tatil_listesi")
    return render(request, "ekders/tatil_listesi.html", {"tatiller": tatiller, "form": form})


@require_POST
@login_required
def tatil_sil(request, pk):
    tatil = get_object_or_404(Tatil, pk=pk)
    tatil.delete()
    messages.success(request, "Tatil silindi.")
    return redirect("ekders:tatil_listesi")
