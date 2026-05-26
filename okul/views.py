# -*- coding: utf-8 -*-
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from okul.forms import DersHavuzuForm
from okul.models import DersHavuzu


@login_required
def ders_havuzu_ayarlari(request):
    from django.db.models import Case, When, IntegerField
    dersler = DersHavuzu.objects.annotate(
        sort_key=Case(
            When(sinav_yapilmayacak=True, then=0),
            When(cift_oturum=1, then=1),
            default=2,
            output_field=IntegerField(),
        )
    ).order_by("sort_key", "ders_adi")
    forms = {d.pk: DersHavuzuForm(instance=d, prefix=f"ders_{d.pk}") for d in dersler}
    return render(request, "okul/ders_havuzu_ayarlari.html", {
        "dersler": dersler,
        "forms": forms,
        "next_url": request.GET.get("next", ""),
    })


@login_required
@require_POST
def ders_havuzu_ayarlari_kaydet(request):
    dersler = DersHavuzu.objects.all()
    guncellenen = 0
    for d in dersler:
        form = DersHavuzuForm(request.POST, instance=d, prefix=f"ders_{d.pk}")
        if form.is_valid() and form.has_changed():
            form.save()
            guncellenen += 1
    messages.success(request, f"{guncellenen} ders güncellendi.")
    next_url = request.POST.get("next_url", "")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("okul:ders_havuzu_ayarlari")


# ─────────────────────────────────────────────────────────
# Okul Yapılandırması
# ─────────────────────────────────────────────────────────

@login_required
def okul_ayarlari(request):
    from django.core.exceptions import PermissionDenied
    from django.shortcuts import get_object_or_404
    from nobet.models import OkulBilgi, EgitimOgretimYili, OkulDonem
    from main.forms import EgitimOgretimYiliForm, OkulBilgiAyarForm, OkulDonemForm

    user = request.user
    if not (user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()):
        raise PermissionDenied

    okul = OkulBilgi.objects.select_related("okul_donem", "okul_egtyil").first()
    egitim_yillari = EgitimOgretimYili.objects.prefetch_related("donemleri").order_by("-egitim_yili")

    action = request.POST.get("action", "") if request.method == "POST" else ""

    okul_form = OkulBilgiAyarForm(
        request.POST if action == "okul_bilgi" else None,
        instance=okul,
    )
    if action == "okul_bilgi" and okul_form.is_valid():
        okul_form.save()
        messages.success(request, "Okul bilgileri güncellendi.")
        return redirect("okul_ayarlari")

    eyil_pk = request.POST.get("eyil_pk", "").strip()
    eyil_instance = get_object_or_404(EgitimOgretimYili, pk=eyil_pk) if eyil_pk else None
    eyil_form = EgitimOgretimYiliForm(
        request.POST if action == "egitim_yili" else None,
        instance=eyil_instance,
    )
    if action == "egitim_yili" and eyil_form.is_valid():
        yil = eyil_form.save()
        msg = "güncellendi" if eyil_pk else "eklendi"
        if not eyil_pk:
            messages.info(request, f"'{yil.egitim_yili}' eklendi. Lütfen dönem tarihlerini giriniz.")
        else:
            messages.success(request, f"'{yil.egitim_yili}' {msg}.")
        return redirect("okul_ayarlari")

    donem_pk = request.POST.get("donem_pk", "").strip()
    donem_instance = get_object_or_404(OkulDonem, pk=donem_pk) if donem_pk else None
    donem_form = OkulDonemForm(
        request.POST if action == "donem" else None,
        instance=donem_instance,
    )
    if action == "donem" and donem_form.is_valid():
        donem_form.save()
        messages.success(request, "Dönem kaydedildi.")
        return redirect("okul_ayarlari")

    aktif_form = action if action in ("okul_bilgi", "egitim_yili", "donem") else None

    context = {
        "title": "Okul Yapılandırması",
        "okul": okul,
        "okul_form": okul_form,
        "egitim_yillari": egitim_yillari,
        "eyil_form": eyil_form,
        "eyil_pk": eyil_pk,
        "donem_form": donem_form,
        "donem_pk": donem_pk,
        "aktif_form": aktif_form,
    }
    return render(request, "okul/okul_ayarlari.html", context)
