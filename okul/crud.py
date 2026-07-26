# -*- coding: utf-8 -*-
"""
okul/yonetim/ — okul app'inin temel yapılandırma modelleri için üretim CRUD'u.

Kapsam dışı bırakılanlar (bilinçli tercih):
  - OkulBilgi: singleton kayıt, ekleme/silme anlamsız — okul_ayarlari'nda kalır.
  - VeriAktarimGecmisi / AktifVeriKonfigurasyonu: import servislerinin ürettiği
    sistem/denetim kayıtları — elle CRUD veri bütünlüğünü bozabilir.
  - OkulYonetici: yetki ataması yapan hassas bir kayıt — Django admin'de kalır.
"""

from collections import Counter

from django.contrib import messages
from django.contrib.admin.utils import NestedObjects
from django.db import router
from django.db.models import Count, ProtectedError, RestrictedError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from main.forms import EgitimOgretimYiliForm, OkulDonemForm
from okul.auth import mudur_yardimcisi_required
from okul.forms import BransForm, DersHavuzuFullForm, DersSaatleriForm, PersonelForm, SinifSubeForm
from okul.models import Brans, DersHavuzu, DersSaatleri, EgitimOgretimYili, OkulDonem, Personel, SinifSube

REGISTRY = {
    "egitim-yili": {
        "model": EgitimOgretimYili,
        "form": EgitimOgretimYiliForm,
        "title": "Eğitim-Öğretim Yılları",
        "singular": "Eğitim-Öğretim Yılı",
        "list_fields": [
            ("egitim_yili", "Yıl"),
            ("egitim_baslangic", "Başlangıç"),
            ("egitim_bitis", "Bitiş"),
        ],
    },
    "donem": {
        "model": OkulDonem,
        "form": OkulDonemForm,
        "title": "Okul Dönemleri",
        "singular": "Dönem",
        "list_fields": [
            ("egitim_yili", "Eğitim Yılı"),
            ("get_donem_display", "Dönem"),
            ("baslangic", "Başlangıç"),
            ("bitis", "Bitiş"),
        ],
    },
    "sinif-sube": {
        "model": SinifSube,
        "form": SinifSubeForm,
        "title": "Sınıf / Şubeler",
        "singular": "Sınıf Şube",
        "list_fields": [
            ("sinif", "Sınıf"),
            ("sube", "Şube"),
            ("acik", "Açık mı?"),
        ],
        "group_by": "sinif",
        "group_order": ["sube"],
        "group_label": "Sınıf",
    },
    "ders-havuzu": {
        "model": DersHavuzu,
        "form": DersHavuzuFullForm,
        "title": "Ders Havuzu",
        "singular": "Ders",
        "list_fields": [
            ("ders_adi", "Ders Adı"),
            ("get_cift_oturum_display", "Sınav Türü"),
            ("sinav_yapilmayacak", "Sınav Yapılmayacak"),
        ],
    },
    "ders-saatleri": {
        "model": DersSaatleri,
        "form": DersSaatleriForm,
        "title": "Ders Saatleri",
        "singular": "Ders Saati",
        "list_fields": [
            ("derssaati_no", "No"),
            ("derssaati_baslangic", "Başlangıç"),
            ("derssaati_bitis", "Bitiş"),
        ],
    },
    "personel": {
        "model": Personel,
        "form": PersonelForm,
        "title": "Personel",
        "singular": "Personel",
        "list_fields": [
            ("kimlikno", "TC No"),
            ("adi_soyadi", "Adı Soyadı"),
            ("brans", "Branş"),
            ("nobeti_var", "Nöbeti Var"),
        ],
        "group_by": "brans__ad",
        "group_order": ["adi_soyadi"],
        "group_label": "",
        "group_collapse": True,
    },
    "brans": {
        "model": Brans,
        "form": BransForm,
        "title": "Branşlar",
        "singular": "Branş",
        "list_fields": [
            ("ad", "Branş Adı"),
        ],
    },
}


def _entry(slug):
    entry = REGISTRY.get(slug)
    if entry is None:
        raise Http404(f"Tanımsız yönetim kaydı: {slug}")
    return entry


@mudur_yardimcisi_required
def yonetim_index(request):
    kartlar = [
        {"slug": slug, "title": entry["title"], "count": entry["model"].objects.count()}
        for slug, entry in REGISTRY.items()
    ]
    return render(request, "okul/yonetim/index.html", {"kartlar": kartlar})


