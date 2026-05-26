from io import BytesIO

from django.contrib import messages
from django.db.models import Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from okul.auth import mudur_yardimcisi_required
from okul.models import OkulBilgi
from ogrenci.models import Ogrenci

from .forms import AlanForm, OgrenciSecimForm
from .models import Alan, AlanDers, OgrenciSecim, OrtakDers, SecmeliDers, SecmeliDersGrubu
from .services.pdf_rapor import secmeli_ders_pdf

# Öğrencinin mevcut sınıf seviyesine 1 eklenerek gelecek yılın sınıf seviyesi hesaplanır.
_GELECEK = lambda sinif: sinif + 1


@mudur_yardimcisi_required
def ogrenci_listesi(request):
    sinif_filtre = request.GET.get("sinif", "").strip()
    sube_filtre = request.GET.get("sube", "").strip()

    qs = Ogrenci.objects.order_by("sinif", "sube", "okulno")
    if sinif_filtre:
        try:
            qs = qs.filter(sinif=int(sinif_filtre))
        except ValueError:
            pass
    if sube_filtre:
        qs = qs.filter(sube__iexact=sube_filtre)

    # (ogrenci_id, gelecek_sinif_seviyesi) → toplam seçilen saat
    secim_map = {
        (row["ogrenci_id"], row["ders__grup__sinif_seviyesi"]): row["toplam"]
        for row in OgrenciSecim.objects.values(
            "ogrenci_id", "ders__grup__sinif_seviyesi"
        ).annotate(toplam=Sum("secilen_saat"))
    }

    tum_siniflar = list(Ogrenci.objects.values_list("sinif", flat=True).distinct().order_by("sinif"))
    tum_subeler = list(Ogrenci.objects.values_list("sube", flat=True).distinct().order_by("sube"))

    ogr_listesi = []
    for o in qs:
        gelecek = _GELECEK(o.sinif)
        ogr_listesi.append({
            "ogrenci": o,
            "gelecek_sinif": gelecek,
            "son_sinif": gelecek > 12,
            "toplam_saat": secim_map.get((o.pk, gelecek), 0),
        })

    context = {
        "title": "Seçmeli Ders Planlaması (Gelecek Yıl)",
        "ogr_listesi": ogr_listesi,
        "tum_siniflar": tum_siniflar,
        "tum_subeler": tum_subeler,
        "secilen_sinif": sinif_filtre,
        "secilen_sube": sube_filtre,
    }
    return render(request, "secmelidersler/ogrenci_listesi.html", context)


@mudur_yardimcisi_required
def ogrenci_secim_formu(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    gelecek_sinif = _GELECEK(ogrenci.sinif)

    # 12. sınıf öğrencisi için gelecek yıl planlaması yapılamaz
    if gelecek_sinif > 12:
        return render(request, "secmelidersler/son_sinif.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
        })

    ortak_dersler = OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif).order_by("sira")
    ortak_toplam_saat = ortak_dersler.aggregate(
        toplam=Coalesce(Sum("haftalik_saat"), Value(0))
    )["toplam"]
    gruplar_var = SecmeliDersGrubu.objects.filter(sinif_seviyesi=gelecek_sinif).exists()

    if not gruplar_var:
        return render(request, "secmelidersler/yapilandirilmamis.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
            "sinif_seviyesi": gelecek_sinif,
        })

    if request.method == "POST":
        form = OgrenciSecimForm(gelecek_sinif, ogrenci=ogrenci, data=request.POST)
        if form.is_valid():
            form.kaydet()
            messages.success(
                request,
                f"{ogrenci.adi} {ogrenci.soyadi} için {gelecek_sinif}. sınıf seçmeli ders seçimi kaydedildi.",
            )
            return redirect("secmeli_ogrenci_listesi")
    else:
        form = OgrenciSecimForm(gelecek_sinif, ogrenci=ogrenci)

    grup_listesi = [
        {
            "grup": grup,
            "fields": [
                {
                    "field": form[fname],
                    "saat_field": form[fname_saat] if fname_saat else None,
                    "ders": ders,
                }
                for fname, fname_saat, ders in field_items
            ],
        }
        for grup, field_items in form.grup_field_map.values()
    ]

    # Alan butonları için: her alan → {ders_id: saat} map'i
    alanlar = Alan.objects.filter(sinif_seviyesi=gelecek_sinif).order_by("sira")
    alan_verileri = []
    for alan in alanlar:
        ders_saat = {
            ad.ders_id: ad.secilen_saat
            for ad in AlanDers.objects.filter(alan=alan)
        }
        alan_verileri.append({"id": alan.pk, "adi": alan.adi, "ders_saat": ders_saat})

    context = {
        "title": f"{gelecek_sinif}. Sınıf Seçmeli Ders — {ogrenci.adi} {ogrenci.soyadi}",
        "ogrenci": ogrenci,
        "mevcut_sinif": ogrenci.sinif,
        "gelecek_sinif": gelecek_sinif,
        "form": form,
        "grup_listesi": grup_listesi,
        "ortak_dersler": ortak_dersler,
        "ortak_toplam_saat": ortak_toplam_saat,
        "maks_saat": form.MAKS_SAAT,
        "alan_verileri": alan_verileri,
    }
    return render(request, "secmelidersler/ogrenci_secim_formu.html", context)


