from datetime import date as dt_date
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import models, transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from dersprogrami.models import NobetDersProgrami
from ogrenci.models import Ogrenci

from .models import OgrenciDevamsizlik


def _mudur_yardimcisi_mi(user):
    return user.is_superuser or user.groups.filter(name="mudur_yardimcisi").exists()


def _ust_yonetici_mi(user):
    return (
        user.is_superuser
        or user.groups.filter(name__in=["mudur_yardimcisi", "okul_muduru"]).exists()
    )


def _parse_tarih(tarih_str, varsayilan=None):
    """GET/POST'tan gelen tarih stringini date'e çevirir; hatalıysa varsayılanı döner."""
    try:
        return dt_date.fromisoformat(tarih_str.strip())
    except (ValueError, TypeError, AttributeError):
        return varsayilan or timezone.localdate()


def _ders_aktif_mi(ders, secili_tarih, bugun, simdi):
    """
    Bugün: ders saati aralığında mı?  → True / False
    Başka gün (geçmiş ya da gelecek): her zaman → True
    """
    if secili_tarih != bugun:
        return True
    return ders.giris_saat <= simdi < ders.cikis_saat


def _ders_listesi_hazirla(bugun_dersleri, secili_tarih, bugun, simdi):
    """QuerySet'i {ders, aktif_mi} listesine dönüştürür."""
    return [
        {"ders": d, "aktif_mi": _ders_aktif_mi(d, secili_tarih, bugun, simdi)}
        for d in bugun_dersleri
    ]


