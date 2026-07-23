from django.contrib import messages
from django.db.models import Count, Max, Sum, Value
from django.urls import reverse
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render

from okul.auth import mudur_yardimcisi_required
from okul.models import Personel

from .forms import AlanForm, OrtakDersHavuzuForm, SecmeliDersForm, SecmeliDersGrubuForm, SecmeliDersHavuzuForm, SinifSeviyeToplamSaatForm
from .models import (
    Alan, DersOgretmenAtama, OgrenciOrtalama, OgrenciSinifTekrari, OgrenciTasdikname,
    OrtakDers, OrtakDersHavuzu,
    SecmeliDers, SecmeliDersGrubu, SecmeliDersHavuzu,
    SinifSeviyeToplamSaat,
    get_aktif_egitim_yili, get_toplam_saat,
)
from .services.ders_dagilimi import alan_ders_paketi, plan_sinif_dagilimi, sube_ders_paketi

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
    dersler = SecmeliDersHavuzu.objects.prefetch_related("branslar")
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
    dersler = OrtakDersHavuzu.objects.prefetch_related("branslar")
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


@mudur_yardimcisi_required
def sinif_dagilimi(request):
    aktif_yil = get_aktif_egitim_yili()

    plan_11 = plan_sinif_dagilimi(10, 11, aktif_yil)
    plan_12 = plan_sinif_dagilimi(11, 12, aktif_yil)

    return render(request, "secmelidersler/sinif_dagilimi.html", {
        "title": "Sınıf Dağılımı",
        "aktif_yil": aktif_yil,
        "plan_11": plan_11,
        "plan_12": plan_12,
    })


# ---------------------------------------------------------------------------
# Ders — Öğretmen Ataması (gelecek yıl şube/alan ders dağılımı)
# ---------------------------------------------------------------------------

def _atama_field_adi(satir):
    return f"ogretmen_{satir['tur']}_{satir['ders'].pk}"


def _atama_satirlari(paket, mevcut_atamalar):
    """Ders paketini, mevcut atamalarla eşleştirip template'e hazır hale getirir."""
    satirlar = []
    for satir in paket:
        ders = satir["ders"]
        anahtar = (ders.pk, None) if satir["tur"] == "ortak" else (None, ders.pk)
        atama = mevcut_atamalar.get(anahtar)
        brans_id_listesi = list(ders.branslar.values_list("pk", flat=True))
        ogretmen_secenekleri = (
            Personel.objects.filter(brans_id__in=brans_id_listesi).order_by("brans__ad", "adi_soyadi")
            if brans_id_listesi
            else Personel.objects.none()
        )
        satirlar.append({
            **satir,
            "field_adi": _atama_field_adi(satir),
            "secili_ogretmen_id": atama.ogretmen_id if atama else None,
            "ogretmen_secenekleri": list(ogretmen_secenekleri),
            "brans_yok": not brans_id_listesi,
        })
    return satirlar


def _atama_kaydet(paket, ortak_kwargs, request):
    for satir in paket:
        ders = satir["ders"]
        field_adi = _atama_field_adi(satir)
        ogretmen_id_str = request.POST.get(field_adi, "").strip()
        ogretmen_id = int(ogretmen_id_str) if ogretmen_id_str.isdigit() else None
        DersOgretmenAtama.objects.update_or_create(
            **ortak_kwargs,
            ortak_ders=ders if satir["tur"] == "ortak" else None,
            secmeli_ders=ders if satir["tur"] == "secmeli" else None,
            defaults={"haftalik_saat": satir["haftalik_saat"], "ogretmen_id": ogretmen_id},
        )


