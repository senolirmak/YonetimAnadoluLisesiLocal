"""Sınıf oturma planı PDF'i (A4 dikey, tek sayfa)."""

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
from reportlab.platypus import (
    Flowable,
    KeepInFrame,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ogrenci.services.oturma_duzeni import N_GRUP, N_KOLON_PER_GRUP


def _fontlar():
    """Türkçe karakterler için DejaVu'yu kaydeder; (normal, kalın) font adlarını döner."""
    fonts_dir = settings.BASE_DIR / "static" / "fonts"
    try:
        pdfmetrics.registerFont(TTFont("DejaVuSans", str(fonts_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(fonts_dir / "DejaVuSans-Bold.ttf")))
        return "DejaVuSans", "DejaVuSans-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


class _DikeyYazi(Flowable):
    """Saat yönünde 90° döndürülmüş, yukarıdan aşağıya okunan tek satırlık yazı."""

    def __init__(self, metin, font, boyut, renk):
        super().__init__()
        self.metin, self.font, self.boyut, self.renk = metin, font, boyut, renk

    def wrap(self, *_):
        self.genislik = pdfmetrics.stringWidth(self.metin, self.font, self.boyut)
        return self.boyut, self.genislik

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont(self.font, self.boyut)
        c.setFillColor(self.renk)
        # Döndürme sonrası yazı (0, genişlik) noktasından aşağı doğru ilerler
        c.translate(self.boyut * 0.25, self.genislik)
        c.rotate(-90)
        c.drawString(0, 0, self.metin)
        c.restoreState()


def oturma_plani_pdf(sinif_sube, egitim_yili, grid, yerlestirilmemis, rehber_adi="", okul_adi=""):
    """Sınıfın oturma planını tek sayfalık A4 dikey PDF olarak üretir; bytes döner.

    `grid` için bkz. `services.oturma_duzeni.oturma_grid`. Yerleşim web sayfasıyla
    aynıdır: tahta üstte, 1. grup solda.
    """
    font, font_kalin = _fontlar()
    stil = ParagraphStyle("normal", fontName=font, fontSize=9, leading=11)
    baslik = ParagraphStyle("baslik", parent=stil, fontName=font_kalin, fontSize=13, leading=16, alignment=1)
    orta = ParagraphStyle("orta", parent=stil, alignment=1)
    koltuk = ParagraphStyle("koltuk", parent=stil, fontName=font_kalin, fontSize=8.5, leading=10, alignment=1)
    okulno = ParagraphStyle("okulno", parent=stil, fontSize=7.5, leading=9, alignment=1,
                            textColor=colors.Color(0.35, 0.35, 0.35))

    yerlesik = sum(1 for satir in grid for grup in satir for h in grup if h["ogr"])
    icerik = []
    if okul_adi:
        icerik.append(Paragraph(escape(okul_adi), baslik))
    icerik += [
        Paragraph(
            f"{escape(egitim_yili or '')} Eğitim-Öğretim Yılı — {escape(sinif_sube)} Sınıfı Oturma Planı",
            baslik,
        ),
        Spacer(1, 3),
        Paragraph(
            f"<font name='{font_kalin}'>Sınıf Rehber Öğretmeni:</font> {escape(rehber_adi or '-')}"
            f" &nbsp;&nbsp; <font name='{font_kalin}'>Yerleştirilen Öğrenci:</font> {yerlesik}",
            orta,
        ),
        Spacer(1, 8),
    ]

    # Sütunlar: [sıra no] + her grup için 2 koltuk, gruplar arasında dar koridor,
    # en sağda sınıf kapısı sütunu
    koltuk_g, koridor_g, sira_g, kapi_g = 2.45 * cm, 0.4 * cm, 0.7 * cm, 0.45 * cm
    sutunlar = [sira_g]
    for g in range(N_GRUP):
        sutunlar += [koltuk_g] * N_KOLON_PER_GRUP
        if g < N_GRUP - 1:
            sutunlar.append(koridor_g)
    sutunlar.append(kapi_g)
    kapi_sutunu = len(sutunlar) - 1
    koridorlar = [1 + (g + 1) * N_KOLON_PER_GRUP + g for g in range(N_GRUP - 1)]

    # Satırlar: 0 tahta, 1 öğretmen masası, 2 grup başlıkları, 3.. koltuk sıraları
    tahta = [""] * len(sutunlar)
    tahta[1] = "TAHTA"
    masa = [""] * len(sutunlar)
    masa[1] = "Öğretmen Masası"
    masa[-1] = _DikeyYazi("KAPI", font_kalin, 8, colors.Color(0.47, 0.21, 0.06))
    grup_basliklari = [""]
    for g in range(1, N_GRUP + 1):
        grup_basliklari += [f"{g}. Grup", ""]
        if g < N_GRUP:
            grup_basliklari.append("")
    grup_basliklari.append("")
    satirlar = [tahta, masa, grup_basliklari]
    ilk_sira = len(satirlar)

    for no, satir in enumerate(grid, 1):
        hucreler = [str(no)]
        for g, grup in enumerate(satir):
            for h in grup:
                o = h["ogr"]
                hucreler.append(
                    [Paragraph(escape(f"{o.adi} {o.soyadi}"), koltuk), Paragraph(str(o.okulno), okulno)]
                    if o else ""
                )
            if g < len(satir) - 1:
                hucreler.append("")
        hucreler.append("")
        satirlar.append(hucreler)

    komutlar = [
        ("FONTNAME", (0, 0), (-1, -1), font),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        # Tahta şeridi
        ("SPAN", (1, 0), (-1, 0)),
        ("BACKGROUND", (1, 0), (-1, 0), colors.Color(0.22, 0.25, 0.32)),
        ("TEXTCOLOR", (1, 0), (-1, 0), colors.white),
        ("FONTNAME", (1, 0), (-1, 0), font_kalin),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        # Öğretmen masası: 1. grubun üstünde
        ("SPAN", (1, 1), (N_KOLON_PER_GRUP, 1)),
        ("BACKGROUND", (1, 1), (N_KOLON_PER_GRUP, 1), colors.Color(0.996, 0.95, 0.78)),
        ("BOX", (1, 1), (N_KOLON_PER_GRUP, 1), 1.2, colors.Color(0.85, 0.47, 0.02)),
        ("FONTNAME", (1, 1), (N_KOLON_PER_GRUP, 1), font_kalin),
        # Grup başlıkları
        ("FONTNAME", (0, 2), (-1, 2), font_kalin),
        ("FONTSIZE", (0, 2), (-1, 2), 8),
        # Sıra numaraları
        ("TEXTCOLOR", (0, ilk_sira), (0, -1), colors.grey),
        ("FONTNAME", (0, ilk_sira), (0, -1), font_kalin),
        # Sınıf kapısı: tahtanın hemen altında, 3. grubun sağında; masa ve grup
        # başlığı satırları boyunca uzanır
        ("SPAN", (kapi_sutunu, 1), (kapi_sutunu, 2)),
        ("BACKGROUND", (kapi_sutunu, 1), (kapi_sutunu, 2), colors.Color(0.91, 0.83, 0.74)),
        ("BOX", (kapi_sutunu, 1), (kapi_sutunu, 2), 1.2, colors.Color(0.57, 0.25, 0.05)),
        ("LEFTPADDING", (kapi_sutunu, 1), (kapi_sutunu, 2), 0),
        ("RIGHTPADDING", (kapi_sutunu, 1), (kapi_sutunu, 2), 0),
    ]
    sutun = 1
    for g in range(N_GRUP):
        ilk, son = sutun, sutun + N_KOLON_PER_GRUP - 1
        komutlar += [
            ("SPAN", (ilk, 2), (son, 2)),
            ("BACKGROUND", (ilk, 2), (son, 2), colors.Color(0.93, 0.93, 0.93)),
            ("BOX", (ilk, ilk_sira), (son, -1), 1, colors.black),
            ("INNERGRID", (ilk, ilk_sira), (son, -1), 0.5, colors.grey),
        ]
        sutun = son + 2
    for k in koridorlar:
        komutlar.append(("BACKGROUND", (k, ilk_sira), (k, -1), colors.Color(0.97, 0.97, 0.97)))

    tablo = Table(
        satirlar,
        colWidths=sutunlar,
        rowHeights=[0.7 * cm, 0.9 * cm, 0.7 * cm] + [2.6 * cm] * len(grid),
    )
    tablo.setStyle(TableStyle(komutlar))
    icerik.append(tablo)

    if yerlestirilmemis:
        icerik += [
            Spacer(1, 6),
            Paragraph(
                f"<font name='{font_kalin}'>Oturma planında yer almayan öğrenciler:</font> "
                + escape(", ".join(f"{o.okulno} {o.adi} {o.soyadi}" for o in yerlestirilmemis)),
                stil,
            ),
        ]

    icerik.append(Spacer(1, 0.6 * cm))
    icerik.append(Table(
        [
            ["", Paragraph(escape(rehber_adi or ""), orta)],
            ["", Paragraph("Sınıf Rehber Öğretmeni", orta)],
            ["", Paragraph("İmza", orta)],
        ],
        colWidths=[10 * cm, 7 * cm],
    ))

    tarih = timezone.localdate().strftime("%d.%m.%Y")

    def _sayfa_alti(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 8)
        canvas.drawString(1.5 * cm, 0.8 * cm, f"Düzenlenme tarihi: {tarih}")
        canvas.restoreState()

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
        title=f"{sinif_sube} Oturma Planı",
    )
    # Çerçevenin iç boşluğu (6pt × 2) düşülür; sığmayan içerik orantılı küçültülür.
    sayfa = KeepInFrame(doc.width - 12, doc.height - 12, icerik, mode="shrink")
    doc.build([sayfa], onFirstPage=_sayfa_alti)
    return tampon.getvalue()
