from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from dersprogrami.models import DersProgrami
from devamsizlik.models import OgrenciDevamsizlik
from ogrenci.models import Ogrenci

from .models import Faaliyet, FaaliyetDersSaati

# ─────────────────────────────────────────────
# Yardımcılar
# ─────────────────────────────────────────────


def _personel(request):
    try:
        return request.user.personel
    except Exception:
        return None


from okul.auth import is_mudur_yardimcisi as _mudur_yardimcisi_mi
from okul.utils import get_aktif_dp_tarihi


def _ogrenci_verileri():
    sinifsube_listesi = (
        Ogrenci.objects.values_list("sinif", "sube").distinct().order_by("sinif", "sube")
    )
    aktif_tarih = get_aktif_dp_tarihi()
    dp_filter = {"sinif_sube__isnull": False}
    if aktif_tarih:
        dp_filter["uygulama_tarihi"] = aktif_tarih
    dp_sinifsube = (
        DersProgrami.objects.filter(**dp_filter)
        .values_list("sinif_sube__sinif", "sinif_sube__sube")
        .distinct()
        .order_by("sinif_sube__sinif", "sinif_sube__sube")
    )
    return {
        "ogrenciler": Ogrenci.objects.all().order_by("sinif", "sube", "soyadi", "adi"),
        "sinifsube_secenekleri": [f"{s}/{sb}" for s, sb in sinifsube_listesi],
        "dp_sinifsube": [{"sinif": s, "sube": sb, "label": f"{s}/{sb}"} for s, sb in dp_sinifsube],
    }


def _post_to_faaliyet(request):
    """POST verisinden faaliyet alan değerlerini toplar."""
    konu = request.POST.get("konu", "").strip()
    tarih = request.POST.get("tarih", "").strip()
    yer = request.POST.get("yer", "").strip()
    aciklama = request.POST.get("aciklama", "").strip()

    hatalar = []
    if not konu:
        hatalar.append("Faaliyet konusu zorunludur.")
    if not tarih:
        hatalar.append("Tarih zorunludur.")
    if not yer:
        hatalar.append("Yapıldığı yer zorunludur.")

    ders_saatleri = []
    for ders_no, bas, bit in zip(
        request.POST.getlist("ders_no[]"),
        request.POST.getlist("baslangic[]"),
        request.POST.getlist("bitis[]"),
    ):
        if ders_no and bas and bit:
            ders_saatleri.append(
                {
                    "ders_no": int(ders_no),
                    "baslangic": bas,
                    "bitis": bit,
                }
            )

    secili_ids = [int(x) for x in request.POST.getlist("ogrenciler")]

    return konu, tarih, yer, aciklama, ders_saatleri, secili_ids, hatalar


# ─────────────────────────────────────────────
# Öğretmen: liste / oluştur / detay / düzenle / sil
# ─────────────────────────────────────────────


@login_required
def faaliyet_liste(request):
    personel = _personel(request)
    if personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    faaliyetler = Faaliyet.objects.filter(ogretmen=personel).prefetch_related(
        "ders_saatleri", "ogrenciler"
    )
    return render(request, "faaliyet/faaliyet_liste.html", {"faaliyetler": faaliyetler})


@login_required
def faaliyet_olustur(request):
    personel = _personel(request)
    if personel is None:
        messages.error(request, "Bu kullanıcıya bağlı personel kaydı bulunamadı.")
        return redirect("index")

    ctx = _ogrenci_verileri()
    ctx["faaliyet"] = None

    if request.method == "POST":
        konu, tarih, yer, aciklama, ders_saatleri, secili_ids, hatalar = _post_to_faaliyet(request)
        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            with transaction.atomic():
                faaliyet = Faaliyet.objects.create(
                    konu=konu,
                    tarih=tarih,
                    yer=yer,
                    aciklama=aciklama,
                    ogretmen=personel,
                    durum=Faaliyet.DURUM_BEKLEMEDE,
                )
                for ds in ders_saatleri:
                    FaaliyetDersSaati.objects.create(faaliyet=faaliyet, **ds)
                if secili_ids:
                    faaliyet.ogrenciler.set(Ogrenci.objects.filter(pk__in=secili_ids))

            messages.success(
                request,
                "Faaliyet kaydedildi ve Müdür Yardımcısı onayına gönderildi. "
                "Onaylandığında devamsızlık girişi yapabileceksiniz.",
            )
            return redirect("faaliyet:faaliyet_liste")

    return render(request, "faaliyet/faaliyet_form.html", ctx)