@mudur_yardimcisi_required
def ders_dagilimi_listesi(request):
    aktif_yil = get_aktif_egitim_yili()

    birimler_11_12 = []
    for mevcut_sinif, gelecek_sinif in ((10, 11), (11, 12)):
        plan = plan_sinif_dagilimi(mevcut_sinif, gelecek_sinif, aktif_yil)
        for grup in plan["alan_gruplari"]:
            if grup["sube_sayisi"] == 0:
                continue
            paket = alan_ders_paketi(grup["alan"], aktif_yil)
            for sube_no in range(1, grup["sube_sayisi"] + 1):
                atanan = DersOgretmenAtama.objects.filter(
                    alan=grup["alan"], sube_no=sube_no, ogretmen__isnull=False
                ).count()
                birimler_11_12.append({
                    "gelecek_sinif": gelecek_sinif,
                    "alan": grup["alan"],
                    "sube_no": sube_no,
                    "ders_sayisi": len(paket),
                    "atanan": atanan,
                })

    from ogrenci.models import Ogrenci

    birimler_9_10 = []
    sube_listesi = (
        Ogrenci.objects.filter(sinif=9, aktif=True)
        .values_list("sube", flat=True).distinct().order_by("sube")
    )
    for sube in sube_listesi:
        if not sube:
            continue
        paket = sube_ders_paketi(9, sube, 10, aktif_yil)
        atanan = DersOgretmenAtama.objects.filter(
            gelecek_sinif=10, alan__isnull=True, sube=sube, ogretmen__isnull=False
        ).count()
        birimler_9_10.append({
            "gelecek_sinif": 10,
            "sube": sube,
            "ders_sayisi": len(paket),
            "atanan": atanan,
        })

    return render(request, "secmelidersler/ders_dagilimi_listesi.html", {
        "title": "Ders Dağılımı — Öğretmen Ataması",
        "aktif_yil": aktif_yil,
        "birimler_11_12": birimler_11_12,
        "birimler_9_10": birimler_9_10,
    })


@mudur_yardimcisi_required
def ders_dagilimi_alan_detay(request, gelecek_sinif, alan_pk, sube_no):
    aktif_yil = get_aktif_egitim_yili()
    alan = get_object_or_404(Alan, pk=alan_pk, sinif_seviyesi=gelecek_sinif)
    paket = alan_ders_paketi(alan, aktif_yil)

    ortak_kwargs = {
        "egitim_yili": aktif_yil,
        "gelecek_sinif": gelecek_sinif,
        "alan": alan,
        "sube_no": sube_no,
    }

    if request.method == "POST":
        _atama_kaydet(paket, ortak_kwargs, request)
        messages.success(request, f"{alan.adi} — Şube {sube_no} ders/öğretmen ataması kaydedildi.")
        return redirect("secmeli_ders_dagilimi_alan_detay", gelecek_sinif=gelecek_sinif, alan_pk=alan_pk, sube_no=sube_no)

    mevcut_atamalar = {
        (a.ortak_ders_id, a.secmeli_ders_id): a
        for a in DersOgretmenAtama.objects.filter(alan=alan, sube_no=sube_no).select_related("ogretmen")
    }
    satirlar = _atama_satirlari(paket, mevcut_atamalar)

    return render(request, "secmelidersler/ders_dagilimi_detay.html", {
        "title": f"{alan.adi} — Şube {sube_no} Ders Dağılımı",
        "aktif_yil": aktif_yil,
        "birim_etiketi": f"{alan.adi} — Şube {sube_no}",
        "satirlar": satirlar,
        "toplam_saat": sum(s["haftalik_saat"] for s in paket),
        "geri_url_adi": "secmeli_ders_dagilimi_listesi",
    })


@mudur_yardimcisi_required
def ders_dagilimi_sube_detay(request, mevcut_sinif, sube):
    aktif_yil = get_aktif_egitim_yili()
    gelecek_sinif = mevcut_sinif + 1
    paket = sube_ders_paketi(mevcut_sinif, sube, gelecek_sinif, aktif_yil)

    ortak_kwargs = {
        "egitim_yili": aktif_yil,
        "gelecek_sinif": gelecek_sinif,
        "alan": None,
        "sube": sube,
    }

    if request.method == "POST":
        _atama_kaydet(paket, ortak_kwargs, request)
        messages.success(request, f"{gelecek_sinif}/{sube} ders/öğretmen ataması kaydedildi.")
        return redirect("secmeli_ders_dagilimi_sube_detay", mevcut_sinif=mevcut_sinif, sube=sube)

    mevcut_atamalar = {
        (a.ortak_ders_id, a.secmeli_ders_id): a
        for a in DersOgretmenAtama.objects.filter(
            alan__isnull=True, gelecek_sinif=gelecek_sinif, sube=sube
        ).select_related("ogretmen")
    }
    satirlar = _atama_satirlari(paket, mevcut_atamalar)

    return render(request, "secmelidersler/ders_dagilimi_detay.html", {
        "title": f"{gelecek_sinif}/{sube} Ders Dağılımı",
        "aktif_yil": aktif_yil,
        "birim_etiketi": f"{mevcut_sinif}/{sube} → {gelecek_sinif}/{sube}",
        "satirlar": satirlar,
        "toplam_saat": sum(s["haftalik_saat"] for s in paket),
        "geri_url_adi": "secmeli_ders_dagilimi_listesi",
    })


