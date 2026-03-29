from collections import defaultdict
from datetime import datetime, time
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from reportlab.lib import colors
from reportlab.platypus import Paragraph, TableStyle

from personeldevamsizlik.models import Devamsizlik

from ..models import (
    GunlukNobetCizelgesi,
    NobetAtanamayan,
    NobetGecmisi,
    NobetGorevi,
    NobetPersonel,
)
from ..services.pdf_rapor import NobetPDFReport
from .dagitim import _gun_adi_tr
from .permissions import is_mudur_yardimcisi, is_yonetici

# ─────────────────────────────────────────────
# Günün Nöbetçileri
# ─────────────────────────────────────────────


@login_required
def gunun_nobetcileri(request):
    if not is_yonetici(request.user):
        raise PermissionDenied
    target_date = timezone.localdate()

    if request.GET.get("tarih"):
        try:
            target_date = datetime.strptime(request.GET.get("tarih"), "%Y-%m-%d").date()
        except ValueError:
            pass

    if request.method == "POST":
        if not is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        if "kaydet" in request.POST:
            try:
                with transaction.atomic():
                    for key, value in request.POST.items():
                        if key.startswith("place_") and value:
                            gorev_id = int(key.split("_")[1])
                            gorev = NobetGorevi.objects.get(id=gorev_id)
                            GunlukNobetCizelgesi.objects.update_or_create(
                                tarih=target_date,
                                ogretmen=gorev.ogretmen,
                                defaults={"nobet_yeri": value},
                            )

                messages.success(
                    request,
                    f"{target_date.strftime('%d.%m.%Y')} tarihi için nöbet yerleri güncellendi.",
                )
                return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")
            except Exception as e:
                messages.error(request, f"Hata oluştu: {e}")
        elif "sifirla" in request.POST:
            try:
                GunlukNobetCizelgesi.objects.filter(tarih=target_date).delete()
                messages.success(
                    request,
                    f"{target_date.strftime('%d.%m.%Y')} tarihi için nöbet yerleri varsayılan ayarlara sıfırlandı.",
                )
                return redirect(f"{request.path}?tarih={target_date.strftime('%Y-%m-%d')}")
            except Exception as e:
                messages.error(request, f"Sıfırlama hatası: {e}")

    days_map = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    day_name_en = days_map[target_date.weekday()]

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    gorevler = []
    if gorev_date:
        tum_gorevler = (
            NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
            .select_related("ogretmen__personel", "nobet_yeri")
            .order_by("nobet_yeri__ad")
        )

        full_day_hours = set(range(1, 9))

        gunluk_degisiklikler = dict(
            GunlukNobetCizelgesi.objects.filter(tarih=target_date).values_list(
                "ogretmen_id", "nobet_yeri"
            )
        )

        from nobet.models import NobetYerleri
        yer_map = {y.ad: y for y in NobetYerleri.objects.all()}

        for gorev in tum_gorevler:
            if gorev.ogretmen.pk in gunluk_degisiklikler:
                yer_str = gunluk_degisiklikler[gorev.ogretmen.pk]
                gorev.nobet_yeri = yer_map.get(yer_str, gorev.nobet_yeri)

            is_full_absent = False
            absences = Devamsizlik.objects.filter(
                ogretmen=gorev.ogretmen,
                baslangic_tarihi__lte=target_date,
                bitis_tarihi__gte=target_date,
            )

            for absence in absences:
                abs_start = absence.baslangic_tarihi
                if isinstance(abs_start, datetime):
                    abs_start = abs_start.date()

                abs_end = absence.bitis_tarihi if absence.bitis_tarihi else abs_start
                if isinstance(abs_end, datetime):
                    abs_end = abs_end.date()

                if abs_start < target_date < abs_end:
                    is_full_absent = True
                else:
                    if hasattr(absence, "ders_saatleri") and absence.ders_saatleri:
                        try:
                            hours = [
                                int(h)
                                for h in absence.ders_saatleri.split(",")
                                if h.strip().isdigit()
                            ]
                            if set(hours).issuperset(full_day_hours):
                                is_full_absent = True
                        except ValueError:
                            pass
                if is_full_absent:
                    break

            if not is_full_absent:
                gorevler.append(gorev)

    tum_yerler = (
        NobetGorevi.objects.filter(nobet_yeri__isnull=False)
        .values_list("nobet_yeri__ad", flat=True)
        .distinct()
        .order_by("nobet_yeri__ad")
    )

    context = {
        "title": "Günün Nöbetçileri",
        "target_date": target_date,
        "gorevler": gorevler,
        "tum_yerler": tum_yerler,
    }
    return render(request, "gunun_nobetcileri.html", context)