@login_required
def ogretmen_devamsizlik(request, ders_saati=None):
    try:
        personel = request.user.personel
    except Exception:
        messages.error(request, "Bu kullanıcıya bağlı öğretmen kaydı bulunamadı.")
        return redirect("index")

    bugun = timezone.localdate()
    simdi = timezone.localtime().time()

    # Ogretmen grubu yalnızca bugünü görebilir
    from main.views import _only_ogretmen

    if _only_ogretmen(request.user):
        secili_tarih = bugun
    else:
        secili_tarih = _parse_tarih(request.GET.get("tarih", ""), bugun)

    gun_adi = secili_tarih.strftime("%A")  # 'Monday', 'Tuesday', …

    from django.conf import settings

    if settings.DEBUG and request.GET.get("gun"):
        gun_adi = request.GET.get("gun")

    # Haftanın başı/sonu (navigasyon için)
    hbas = secili_tarih - timedelta(days=secili_tarih.weekday())  # Pazartesi
    _hson = hbas + timedelta(days=6)  # Pazar

    gun_navigasyon = [
        {
            "tarih": hbas + timedelta(days=i),
            "ad": ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"][i],
        }
        for i in range(5)  # Pazartesi–Cuma
    ]

    bugun_dersleri = NobetDersProgrami.objects.filter(
        ogretmen=personel,
        gun=gun_adi,
    ).order_by("ders_saati")

    if not bugun_dersleri.exists():
        return render(
            request,
            "devamsizlik/ogretmen_devamsizlik.html",
            {
                "durum": "ders_yok",
                "bugun": bugun,
                "secili_tarih": secili_tarih,
                "gun_navigasyon": gun_navigasyon,
            },
        )

    # Her ders için aktif_mi bayrağı (sadece bugün için saat kontrolü)
    ders_listesi = _ders_listesi_hazirla(bugun_dersleri, secili_tarih, bugun, simdi)
    aktif_ders = next((d["ders"] for d in ders_listesi if d["aktif_mi"]), None)

    # Ders seçimi: URL parametresi yoksa → bugünse aktif ders, değilse None
    if ders_saati:
        secili_ders = bugun_dersleri.filter(ders_saati=ders_saati).first()

        # Bugün için: ders saati dışında direkt URL ile erişim engelle
        if secili_ders and secili_tarih == bugun:
            if not _ders_aktif_mi(secili_ders, secili_tarih, bugun, simdi):
                messages.warning(
                    request,
                    f"{secili_ders.ders_saati}. ders yoklaması yalnızca ders saati içinde açılabilir "
                    f"({secili_ders.giris_saat.strftime('%H:%M')}–{secili_ders.cikis_saat.strftime('%H:%M')}).",
                )
                return redirect(
                    reverse("devamsizlik:ogretmen_devamsizlik")
                    + f"?tarih={secili_tarih.isoformat()}"
                )
    elif secili_tarih == bugun:
        secili_ders = aktif_ders
    else:
        secili_ders = None

    if not secili_ders:
        return render(
            request,
            "devamsizlik/ogretmen_devamsizlik.html",
            {
                "durum": "ders_sec",
                "ders_listesi": ders_listesi,
                "aktif_ders": aktif_ders,
                "bugun": bugun,
                "secili_tarih": secili_tarih,
                "gun_navigasyon": gun_navigasyon,
            },
        )

    if not secili_ders.sinif_sube:
        messages.error(request, "Seçilen derse ait sınıf/şube bilgisi bulunamadı.")
        return redirect(
            reverse("devamsizlik:ogretmen_devamsizlik") + f"?tarih={secili_tarih.isoformat()}"
        )

    sinif_sube = secili_ders.sinif_sube
    ogrenciler = Ogrenci.objects.filter(
        sinif=sinif_sube.sinif,
        sube=sinif_sube.sube,
    ).order_by("okulno")

    kayitli_devamsiz_ids = set(
        OgrenciDevamsizlik.objects.filter(
            ogrenci__in=ogrenciler,
            tarih=secili_tarih,
            ders_saati=secili_ders.ders_saati,
        ).values_list("ogrenci_id", flat=True)
    )

    if request.method == "POST":
        post_tarih = _parse_tarih(request.POST.get("tarih", ""), bugun)
        devamsiz_ids = set(int(x) for x in request.POST.getlist("devamsiz"))

        with transaction.atomic():
            OgrenciDevamsizlik.objects.filter(
                ogrenci__in=ogrenciler,
                tarih=post_tarih,
                ders_saati=secili_ders.ders_saati,
            ).delete()
            for ogr in ogrenciler:
                if ogr.pk in devamsiz_ids:
                    OgrenciDevamsizlik.objects.create(
                        ogrenci=ogr,
                        tarih=post_tarih,
                        ders_saati=secili_ders.ders_saati,
                        ders_adi=secili_ders.ders_adi,
                        ogretmen_adi=personel.adi_soyadi,
                    )

        messages.success(request, f"{len(devamsiz_ids)} öğrenci devamsız olarak kaydedildi.")
        return redirect(
            reverse("devamsizlik:ogretmen_devamsizlik") + f"?tarih={post_tarih.isoformat()}"
        )

    return render(
        request,
        "devamsizlik/ogretmen_devamsizlik.html",
        {
            "durum": "form",
            "secili_ders": secili_ders,
            "sinif_sube": sinif_sube,
            "ogrenciler": ogrenciler,
            "kayitli_devamsiz_ids": kayitli_devamsiz_ids,
            "ders_listesi": ders_listesi,
            "aktif_ders": aktif_ders,
            "bugun": bugun,
            "secili_tarih": secili_tarih,
            "gun_navigasyon": gun_navigasyon,
        },
    )


