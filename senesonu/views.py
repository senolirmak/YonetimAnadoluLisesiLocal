from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from okul.auth import ust_yonetici_required
from okul.models import EgitimOgretimYili, SinifSube
from okul.utils import get_aktif_egitim_yili

from . import services
from .models import SeneSonuGecisi, SeneSonuOgrenciGecisi


@ust_yonetici_required
def gecis_listesi(request):
    aktif_yil = get_aktif_egitim_yili()
    gecisler = SeneSonuGecisi.objects.select_related("eski_egitim_yili", "yeni_egitim_yili")
    hedef_yillar = EgitimOgretimYili.objects.all()
    if aktif_yil:
        hedef_yillar = hedef_yillar.exclude(pk=aktif_yil.pk)

    return render(request, "senesonu/gecis_listesi.html", {
        "title": "Sene Sonu Geçişleri",
        "gecisler": gecisler,
        "aktif_yil": aktif_yil,
        "hedef_yillar": hedef_yillar,
    })


@ust_yonetici_required
@require_POST
def gecis_olustur(request):
    aktif_yil = get_aktif_egitim_yili()
    if not aktif_yil:
        messages.error(request, "Aktif eğitim-öğretim yılı tanımlı değil.")
        return redirect("senesonu:gecis_listesi")

    yeni_yil_pk = request.POST.get("yeni_yil", "").strip()
    yeni_yil = EgitimOgretimYili.objects.filter(pk=yeni_yil_pk).first()
    if not yeni_yil:
        messages.error(request, "Geçerli bir hedef eğitim-öğretim yılı seçin.")
        return redirect("senesonu:gecis_listesi")

    mevcut_taslak = SeneSonuGecisi.objects.filter(
        eski_egitim_yili=aktif_yil, uygulandi=False
    ).first()
    if mevcut_taslak:
        return redirect("senesonu:gecis_detay", pk=mevcut_taslak.pk)

    gecis = services.gecis_olustur(aktif_yil, yeni_yil, request.user)
    messages.success(request, "Sene sonu geçiş taslağı oluşturuldu.")
    return redirect("senesonu:gecis_detay", pk=gecis.pk)


@ust_yonetici_required
def gecis_detay(request, pk):
    gecis = get_object_or_404(
        SeneSonuGecisi.objects.select_related("eski_egitim_yili", "yeni_egitim_yili"), pk=pk
    )
    satirlar = gecis.ogrenci_gecisleri.select_related("ogrenci").order_by(
        "eski_sinif", "eski_sube", "ogrenci__okulno"
    )

    durum_filtre = request.GET.get("durum", "").strip()
    if durum_filtre:
        satirlar = satirlar.filter(durum=durum_filtre)

    ozet = {
        "toplam": gecis.ogrenci_gecisleri.count(),
        "normal": gecis.ogrenci_gecisleri.filter(durum="normal").count(),
        "sinif_tekrari": gecis.ogrenci_gecisleri.filter(durum="sinif_tekrari").count(),
        "mezun": gecis.ogrenci_gecisleri.filter(durum="mezun").count(),
        "inceleme_gerekli": gecis.ogrenci_gecisleri.filter(durum="inceleme_gerekli").count(),
    }

    return render(request, "senesonu/gecis_detay.html", {
        "title": f"Sene Sonu Geçişi — {gecis}",
        "gecis": gecis,
        "satirlar": satirlar,
        "ozet": ozet,
        "durum_filtre": durum_filtre,
        "durum_choices": SeneSonuOgrenciGecisi.DURUM_CHOICES,
    })


@ust_yonetici_required
@require_POST
def satir_duzenle(request, pk):
    satir = get_object_or_404(SeneSonuOgrenciGecisi.objects.select_related("gecis"), pk=pk)
    if satir.gecis.uygulandi:
        messages.error(request, "Uygulanmış bir geçişin satırları düzenlenemez.")
        return redirect("senesonu:gecis_detay", pk=satir.gecis_id)

    yeni_sube = request.POST.get("yeni_sube", "").strip().upper()
    yeni_sinif = request.POST.get("yeni_sinif", "").strip()

    hedef_sinif = int(yeni_sinif) if yeni_sinif else satir.yeni_sinif
    if yeni_sube and hedef_sinif:
        kayit = SinifSube.objects.filter(sinif=hedef_sinif, sube__iexact=yeni_sube).first()
        if kayit and not kayit.acik_mi(satir.gecis.yeni_egitim_yili):
            messages.warning(
                request,
                f"{hedef_sinif}/{yeni_sube} şubesi şu an kapalı — geçiş uygulandığında "
                "otomatik olarak yeniden açılacak.",
            )

    satir.yeni_sube = yeni_sube
    if yeni_sinif:
        try:
            satir.yeni_sinif = int(yeni_sinif)
        except ValueError:
            pass
    if satir.durum == "inceleme_gerekli" and yeni_sube:
        satir.durum = "normal"
    satir.save(update_fields=["yeni_sube", "yeni_sinif", "durum"])
    messages.success(request, f"{satir.ogrenci} için yeni şube güncellendi.")
    return redirect("senesonu:gecis_detay", pk=satir.gecis_id)


@ust_yonetici_required
@require_POST
def gecis_uygula(request, pk):
    gecis = get_object_or_404(SeneSonuGecisi, pk=pk)
    try:
        services.gecis_uygula(gecis)
        messages.success(
            request,
            f"Sene sonu geçişi uygulandı: aktif eğitim-öğretim yılı artık {gecis.yeni_egitim_yili}.",
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect("senesonu:gecis_detay", pk=gecis.pk)


@ust_yonetici_required
@require_POST
def gecis_sil(request, pk):
    gecis = get_object_or_404(SeneSonuGecisi, pk=pk)
    if gecis.uygulandi:
        messages.error(request, "Uygulanmış bir geçiş silinemez.")
        return redirect("senesonu:gecis_detay", pk=gecis.pk)
    gecis.delete()
    messages.success(request, "Taslak silindi.")
    return redirect("senesonu:gecis_listesi")