# ─────────────────────────────────────────────
# PNG İndirme: Günün Nöbetçileri
# ─────────────────────────────────────────────


def _generate_gunun_nobetcileri_pdf_bytes(target_date):
    days_map = {
        0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday",
        4: "Friday", 5: "Saturday", 6: "Sunday",
    }
    day_name_en = days_map[target_date.weekday()]

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=target_date)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )

    data_rows = []
    if gorev_date:
        tum_gorevler = (
            NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
            .select_related("ogretmen__personel", "nobet_yeri")
            .order_by("nobet_yeri__ad")
        )
        full_day_hours = set(range(1, 9))
        gunluk_degisiklikler = dict(
            GunlukNobetCizelgesi.objects.filter(tarih=target_date).values_list(
                "ogretmen_id", "nobet_yeri"
            )
        )
        from nobet.models import NobetYerleri
        yer_map = {y.ad: y for y in NobetYerleri.objects.all()}
        counter = 1
        for gorev in tum_gorevler:
            if gorev.ogretmen.pk in gunluk_degisiklikler:
                yer_str = gunluk_degisiklikler[gorev.ogretmen.pk]
                gorev.nobet_yeri = yer_map.get(yer_str, gorev.nobet_yeri)
            is_full_absent = False
            absences = Devamsizlik.objects.filter(
                ogretmen=gorev.ogretmen,
                baslangic_tarihi__lte=target_date,
                bitis_tarihi__gte=target_date,
            )
            for absence in absences:
                abs_start = absence.baslangic_tarihi
                if isinstance(abs_start, datetime):
                    abs_start = abs_start.date()
                abs_end = absence.bitis_tarihi if absence.bitis_tarihi else abs_start
                if isinstance(abs_end, datetime):
                    abs_end = abs_end.date()
                if abs_start < target_date < abs_end:
                    is_full_absent = True
                else:
                    if hasattr(absence, "ders_saatleri") and absence.ders_saatleri:
                        try:
                            hours = [
                                int(h)
                                for h in absence.ders_saatleri.split(",")
                                if h.strip().isdigit()
                            ]
                            if set(hours).issuperset(full_day_hours):
                                is_full_absent = True
                        except ValueError:
                            pass
                if is_full_absent:
                    break
            if not is_full_absent:
                data_rows.append([
                    str(counter),
                    gorev.ogretmen.personel.adi_soyadi,
                    gorev.ogretmen.personel.brans,
                    str(gorev.nobet_yeri) if gorev.nobet_yeri else "",
                ])
                counter += 1

    buffer = BytesIO()
    report = NobetPDFReport(
        buffer,
        target_date,
        f"Nöbetçi Öğretmen Listesi ({target_date.strftime('%d.%m.%Y')} {_gun_adi_tr(target_date)})",
        dynamic_height=True,
        row_count=len(data_rows) if data_rows else 1,
    )
    report.add_header()
    headers = ["#", "Nöbetçi Öğretmen", "Branş", "Nöbet Yeri"]
    table_data = [[Paragraph(h, report.header_style) for h in headers]]
    if not data_rows:
        table_data.append([
            Paragraph("-", report.cell_style),
            Paragraph("Kayıt Bulunamadı", report.cell_style),
            Paragraph("-", report.cell_style),
            Paragraph("-", report.cell_style),
        ])
    else:
        for r in data_rows:
            table_data.append([
                Paragraph(r[0], report.cell_style),
                Paragraph(r[1], report.cell_style),
                Paragraph(r[2], report.cell_style),
                Paragraph(r[3], report.cell_style),
            ])
    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F81BD")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        + [
            ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DCE6F1"))
            for i in range(1, len(table_data))
            if i % 2 != 0
        ]
    )
    report.add_table(table_data, col_widths=[40, 160, 120, 210], style=style)
    report.build()
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes, target_date