@login_required
def ogrenci_devamsizlik_listesi(request):
    if not _mudur_yardimcisi_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    tarih_bas = request.GET.get("tarih_bas", "")
    tarih_bit = request.GET.get("tarih_bit", "")
    sinifsube = request.GET.get("sinifsube", "")
    ogrenci_q = request.GET.get("ogrenci", "")
    kaynak = request.GET.get("kaynak", "")

    qs = OgrenciDevamsizlik.objects.select_related("ogrenci").order_by(
        "-tarih", "ogrenci__sinif", "ogrenci__sube", "ders_saati"
    )

    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)
    if sinifsube:
        try:
            sinif, sube = sinifsube.split("/")
            qs = qs.filter(ogrenci__sinif=sinif.strip(), ogrenci__sube__iexact=sube.strip())
        except ValueError:
            pass
    if ogrenci_q:
        qs = qs.filter(
            models.Q(ogrenci__adi__icontains=ogrenci_q)
            | models.Q(ogrenci__soyadi__icontains=ogrenci_q)
            | models.Q(ogrenci__okulno__icontains=ogrenci_q)
        )
    if kaynak == "normal":
        qs = qs.exclude(aciklama__startswith="Faaliyet:")
    elif kaynak == "faaliyet":
        qs = qs.filter(aciklama__startswith="Faaliyet:")

    sinifsube_secenekleri = [
        f"{s}/{sb}"
        for s, sb in Ogrenci.objects.values_list("sinif", "sube")
        .distinct()
        .order_by("sinif", "sube")
    ]

    return render(
        request,
        "devamsizlik/ogrenci_devamsizlik_listesi.html",
        {
            "devamsizliklar": qs,
            "toplam": qs.count(),
            "sinifsube_secenekleri": sinifsube_secenekleri,
            "secili_tarih_bas": tarih_bas,
            "secili_tarih_bit": tarih_bit,
            "secili_sinifsube": sinifsube,
            "ogrenci_q": ogrenci_q,
            "secili_kaynak": kaynak,
        },
    )


# ─────────────────────────────────────────────
# Öğrenci Yoklama PDF Raporu
# ─────────────────────────────────────────────