@login_required
def faaliyet_detay(request, pk):
    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel != faaliyet.ogretmen and not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu faaliyeti görme yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    return render(
        request,
        "faaliyet/faaliyet_detay.html",
        {
            "faaliyet": faaliyet,
            "ders_saatleri": faaliyet.ders_saatleri.all(),
            "ogrenciler": faaliyet.ogrenciler.order_by("sinif", "sube", "soyadi", "adi"),
        },
    )


@login_required
def faaliyet_duzenle(request, pk):
    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel != faaliyet.ogretmen and not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu faaliyeti düzenleme yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    # Onaylanmış veya tamamlanmış faaliyetler düzenlenemez
    if faaliyet.durum == Faaliyet.DURUM_ONAYLANDI:
        messages.warning(request, "Onaylanmış faaliyet düzenlenemez.")
        return redirect("faaliyet:faaliyet_detay", pk=pk)
    if faaliyet.devamsizlik_girildi:
        messages.warning(request, "Devamsızlığı girilmiş faaliyet düzenlenemez.")
        return redirect("faaliyet:faaliyet_detay", pk=pk)

    ctx = _ogrenci_verileri()
    ctx["faaliyet"] = faaliyet
    ctx["secili_ids"] = set(faaliyet.ogrenciler.values_list("pk", flat=True))

    if request.method == "POST":
        konu, tarih, yer, aciklama, ders_saatleri, secili_ids, hatalar = _post_to_faaliyet(request)
        if hatalar:
            for h in hatalar:
                messages.error(request, h)
        else:
            with transaction.atomic():
                faaliyet.konu = konu
                faaliyet.tarih = tarih
                faaliyet.yer = yer
                faaliyet.aciklama = aciklama
                faaliyet.durum = Faaliyet.DURUM_BEKLEMEDE  # tekrar onaya gider
                faaliyet.ret_aciklamasi = ""
                faaliyet.save()
                faaliyet.ders_saatleri.all().delete()
                for ds in ders_saatleri:
                    FaaliyetDersSaati.objects.create(faaliyet=faaliyet, **ds)
                faaliyet.ogrenciler.set(Ogrenci.objects.filter(pk__in=secili_ids))

            messages.success(request, "Faaliyet güncellendi ve tekrar onaya gönderildi.")
            return redirect("faaliyet:faaliyet_detay", pk=faaliyet.pk)

    return render(request, "faaliyet/faaliyet_form.html", ctx)


@login_required
def faaliyet_sil(request, pk):
    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel != faaliyet.ogretmen and not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu faaliyeti silme yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    # Öğretmen onaylanmış ya da tamamlanmış faaliyeti silemez
    if not _mudur_yardimcisi_mi(request.user):
        if faaliyet.durum == Faaliyet.DURUM_ONAYLANDI:
            messages.error(request, "Onaylanmış faaliyet silinemez.")
            return redirect("faaliyet:faaliyet_detay", pk=pk)
        if faaliyet.devamsizlik_girildi:
            messages.error(request, "Devamsızlığı girilmiş faaliyet silinemez.")
            return redirect("faaliyet:faaliyet_detay", pk=pk)

    next_url = request.POST.get("next") or request.GET.get("next", "")

    if request.method == "POST":
        faaliyet.delete()
        messages.success(request, "Faaliyet silindi.")
        if next_url:
            return redirect(next_url)
        return redirect("faaliyet:faaliyet_liste")

    return render(request, "faaliyet/faaliyet_sil.html", {"faaliyet": faaliyet, "next": next_url})


# ─────────────────────────────────────────────
# AJAX: Ders programından ders saati getir
# ─────────────────────────────────────────────