@mudur_yardimcisi_required
def ogrenci_secim_pdf(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    gelecek_sinif = _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return redirect("secmeli_ogrenci_formu", ogrenci_pk=ogrenci_pk)

    ortak_dersler = OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif).order_by("sira")
    secmeli_gruplar = (
        SecmeliDersGrubu.objects.filter(sinif_seviyesi=gelecek_sinif)
        .prefetch_related("dersler")
        .order_by("sira")
    )
    secimler = OgrenciSecim.objects.filter(
        ogrenci=ogrenci, ders__grup__sinif_seviyesi=gelecek_sinif
    )
    secilen_ders_ids = {s.ders_id for s in secimler}
    secilen_saatler  = {s.ders_id: s.secilen_saat for s in secimler}

    okul_bilgi = OkulBilgi.objects.first()
    egitim_yili = okul_bilgi.okul_egtyil if okul_bilgi else None

    buf = BytesIO()
    secmeli_ders_pdf(
        buffer=buf,
        ogrenci=ogrenci,
        gelecek_sinif=gelecek_sinif,
        ortak_dersler=ortak_dersler,
        secmeli_gruplar=secmeli_gruplar,
        secilen_ders_ids=secilen_ders_ids,
        secilen_saatler=secilen_saatler,
        okul_bilgi=okul_bilgi,
        egitim_yili=egitim_yili,
    )
    buf.seek(0)
    dosya_adi = f"secmeli_{ogrenci.okulno}_{gelecek_sinif}sinif.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dosya_adi}"'
    return response


@mudur_yardimcisi_required
def alan_listesi(request):
    alanlar_11 = Alan.objects.filter(sinif_seviyesi=11).prefetch_related("dersler").order_by("sira")
    alanlar_12 = Alan.objects.filter(sinif_seviyesi=12).prefetch_related("dersler").order_by("sira")
    return render(request, "secmelidersler/alan_listesi.html", {
        "title": "Alan Tanımları (11–12. Sınıf)",
        "alanlar_11": alanlar_11,
        "alanlar_12": alanlar_12,
    })


@mudur_yardimcisi_required
def alan_form(request, pk=None):
    if pk:
        alan = get_object_or_404(Alan, pk=pk)
        title = f"Alan Düzenle — {alan.sinif_seviyesi}. Sınıf / {alan.adi}"
    else:
        alan = None
        title = "Yeni Alan Tanımla"

    _TOPLAM = 40  # Haftalık toplam ders saati
    sinif_ozet = {}
    for sv in (11, 12):
        ortak = OrtakDers.objects.filter(sinif_seviyesi=sv).aggregate(
            toplam=Coalesce(Sum("haftalik_saat"), Value(0))
        )["toplam"]
        sinif_ozet[sv] = {
            "ortak": ortak,
            "rehberlik": 1,
            "secmeli_maks": _TOPLAM - ortak - 1,
        }

    if request.method == "POST":
        form = AlanForm(request.POST, instance=alan)
        if form.is_valid():
            form.save()
            messages.success(request, "Alan kaydedildi.")
            return redirect("secmeli_alan_listesi")
    else:
        form = AlanForm(instance=alan)

    return render(request, "secmelidersler/alan_form.html", {
        "title": title,
        "form": form,
        "alan": alan,
        "sinif_ozet": sinif_ozet,
    })


@mudur_yardimcisi_required
def alan_sil(request, pk):
    alan = get_object_or_404(Alan, pk=pk)
    if request.method == "POST":
        alan.delete()
        messages.success(request, f"'{alan.adi}' alanı silindi.")
    return redirect("secmeli_alan_listesi")