@login_required
def download_gunun_nobetcileri_pdf(request):
    target_date = timezone.localdate()
    if request.GET.get("tarih"):
        try:
            target_date = datetime.strptime(request.GET.get("tarih"), "%Y-%m-%d").date()
        except ValueError:
            pass
    pdf_bytes, target_date = _generate_gunun_nobetcileri_pdf_bytes(target_date)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="gunun_nobetcileri_{target_date.strftime("%Y-%m-%d")}.pdf"'
    )
    response.write(pdf_bytes)
    return response


@login_required
def download_gunun_nobetcileri_png(request):
    target_date = timezone.localdate()
    if request.GET.get("tarih"):
        try:
            target_date = datetime.strptime(request.GET.get("tarih"), "%Y-%m-%d").date()
        except ValueError:
            pass

    from pdf2image import convert_from_bytes

    pdf_bytes, target_date = _generate_gunun_nobetcileri_pdf_bytes(target_date)
    try:
        images = convert_from_bytes(pdf_bytes, dpi=150)
        if images:
            response = HttpResponse(content_type="image/png")
            response["Content-Disposition"] = (
                f'attachment; filename="gunun_nobetcileri_{target_date.strftime("%Y-%m-%d")}.png"'
            )
            img_buffer = BytesIO()
            images[0].save(img_buffer, format="PNG")
            response.write(img_buffer.getvalue())
            img_buffer.close()
            return response
    except Exception as e:
        messages.error(request, f"Resim oluşturulurken hata (Poppler yüklü mü?): {e}")

    return redirect("gunun_nobetcileri")


# ─────────────────────────────────────────────
# PNG İndirme: Atanamayan Dersler
# ─────────────────────────────────────────────


