from io import BytesIO

from django.contrib import messages
from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from okul.auth import mudur_yardimcisi_required
from okul.models import OkulBilgi, SinifSube
from ogrenci.models import Ogrenci
from dersprogrami.models import DersProgrami
from secmelidersler.models import (
    Alan, AlanDers, OgrenciSinifTekrari, OgrenciTasdikname, OrtakDers, SecmeliDersGrubu,
    get_toplam_saat, get_toplam_saat_map, get_aktif_egitim_yili, _VARSAYILAN_TOPLAM_SAAT,
)
from secmelidersler.services.pdf_rapor import secmeli_ders_pdf

from .forms import OgrenciSecmeliDersForm
from .models import OgrenciMevcutDers, OgrenciSecmeliDers, OgrenciZorunluDers

_GELECEK = lambda sinif: sinif + 1


def _yf(qs, aktif_yil):
    return qs.filter(egitim_yili=aktif_yil) if aktif_yil else qs


def _sinif_tekrari_ids(ogr_ids, aktif_yil=None):
    """OgrenciSinifTekrari modeline kayıtlı öğrenci pk seti."""
    return set(
        OgrenciSinifTekrari.objects.filter(
            ogrenci_id__in=ogr_ids,
        ).values_list("ogrenci_id", flat=True)
    )


def _tasdikname_ids(ogr_ids):
    """Tasdikname kaydı olan öğrenci pk seti."""
    return set(
        OgrenciTasdikname.objects.filter(
            ogrenci_id__in=ogr_ids,
        ).values_list("ogrenci_id", flat=True)
    )


def _dp_ders_saatleri(sinif_sube_obj):
    """
    Aktif ders programından verilen sınıf/şubeye ait ders → haftalık saat sözlüğünü döndürür.

    Aynı ders saatini birden fazla öğretmenin paylaşması durumunda (örn. GÖRSEL SANATLAR/MÜZİK
    için iki öğretmen aynı slotta görünür) COUNT(id) yanlış sonuç verir.  Bunun yerine
    (ders_id, gun, ders_saati_id) üçlüsünü distinct alıp Python'da gruplama yapıyoruz;
    böylece her zaman dilimi tek sayılır.

    Döndürür: [{ders_id, ders__ders_adi, haftalik_saat}, ...]
    """
    slots = (
        DersProgrami.objects.aktif()
        .filter(sinif_sube=sinif_sube_obj)
        .values("ders_id", "ders__ders_adi", "gun", "ders_saati_id")
        .distinct()
    )
    ders_map = {}
    for slot in slots:
        did = slot["ders_id"]
        if did not in ders_map:
            ders_map[did] = {
                "ders_id": did,
                "ders__ders_adi": slot["ders__ders_adi"],
                "haftalik_saat": 0,
            }
        ders_map[did]["haftalik_saat"] += 1
    return list(ders_map.values())


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

    secmeli_map = {
        (row["ogrenci_id"], row["ders__grup__sinif_seviyesi"]): row["toplam"]
        for row in OgrenciSecmeliDers.objects.values(
            "ogrenci_id", "ders__grup__sinif_seviyesi"
        ).annotate(toplam=Sum("secilen_saat"))
    }
    zorunlu_map = {
        row["ogrenci_id"]: row["sayi"]
        for row in OgrenciZorunluDers.objects.values("ogrenci_id").annotate(sayi=Count("pk"))
    }
    mevcut_map = {
        row["ogrenci_id"]: row["sayi"]
        for row in OgrenciMevcutDers.objects.values("ogrenci_id").annotate(sayi=Count("pk"))
    }

    # Gelecek sınıf seviyesi → maks seçmeli saat (toplam - zorunlu)
    _aktif_yil = get_aktif_egitim_yili()
    _toplam_map = get_toplam_saat_map(_aktif_yil)
    secmeli_maks_map = {
        row["sinif_seviyesi"]: _toplam_map.get(row["sinif_seviyesi"], _VARSAYILAN_TOPLAM_SAAT) - (row["zorunlu"] or 0)
        for row in _yf(OrtakDers.objects, _aktif_yil).values("sinif_seviyesi").annotate(
            zorunlu=Sum("haftalik_saat")
        )
    }

    tum_siniflar = list(Ogrenci.objects.values_list("sinif", flat=True).distinct().order_by("sinif"))
    tum_subeler = list(Ogrenci.objects.values_list("sube", flat=True).distinct().order_by("sube"))

    tum_ogr_ids = list(qs.values_list("pk", flat=True))
    _tekrari_ids   = _sinif_tekrari_ids(tum_ogr_ids, _aktif_yil)
    _tasdikname_ids_set = _tasdikname_ids(tum_ogr_ids)

    ogr_listesi = []
    for o in qs:
        tekrari    = o.pk in _tekrari_ids
        tasdikname = o.pk in _tasdikname_ids_set
        gelecek = o.sinif if tekrari else _GELECEK(o.sinif)
        secmeli_maks = secmeli_maks_map.get(gelecek, 0)
        ogr_listesi.append({
            "ogrenci": o,
            "gelecek_sinif": gelecek,
            "son_sinif": gelecek > 12,
            "tasdikname": tasdikname,
            "sinif_tekrari": tekrari,
            "mevcut_ders_sayi": mevcut_map.get(o.pk, 0),
            "secmeli_saat": secmeli_map.get((o.pk, gelecek), 0),
            "secmeli_maks": secmeli_maks,
            "zorunlu_sayi": zorunlu_map.get(o.pk, 0),
        })

    # Seviye → Şube → Öğrenciler gruplu yapı (yeni template için)
    from collections import defaultdict
    seviye_sube_map = defaultdict(lambda: defaultdict(list))
    for ogr in ogr_listesi:
        seviye_sube_map[ogr["ogrenci"].sinif][ogr["ogrenci"].sube].append(ogr)

    seviyeler = []
    for sinif_no in sorted(seviye_sube_map):
        subeler = []
        for sube_harf in sorted(seviye_sube_map[sinif_no]):
            ogrenciler = seviye_sube_map[sinif_no][sube_harf]
            tamamladi = sum(
                1 for o in ogrenciler
                if not o["son_sinif"] and o["secmeli_maks"] > 0
                and o["secmeli_saat"] >= o["secmeli_maks"]
            )
            subeler.append({
                "sube": sube_harf,
                "sinif_sube": f"{sinif_no}/{sube_harf}",
                "ogrenciler": ogrenciler,
                "toplam": len(ogrenciler),
                "tamamladi": tamamladi,
            })
        seviyeler.append({
            "sinif_no": sinif_no,
            "subeler": subeler,
            "toplam_ogr": sum(len(s["ogrenciler"]) for s in subeler),
        })

    return render(request, "ogrencidersleri/ogrenci_listesi.html", {
        "title": "Öğrenci Ders Planlaması",
        "ogr_listesi": ogr_listesi,
        "seviyeler": seviyeler,
        "tum_siniflar": tum_siniflar,
        "tum_subeler": tum_subeler,
        "secilen_sinif": sinif_filtre,
        "secilen_sube": sube_filtre,
    })


