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