@login_required
def ders_programi_getir(request):
    """
    Verilen gün + sınıf/şube için DersProgrami kayıtlarını döndürür.
    GET parametreleri: gun (Monday…), sinif (int), sube (str)
    """
    gun = request.GET.get("gun", "").strip()
    sinif = request.GET.get("sinif", "").strip()
    sube = request.GET.get("sube", "").strip()

    if not (gun and sinif and sube):
        return JsonResponse({"dersler": []})

    aktif_tarih = get_aktif_dp_tarihi()
    dp_filter = {"gun": gun, "sinif_sube__sinif": sinif, "sinif_sube__sube__iexact": sube}
    if aktif_tarih:
        dp_filter["uygulama_tarihi"] = aktif_tarih
    qs = (
        DersProgrami.objects.filter(**dp_filter)
        .select_related("sinif_sube", "ders_saati")
        .order_by("ders_saati__derssaati_no")
    )

    dersler = [
        {
            "ders_no": d.ders_saati.derssaati_no if d.ders_saati else None,
            "ders_adi": d.ders_adi,
            "baslangic": d.giris_saat.strftime("%H:%M") if d.giris_saat else "",
            "bitis": d.cikis_saat.strftime("%H:%M") if d.cikis_saat else "",
        }
        for d in qs
    ]
    return JsonResponse({"dersler": dersler})


# ─────────────────────────────────────────────
# Müdür Yardımcısı: tüm faaliyetler yönetim listesi
# ─────────────────────────────────────────────


@login_required
def faaliyet_yonetim_listesi(request):
    if not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    from okul.models import Personel

    qs = (
        Faaliyet.objects.select_related("ogretmen")
        .prefetch_related("ders_saatleri", "ogrenciler")
        .order_by("-tarih", "-olusturma_zamani")
    )

    # Filtreler
    ogretmen_id = request.GET.get("ogretmen", "").strip()
    durum = request.GET.get("durum", "").strip()
    tarih_bas = request.GET.get("tarih_bas", "").strip()
    tarih_bit = request.GET.get("tarih_bit", "").strip()

    if ogretmen_id:
        qs = qs.filter(ogretmen_id=ogretmen_id)
    if durum:
        qs = qs.filter(durum=durum)
    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)

    ogretmenler = Personel.objects.filter(faaliyetler__isnull=False).distinct().order_by("adi_soyadi")

    return render(
        request,
        "faaliyet/faaliyet_yonetim_listesi.html",
        {
            "faaliyetler": qs,
            "ogretmenler": ogretmenler,
            "secili_ogretmen": ogretmen_id,
            "secili_durum": durum,
            "tarih_bas": tarih_bas,
            "tarih_bit": tarih_bit,
            "DURUM_CHOICES": Faaliyet.DURUM_CHOICES,
        },
    )


# ─────────────────────────────────────────────
# Müdür Yardımcısı: onay akışı
# ─────────────────────────────────────────────


@login_required
def faaliyet_onay_listesi(request):
    if not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    bekleyenler = (
        Faaliyet.objects.filter(durum=Faaliyet.DURUM_BEKLEMEDE)
        .select_related("ogretmen")
        .prefetch_related("ders_saatleri")
    )
    return render(request, "faaliyet/faaliyet_onay_listesi.html", {"bekleyenler": bekleyenler})