@mudur_yardimcisi_required
def ogrenci_detay(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    tasdikname_var = OgrenciTasdikname.objects.filter(ogrenci=ogrenci).exists()
    sinif_tekrari   = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci).exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return render(request, "ogrencidersleri/son_sinif.html", {
            "title": "Öğrenci Ders Planlaması",
            "ogrenci": ogrenci,
        })

    # --- Mevcut Yıl ---
    mevcut_dersler = (
        OgrenciMevcutDers.objects
        .filter(ogrenci=ogrenci)
        .select_related("ders")
        .order_by("ders__ders_adi")
    )
    mevcut_toplam_saat = sum(d.haftalik_saat for d in mevcut_dersler)

    # Ders programında bu sınıf/şube için tanımlı ders sayısı (atama için referans)
    try:
        sinif_sube_obj = SinifSube.objects.get(sinif=ogrenci.sinif, sube=ogrenci.sube)
        dp_ders_sayisi = len(_dp_ders_saatleri(sinif_sube_obj))
    except SinifSube.DoesNotExist:
        sinif_sube_obj = None
        dp_ders_sayisi = 0

    # --- Sonraki Yıl ---
    zorunlu_atamalar = (
        OgrenciZorunluDers.objects
        .filter(ogrenci=ogrenci, ortak_ders__sinif_seviyesi=gelecek_sinif)
        .select_related("ortak_ders")
        .order_by("ortak_ders__sira")
    )
    aktif_yil = get_aktif_egitim_yili()
    ortak_ders_havuz = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).order_by("sira")
    atanmis_ids = {a.ortak_ders_id for a in zorunlu_atamalar}
    zorunlu_toplam_saat = sum(a.ortak_ders.haftalik_saat for a in zorunlu_atamalar)

    secmeli_secimler = (
        OgrenciSecmeliDers.objects
        .filter(ogrenci=ogrenci, ders__grup__sinif_seviyesi=gelecek_sinif)
        .select_related("ders__grup")
        .order_by("ders__grup__sira", "ders__sira")
    )
    secmeli_toplam_saat = sum(s.secilen_saat for s in secmeli_secimler)

    ortak_toplam = ortak_ders_havuz.aggregate(
        t=Coalesce(Sum("haftalik_saat"), Value(0))
    )["t"]
    secmeli_maks_saat = get_toplam_saat(gelecek_sinif, egitim_yili=aktif_yil) - ortak_toplam

    return render(request, "ogrencidersleri/ogrenci_detay.html", {
        "title": f"Ders Planı — {ogrenci.adi} {ogrenci.soyadi}",
        "ogrenci": ogrenci,
        "gelecek_sinif": gelecek_sinif,
        "tasdikname_var": tasdikname_var,
        "sinif_tekrari": sinif_tekrari,
        # Mevcut yıl
        "mevcut_dersler": mevcut_dersler,
        "mevcut_toplam_saat": mevcut_toplam_saat,
        "dp_ders_sayisi": dp_ders_sayisi,
        "sinif_sube_obj": sinif_sube_obj,
        "mevcut_tamamlandi": bool(mevcut_dersler) and len(mevcut_dersler) == dp_ders_sayisi,
        # Sonraki yıl
        "zorunlu_atamalar": zorunlu_atamalar,
        "ortak_ders_havuz": ortak_ders_havuz,
        "atanmis_ids": atanmis_ids,
        "zorunlu_toplam_saat": zorunlu_toplam_saat,
        "secmeli_secimler": secmeli_secimler,
        "secmeli_toplam_saat": secmeli_toplam_saat,
        "secmeli_maks_saat": secmeli_maks_saat,
        "tum_zorunlu_atandi": len(atanmis_ids) == ortak_ders_havuz.count(),
    })