@mudur_yardimcisi_required
def yonetim_list(request, slug):
    entry = _entry(slug)
    group_by = entry.get("group_by")
    model = entry["model"]

    # Branş gibi değerler "/" içerebildiğinden (ör. "Kimya / Kimya Teknolojisi"),
    # grup değeri URL path'inde değil query string'te taşınır (?grup=...) —
    # path converter'ları "/" içeren değerlerle güvenli çalışmaz.
    grup_deger = request.GET.get("grup") if group_by and entry.get("group_collapse") else None

    if group_by and entry.get("group_collapse") and grup_deger is None:
        gruplar = list(
            model.objects.values(group_by)
            .annotate(sayi=Count("id"))
            .order_by(group_by)
        )
        for g in gruplar:
            g["deger"] = g[group_by]
        return render(request, "okul/yonetim/liste.html", {
            "entry": entry, "slug": slug, "gruplar": gruplar,
        })

    objects = model.objects.all()
    if grup_deger is not None:
        objects = objects.filter(**{group_by: grup_deger}).order_by(*entry.get("group_order", []))
        return render(request, "okul/yonetim/liste.html", {
            "entry": entry, "slug": slug, "objects": objects, "grup_deger": grup_deger,
        })

    grouped = None
    if group_by:
        objects = objects.order_by(group_by, *entry.get("group_order", []))
        grouped = []
        current_key = object()
        for obj in objects:
            key = getattr(obj, group_by)
            if key != current_key:
                current_key = key
                grouped.append((key, []))
            grouped[-1][1].append(obj)

    return render(request, "okul/yonetim/liste.html", {
        "entry": entry, "slug": slug, "objects": objects, "grouped": grouped,
    })


@mudur_yardimcisi_required
def yonetim_create(request, slug):
    entry = _entry(slug)
    if request.method == "POST":
        form = entry["form"](request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"{entry['singular']} eklendi.")
            return redirect("okul:yonetim_list", slug=slug)
    else:
        form = entry["form"]()
    return render(request, "okul/yonetim/form.html", {
        "entry": entry, "slug": slug, "form": form, "is_create": True,
    })


@mudur_yardimcisi_required
def yonetim_update(request, slug, pk):
    entry = _entry(slug)
    instance = get_object_or_404(entry["model"], pk=pk)
    if request.method == "POST":
        form = entry["form"](request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, f"{entry['singular']} güncellendi.")
            return redirect("okul:yonetim_list", slug=slug)
    else:
        form = entry["form"](instance=instance)
    return render(request, "okul/yonetim/form.html", {
        "entry": entry, "slug": slug, "form": form, "is_create": False, "instance": instance,
    })


@mudur_yardimcisi_required
def yonetim_delete(request, slug, pk):
    entry = _entry(slug)
    instance = get_object_or_404(entry["model"], pk=pk)

    # NestedObjects (Django admin'in sil onay sayfasında kullandığı aynı
    # yardımcı): PROTECT/RESTRICT ile engellenmiş ilişkileri collect() içinde
    # yakalayıp collector.protected'a toplar, exception fırlatmaz.
    collector = NestedObjects(using=router.db_for_write(entry["model"]))
    collector.collect([instance])

    etkilenen = Counter()
    for model, objs in collector.model_objs.items():
        if model is entry["model"]:
            continue
        etkilenen[model._meta.verbose_name] += len(objs)

    engellenen = Counter()
    for obj in collector.protected:
        engellenen[obj._meta.verbose_name] += 1

    if request.method == "POST":
        if engellenen:
            messages.error(
                request,
                f"{entry['singular']} silinemedi: başka kayıtlarla korumalı (PROTECT) ilişkisi var.",
            )
            return redirect("okul:yonetim_delete", slug=slug, pk=pk)
        try:
            instance.delete()
        except (ProtectedError, RestrictedError):
            messages.error(
                request,
                f"{entry['singular']} silinemedi: başka kayıtlarla korumalı (PROTECT) ilişkisi var.",
            )
            return redirect("okul:yonetim_delete", slug=slug, pk=pk)
        messages.success(request, f"{entry['singular']} silindi.")
        return redirect("okul:yonetim_list", slug=slug)

    return render(request, "okul/yonetim/sil.html", {
        "entry": entry,
        "slug": slug,
        "instance": instance,
        "etkilenen": dict(etkilenen),
        "engellenen": dict(engellenen),
    })