@mudur_yardimcisi_required
def ogretmen_yuku_raporu(request):
    aktif_yil = get_aktif_egitim_yili()
    qs = _yf(DersOgretmenAtama.objects, aktif_yil)

    atanmamis_sayisi = qs.filter(ogretmen__isnull=True).count()

    yukler = (
        qs.filter(ogretmen__isnull=False)
        .values("ogretmen_id", "ogretmen__adi_soyadi", "ogretmen__brans__ad")
        .annotate(toplam_saat=Sum("haftalik_saat"), ders_sayisi=Count("pk"))
        .order_by("ogretmen__brans__ad", "ogretmen__adi_soyadi")
    )

    return render(request, "secmelidersler/ogretmen_yuku_raporu.html", {
        "title": "Öğretmen Ders Yükü Raporu",
        "aktif_yil": aktif_yil,
        "yukler": yukler,
        "atanmamis_sayisi": atanmamis_sayisi,
    })


# ---------------------------------------------------------------------------
# Öğrenci Dönem Ağırlıklı Ortalaması — CRUD
# ---------------------------------------------------------------------------

def _excel_satirlari_oku(dosya):
    """
    XLS veya XLSX dosyasından tüm satırları liste olarak döndürür.
    Her satır: [hücre1, hücre2, ...] (ham değer).
    İlk satır başlık satırı olarak döndürülür.
    """
    adi = dosya.name.lower()
    if adi.endswith(".xlsx"):
        from openpyxl import load_workbook
        wb = load_workbook(dosya, read_only=True, data_only=True)
        ws = wb.active
        satirlar = [[c.value for c in row] for row in ws.iter_rows()]
        wb.close()
    elif adi.endswith(".xls"):
        import xlrd, tempfile, os
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xls")
        for chunk in dosya.chunks():
            tmp.write(chunk)
        tmp.close()
        wb = xlrd.open_workbook(tmp.name)
        ws = wb.sheet_by_index(0)
        satirlar = [ws.row_values(r) for r in range(ws.nrows)]
        os.unlink(tmp.name)
    else:
        raise ValueError("Desteklenmeyen dosya formatı. Lütfen .xls veya .xlsx yükleyin.")
    return satirlar


def _sutun_indeksleri_bul(baslik_satiri):
    """Başlık satırından okulno ve a_ortalama sütun indekslerini bulur."""
    normalize = lambda s: str(s).strip().lower().replace(" ", "_").replace("ı", "i").replace("ö", "o").replace("ü", "u")
    basliklar = [normalize(h) for h in baslik_satiri]
    okulno_idx = a_ort_idx = None
    for i, h in enumerate(basliklar):
        if "okulno" in h or h == "okul_no":
            okulno_idx = i
        if "a_ortalama" in h or "agirlikli" in h or "ortalama" in h:
            a_ort_idx = i
    return okulno_idx, a_ort_idx


@mudur_yardimcisi_required
def ortalama_listesi(request):
    from django.core.paginator import Paginator

    aktif_yil = get_aktif_egitim_yili()
    qs = (
        OgrenciOrtalama.objects
        .filter(egitim_yili=aktif_yil)
        .select_related("ogrenci")
        .order_by("ogrenci__okulno")
    )

    arama = request.GET.get("q", "").strip()
    if arama:
        from django.db.models import Q
        qs = qs.filter(
            Q(ogrenci__okulno__icontains=arama)
            | Q(ogrenci__adi__icontains=arama)
            | Q(ogrenci__soyadi__icontains=arama)
        )

    paginator = Paginator(qs, 50)
    sayfa = paginator.get_page(request.GET.get("sayfa"))

    return render(request, "secmelidersler/ortalama_listesi.html", {
        "title": "Dönem Ağırlıklı Ortalamalar",
        "aktif_yil": aktif_yil,
        "sayfa": sayfa,
        "arama": arama,
        "toplam": qs.count(),
    })