@login_required
def faaliyet_onayla(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("index")

    faaliyet = get_object_or_404(Faaliyet, pk=pk)
    if request.method == "POST":
        faaliyet.durum = Faaliyet.DURUM_ONAYLANDI
        faaliyet.ret_aciklamasi = ""
        # Onaylayan bilgisini kaydet
        try:
            personel = request.user.personel
            faaliyet.onaylayan_adi = (
                personel.adi_soyadi or request.user.get_full_name() or request.user.username
            )
        except Exception:
            faaliyet.onaylayan_adi = request.user.get_full_name() or request.user.username
        faaliyet.onay_zamani = timezone.now()
        faaliyet.save()
        messages.success(
            request,
            f'"{faaliyet.konu}" faaliyeti onaylandı. Öğretmen artık devamsızlık girişi yapabilir.',
        )
        return redirect("faaliyet:faaliyet_onay_listesi")

    return render(request, "faaliyet/faaliyet_onayla.html", {"faaliyet": faaliyet})


@login_required
def faaliyet_reddet(request, pk):
    if not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu işlem için yetkiniz yok.")
        return redirect("index")

    faaliyet = get_object_or_404(Faaliyet, pk=pk)
    if request.method == "POST":
        aciklama = request.POST.get("ret_aciklamasi", "").strip()
        faaliyet.durum = Faaliyet.DURUM_REDDEDILDI
        faaliyet.ret_aciklamasi = aciklama
        faaliyet.save()
        messages.warning(request, f'"{faaliyet.konu}" faaliyeti reddedildi.')
        return redirect("faaliyet:faaliyet_onay_listesi")

    return render(request, "faaliyet/faaliyet_reddet.html", {"faaliyet": faaliyet})


# ─────────────────────────────────────────────
# Öğretmen: devam/devamsızlık girişi (onay sonrası)
# ─────────────────────────────────────────────


@login_required
def faaliyet_devamsizlik(request, pk):
    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel is None or personel != faaliyet.ogretmen:
        messages.error(request, "Bu faaliyetin devamsızlık girişini yapma yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    if faaliyet.durum != Faaliyet.DURUM_ONAYLANDI:
        messages.error(
            request, "Devamsızlık girişi yalnızca onaylanmış faaliyetler için yapılabilir."
        )
        return redirect("faaliyet:faaliyet_detay", pk=pk)

    ders_saatleri = list(FaaliyetDersSaati.objects.filter(faaliyet=faaliyet))
    ogrenciler = list(faaliyet.ogrenciler.order_by("sinif", "sube", "soyadi", "adi"))

    if request.method == "POST":
        from okul.models import DersSaatleri as _DersSaatleri
        _ds_map = {d.derssaati_no: d for d in _DersSaatleri.objects.all()}
        with transaction.atomic():
            for ds in ders_saatleri:
                devamsiz_ids = set(int(x) for x in request.POST.getlist(f"devamsiz_{ds.ders_no}"))
                ds_obj = _ds_map.get(ds.ders_no)
                # Bu faaliyet için aynı tarih+ders_saatindeki önceki kayıtları temizle
                OgrenciDevamsizlik.objects.filter(
                    ogrenci__in=ogrenciler,
                    tarih=faaliyet.tarih,
                    ders_saati=ds_obj,
                    aciklama__startswith="Faaliyet:",
                ).delete()

                for ogr in ogrenciler:
                    # Katıldı → 'Faaliyet: Katıldı', Devamsız → 'Faaliyet: {konu}'
                    aciklama = (
                        f"Faaliyet: {faaliyet.konu}"
                        if ogr.pk in devamsiz_ids
                        else "Faaliyet: Katıldı"
                    )
                    OgrenciDevamsizlik.objects.update_or_create(
                        ogrenci=ogr,
                        tarih=faaliyet.tarih,
                        ders_saati=ds_obj,
                        defaults={
                            "ders_adi": f"Faaliyet: {faaliyet.konu}",
                            "ogretmen_adi": personel.adi_soyadi,
                            "aciklama": aciklama,
                        },
                    )

            faaliyet.devamsizlik_girildi = True
            faaliyet.save(update_fields=["devamsizlik_girildi"])

        messages.success(request, "Devamsızlık bilgileri kaydedildi. Faaliyet raporu oluşturuldu.")
        return redirect("faaliyet:faaliyet_rapor", pk=pk)

    # Ders+öğrenci verisini template'te kolayca kullanılacak şekilde grupla
    ders_gruplari = []
    for ds in ders_saatleri:
        kayitli_ids = set(
            OgrenciDevamsizlik.objects.filter(
                ogrenci__in=ogrenciler,
                tarih=faaliyet.tarih,
                ders_saati__derssaati_no=ds.ders_no,
                aciklama__startswith="Faaliyet:",
            )
            .exclude(aciklama="Faaliyet: Katıldı")
            .values_list("ogrenci_id", flat=True)
        )
        ders_gruplari.append(
            {
                "ds": ds,
                "ogrenciler": [
                    {"ogr": ogr, "devamsiz": ogr.pk in kayitli_ids} for ogr in ogrenciler
                ],
            }
        )

    return render(
        request,
        "faaliyet/faaliyet_devamsizlik.html",
        {
            "faaliyet": faaliyet,
            "ders_gruplari": ders_gruplari,
        },
    )


# ─────────────────────────────────────────────
# Faaliyet Raporu
# ─────────────────────────────────────────────


@login_required
def faaliyet_rapor(request, pk):
    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel != faaliyet.ogretmen and not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu rapora erişim yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    if not faaliyet.devamsizlik_girildi:
        messages.warning(
            request,
            "Rapor yalnızca devamsızlık girişi tamamlanan faaliyetler için görüntülenebilir.",
        )
        return redirect("faaliyet:faaliyet_detay", pk=pk)

    ogrenciler = list(faaliyet.ogrenciler.order_by("sinif", "sube", "soyadi", "adi"))
    ders_saatleri = list(FaaliyetDersSaati.objects.filter(faaliyet=faaliyet))

    # Her ders saati için devamsız öğrenci setlerini hazırla
    ders_gruplari = []
    toplam_devamsizlik = 0
    for ds in ders_saatleri:
        devamsiz_ids = set(
            OgrenciDevamsizlik.objects.filter(
                ogrenci__in=ogrenciler,
                tarih=faaliyet.tarih,
                ders_saati__derssaati_no=ds.ders_no,
                aciklama__startswith="Faaliyet:",
            )
            .exclude(aciklama="Faaliyet: Katıldı")
            .values_list("ogrenci_id", flat=True)
        )
        devamsizlar = [ogr for ogr in ogrenciler if ogr.pk in devamsiz_ids]
        katilimcilar = [ogr for ogr in ogrenciler if ogr.pk not in devamsiz_ids]
        toplam_devamsizlik += len(devamsizlar)
        ders_gruplari.append(
            {
                "ds": ds,
                "katilimcilar": katilimcilar,
                "devamsizlar": devamsizlar,
            }
        )

    return render(
        request,
        "faaliyet/faaliyet_rapor.html",
        {
            "faaliyet": faaliyet,
            "ogrenciler": ogrenciler,
            "ders_gruplari": ders_gruplari,
            "toplam_ogrenci": len(ogrenciler),
            "toplam_devamsizlik": toplam_devamsizlik,
        },
    )


# ─────────────────────────────────────────────
# Faaliyet Raporu PDF
# ─────────────────────────────────────────────


@login_required
def faaliyet_rapor_pdf(request, pk):
    import os
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    personel = _personel(request)
    faaliyet = get_object_or_404(Faaliyet, pk=pk)

    if personel != faaliyet.ogretmen and not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu rapora erişim yetkiniz yok.")
        return redirect("faaliyet:faaliyet_liste")

    if not faaliyet.devamsizlik_girildi:
        return redirect("faaliyet:faaliyet_detay", pk=pk)

    ogrenciler = list(faaliyet.ogrenciler.order_by("sinif", "sube", "okulno"))
    ders_saatleri = list(FaaliyetDersSaati.objects.filter(faaliyet=faaliyet))

    # Her ders saati için devamsız öğrenci setleri
    devamsiz_map = {}  # ds.ders_no → set(ogrenci_pk)
    toplam_devamsizlik = 0
    for ds in ders_saatleri:
        ids = set(
            OgrenciDevamsizlik.objects.filter(
                ogrenci__in=ogrenciler,
                tarih=faaliyet.tarih,
                ders_saati__derssaati_no=ds.ders_no,
                aciklama__startswith="Faaliyet:",
            )
            .exclude(aciklama="Faaliyet: Katıldı")
            .values_list("ogrenci_id", flat=True)
        )
        devamsiz_map[ds.ders_no] = ids
        toplam_devamsizlik += len(ids)

    # DejaVu font (Türkçe karakter desteği)
    font_dir = os.path.join(os.path.dirname(__file__), "fonts")
    font_regular = os.path.join(font_dir, "DejaVuSans.ttf")
    font_bold = os.path.join(font_dir, "DejaVuSans-Bold.ttf")
    if os.path.exists(font_regular) and os.path.exists(font_bold):
        pdfmetrics.registerFont(TTFont("DejaVu", font_regular))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", font_bold))
        base_font = "DejaVu"
        bold_font = "DejaVu-Bold"
    else:
        base_font = "Helvetica"
        bold_font = "Helvetica-Bold"

    # 6'dan fazla ders saati varsa yatay sayfa kullan
    n_ders = len(ders_saatleri)
    page_size = landscape(A4) if n_ders > 5 else A4
    margin = 1.5 * cm

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    # Stil tanımları — sıkı tutmak için küçük font
    fs_normal = 8
    fs_header = 8
    pad = 3

    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    def ps(name, bold=False, size=None, center=False, color=colors.black):
        return ParagraphStyle(
            name,
            fontName=bold_font if bold else base_font,
            fontSize=size or fs_normal,
            leading=(size or fs_normal) + 3,
            alignment=TA_CENTER if center else TA_LEFT,
            textColor=color,
        )

    s_normal = ps("n")
    s_bold = ps("b", bold=True)
    s_title = ps("t", bold=True, size=13, center=True)
    s_hdr = ps("h", bold=True, size=fs_header, color=colors.white)
    s_center = ps("c", center=True)

    KATILDI = colors.HexColor("#1a7f37")  # koyu yeşil
    DEVAMSIZ = colors.HexColor("#c0392b")  # koyu kırmızı
    HDR_BG = colors.HexColor("#417690")
    ROW1 = colors.white
    ROW2 = colors.HexColor("#f4f8fb")

    story = []

    # ── Başlık ──────────────────────────────────────────
    story.append(Paragraph("FAALİYET KATILIM RAPORU", s_title))
    story.append(Spacer(1, 0.25 * cm))
    story.append(HRFlowable(width="100%", thickness=1.5, color=HDR_BG))
    story.append(Spacer(1, 0.2 * cm))

    # ── Bilgi satırı (tek satır, yatay) ─────────────────
    bilgi_satirlari = [
        [
            Paragraph("<b>Konu:</b>", s_bold),
            Paragraph(faaliyet.konu, s_normal),
            Paragraph("<b>Tarih:</b>", s_bold),
            Paragraph(faaliyet.tarih.strftime("%d.%m.%Y"), s_normal),
            Paragraph("<b>Yer:</b>", s_bold),
            Paragraph(faaliyet.yer, s_normal),
        ],
        [
            Paragraph("<b>Öğretmen:</b>", s_bold),
            Paragraph(faaliyet.ogretmen.adi_soyadi or "", s_normal),
            Paragraph("<b>Toplam Öğrenci:</b>", s_bold),
            Paragraph(str(len(ogrenciler)), s_normal),
            Paragraph("<b>Toplam Devamsız:</b>", s_bold),
            Paragraph(str(toplam_devamsizlik), s_normal),
        ],
    ]

    # Açıklama satırı (varsa)
    aciklama_val = faaliyet.aciklama or ""
    if aciklama_val:
        bilgi_satirlari.append(
            [
                Paragraph("<b>Açıklama:</b>", s_bold),
                Paragraph(aciklama_val, s_normal),
                Paragraph("", s_normal),
                Paragraph("", s_normal),
                Paragraph("", s_normal),
                Paragraph("", s_normal),
            ]
        )

    # onay_str — tablo sonrasında kullanılacak
    onay_str = faaliyet.onaylayan_adi or ""
    if onay_str and faaliyet.onay_zamani:
        onay_str += f"  ({faaliyet.onay_zamani.strftime('%d.%m.%Y %H:%M')})"

    iw = doc.width / 6
    info_tbl = Table(
        bilgi_satirlari, colWidths=[iw * 0.7, iw * 1.3, iw * 0.7, iw * 0.8, iw * 0.7, iw * 0.8]
    )
    info_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f7")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#eef3f7")),
                ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#eef3f7")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), pad),
                ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(info_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # ── Ana katılım tablosu ──────────────────────────────
    # Sütunlar: No | Sınıf/Şube | Adı Soyadı | 1.Ders | 2.Ders | ...
    # Sabit sütun genişlikleri
    w_sira = 0.9 * cm  # ön tanım — hdr bloğunda tekrar kullanılır
    w_no = 1.4 * cm
    w_ss = 1.5 * cm
    w_ad = 4.5 * cm
    ders_w_toplam = doc.width - w_sira - w_no - w_ss - w_ad
    w_ders = ders_w_toplam / n_ders if n_ders else ders_w_toplam

    # Başlık satırı
    hdr = [
        Paragraph("Sn", s_hdr),
        Paragraph("Okul No", s_hdr),
        Paragraph("Sınıf/\nŞube", s_hdr),
        Paragraph("Adı Soyadı", s_hdr),
    ]
    for ds in ders_saatleri:
        hdr.append(
            Paragraph(
                f"{ds.ders_no}. Ders\n{ds.baslangic.strftime('%H:%M')}\n–{ds.bitis.strftime('%H:%M')}",
                s_hdr,
            )
        )

    tablo_data = [hdr]

    for sira, ogr in enumerate(ogrenciler, start=1):
        satir = [
            Paragraph(str(sira), s_center),
            Paragraph(ogr.okulno or "", s_center),
            Paragraph(f"{ogr.sinif}/{ogr.sube}", s_center),
            Paragraph(f"{ogr.adi} {ogr.soyadi}", s_normal),
        ]
        for ds in ders_saatleri:
            if ogr.pk in devamsiz_map[ds.ders_no]:
                satir.append(Paragraph("✗", ps("dx", bold=True, center=True, color=DEVAMSIZ)))
            else:
                satir.append(Paragraph("✓", ps("dk", bold=True, center=True, color=KATILDI)))
        tablo_data.append(satir)

    col_widths = [w_sira, w_no, w_ss, w_ad] + [w_ders] * n_ders
    main_tbl = Table(tablo_data, colWidths=col_widths, repeatRows=1)

    # Tablo stili
    tbl_style = [
        # Başlık satırı
        ("BACKGROUND", (0, 0), (-1, 0), HDR_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("FONTSIZE", (0, 0), (-1, 0), fs_header),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        # Veri satırları
        ("FONTNAME", (0, 1), (-1, -1), base_font),
        ("FONTSIZE", (0, 1), (-1, -1), fs_normal),
        ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
        ("ALIGN", (4, 1), (-1, -1), "CENTER"),  # ders sütunları ortala (sıra+no+ss+ad = 4 sabit)
        # Izgara
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c0c8d0")),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HDR_BG),
        # Padding
        ("TOPPADDING", (0, 0), (-1, -1), pad),
        ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    # Satır arkaplan renkleri
    for i in range(1, len(tablo_data)):
        bg = ROW1 if i % 2 == 1 else ROW2
        tbl_style.append(("BACKGROUND", (0, i), (-1, i), bg))

    main_tbl.setStyle(TableStyle(tbl_style))
    story.append(main_tbl)

    # ── Alt bilgi ───────────────────────────────────────
    story.append(Spacer(1, 0.25 * cm))
    story.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.2 * cm))

    if onay_str:
        onay_tbl = Table(
            [[Paragraph("<b>Onaylayan:</b>", s_bold), Paragraph(onay_str, s_normal)]],
            colWidths=[2.2 * cm, doc.width - 2.2 * cm],
        )
        onay_tbl.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), pad),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
                ]
            )
        )
        story.append(onay_tbl)
        story.append(Spacer(1, 0.15 * cm))

    tarih_str = timezone.localdate().strftime("%d.%m.%Y")
    story.append(
        Paragraph(
            f"Rapor Tarihi: {tarih_str}     ✓ Katıldı   ✗ Devamsız",
            ps("alt", size=7, color=colors.HexColor("#666666")),
        )
    )

    doc.build(story)
    buffer.seek(0)

    dosya_adi = f"faaliyet_rapor_{faaliyet.pk}_{faaliyet.tarih.strftime('%Y%m%d')}.pdf"
    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response