@login_required
def download_unassigned_ders_png(request):
    from pdf2image import convert_from_bytes

    tarih_str = request.GET.get("tarih")
    unassigned = []
    target_date = None

    if tarih_str:
        start_dt = None
        end_dt = None
        try:
            view_dt = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
            target_date = view_dt.date()
            start_dt = timezone.make_aware(view_dt.replace(microsecond=0))
            end_dt = timezone.make_aware(view_dt.replace(microsecond=999999))
        except ValueError:
            try:
                target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
                start_day = timezone.make_aware(datetime.combine(target_date, time.min))
                end_day = timezone.make_aware(datetime.combine(target_date, time.max))
                latest_rec = (
                    NobetGecmisi.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )
                latest_un = (
                    NobetAtanamayan.objects.filter(tarih__range=[start_day, end_day])
                    .order_by("-tarih")
                    .first()
                )

                found_dt = None
                if latest_rec and latest_un:
                    found_dt = (
                        latest_rec.tarih if latest_rec.tarih >= latest_un.tarih else latest_un.tarih
                    )
                elif latest_rec:
                    found_dt = latest_rec.tarih
                elif latest_un:
                    found_dt = latest_un.tarih

                if found_dt:
                    start_dt = found_dt.replace(microsecond=0)
                    end_dt = found_dt.replace(microsecond=999999)
            except ValueError:
                pass

        if start_dt and end_dt:
            saved_unassigns = NobetAtanamayan.objects.filter(
                tarih__range=[start_dt, end_dt]
            ).select_related("ogretmen__personel")
            if saved_unassigns.exists():
                query_date = target_date
                absent_records = Devamsizlik.objects.filter(
                    baslangic_tarihi__lte=query_date, bitis_tarihi__gte=query_date
                ).select_related("ogretmen__personel")
                absent_map = {
                    r.ogretmen.personel.pk: r.get_devamsiz_tur_display() for r in absent_records
                }

                for u in saved_unassigns:
                    unassigned.append(
                        {
                            "hour": u.saat,
                            "class": u.sinif,
                            "absent_teacher_id": u.ogretmen.personel.pk,
                            "devamsiz_tur": absent_map.get(u.ogretmen.personel.pk, "-"),
                        }
                    )

    if not unassigned:
        unassigned = request.session.get("nobet_unassigned", [])
        date_str = request.session.get(
            "nobet_target_date", timezone.localdate().strftime("%Y-%m-%d")
        )
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if not unassigned:
        messages.warning(request, "Atanamayan ders bulunamadı.")
        return redirect("nobet_ders_doldurma")

    all_ids = set()
    for item in unassigned:
        all_ids.add(item.get("absent_teacher_id"))
    personeller = NobetPersonel.objects.filter(id__in=all_ids)
    personel_map = {p.pk: p.adi_soyadi for p in personeller}
    brans_map = {p.pk: p.brans for p in personeller}

    pdf_buffer = BytesIO()
    page_width, _ = A4

    report = NobetPDFReport(
        pdf_buffer,
        target_date,
        f"Dağıtılamayan Dersler ({target_date.strftime('%d.%m.%Y')} {_gun_adi_tr(target_date)})",
        dynamic_height=True,
        row_count=len(unassigned),
    )
    report.add_header(custom_title_color=colors.red)

    headers = ["Ders Saati", "Sınıf", "Devamsız Öğretmen", "Branş", "Mazeret"]
    table_data = [[Paragraph(h, report.header_style) for h in headers]]

    for item in sorted(unassigned, key=lambda x: x.get("hour", 0)):
        table_data.append(
            [
                Paragraph(f"{item.get('hour', '?')}. Ders", report.cell_style),
                Paragraph(str(item.get("class", "")), report.cell_style),
                Paragraph(personel_map.get(item.get("absent_teacher_id"), "-"), report.cell_style),
                Paragraph(brans_map.get(item.get("absent_teacher_id"), "-"), report.cell_style),
                Paragraph(str(item.get("devamsiz_tur", "")), report.cell_style),
            ]
        )

    style = TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dc3545")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ]
        + [
            ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8d7da"))
            for i in range(1, len(table_data))
            if i % 2 != 0
        ]
    )

    report.add_table(
        table_data,
        col_widths=[
            page_width * 0.12,
            page_width * 0.12,
            page_width * 0.30,
            page_width * 0.20,
            page_width * 0.26,
        ],
        style=style,
    )
    report.build()

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    try:
        images = convert_from_bytes(pdf_bytes, dpi=150)
        if images:
            response = HttpResponse(content_type="image/png")
            response["Content-Disposition"] = (
                f'attachment; filename="atanamayan_dersler_{target_date.strftime("%Y-%m-%d")}.png"'
            )
            img_buffer = BytesIO()
            images[0].save(img_buffer, format="PNG")
            response.write(img_buffer.getvalue())
            img_buffer.close()
            return response
    except Exception as e:
        messages.error(request, f"Resim oluşturulurken hata: {e}")

    return redirect("nobet_ders_doldurma")


# ─────────────────────────────────────────────
# Günün Öğrenci Devamsızlık Listesi — Sınıf PDF
# ─────────────────────────────────────────────


