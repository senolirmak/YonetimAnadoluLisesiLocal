# -*- coding: utf-8 -*-
"""
PDF rapor üreticisi.

oturum_plani_pdf   – Oturma planı: her salon için bir A4 sayfası (koltuk ızgarası)
sinif_raporu_pdf   – A4 sınıf listesi: her salon için bir A4 sayfası (öğrenci tablosu)
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)

# ---------------------------------------------------------------------------
# Türkçe karakter desteği için TTF font kaydı
# ---------------------------------------------------------------------------
_FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

def _register_fonts():
    pdfmetrics.registerFont(TTFont("DejaVuSans",             str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold",        str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Oblique",     str(_FONTS_DIR / "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-BoldOblique", str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
    registerFontFamily(
        "DejaVuSans",
        normal="DejaVuSans",
        bold="DejaVuSans-Bold",
        italic="DejaVuSans-Oblique",
        boldItalic="DejaVuSans-BoldOblique",
    )
    # ps2tt eşleme tablosuna kaydet (Paragraph içi <b>/<i> etiketleri için)
    addMapping("DejaVuSans", 0, 0, "DejaVuSans")
    addMapping("DejaVuSans", 1, 0, "DejaVuSans-Bold")
    addMapping("DejaVuSans", 0, 1, "DejaVuSans-Oblique")
    addMapping("DejaVuSans", 1, 1, "DejaVuSans-BoldOblique")

_register_fonts()


# ---------------------------------------------------------------------------
# Ortak yardımcılar
# ---------------------------------------------------------------------------

def _header_style(size=10, bold=False):
    return ParagraphStyle(
        "h", fontName="DejaVuSans-Bold" if bold else "DejaVuSans",
        fontSize=size, leading=size * 1.3, alignment=1,  # center
    )


def _left_style(size=9):
    return ParagraphStyle(
        "l", fontName="DejaVuSans", fontSize=size, leading=size * 1.3, alignment=0,
    )


# ---------------------------------------------------------------------------
# 1. OTURMA PLANI PDF
# ---------------------------------------------------------------------------

def oturum_plani_pdf(salon_grids: dict, out_path: str, baslik: str, okul,
                     aktif_uretim=None, tarih=None, saat=None):
    """
    salon_grids : { salon_adi: grid }   (grid = 3 blok × 6 satır × 2 koltuk)
    Her salon için bir sayfa üretir.
    """
    from okul.models import SinifSube
    from ortaksinav_engine.utils import salon_gozetmen_bul
    sinav = aktif_uretim.sinav if aktif_uretim else None

    # "Salon-9_A" → SinifSube nesnesi eşleme tablosu
    ss_map = {
        f"Salon-{ss.sinifsube.replace('/', '_')}": ss
        for ss in SinifSube.objects.all()
    }
    salon_display  = {k: ss.salon for k, ss in ss_map.items()}
    salon_ogretmen = salon_gozetmen_bul(tarih, saat, ss_map)
    sinav_bilgi = (
        f"{sinav.get_donem_display()}  –  {sinav.get_sinav_adi_display()}"
        if sinav else ""
    )

    story = []
    h_st = _header_style(size=10, bold=False)
    h_sub_st = _header_style(size=9, bold=False)
    l_st = _left_style(size=8)

    for salon_idx, (salon_adi, grid) in enumerate(salon_grids.items()):
        if salon_idx > 0:
            story.append(PageBreak())

        # ── Başlık ──────────────────────────────────────────────
        salon_goster = salon_display.get(salon_adi, salon_adi)
        story.append(Paragraph(okul.okul_adi, h_st))
        story.append(Spacer(1, 0.1 * cm))
        if sinav_bilgi:
            story.append(Paragraph(sinav_bilgi, h_sub_st))
            story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph(f"{salon_goster}  –  Oturma Planı  ({baslik})", h_sub_st))
        story.append(Spacer(1, 0.3 * cm))

        # ── Koltuk ızgarası ─────────────────────────────────────
        # grid: 3 blok × 6 satır × 2 koltuk
        # Sayfa düzeni: 3 blok yan yana ayrılmış (araya boş sütun)
        # Tablo sütunları: [kol-A, kol-B, boşluk, kol-C, kol-D, boşluk, kol-E, kol-F]
        ROWS, COLS_PER_BLOCK, BLOCKS = 6, 2, 3

        cell_no_st = ParagraphStyle(
            "cn", fontName="DejaVuSans", fontSize=12, leading=14, alignment=1,
        )
        cell_center_st = ParagraphStyle(
            "cc", fontName="DejaVuSans", fontSize=8, leading=11, alignment=1,
        )

        # Blok bazında S-şeklinde sıra numarası: sol blok biter, orta bloğa geçilir, sağa geçilir
        seat_map: dict = {}
        sn = 1
        for b in range(BLOCKS):
            for r in range(ROWS):
                for c in ([0, 1] if r % 2 == 0 else [1, 0]):
                    seat_map[(b, r, c)] = sn
                    sn += 1

        def make_cell(ogr_dict, seat_no):
            no_p = Paragraph(str(seat_no), cell_no_st)
            if not isinstance(ogr_dict, dict):
                return [no_p]
            okulno   = str(ogr_dict.get("okulno") or "")
            sinifube = str(ogr_dict.get("sinifsube") or "")
            adi      = str(ogr_dict.get("adi") or ogr_dict.get("ad") or "")
            soyadi   = str(ogr_dict.get("soyadi") or ogr_dict.get("soyad") or "")
            ders     = str(ogr_dict.get("ders") or "")
            content_p = Paragraph(
                f"{okulno}-{sinifube}<br/>{adi} {soyadi}<br/><i>{ders}</i>",
                cell_center_st,
            )
            return [no_p, content_p]

        table_data = []
        for r in range(ROWS):
            row_cells = []
            for b in range(BLOCKS):
                for c in range(COLS_PER_BLOCK):
                    row_cells.append(make_cell(grid[b][r][c], seat_map[(b, r, c)]))
                if b < BLOCKS - 1:
                    row_cells.append("")   # bloklar arası boşluk sütunu
            table_data.append(row_cells)

        # Sütun genişlikleri: [blok1_A, blok1_B, sep, blok2_A, blok2_B, sep, blok3_A, blok3_B]
        avail_w = 17.6 * cm   # A4 - kenar boşlukları
        sep_w   = 0.2 * cm
        cell_w  = (avail_w - 2 * sep_w) / 6
        col_ws  = [cell_w, cell_w, sep_w, cell_w, cell_w, sep_w, cell_w, cell_w]
        cell_h  = 3.2 * cm

        DASH = [3, 3]
        BC   = colors.HexColor("#aaaaaa")

        style = TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND",   (2, 0), (2, ROWS - 1), colors.white),
            ("BACKGROUND",   (5, 0), (5, ROWS - 1), colors.white),
            ("LINEABOVE",    (0, 0), (-1, -1), 0.5, BC, 0, DASH),
            ("LINEBELOW",    (0, 0), (-1, -1), 0.5, BC, 0, DASH),
            ("LINEBEFORE",   (0, 0), (-1, -1), 0.5, BC, 0, DASH),
            ("LINEAFTER",    (0, 0), (-1, -1), 0.5, BC, 0, DASH),
            ("LINEABOVE",    (2, 0), (2, ROWS - 1), 0, colors.white),
            ("LINEBELOW",    (2, 0), (2, ROWS - 1), 0, colors.white),
            ("LINEBEFORE",   (2, 0), (2, ROWS - 1), 0, colors.white),
            ("LINEAFTER",    (2, 0), (2, ROWS - 1), 0, colors.white),
            ("LINEABOVE",    (5, 0), (5, ROWS - 1), 0, colors.white),
            ("LINEBELOW",    (5, 0), (5, ROWS - 1), 0, colors.white),
            ("LINEBEFORE",   (5, 0), (5, ROWS - 1), 0, colors.white),
            ("LINEAFTER",    (5, 0), (5, ROWS - 1), 0, colors.white),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
        ])
        t = Table(table_data, colWidths=col_ws, rowHeights=[cell_h] * ROWS)
        t.setStyle(style)
        story.append(t)

        # ── Özet ────────────────────────────────────────────────
        summary = {}
        for b in range(BLOCKS):
            for r in range(ROWS):
                for c in range(COLS_PER_BLOCK):
                    ogr = grid[b][r][c]
                    if isinstance(ogr, dict):
                        k = (str(ogr.get("sinif") or ""), str(ogr.get("ders") or ""))
                        summary[k] = summary.get(k, 0) + 1

        story.append(Spacer(1, 0.3 * cm))
        toplam = sum(summary.values())
        ozet_lines = [
            f"{sinif}. Sınıf  {ders}:  {cnt}"
            for (sinif, ders), cnt in sorted(summary.items())
        ]
        ozet_lines.append(f"Toplam:  {toplam}")
        ozet_st = _left_style(size=8)
        for ln in ozet_lines:
            story.append(Paragraph(ln, ozet_st))

        story.append(Spacer(1, 0.4 * cm))
        yoklama_st = ParagraphStyle(
            "yok", fontName="DejaVuSans", fontSize=8, alignment=0,
        )
        goz_st = ParagraphStyle(
            "goz", fontName="DejaVuSans-Oblique", fontSize=8, alignment=2,
        )
        ogretmen = salon_ogretmen.get(salon_adi, "")
        goz_txt = f"Gözetmen: {ogretmen}" if ogretmen else "Gözetmen: ......................................................."
        footer_row = [[
            Paragraph("<u>YOKLAMA:</u>", yoklama_st),
            Paragraph(goz_txt, goz_st),
        ]]
        footer_t = Table(footer_row, colWidths=[avail_w / 2, avail_w / 2])
        footer_t.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))
        story.append(footer_t)

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="n")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])
    doc.build(story)


# ---------------------------------------------------------------------------
# 2. A4 SINIF LİSTESİ PDF (şube bazlı — Excel ile aynı mantık)
# ---------------------------------------------------------------------------

import re as _re


# ---------------------------------------------------------------------------
# 3. SINAV TAKVİMİ PDF (öğrenciler için tek sayfa)
# ---------------------------------------------------------------------------

_GUNLER = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba",
           3: "Perşembe", 4: "Cuma", 5: "Cumartesi", 6: "Pazar"}


def sinav_takvimi_pdf(out, okul, aktif_uretim):
    """
    Aktif TakvimUretim'e bağlı Takvim kayıtlarından tek sayfalık öğrenci sınav takvimi PDF üretir.
    out: dosya yolu veya BytesIO
    """
    from collections import defaultdict
    from sinav.models import Takvim

    qs = (
        Takvim.objects
        .filter(uretim=aktif_uretim)
        .order_by("tarih", "oturum", "saat")
        .values("tarih", "saat", "oturum", "ders__ders_adi", "sinav_turu")
    )

    # (tarih, oturum, saat) → [ders_adi, ...]
    session_map = defaultdict(list)
    for r in qs:
        adi = r["ders__ders_adi"] or ""
        if r["sinav_turu"]:
            adi = f"{adi} ({r['sinav_turu']})"
        session_map[(r["tarih"], r["oturum"], r["saat"])].append(adi)
    sessions = sorted(session_map.items(), key=lambda x: (x[0][0], x[0][1]))

    h_okul = _header_style(size=12, bold=False)
    h_sub  = _header_style(size=9,  bold=False)
    cell_st = ParagraphStyle("c", fontName="DejaVuSans", fontSize=8, leading=10, alignment=0)
    cell_bold = ParagraphStyle("cb", fontName="DejaVuSans-Bold", fontSize=8, leading=10, alignment=0)

    story = []
    story.append(Paragraph(okul.okul_adi.title(), h_okul))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph(
        f"(Okul Kodu: {okul.okul_kodu})  –  "
        f"{aktif_uretim.sinav.egitim_ogretim_yili} Eğitim Öğretim Yılı  {aktif_uretim.sinav.donem}  {aktif_uretim.sinav.sinav_adi}",
        h_sub,
    ))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph("Sınav Takvimi", _header_style(size=11, bold=False)))
    story.append(Spacer(1, 0.3 * cm))

    # Tablo başlıkları
    header = [
        Paragraph("<b>Tarih</b>", cell_bold),
        Paragraph("<b>Gün</b>", cell_bold),
        Paragraph("<b>Oturum</b>", cell_bold),
        Paragraph("<b>Saat</b>", cell_bold),
        Paragraph("<b>Dersler</b>", cell_bold),
    ]
    data = [header]
    for (tarih, oturum, saat), dersler in sessions:
        gun = _GUNLER.get(tarih.weekday(), "")
        tarih_str = tarih.strftime("%d.%m.%Y")
        dersler_str = "<br/>".join(sorted(set(d for d in dersler if d)))
        data.append([
            Paragraph(tarih_str, cell_st),
            Paragraph(gun, cell_st),
            Paragraph(str(oturum), cell_st),
            Paragraph(str(saat)[:5], cell_st),
            Paragraph(dersler_str, cell_st),
        ])

    avail_w = 17.6 * cm
    col_ws = [2.5 * cm, 2.3 * cm, 1.8 * cm, 1.8 * cm, avail_w - 8.4 * cm]

    tbl_style = TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#e8eaf6")),
        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTNAME",      (0, 0), (-1, 0),  "DejaVuSans-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
    ])
    t = Table(data, colWidths=col_ws, repeatRows=1)
    t.setStyle(tbl_style)
    story.append(t)

    mudur = okul.okul_muduru or ""

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVuSans", 9)
        x = doc.leftMargin + doc.width / 2
        lh = 0.48 * cm
        y = 1.2 * cm
        canvas.drawCentredString(x, y,            "Okul Müdürü")
        canvas.drawCentredString(x, y + lh,       mudur)
        canvas.drawCentredString(x, y + 2 * lh,   "... / ... / 2026")
        canvas.drawCentredString(x, y + 4.5 * lh, "UYGUNDUR")
        canvas.restoreState()

    doc = BaseDocTemplate(
        out, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=5.0 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="n")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_footer)])
    doc.build(story)

def _sinif_sube_key(s):
    s = s.replace("/", "_").upper()
    m = _re.match(r"(\d+)_?([A-ZÇĞİÖŞÜ]*)", s)
    if m:
        try:
            return (int(m.group(1)), m.group(2))
        except Exception:
            pass
    return (99, s)


def sinif_raporu_pdf(tarih, saat, oturum, out_path: str, okul, aktif_uretim, sinifsube_filter=None):
    """
    Her şube için bir sayfa: o şubedeki öğrencilerin hangi salona/sıraya
    atandığını gösteren liste (Excel raporu ile aynı içerik).
    Sütunlar: Sıra No | Okul No | Ad Soyad | Sıra | Salon
    sinifsube_filter verilirse sadece o şube gösterilir.
    """
    from okul.models import SinifSube
    from sinav.models import OturmaPlani

    qs = OturmaPlani.objects.filter(
        tarih=tarih, saat=saat, oturum=oturum, uretim=aktif_uretim
    )
    if sinifsube_filter:
        qs = qs.filter(sinifsube=sinifsube_filter)
    qs = qs.order_by("sinifsube", "okulno")

    if not qs.exists():
        return

    tarih_str = str(tarih)
    saat_str  = str(saat)

    # OturmaPlani.salon ("Salon-9_A") → SinifSube.salon ("Salon 9/A") eşleme tablosu
    salon_display = {
        f"Salon-{ss.sinifsube.replace('/', '_')}": ss.salon
        for ss in SinifSube.objects.all()
    }

    rows = list(qs.values("salon", "sira_no", "okulno", "adi_soyadi", "sinifsube", "ders_adi"))
    for r in rows:
        r["sinifsube"] = str(r["sinifsube"] or "").upper().replace("_", "/")
        r["salon"] = salon_display.get(r["salon"], r["salon"])

    siniflar = sorted(
        set(r["sinifsube"] for r in rows),
        key=_sinif_sube_key,
    )

    sinav = aktif_uretim.sinav if aktif_uretim else None

    story = []
    h_okul = _header_style(size=11, bold=False)
    h_sub  = _header_style(size=9,  bold=False)

    tbl_style = TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (2, 1), (2, -1),  "LEFT"),
        ("ALIGN",         (4, 1), (4, -1),  "LEFT"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (4, 1), (4, -1),  10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ])

    avail_w = 17.6 * cm  # A4 - kenar boşlukları
    # Sütun genişlikleri: Sıra No | Okul No | Ad Soyad | Sıra | Salon
    col_ws = [1.2 * cm, 2.2 * cm, 8.0 * cm, 1.8 * cm, 4.4 * cm]

    for sinif_idx, sinifsube in enumerate(siniflar):
        if sinif_idx > 0:
            story.append(PageBreak())

        sinif_rows = sorted(
            [r for r in rows if r["sinifsube"] == sinifsube],
            key=lambda r: (int(r["okulno"]) if str(r["okulno"]).isdigit() else 0),
        )
        ders_adi = sinif_rows[0]["ders_adi"] if sinif_rows else ""

        _TR_AYLAR = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                     "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
        tarih_tr = f"{tarih.day} {_TR_AYLAR[tarih.month - 1]} {tarih.year} {_GUNLER[tarih.weekday()]}  Saat: {saat_str}"
        tarih_st = ParagraphStyle("th_r", fontName="DejaVuSans", fontSize=8, leading=10, alignment=2)

        if sinav:
            kurum_adi = sinav.kurum.okul_adi if sinav.kurum else okul.okul_adi
            sinav_bilgi_str = f"{sinav.egitim_ogretim_yili} Eğitim Öğretim Yılı  {sinav.get_donem_display()}  {sinav.get_sinav_adi_display()}"
        else:
            kurum_adi = okul.okul_adi
            sinav_bilgi_str = ""

        story.append(Paragraph(tarih_tr, tarih_st))
        story.append(Spacer(1, 0.1 * cm))
        story.append(Paragraph(kurum_adi, h_okul))
        if sinav_bilgi_str:
            story.append(Spacer(1, 0.1 * cm))
            story.append(Paragraph(sinav_bilgi_str, h_sub))
        story.append(Spacer(1, 0.1 * cm))
        sube_ders_row = [[
            Paragraph(f"Şube: {sinifsube}", _left_style(size=9)),
            Paragraph(f"Sınav Yapılacak Ders: {ders_adi}", ParagraphStyle(
                "sd_r", fontName="DejaVuSans", fontSize=9, leading=11, alignment=2,
            )),
        ]]
        sube_ders_t = Table(sube_ders_row, colWidths=[3.5 * cm, avail_w - 3.5 * cm])
        sube_ders_t.hAlign = "LEFT"
        sube_ders_t.setStyle(TableStyle([
            ("VALIGN",       (0, 0), (-1, -1), "BOTTOM"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))
        story.append(sube_ders_t)
        story.append(Spacer(1, 0.3 * cm))

        data = [["Sıra No", "Okul No", "Ad Soyad", "Sıra", "Salon"]]
        for idx, r in enumerate(sinif_rows, start=1):
            data.append([
                str(idx),
                str(r["okulno"] or ""),
                str(r["adi_soyadi"] or ""),
                str(r["sira_no"] or ""),
                str(r["salon"] or ""),
            ])

        t = Table(data, colWidths=col_ws, repeatRows=1)
        t.setStyle(tbl_style)
        story.append(t)

        story.append(Spacer(1, 0.3 * cm))
        story.append(Paragraph(
            f"Bu şubeden toplam  {len(sinif_rows)}  öğrenci.",
            _left_style(size=8),
        ))

    doc = BaseDocTemplate(
        out_path, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="n")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame)])
    doc.build(story)
