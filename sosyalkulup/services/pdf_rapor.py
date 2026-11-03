"""Sosyal kulüp öğrenci listesi PDF'i."""

import io

from django.conf import settings
from django.utils import timezone
from django.utils.html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _fontlar():
    """Türkçe karakterler için DejaVu'yu kaydeder; (normal, kalın) font adlarını döner."""
    fonts_dir = settings.BASE_DIR / "static" / "fonts"
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(fonts_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(fonts_dir / "DejaVuSans-Bold.ttf")))
        return "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


def kulup_ogrenci_listesi_pdf(kulup, egitim_yili, danismanlar, uyelikler, okul_adi=""):
    """Kulübün öğrenci listesini A4 dikey PDF olarak üretir; bytes döner."""
    font, font_kalin = _fontlar()
    stil = ParagraphStyle("normal", fontName=font, fontSize=10, leading=13)
    baslik = ParagraphStyle("baslik", parent=stil, fontName=font_kalin, fontSize=13, leading=17, alignment=1)
    alt_baslik = ParagraphStyle("alt", parent=stil, alignment=1)
    hucre = ParagraphStyle("hucre", parent=stil, fontSize=9.5, leading=12)

    danisman_adlari = [d.ogretmen.adi_soyadi for d in danismanlar]
    icerik = []
    if okul_adi:
        icerik.append(Paragraph(escape(okul_adi), baslik))
    icerik += [
        Paragraph(f"{escape(egitim_yili)} Eğitim-Öğretim Yılı", alt_baslik),
        Spacer(1, 4),
        Paragraph(f"{escape(kulup.ad)} — Öğrenci Listesi", baslik),
        Spacer(1, 8),
        Paragraph(
            f"<font name='{font_kalin}'>Danışman Öğretmen(ler):</font> "
            f"{escape(', '.join(danisman_adlari) or '-')}"
            f" &nbsp;&nbsp; <font name='{font_kalin}'>Öğrenci Sayısı:</font> {len(uyelikler)}",
            stil,
        ),
        Spacer(1, 8),
    ]

    satirlar = [["#", "Sınıf/Şube", "Okul No", "Adı Soyadı", "Kulüpteki Görevi"]]
    for i, u in enumerate(uyelikler, 1):
        o = u.ogrenci
        satirlar.append([
            str(i),
            o.sinifsube,
            str(o.okulno),
            Paragraph(escape(f"{o.adi} {o.soyadi}"), hucre),
            u.get_gorev_display(),
        ])
    if len(satirlar) == 1:
        satirlar.append(["", "", "", "Kulübe kayıtlı öğrenci yok.", ""])

    tablo = Table(
        satirlar,
        colWidths=[1 * cm, 2.4 * cm, 2.2 * cm, 7.4 * cm, 4 * cm],
        repeatRows=1,
    )
    tablo.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTNAME", (0, 0), (-1, 0), font_kalin),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.88, 0.88, 0.88)),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (2, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.96, 0.96, 0.96)]),
    ]))
    icerik.append(tablo)

    # İmza alanı: her danışman öğretmen için bir sütun
    if danisman_adlari:
        icerik.append(Spacer(1, 1.2 * cm))
        imza = Table(
            [
                [Paragraph(escape(ad), alt_baslik) for ad in danisman_adlari],
                [Paragraph("Kulüp Danışman Öğretmeni", alt_baslik) for _ in danisman_adlari],
                [Paragraph("İmza", alt_baslik) for _ in danisman_adlari],
            ],
            colWidths=[17 * cm / len(danisman_adlari)] * len(danisman_adlari),
        )
        icerik.append(imza)

    tarih = timezone.localdate().strftime("%d.%m.%Y")

    def _sayfa_alti(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.drawString(2 * cm, 1.2 * cm, f"Düzenlenme tarihi: {tarih}")
        canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Sayfa {doc.page}")
        canvas.restoreState()

    tampon = io.BytesIO()
    SimpleDocTemplate(
        tampon,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=2 * cm,
        title=f"{kulup.ad} Öğrenci Listesi",
    ).build(icerik, onFirstPage=_sayfa_alti, onLaterPages=_sayfa_alti)
    return tampon.getvalue()