@mudur_yardimcisi_required
def ortalama_yukle(request):
    if request.method != "POST":
        return redirect("ortalama_listesi")

    aktif_yil = get_aktif_egitim_yili()
    dosya = request.FILES.get("excel_dosya")
    if not dosya:
        messages.error(request, "Dosya seçilmedi.")
        return redirect("ortalama_listesi")

    from ogrenci.models import Ogrenci

    try:
        satirlar = _excel_satirlari_oku(dosya)
    except Exception as e:
        messages.error(request, f"Dosya okunamadı: {e}")
        return redirect("ortalama_listesi")

    if len(satirlar) < 2:
        messages.warning(request, "Dosya boş veya yalnızca başlık satırı içeriyor.")
        return redirect("ortalama_listesi")

    okulno_idx, a_ort_idx = _sutun_indeksleri_bul(satirlar[0])
    if okulno_idx is None or a_ort_idx is None:
        messages.error(
            request,
            "Başlık satırında 'okulno' ve 'a_ortalama' sütunları bulunamadı. "
            "Lütfen Excel dosyanızın başlık satırını kontrol edin."
        )
        return redirect("ortalama_listesi")

    ogrenci_map = {o.okulno: o for o in Ogrenci.objects.all()}

    olusturulan = guncellenen = bulunamayan = hatali = 0
    bulunamayan_liste = []

    for satir_no, satir in enumerate(satirlar[1:], start=2):
        try:
            ham_okulno = satir[okulno_idx]
            ham_ort    = satir[a_ort_idx]
            if ham_okulno is None or ham_ort is None:
                continue
            okulno   = int(float(str(ham_okulno).strip()))
            a_ort    = round(float(str(ham_ort).strip().replace(",", ".")), 2)
        except (ValueError, TypeError, IndexError):
            hatali += 1
            continue

        ogr = ogrenci_map.get(okulno)
        if ogr is None:
            bulunamayan += 1
            bulunamayan_liste.append(okulno)
            continue

        obj, created = OgrenciOrtalama.objects.update_or_create(
            ogrenci=ogr,
            egitim_yili=aktif_yil,
            defaults={"a_ortalama": a_ort},
        )
        if created:
            olusturulan += 1
        else:
            guncellenen += 1

    ozet = f"{olusturulan} yeni kayıt eklendi, {guncellenen} kayıt güncellendi."
    if bulunamayan:
        ozet += f" {bulunamayan} okul no sistemde bulunamadı."
    if hatali:
        ozet += f" {hatali} satır hatalı format nedeniyle atlandı."

    if olusturulan + guncellenen > 0:
        messages.success(request, ozet)
    else:
        messages.warning(request, ozet)

    if bulunamayan_liste:
        request.session["bulunamayan_okulno"] = bulunamayan_liste[:50]

    return redirect("ortalama_listesi")


@mudur_yardimcisi_required
def ortalama_sil(request, pk):
    obj = OgrenciOrtalama.objects.filter(pk=pk).first()
    if obj:
        obj.delete()
        messages.success(request, f"{obj.ogrenci} kaydı silindi.")
    return redirect("ortalama_listesi")


@mudur_yardimcisi_required
def ortalama_toplu_sil(request):
    if request.method == "POST":
        aktif_yil = get_aktif_egitim_yili()
        sayi, _ = OgrenciOrtalama.objects.filter(egitim_yili=aktif_yil).delete()
        messages.success(request, f"{sayi} kayıt silindi.")
    return redirect("ortalama_listesi")


# ---------------------------------------------------------------------------
# Tasdikname CRUD — Okuma Hakkı Biten Öğrenciler
# ---------------------------------------------------------------------------

@mudur_yardimcisi_required
def tasdikname_listesi(request):
    from ogrenci.models import Ogrenci

    aktif_yil = get_aktif_egitim_yili()
    kayitlar = (
        OgrenciTasdikname.objects
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )

    arama = request.GET.get("q", "").strip()
    arama_sonuclari = []
    if arama:
        from django.db.models import Q
        mevcut_ids = set(kayitlar.values_list("ogrenci_id", flat=True))
        arama_sonuclari = list(
            Ogrenci.objects.filter(
                Q(okulno__icontains=arama)
                | Q(adi__icontains=arama)
                | Q(soyadi__icontains=arama),
                aktif=True,
            ).exclude(pk__in=mevcut_ids).order_by("sinif", "sube", "okulno")[:20]
        )

    return render(request, "secmelidersler/tasdikname_listesi.html", {
        "title": "Tasdikname — Okuma Hakkı Biten Öğrenciler",
        "aktif_yil": aktif_yil,
        "kayitlar": kayitlar,
        "arama": arama,
        "arama_sonuclari": arama_sonuclari,
        "toplam": kayitlar.count(),
    })