@login_required
def devamsizlik_sinif_pdf(request):
    from io import BytesIO as _BytesIO

    from django.http import HttpResponse as _HttpResponse

    from devamsizlik.models import OgrenciDevamsizlik

    if not is_mudur_yardimcisi(request.user):
        raise PermissionDenied

    tarih_str = request.GET.get("tarih", "").strip()
    sinif_str = request.GET.get("sinif", "").strip()

    try:
        target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        target_date = timezone.localdate()

    try:
        sinif = int(sinif_str)
        if sinif not in (9, 10, 11, 12):
            sinif = 9
    except (ValueError, TypeError):
        sinif = 9

    kayitlar = (
        OgrenciDevamsizlik.objects.filter(tarih=target_date, ogrenci__sinif=sinif)
        .select_related("ogrenci")
        .order_by("ogrenci__sube", "ders_saati__derssaati_no", "ogrenci__soyadi", "ogrenci__adi")
    )

    buffer = _BytesIO()
    report = NobetPDFReport(
        buffer=buffer,
        target_date=target_date,
        title=f"{sinif}. Sınıf Öğrenci Devamsızlık Listesi — {target_date.strftime('%d.%m.%Y')}",
    )
    report.add_header()

    if not kayitlar.exists():
        report.elements.append(Spacer(1, 20))
        report.elements.append(
            Paragraph(
                f"{target_date.strftime('%d.%m.%Y')} tarihinde {sinif}. sınıf için devamsızlık kaydı bulunamadı.",
                ParagraphStyle("Info", fontName=report.font_name, fontSize=11, alignment=1),
            )
        )
    else:
        sube_gruplari: dict = defaultdict(list)
        for k in kayitlar:
            sube_gruplari[k.ogrenci.sube].append(k)

        col_widths = [25, 55, 140, 40, 55, 100, 100, 80]

        for sube in sorted(sube_gruplari.keys()):
            grup = sube_gruplari[sube]

            baslik = Paragraph(
                f"{sinif}/{sube} Şubesi  ({len(grup)} öğrenci)",
                ParagraphStyle(
                    "SubeBaslik",
                    fontName=report.font_name_bold,
                    fontSize=11,
                    textColor=colors.HexColor("#1a3a5c"),
                    spaceBefore=14,
                    spaceAfter=4,
                ),
            )
            report.elements.append(baslik)

            header = [
                Paragraph("#", report.header_style_small),
                Paragraph("Okul No", report.header_style_small),
                Paragraph("Ad Soyad", report.header_style_small),
                Paragraph("Şube", report.header_style_small),
                Paragraph("Ders", report.header_style_small),
                Paragraph("Ders Adı", report.header_style_small),
                Paragraph("Öğretmen", report.header_style_small),
                Paragraph("Açıklama", report.header_style_small),
            ]
            rows = [header]
            for i, k in enumerate(grup, 1):
                rows.append(
                    [
                        Paragraph(str(i), report.cell_style_small),
                        Paragraph(k.ogrenci.okulno, report.cell_style_small),
                        Paragraph(f"{k.ogrenci.adi} {k.ogrenci.soyadi}", report.cell_style_small),
                        Paragraph(k.ogrenci.sube, report.cell_style_small),
                        Paragraph(
                            f"{k.ders_saati.derssaati_no}." if k.ders_saati else "—", report.cell_style_small
                        ),
                        Paragraph(k.ders_adi or "—", report.cell_style_small),
                        Paragraph(k.ogretmen_adi or "—", report.cell_style_small),
                        Paragraph(k.aciklama or "—", report.cell_style_small),
                    ]
                )

            tablo_stili = TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#417690")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), report.font_name_bold),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f2f7fb")],
                    ),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c0c0c0")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
            report.add_table(rows, col_widths, tablo_stili)

    report.build()
    buffer.seek(0)

    dosya_adi = f"devamsizlik_{sinif}sinif_{target_date.strftime('%Y%m%d')}.pdf"
    response = _HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{dosya_adi}"'
    return response
