"""
PDF / PNG üretimi ve indirme view'ları.
"""
from datetime import datetime
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from reportlab.lib import colors
from reportlab.platypus import Paragraph, TableStyle

from personeldevamsizlik.models import Devamsizlik
from ...models import NobetGecmisi, NobetPersonel
from ...services.pdf_rapor import NobetPDFReport
from ..dagitim import _gun_adi_tr
from ._queries import en_son_kayit_dt


def _load_atamalar(tarih_str):
    """
    URL'den gelen tarih_str'ye göre DB'den atamaları yükler.
    "YYYY-MM-DD HH:MM:SS" veya "YYYY-MM-DD" formatını kabul eder.
    Döndürür: (atamalar_listesi, target_date)
    """
    try:
        view_dt = datetime.strptime(tarih_str, "%Y-%m-%d %H:%M:%S")
        target_date = view_dt.date()
        start_dt = timezone.make_aware(view_dt.replace(microsecond=0))
        end_dt   = timezone.make_aware(view_dt.replace(microsecond=999999))
    except ValueError:
        try:
            target_date = datetime.strptime(tarih_str, "%Y-%m-%d").date()
            found_dt = en_son_kayit_dt(target_date)
            if not found_dt:
                return [], target_date
            start_dt = found_dt.replace(microsecond=0)
            end_dt   = found_dt.replace(microsecond=999999)
        except ValueError:
            return [], None

    saved = list(
        NobetGecmisi.objects.filter(tarih__range=[start_dt, end_dt])
        .select_related("ogretmen__personel")
    )
    if not saved:
        return [], target_date

    absent_map = {
        r.ogretmen.personel.pk: r.get_devamsiz_tur_display()
        for r in Devamsizlik.objects.filter(baslangic_tarihi__lte=target_date)
        .filter(Q(bitis_tarihi__gte=target_date) | Q(bitis_tarihi__isnull=True))
        .select_related("ogretmen__personel")
    }
    return [
        {
            "hour": s.saat,
            "class": s.sinif,
            "teacher_id": s.ogretmen.personel.pk,
            "absent_teacher_id": s.devamsiz,
            "devamsiz_tur": absent_map.get(s.devamsiz, "-"),
        }
        for s in saved
    ], target_date


def generate_pdf_bytes(request, dynamic_height=False):
    """
    Rapor için PDF bytes üretir.
    Önce URL'deki tarih_str'yi dener, yoksa session'a düşer.
    Döndürür: (pdf_bytes, target_date) — veri yoksa (None, None).
    """
    tarih_str   = request.GET.get("tarih")
    assignments = []
    target_date = None

    if tarih_str:
        assignments, target_date = _load_atamalar(tarih_str)

    if not assignments:
        assignments = request.session.get("nobet_assignments", [])
        date_str    = request.session.get(
            "nobet_target_date", timezone.localdate().strftime("%Y-%m-%d")
        )
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    if not assignments:
        messages.error(request, "Rapor oluşturmak için atanmış ders bulunamadı.")
        return None, None

    all_ids      = {a.get("teacher_id") for a in assignments} | {a.get("absent_teacher_id") for a in assignments}
    personeller  = NobetPersonel.objects.filter(id__in=all_ids)
    personel_map = {p.pk: p.adi_soyadi for p in personeller}
    brans_map    = {p.pk: p.brans for p in personeller}

    pdf_buffer = BytesIO()
    baslik = (
        f"Nöbetçi Öğretmen Ders Doldurma Listesi "
        f"({target_date.strftime('%d.%m.%Y')} {_gun_adi_tr(target_date)})"
    )
    report = NobetPDFReport(pdf_buffer, target_date, baslik, dynamic_height, len(assignments))
    report.add_header()

    sutunlar = ["Ders Saati", "Sınıf", "Devamsız Öğretmen", "Mazeret", "Görevlendirilen Nöbetçi", "Branş"]
    rows = [[Paragraph(c, report.header_style_small) for c in sutunlar]]

    for item in sorted(assignments, key=lambda x: x.get("hour", 0)):
        rows.append([
            Paragraph(f"{item.get('hour', '?')}. Ders",                        report.cell_style_small),
            Paragraph(str(item.get("class", "")),                               report.cell_style_small),
            Paragraph(personel_map.get(item.get("absent_teacher_id"), "-"),     report.cell_style_small),
            Paragraph(str(item.get("devamsiz_tur", "")),                        report.cell_style_small),
            Paragraph(f"<b>{personel_map.get(item.get('teacher_id'), '-')}</b>", report.cell_style_small),
            Paragraph(brans_map.get(item.get("teacher_id"), "-"),               report.cell_style_small),
        ])

    page_width = report.pagesize[0] - 60
    style = TableStyle(
        [
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#4F81BD")),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("GRID",          (0, 0), (-1, -1), 1, colors.black),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ] + [
            ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#DCE6F1"))
            for i in range(1, len(rows))
            if i % 2 != 0
        ]
    )
    report.add_table(
        rows,
        col_widths=[
            page_width * 0.10, page_width * 0.10, page_width * 0.25,
            page_width * 0.15, page_width * 0.25, page_width * 0.15,
        ],
        style=style,
    )
    report.build()
    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()
    return pdf_bytes, target_date


# ── İndirme view'ları ──────────────────────────────────────────────────────────


@login_required
def download_ders_doldurma_pdf(request):
    pdf_bytes, target_date = generate_pdf_bytes(request)
    if not pdf_bytes:
        return redirect("nobet_ders_doldurma")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="ders_doldurma_{target_date.strftime("%Y-%m-%d")}.pdf"'
    )
    response.write(pdf_bytes)
    return response


@login_required
def download_ders_doldurma_png(request):
    from pdf2image import convert_from_bytes
    from PIL import Image as PILImage

    pdf_bytes, target_date = generate_pdf_bytes(request, dynamic_height=True)
    if not pdf_bytes:
        return redirect("nobet_ders_doldurma")

    try:
        images = convert_from_bytes(pdf_bytes, dpi=150)
        if images:
            response = HttpResponse(content_type="image/png")
            response["Content-Disposition"] = (
                f'attachment; filename="ders_doldurma_{target_date.strftime("%Y-%m-%d")}.png"'
            )
            img_buffer = BytesIO()
            if len(images) == 1:
                images[0].save(img_buffer, format="PNG")
            else:
                total_width  = max(img.width  for img in images)
                total_height = sum(img.height for img in images)
                combined = PILImage.new("RGB", (total_width, total_height), "white")
                y_offset = 0
                for img in images:
                    combined.paste(img, (0, y_offset))
                    y_offset += img.height
                combined.save(img_buffer, format="PNG")
            response.write(img_buffer.getvalue())
            img_buffer.close()
            return response
    except Exception as e:
        messages.error(
            request,
            f"Rapor resme dönüştürülürken bir hata oluştu. "
            f"Lütfen sistem yöneticinize 'poppler' kütüphanesinin kurulu olduğunu teyit ettirin. "
            f"Hata: {e}",
        )
        return redirect("nobet_ders_doldurma")

    messages.error(request, "Rapor resmi oluşturulamadı.")
    return redirect("nobet_ders_doldurma")