@mudur_yardimcisi_required
def tasdikname_ekle(request):
    if request.method != "POST":
        return redirect("tasdikname_listesi")

    from ogrenci.models import Ogrenci
    ogrenci_pk = request.POST.get("ogrenci_pk")
    tarih = request.POST.get("tarih") or None
    aciklama = request.POST.get("aciklama", "").strip()
    aktif_yil = get_aktif_egitim_yili()

    ogr = Ogrenci.objects.filter(pk=ogrenci_pk).first()
    if not ogr:
        messages.error(request, "Öğrenci bulunamadı.")
        return redirect("tasdikname_listesi")

    _, created = OgrenciTasdikname.objects.get_or_create(
        ogrenci=ogr,
        defaults={"egitim_yili": aktif_yil, "tarih": tarih, "aciklama": aciklama},
    )
    if created:
        if ogr.aktif:
            ogr.aktif = False
            ogr.save(update_fields=["aktif"])
        messages.success(
            request,
            f"{ogr.adi} {ogr.soyadi} tasdikname listesine eklendi ve aktif öğrenci "
            "listelerinden çıkarıldı.",
        )
    else:
        messages.warning(request, f"{ogr.adi} {ogr.soyadi} zaten tasdikname listesinde.")

    from django.urls import reverse as _rev
    q = request.POST.get("q", "")
    return redirect(f"{_rev('tasdikname_listesi')}?q={q}")


@mudur_yardimcisi_required
def tasdikname_sil(request, pk):
    if request.method == "POST":
        kayit = OgrenciTasdikname.objects.filter(pk=pk).select_related("ogrenci").first()
        if kayit:
            ogr = kayit.ogrenci
            ad = f"{ogr.adi} {ogr.soyadi}"
            kayit.delete()
            if not ogr.aktif:
                ogr.aktif = True
                ogr.save(update_fields=["aktif"])
            messages.success(
                request, f"{ad} tasdikname listesinden çıkarıldı ve tekrar aktif hale getirildi."
            )
    return redirect("tasdikname_listesi")


# ---------------------------------------------------------------------------
# Sınıf Tekrarı CRUD
# ---------------------------------------------------------------------------

@mudur_yardimcisi_required
def sinif_tekrari_listesi(request):
    from ogrenci.models import Ogrenci

    aktif_yil = get_aktif_egitim_yili()
    kayitlar = (
        OgrenciSinifTekrari.objects
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )

    arama = request.GET.get("q", "").strip()
    arama_sonuclari = []
    if arama:
        from django.db.models import Q
        mevcut_ids = set(kayitlar.values_list("ogrenci_id", flat=True))
        arama_sonuclari = list(
            Ogrenci.objects.filter(
                Q(okulno__icontains=arama)
                | Q(adi__icontains=arama)
                | Q(soyadi__icontains=arama),
                aktif=True,
            ).exclude(pk__in=mevcut_ids).order_by("sinif", "sube", "okulno")[:20]
        )

    return render(request, "secmelidersler/sinif_tekrari_listesi.html", {
        "title": "Sınıf Tekrarı Öğrencileri",
        "aktif_yil": aktif_yil,
        "kayitlar": kayitlar,
        "arama": arama,
        "arama_sonuclari": arama_sonuclari,
        "toplam": kayitlar.count(),
    })


@mudur_yardimcisi_required
def sinif_tekrari_ekle(request):
    if request.method != "POST":
        return redirect("sinif_tekrari_listesi")

    from ogrenci.models import Ogrenci
    ogrenci_pk = request.POST.get("ogrenci_pk")
    aciklama = request.POST.get("aciklama", "").strip()
    aktif_yil = get_aktif_egitim_yili()

    ogr = Ogrenci.objects.filter(pk=ogrenci_pk).first()
    if not ogr:
        messages.error(request, "Öğrenci bulunamadı.")
        return redirect("sinif_tekrari_listesi")

    _, created = OgrenciSinifTekrari.objects.get_or_create(
        ogrenci=ogr,
        defaults={"egitim_yili": aktif_yil, "aciklama": aciklama},
    )
    if created:
        messages.success(request, f"{ogr.adi} {ogr.soyadi} sınıf tekrarı listesine eklendi.")
    else:
        messages.warning(request, f"{ogr.adi} {ogr.soyadi} zaten listede.")

    from django.urls import reverse as _rev
    q = request.POST.get("q", "")
    return redirect(f"{_rev('sinif_tekrari_listesi')}?q={q}")


@mudur_yardimcisi_required
def sinif_tekrari_sil(request, pk):
    if request.method == "POST":
        kayit = OgrenciSinifTekrari.objects.filter(pk=pk).select_related("ogrenci").first()
        if kayit:
            ad = f"{kayit.ogrenci.adi} {kayit.ogrenci.soyadi}"
            kayit.delete()
            messages.success(request, f"{ad} sınıf tekrarı listesinden çıkarıldı.")
    return redirect("sinif_tekrari_listesi")