@mudur_yardimcisi_required
def sinif_toplu_ders_ata(request):
    """POST: Bir sınıf/şubedeki tüm öğrencilere aktif ders programından mevcut yıl derslerini toplu atar."""
    if request.method != "POST":
        return redirect("ogrdrs_listesi")

    sinif_str = request.POST.get("sinif", "").strip()
    sube = request.POST.get("sube", "").strip().upper()

    try:
        sinif = int(sinif_str)
    except (ValueError, TypeError):
        messages.error(request, "Geçersiz sınıf değeri.")
        return redirect("ogrdrs_listesi")

    try:
        sinif_sube_obj = SinifSube.objects.get(sinif=sinif, sube=sube)
    except SinifSube.DoesNotExist:
        messages.error(request, f"{sinif}/{sube} sınıf/şubesi ders programında tanımlı değil.")
        return redirect(f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo")

    dp_dersler = _dp_ders_saatleri(sinif_sube_obj)
    if not dp_dersler:
        messages.warning(request, f"{sinif}/{sube} için aktif ders programında kayıt bulunamadı.")
        return redirect(f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo")

    ogrenciler = list(Ogrenci.objects.filter(sinif=sinif, sube=sube))
    if not ogrenciler:
        messages.warning(request, f"{sinif}/{sube} şubesinde öğrenci bulunamadı.")
        return redirect(f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo")

    # Şubedeki tüm öğrencilerin mevcut atamalarını silip ders programından yeniden oluştur
    ogr_ids = [o.pk for o in ogrenciler]
    OgrenciMevcutDers.objects.filter(ogrenci_id__in=ogr_ids).delete()
    yeni_atamalar = [
        OgrenciMevcutDers(ogrenci=ogr, ders_id=row["ders_id"], haftalik_saat=row["haftalik_saat"])
        for ogr in ogrenciler
        for row in dp_dersler
    ]
    OgrenciMevcutDers.objects.bulk_create(yeni_atamalar)

    messages.success(
        request,
        f"{sinif}/{sube} — {len(ogrenciler)} öğrenciye {len(dp_dersler)} ders atandı "
        f"(toplam {len(yeni_atamalar)} kayıt)."
    )
    return redirect(f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo")


@mudur_yardimcisi_required
def ogrenci_mevcutyil_ata(request, ogrenci_pk):
    """POST: Ders programından öğrencinin sınıf/şubesine ait dersleri mevcut yıl olarak atar."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)

    try:
        sinif_sube_obj = SinifSube.objects.get(sinif=ogrenci.sinif, sube=ogrenci.sube)
    except SinifSube.DoesNotExist:
        messages.error(request, f"{ogrenci.sinif}/{ogrenci.sube} sınıf/şubesi ders programında bulunamadı.")
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    dp_dersler = _dp_ders_saatleri(sinif_sube_obj)

    if not dp_dersler:
        messages.warning(request, "Bu sınıf/şube için aktif ders programında kayıt bulunamadı.")
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    # Mevcut atamaları sil, ders programından yeniden oluştur
    OgrenciMevcutDers.objects.filter(ogrenci=ogrenci).delete()
    for row in dp_dersler:
        OgrenciMevcutDers.objects.create(
            ogrenci=ogrenci,
            ders_id=row["ders_id"],
            haftalik_saat=row["haftalik_saat"],
        )

    messages.success(request, f"{len(dp_dersler)} ders atandı ({ogrenci.sinif}/{ogrenci.sube} ders programından).")
    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


@mudur_yardimcisi_required
def ogrenci_mevcutyil_sil(request, ogrenci_pk, ders_pk):
    """POST: Öğrencinin mevcut yıl ders atamasını kaldırır."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    atama = get_object_or_404(OgrenciMevcutDers, ogrenci_id=ogrenci_pk, ders_id=ders_pk)
    ders_adi = atama.ders.ders_adi
    atama.delete()
    messages.success(request, f"'{ders_adi}' mevcut yıl listesinden kaldırıldı.")
    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


@mudur_yardimcisi_required
def sinif_toplu_zorunlu_ata(request):
    """POST: Bir sınıf/şubedeki tüm öğrencilere gelecek yıl zorunlu derslerini toplu atar."""
    if request.method != "POST":
        return redirect("ogrdrs_listesi")

    sinif_str = request.POST.get("sinif", "").strip()
    sube = request.POST.get("sube", "").strip().upper()

    try:
        sinif = int(sinif_str)
    except (ValueError, TypeError):
        messages.error(request, "Geçersiz sınıf değeri.")
        return redirect("ogrdrs_listesi")

    gelecek_sinif = _GELECEK(sinif)
    yonlendir = f"{reverse('ogrdrs_listesi')}?sinif={sinif}&sube={sube}#ogr-tablo"

    if gelecek_sinif > 12:
        messages.warning(request, f"{sinif}/{sube} öğrencileri son sınıf — gelecek yıl zorunlu ders ataması yapılamaz.")
        return redirect(yonlendir)

    aktif_yil = get_aktif_egitim_yili()
    zorunlu_dersler = list(_yf(OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil))

    if not zorunlu_dersler:
        messages.warning(request, f"{gelecek_sinif}. sınıf için aktif yılda zorunlu ders tanımlanmamış.")
        return redirect(yonlendir)

    ogrenciler = list(Ogrenci.objects.filter(sinif=sinif, sube=sube))
    if not ogrenciler:
        messages.warning(request, f"{sinif}/{sube} şubesinde öğrenci bulunamadı.")
        return redirect(yonlendir)

    yeni_atamalar = [
        OgrenciZorunluDers(ogrenci=ogr, ortak_ders=ders)
        for ogr in ogrenciler
        for ders in zorunlu_dersler
    ]
    OgrenciZorunluDers.objects.bulk_create(yeni_atamalar, ignore_conflicts=True)

    messages.success(
        request,
        f"{sinif}/{sube} — {len(ogrenciler)} öğrenciye {gelecek_sinif}. sınıf "
        f"{len(zorunlu_dersler)} zorunlu ders atandı."
    )
    return redirect(yonlendir)


@mudur_yardimcisi_required
def ogrenci_zorunlu_ata(request, ogrenci_pk):
    """POST: Öğrencinin gelecek sınıf seviyesindeki tüm zorunlu dersleri atar."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    gelecek_sinif = _GELECEK(ogrenci.sinif)

    ortak_dersler = OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif)
    eklenen = 0
    for ders in ortak_dersler:
        _, created = OgrenciZorunluDers.objects.get_or_create(
            ogrenci=ogrenci, ortak_ders=ders
        )
        if created:
            eklenen += 1

    if eklenen:
        messages.success(request, f"{eklenen} zorunlu ders atandı.")
    else:
        messages.info(request, "Tüm zorunlu dersler zaten atanmış.")

    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


@mudur_yardimcisi_required
def ogrenci_zorunlu_sil(request, ogrenci_pk, ders_pk):
    """POST: Öğrencinin bir zorunlu ders atamasını kaldırır."""
    if request.method != "POST":
        return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)

    atama = get_object_or_404(OgrenciZorunluDers, ogrenci_id=ogrenci_pk, ortak_ders_id=ders_pk)
    ders_adi = atama.ortak_ders.ders_adi
    atama.delete()
    messages.success(request, f"'{ders_adi}' ataması kaldırıldı.")
    return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)


@mudur_yardimcisi_required
def ogrenci_secmeli_form(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    aktif_yil = get_aktif_egitim_yili()

    # Tasdikname kontrolü — seçmeli ders seçiminden dışarıda
    if OgrenciTasdikname.objects.filter(ogrenci=ogrenci).exists():
        return render(request, "ogrencidersleri/tasdikname_engel.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
        })

    # Sınıf tekrarı kontrolü — aynı seviyede seçim yapar
    sinif_tekrari = OgrenciSinifTekrari.objects.filter(ogrenci=ogrenci).exists()
    gelecek_sinif = ogrenci.sinif if sinif_tekrari else _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return render(request, "ogrencidersleri/son_sinif.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
        })

    ortak_dersler = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).order_by("sira")
    ortak_toplam_saat = ortak_dersler.aggregate(
        toplam=Coalesce(Sum("haftalik_saat"), Value(0))
    )["toplam"]
    gruplar_var = _yf(
        SecmeliDersGrubu.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).exists()

    if not gruplar_var:
        return render(request, "ogrencidersleri/yapilandirilmamis.html", {
            "title": "Seçmeli Ders Seçimi",
            "ogrenci": ogrenci,
            "sinif_seviyesi": gelecek_sinif,
        })

    if request.method == "POST":
        form = OgrenciSecmeliDersForm(gelecek_sinif, ogrenci=ogrenci, egitim_yili=aktif_yil, data=request.POST)
        if form.is_valid():
            form.kaydet()
            messages.success(
                request,
                f"{ogrenci.adi} {ogrenci.soyadi} için {gelecek_sinif}. sınıf seçmeli ders seçimi kaydedildi.",
            )
            return redirect("ogrdrs_detay", ogrenci_pk=ogrenci_pk)
    else:
        form = OgrenciSecmeliDersForm(gelecek_sinif, ogrenci=ogrenci, egitim_yili=aktif_yil)

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

    alanlar = Alan.objects.filter(sinif_seviyesi=gelecek_sinif).order_by("sira")
    alan_verileri = []
    for alan in alanlar:
        ders_saat = {
            ad.ders_id: ad.secilen_saat
            for ad in AlanDers.objects.filter(alan=alan)
        }
        alan_verileri.append({"id": alan.pk, "adi": alan.adi, "ders_saat": ders_saat})

    return render(request, "ogrencidersleri/ogrenci_secmeli_form.html", {
        "title": f"{gelecek_sinif}. Sınıf Seçmeli Ders — {ogrenci.adi} {ogrenci.soyadi}",
        "ogrenci": ogrenci,
        "mevcut_sinif": ogrenci.sinif,
        "gelecek_sinif": gelecek_sinif,
        "form": form,
        "grup_listesi": grup_listesi,
        "ortak_dersler": ortak_dersler,
        "ortak_toplam_saat": ortak_toplam_saat,
        "maks_saat": form.MAKS_SAAT,
        "toplam_saat": get_toplam_saat(gelecek_sinif),
        "alan_verileri": alan_verileri,
    })


@mudur_yardimcisi_required
def ogrenci_secmeli_pdf(request, ogrenci_pk):
    ogrenci = get_object_or_404(Ogrenci, pk=ogrenci_pk)
    gelecek_sinif = _GELECEK(ogrenci.sinif)

    if gelecek_sinif > 12:
        return redirect("ogrdrs_secmeli_form", ogrenci_pk=ogrenci_pk)

    aktif_yil = get_aktif_egitim_yili()
    ortak_dersler = _yf(
        OrtakDers.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).order_by("sira")
    secmeli_gruplar = _yf(
        SecmeliDersGrubu.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil
    ).prefetch_related("dersler").order_by("sira")
    secimler = OgrenciSecmeliDers.objects.filter(
        ogrenci=ogrenci, ders__grup__sinif_seviyesi=gelecek_sinif
    )
    secilen_ders_ids = {s.ders_id for s in secimler}
    secilen_saatler = {s.ders_id: s.secilen_saat for s in secimler}

    okul_bilgi = OkulBilgi.objects.first()
    egitim_yili = aktif_yil

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
        toplam_saat=get_toplam_saat(gelecek_sinif),
    )
    buf.seek(0)
    dosya_adi = f"secmeli_{ogrenci.okulno}_{gelecek_sinif}sinif.pdf"
    response = HttpResponse(buf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dosya_adi}"'
    return response
