from django.contrib import messages
from django.db.models import Count, Max, Sum, Value
from django.urls import reverse
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from okul.auth import mudur_yardimcisi_required

from .forms import AlanForm, OrtakDersHavuzuForm, SecmeliDersForm, SecmeliDersGrubuForm, SecmeliDersHavuzuForm, SinifSeviyeToplamSaatForm
from .models import (
    Alan, AlanDers, OrtakDers, OrtakDersHavuzu,
    SecmeliDers, SecmeliDersGrubu, SecmeliDersHavuzu,
    SinifSeviyeToplamSaat,
    get_aktif_egitim_yili, get_toplam_saat,
)

_SINIFLAR = [9, 10, 11, 12]


def _yf(qs, aktif_yil):
    """Aktif EÖY varsa queryset'i yıla göre filtreler; yoksa tüm kayıtları döndürür."""
    return qs.filter(egitim_yili=aktif_yil) if aktif_yil else qs


@mudur_yardimcisi_required
def index(request):
    aktif_yil = get_aktif_egitim_yili()
    return render(request, "secmelidersler/index.html", {
        "title": "Seçmeli Dersler Yönetimi",
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def alan_listesi(request):
    aktif_yil = get_aktif_egitim_yili()
    alanlar_11 = _yf(Alan.objects.filter(sinif_seviyesi=11), aktif_yil).prefetch_related("dersler").order_by("sira")
    alanlar_12 = _yf(Alan.objects.filter(sinif_seviyesi=12), aktif_yil).prefetch_related("dersler").order_by("sira")
    return render(request, "secmelidersler/alan_listesi.html", {
        "title": "Alan Tanımları (11–12. Sınıf)",
        "alanlar_11": alanlar_11,
        "alanlar_12": alanlar_12,
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def alan_form(request, pk=None):
    aktif_yil = get_aktif_egitim_yili()
    if pk:
        alan = get_object_or_404(Alan, pk=pk)
        title = f"Alan Düzenle — {alan.sinif_seviyesi}. Sınıf / {alan.adi}"
    else:
        alan = None
        title = "Yeni Alan Tanımla"

    sinif_ozet = {}
    for sv in (11, 12):
        toplam = get_toplam_saat(sv, egitim_yili=aktif_yil)
        ortak = _yf(OrtakDers.objects.filter(sinif_seviyesi=sv), aktif_yil).aggregate(
            toplam=Coalesce(Sum("haftalik_saat"), Value(0))
        )["toplam"]
        sinif_ozet[sv] = {
            "toplam": toplam,
            "ortak": ortak,
            "secmeli_maks": toplam - ortak,
        }

    if request.method == "POST":
        form = AlanForm(request.POST, instance=alan, egitim_yili=aktif_yil)
        if form.is_valid():
            if not form.instance.pk:
                form.instance.egitim_yili = aktif_yil
            form.save()
            messages.success(request, "Alan kaydedildi.")
            return redirect("secmeli_alan_listesi")
    else:
        form = AlanForm(instance=alan, egitim_yili=aktif_yil)

    return render(request, "secmelidersler/alan_form.html", {
        "title": title,
        "form": form,
        "alan": alan,
        "sinif_ozet": sinif_ozet,
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def alan_sil(request, pk):
    alan = get_object_or_404(Alan, pk=pk)
    if request.method == "POST":
        alan.delete()
        messages.success(request, f"'{alan.adi}' alanı silindi.")
    return redirect("secmeli_alan_listesi")


@mudur_yardimcisi_required
def secmeli_grup_listesi(request):
    aktif_yil = get_aktif_egitim_yili()
    gruplar = _yf(
        SecmeliDersGrubu.objects.annotate(ders_sayisi=Count("dersler")),
        aktif_yil,
    ).order_by("sinif_seviyesi", "sira")

    sinif_map = {}
    for g in gruplar:
        sinif_map.setdefault(g.sinif_seviyesi, []).append(g)
    sinif_gruplari = [(s, sinif_map.get(s, [])) for s in _SINIFLAR]
    return render(request, "secmelidersler/secmeli_grup_listesi.html", {
        "title": "Seçmeli Ders Grupları",
        "sinif_gruplari": sinif_gruplari,
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def secmeli_grup_form(request, pk=None):
    aktif_yil = get_aktif_egitim_yili()
    if pk:
        grup = get_object_or_404(SecmeliDersGrubu, pk=pk)
        title = f"Grup Düzenle — {grup.sinif_seviyesi}. Sınıf / {grup.adi}"
    else:
        grup = None
        title = "Yeni Seçmeli Ders Grubu"

    if request.method == "POST":
        form = SecmeliDersGrubuForm(request.POST, instance=grup)
        if form.is_valid():
            yeni_grup = form.save(commit=False)
            if not yeni_grup.pk:
                yeni_grup.egitim_yili = aktif_yil
            yeni_grup.save()
            messages.success(request, "Grup kaydedildi.")
            return redirect("secmeli_grup_listesi")
    else:
        initial = {}
        sinif_param = request.GET.get("sinif", "").strip()
        if sinif_param.isdigit() and int(sinif_param) in _SINIFLAR:
            initial["sinif_seviyesi"] = int(sinif_param)
        form = SecmeliDersGrubuForm(instance=grup, initial=initial or None)

    return render(request, "secmelidersler/secmeli_grup_form.html", {
        "title": title,
        "form": form,
        "grup": grup,
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def secmeli_grup_sil(request, pk):
    grup = get_object_or_404(SecmeliDersGrubu, pk=pk)
    if request.method == "POST":
        grup.delete()
        messages.success(request, f"'{grup.adi}' grubu ve tüm dersleri silindi.")
    return redirect("secmeli_grup_listesi")


@mudur_yardimcisi_required
def secmeli_ders_havuzdan_ekle(request, grup_pk):
    if request.method != "POST":
        return redirect("secmeli_grup_ders_listesi", grup_pk=grup_pk)

    grup = get_object_or_404(SecmeliDersGrubu, pk=grup_pk)
    ders_adi = request.POST.get("ders_adi", "").strip()
    saat_secenekleri = request.POST.get("saat_secenekleri", "").strip()

    if not ders_adi or not saat_secenekleri:
        messages.error(request, "Geçersiz istek.")
        return redirect("secmeli_grup_ders_listesi", grup_pk=grup_pk)

    if SecmeliDers.objects.filter(grup=grup, ders_adi=ders_adi).exists():
        messages.warning(request, f"'{ders_adi}' bu grupta zaten mevcut.")
    else:
        maks_sira = SecmeliDers.objects.filter(grup=grup).aggregate(
            m=Coalesce(Max("sira"), Value(0))
        )["m"]
        SecmeliDers.objects.create(
            grup=grup,
            ders_adi=ders_adi,
            saat_secenekleri=saat_secenekleri,
            sira=maks_sira + 1,
            aktif=True,
        )
        messages.success(request, f"'{ders_adi}' gruba eklendi.")

    return redirect("secmeli_grup_ders_listesi", grup_pk=grup_pk)


@mudur_yardimcisi_required
def secmeli_ders_form(request, grup_pk, pk=None):
    grup = get_object_or_404(SecmeliDersGrubu, pk=grup_pk)
    if pk:
        ders = get_object_or_404(SecmeliDers, pk=pk, grup=grup)
        title = f"Ders Düzenle — {ders.ders_adi}"
    else:
        ders = None
        title = f"Yeni Ders — {grup.sinif_seviyesi}. Sınıf / {grup.adi}"

    if request.method == "POST":
        form = SecmeliDersForm(request.POST, instance=ders)
        if form.is_valid():
            yeni_ders = form.save(commit=False)
            yeni_ders.grup = grup
            yeni_ders.save()
            messages.success(request, "Ders kaydedildi.")
            return redirect("secmeli_grup_ders_listesi", grup_pk=grup_pk)
    else:
        initial = {}
        ders_adi_param = request.GET.get("ders_adi", "").strip()
        if ders_adi_param:
            initial["ders_adi"] = ders_adi_param
        form = SecmeliDersForm(instance=ders, initial=initial or None)

    return render(request, "secmelidersler/secmeli_ders_form.html", {
        "title": title,
        "form": form,
        "grup": grup,
        "ders": ders,
    })


@mudur_yardimcisi_required
def secmeli_ders_sil(request, grup_pk, pk):
    grup = get_object_or_404(SecmeliDersGrubu, pk=grup_pk)
    ders = get_object_or_404(SecmeliDers, pk=pk, grup=grup)
    if request.method == "POST":
        ders.delete()
        messages.success(request, f"'{ders.ders_adi}' dersi silindi.")
    return redirect("secmeli_grup_ders_listesi", grup_pk=grup_pk)


@mudur_yardimcisi_required
def secmeli_grup_ders_listesi(request, grup_pk):
    grup = get_object_or_404(SecmeliDersGrubu, pk=grup_pk)

    grup_dersleri = list(grup.dersler.order_by("sira"))
    grup_adlari = {d.ders_adi for d in grup_dersleri}

    havuz_dersler = list(SecmeliDersHavuzu.objects.all())
    havuz_adlari = {h.ders_adi for h in havuz_dersler}
    havuz_map = {h.ders_adi: h for h in havuz_dersler}

    sag_kart = []

    # 1. Grupta olan dersler — atanmış olarak göster (Çıkar)
    for d in grup_dersleri:
        sag_kart.append({
            "ders_adi": d.ders_adi,
            "atanmis": True,
            "aktif": d.aktif,
            "ders_obj": d,
            "havuz_ders": havuz_map.get(d.ders_adi),
            "saat_str": d.saat_secenekleri,
        })

    # 2. Havuzda olup grupta olmayan dersler — Ekle
    for h in havuz_dersler:
        if h.ders_adi not in grup_adlari:
            sag_kart.append({
                "ders_adi": h.ders_adi,
                "atanmis": False,
                "aktif": h.aktif,
                "ders_obj": None,
                "havuz_ders": h,
                "saat_str": h.derssaati,
            })

    return render(request, "secmelidersler/secmeli_grup_ders_listesi.html", {
        "title": f"{grup.sinif_seviyesi}. Sınıf — {grup.adi}",
        "grup": grup,
        "grup_dersleri": grup_dersleri,
        "havuz": sag_kart,
        "veri_var": bool(grup_dersleri),
    })


@mudur_yardimcisi_required
def ortak_ders_listesi(request):
    aktif_yil = get_aktif_egitim_yili()
    sinif_param = request.GET.get("sinif", "").strip()
    secili_sinif = int(sinif_param) if sinif_param.isdigit() and int(sinif_param) in _SINIFLAR else None

    ders_qs = _yf(OrtakDers.objects.order_by("sinif_seviyesi", "sira"), aktif_yil)
    ders_map = {}
    ders_sira = {}
    for ders in ders_qs:
        if ders.ders_adi not in ders_map:
            ders_map[ders.ders_adi] = {}
            ders_sira[ders.ders_adi] = ders.sira
        ders_map[ders.ders_adi][ders.sinif_seviyesi] = ders
        ders_sira[ders.ders_adi] = min(ders_sira[ders.ders_adi], ders.sira)

    ders_adlari = sorted(ders_map, key=lambda d: ders_sira[d])

    if secili_sinif:
        sinif_dersleri = [
            ders_map[adi][secili_sinif]
            for adi in ders_adlari
            if secili_sinif in ders_map[adi]
        ]
        sinif_ders_adlari = {d.ders_adi for d in sinif_dersleri}
        havuz = [
            {
                "havuz_ders": hd,
                "ders_adi": hd.ders_adi,
                "aktif": hd.aktif,
                "atanmis": hd.ders_adi in sinif_ders_adlari,
                "ders_obj": ders_map.get(hd.ders_adi, {}).get(secili_sinif),
            }
            for hd in OrtakDersHavuzu.objects.all()
        ]
        return render(request, "secmelidersler/ortak_ders_listesi.html", {
            "title": f"Zorunlu Dersler — {secili_sinif}. Sınıf",
            "siniflar": _SINIFLAR,
            "secili_sinif": secili_sinif,
            "sinif_dersleri": sinif_dersleri,
            "sinif_toplam": sum(d.haftalik_saat for d in sinif_dersleri),
            "havuz": havuz,
            "veri_var": bool(sinif_dersleri),
            "aktif_yil": aktif_yil,
        })

    satirlar = [(adi, [ders_map[adi].get(s) for s in _SINIFLAR]) for adi in ders_adlari]
    toplamlar = [
        sum(ders_map[adi].get(s).haftalik_saat for adi in ders_map if s in ders_map[adi])
        for s in _SINIFLAR
    ]
    return render(request, "secmelidersler/ortak_ders_listesi.html", {
        "title": "Zorunlu (Ortak) Dersler",
        "siniflar": _SINIFLAR,
        "secili_sinif": None,
        "satirlar": satirlar,
        "toplamlar": toplamlar,
        "veri_var": bool(satirlar),
        "aktif_yil": aktif_yil,
    })


@mudur_yardimcisi_required
def ortak_ders_sil(request, pk):
    ders = get_object_or_404(OrtakDers, pk=pk)
    if request.method == "POST":
        ders.delete()
        messages.success(request, f"'{ders.ders_adi}' dersi silindi.")
        ref_sinif = request.POST.get("ref_sinif", "").strip()
        if ref_sinif.isdigit() and int(ref_sinif) in _SINIFLAR:
            return redirect(f"{reverse('secmeli_ortak_ders_listesi')}?sinif={ref_sinif}")
    return redirect("secmeli_ortak_ders_listesi")


@mudur_yardimcisi_required
def ortak_ders_havuzdan_ekle(request):
    if request.method != "POST":
        return redirect("secmeli_ortak_ders_listesi")

    aktif_yil = get_aktif_egitim_yili()
    sinif_str = request.POST.get("sinif_seviyesi", "").strip()
    ders_adi = request.POST.get("ders_adi", "").strip()
    saat_str = request.POST.get("haftalik_saat", "").strip()

    secili_sinif = int(sinif_str) if sinif_str.isdigit() and int(sinif_str) in _SINIFLAR else None
    if not secili_sinif or not ders_adi:
        messages.error(request, "Geçersiz istek.")
        return redirect("secmeli_ortak_ders_listesi")

    try:
        haftalik_saat = int(saat_str.split(",")[0].strip())
        if haftalik_saat < 1:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, "Geçerli bir haftalık saat girin (en az 1).")
        return redirect(f"{reverse('secmeli_ortak_ders_listesi')}?sinif={secili_sinif}")

    kontrol_qs = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=secili_sinif, ders_adi=ders_adi),
        aktif_yil,
    )
    if kontrol_qs.exists():
        messages.warning(request, f"'{ders_adi}' bu sınıf seviyesi ve yıl için zaten tanımlı.")
    else:
        maks_sira = _yf(OrtakDers.objects.filter(sinif_seviyesi=secili_sinif), aktif_yil).aggregate(
            m=Coalesce(Max("sira"), Value(0))
        )["m"]
        OrtakDers.objects.create(
            egitim_yili=aktif_yil,
            sinif_seviyesi=secili_sinif,
            ders_adi=ders_adi,
            haftalik_saat=haftalik_saat,
            sira=maks_sira + 1,
        )
        messages.success(request, f"'{ders_adi}' {secili_sinif}. sınıfa eklendi.")

    return redirect(f"{reverse('secmeli_ortak_ders_listesi')}?sinif={secili_sinif}")


# ── Seçmeli Ders Havuzu CRUD ────────────────────────────────────────────────

@mudur_yardimcisi_required
def secmeli_havuz_listesi(request):
    dersler = SecmeliDersHavuzu.objects.all()
    return render(request, "secmelidersler/secmeli_havuz_listesi.html", {
        "title": "Seçmeli Ders Havuzu",
        "dersler": dersler,
    })


@mudur_yardimcisi_required
def secmeli_havuz_form(request, pk=None):
    if pk:
        ders = get_object_or_404(SecmeliDersHavuzu, pk=pk)
        title = f"Havuz Dersi Düzenle — {ders.ders_adi}"
    else:
        ders = None
        title = "Havuza Yeni Ders Ekle"

    if request.method == "POST":
        form = SecmeliDersHavuzuForm(request.POST, instance=ders)
        if form.is_valid():
            form.save()
            messages.success(request, "Ders kaydedildi.")
            return redirect("secmeli_havuz_listesi")
    else:
        form = SecmeliDersHavuzuForm(instance=ders)

    return render(request, "secmelidersler/secmeli_havuz_form.html", {
        "title": title,
        "form": form,
        "ders": ders,
    })


@mudur_yardimcisi_required
def secmeli_havuz_sil(request, pk):
    ders = get_object_or_404(SecmeliDersHavuzu, pk=pk)
    if request.method == "POST":
        ders.delete()
        messages.success(request, f"'{ders.ders_adi}' havuzdan silindi.")
    return redirect("secmeli_havuz_listesi")


# ── Ortak Ders Havuzu CRUD ──────────────────────────────────────────────────

@mudur_yardimcisi_required
def ortak_havuz_listesi(request):
    dersler = OrtakDersHavuzu.objects.all()
    return render(request, "secmelidersler/ortak_havuz_listesi.html", {
        "title": "Ortak (Zorunlu) Ders Havuzu",
        "dersler": dersler,
    })


@mudur_yardimcisi_required
def ortak_havuz_form(request, pk=None):
    if pk:
        ders = get_object_or_404(OrtakDersHavuzu, pk=pk)
        title = f"Havuz Dersi Düzenle — {ders.ders_adi}"
    else:
        ders = None
        title = "Havuza Yeni Ders Ekle"

    if request.method == "POST":
        form = OrtakDersHavuzuForm(request.POST, instance=ders)
        if form.is_valid():
            form.save()
            messages.success(request, "Ders kaydedildi.")
            return redirect("ortak_havuz_listesi")
    else:
        form = OrtakDersHavuzuForm(instance=ders)

    return render(request, "secmelidersler/ortak_havuz_form.html", {
        "title": title,
        "form": form,
        "ders": ders,
    })


@mudur_yardimcisi_required
def ortak_havuz_sil(request, pk):
    ders = get_object_or_404(OrtakDersHavuzu, pk=pk)
    if request.method == "POST":
        ders.delete()
        messages.success(request, f"'{ders.ders_adi}' havuzdan silindi.")
    return redirect("ortak_havuz_listesi")


# ── Sınıf Seviyesi Toplam Saat ──────────────────────────────────────────────

@mudur_yardimcisi_required
def sinif_toplam_saat_listesi(request):
    aktif_yil = get_aktif_egitim_yili()

    if request.method == "POST":
        pk = request.POST.get("pk")
        obj = get_object_or_404(SinifSeviyeToplamSaat, pk=pk)
        form = SinifSeviyeToplamSaatForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, f"{obj.sinif_seviyesi}. sınıf toplam saati güncellendi.")
        else:
            for hata in form.errors.values():
                messages.error(request, hata.as_text())
        return redirect("secmeli_sinif_toplam_saat")

    mevcut = {
        obj.sinif_seviyesi: obj
        for obj in _yf(SinifSeviyeToplamSaat.objects.all(), aktif_yil)
    }
    satirlar = []
    for sv in _SINIFLAR:
        if sv not in mevcut:
            obj = SinifSeviyeToplamSaat.objects.create(
                egitim_yili=aktif_yil,
                sinif_seviyesi=sv,
                haftalik_toplam_saat=40,
            )
            mevcut[sv] = obj
        obj = mevcut[sv]
        satirlar.append({
            "obj": obj,
            "form": SinifSeviyeToplamSaatForm(instance=obj),
        })

    return render(request, "secmelidersler/sinif_toplam_saat_listesi.html", {
        "title": "Sınıf Seviyesi Toplam Ders Saati",
        "satırlar": satirlar,
        "aktif_yil": aktif_yil,
    })