def _build_pdf(qs, tarih_bas, tarih_bit, secili_sinifler, okul_adi=""):
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    # Türkçe karakter desteği için DejaVu fontları
    font_normal = "Helvetica"
    font_bold = "Helvetica-Bold"
    try:
        pdfmetrics.registerFont(
            TTFont("DejaVuSans", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
        )
        pdfmetrics.registerFont(
            TTFont("DejaVuSans-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
        )
        font_normal = "DejaVuSans"
        font_bold = "DejaVuSans-Bold"
    except Exception:
        pass

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    def para(text, size=9, bold=False, color=colors.black):
        return Paragraph(
            str(text),
            ParagraphStyle(
                "custom",
                fontName=font_bold if bold else font_normal,
                fontSize=size,
                textColor=color,
                leading=size * 1.3,
            ),
        )

    elements = []

    # — Başlık —
    if okul_adi:
        elements.append(para(okul_adi, size=12, bold=True))
        elements.append(Spacer(1, 0.15 * cm))
    elements.append(para("Öğrenci Yoklama Raporu", size=14, bold=True))
    elements.append(Spacer(1, 0.2 * cm))

    tarih_aralik = f"{tarih_bas.strftime('%d.%m.%Y')} – {tarih_bit.strftime('%d.%m.%Y')}"
    elements.append(para(f"Tarih Aralığı: {tarih_aralik}", size=9))
    if secili_sinifler:
        etiketler = [f"{s}. Sınıf" for s in sorted(secili_sinifler, key=int)]
        elements.append(para(f"Sınıflar: {', '.join(etiketler)}", size=9))
    elements.append(Spacer(1, 0.4 * cm))

    # — Tablo —
    from itertools import groupby

    basliklar = ["Sınıf", "Okul No", "Adı Soyadı", "Ders S.", "Açıklama"]
    n_cols = len(basliklar)
    data = [[para(h, size=8, bold=True) for h in basliklar]]

    tarih_satirlari = []  # tarih başlığı olan satır indeksleri

    for tarih, grup in groupby(qs, key=lambda k: k.tarih):
        # Tarih başlık satırı
        tarih_idx = len(data)
        tarih_satirlari.append(tarih_idx)
        gun_tr = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        gun_adi = gun_tr[tarih.weekday()]
        tarih_label = f"{tarih.strftime('%d.%m.%Y')}  –  {gun_adi}"
        data.append([para(tarih_label, size=8, bold=True)] + [""] * (n_cols - 1))

        for kayit in grup:
            ogr = kayit.ogrenci
            aciklama = kayit.aciklama or ""
            if aciklama.startswith("Faaliyet:"):
                aciklama_goster = aciklama.replace("Faaliyet:", "Faaliyet –", 1).strip()
            else:
                aciklama_goster = "Devamsız" if not aciklama else aciklama

            data.append(
                [
                    para(ogr.sinifsube, size=8),
                    para(ogr.okulno, size=8),
                    para(f"{ogr.adi} {ogr.soyadi}", size=8),
                    para(str(kayit.ders_saati), size=8),
                    para(aciklama_goster, size=8),
                ]
            )

    col_widths = [1.5 * cm, 2.0 * cm, 6.5 * cm, 1.5 * cm, 6.5 * cm]

    style_cmds = [
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
        ("LINEABOVE", (0, 0), (-1, 0), 0.8, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#aaaaaa")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    for r in tarih_satirlari:
        style_cmds += [
            ("SPAN", (0, r), (-1, r)),
            ("LINEABOVE", (0, r), (-1, r), 0.6, colors.black),
            ("LINEBELOW", (0, r), (-1, r), 0.4, colors.HexColor("#aaaaaa")),
            ("TOPPADDING", (0, r), (-1, r), 4),
            ("BOTTOMPADDING", (0, r), (-1, r), 4),
        ]

    tablo = Table(data, colWidths=col_widths, repeatRows=1)
    tablo.setStyle(TableStyle(style_cmds))
    elements.append(tablo)

    # — Alt bilgi —
    elements.append(Spacer(1, 0.4 * cm))
    from django.utils import timezone as tz

    elements.append(
        para(
            f"Rapor oluşturma tarihi: {tz.localdate().strftime('%d.%m.%Y')}  |  "
            f"Toplam kayıt: {qs.count()}",
            size=8,
            color=colors.grey,
        )
    )

    doc.build(elements)
    return buffer.getvalue()


@login_required
def ogrenci_devamsizlik_pdf(request):
    if not _ust_yonetici_mi(request.user):
        messages.error(request, "Bu sayfaya erişim yetkiniz yok.")
        return redirect("index")

    sinif_secenekleri = list(
        Ogrenci.objects.values_list("sinif", flat=True).distinct().order_by("sinif")
    )

    if request.method != "POST":
        bugun = timezone.localdate()
        return render(
            request,
            "devamsizlik/ogrenci_devamsizlik_pdf_form.html",
            {
                "sinif_secenekleri": sinif_secenekleri,
                "tarih_bas_default": bugun.replace(day=1).isoformat(),
                "tarih_bit_default": bugun.isoformat(),
            },
        )

    tarih_bas = _parse_tarih(request.POST.get("tarih_bas", ""), timezone.localdate().replace(day=1))
    tarih_bit = _parse_tarih(request.POST.get("tarih_bit", ""), timezone.localdate())
    secili_sinifler = request.POST.getlist("sinif")  # ['9', '10', ...]

    qs = (
        OgrenciDevamsizlik.objects.select_related("ogrenci")
        .filter(tarih__gte=tarih_bas, tarih__lte=tarih_bit)
        .order_by("tarih", "ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno", "ders_saati")
    )

    if secili_sinifler:
        qs = qs.filter(ogrenci__sinif__in=secili_sinifler)

    if not qs.exists():
        messages.warning(request, "Seçilen kriterlere uygun yoklama kaydı bulunamadı.")
        return render(
            request,
            "devamsizlik/ogrenci_devamsizlik_pdf_form.html",
            {
                "sinif_secenekleri": sinif_secenekleri,
                "tarih_bas_default": tarih_bas.isoformat(),
                "tarih_bit_default": tarih_bit.isoformat(),
                "secili_sinifler": secili_sinifler,
            },
        )

    from nobet.models import OkulBilgi

    okul_bilgi = OkulBilgi.objects.first()
    okul_adi = okul_bilgi.okul_adi if okul_bilgi else ""

    pdf_bytes = _build_pdf(qs, tarih_bas, tarih_bit, secili_sinifler, okul_adi)

    dosya_adi = f"yoklama_raporu_{tarih_bas.strftime('%Y%m%d')}_{tarih_bit.strftime('%Y%m%d')}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{dosya_adi}"'
    return response
