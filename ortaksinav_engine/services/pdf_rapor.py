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
    Paragraph, Spacer, Table, TableStyle, KeepTogether,
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
        ogretmen_obj = salon_ogretmen.get(salon_adi)
        ogretmen = ogretmen_obj.adi_soyadi if ogretmen_obj else ""
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


def sinav_takvimi_pdf(out, okul, aktif_uretim, hazirlayan_user=None, goster_subeler=True):
    """
    Aktif TakvimUretim'e bağlı Takvim kayıtlarından yayın kaliteli sınav takvimi PDF üretir.
    Gün başlık satırı + oturum başına ders satırları, imza bölümü ile A4 PDF.
    goster_subeler=False: Şubeler sütunu olmadan üretir.
    out: dosya yolu veya BytesIO
    """
    from sinav.models import Takvim

    qs = (
        Takvim.objects
        .filter(uretim=aktif_uretim)
        .select_related("ders")
        .order_by("tarih", "oturum", "ders__ders_adi")
    )

    gun_map: dict = {}
    for t in qs:
        gun_map.setdefault(t.tarih, []).append(t)
    gunler = sorted(gun_map.items())

    if not gunler:
        return

    _TR_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]

    def _tarih_tr(d):
        return f"{d.day} {_TR_AYLAR[d.month - 1]} {d.year}"

    avail_w = 17.6 * cm

    h_okul  = ParagraphStyle("ho",  fontName="DejaVuSans-Bold", fontSize=13, leading=16, alignment=1)
    h_sub   = ParagraphStyle("hs",  fontName="DejaVuSans",      fontSize=9,  leading=12, alignment=1)
    h_bas   = ParagraphStyle("hb",  fontName="DejaVuSans-Bold", fontSize=12, leading=15, alignment=1)
    h_ara   = ParagraphStyle("ha",  fontName="DejaVuSans",      fontSize=8,  leading=10, alignment=1)
    cell_st = ParagraphStyle("mc",  fontName="DejaVuSans",      fontSize=8,  leading=10, alignment=0)
    cell_b  = ParagraphStyle("mb",  fontName="DejaVuSans-Bold", fontSize=8,  leading=10, alignment=0)
    ctr_st  = ParagraphStyle("ct",  fontName="DejaVuSans",      fontSize=8,  leading=10, alignment=1)
    sig_st  = ParagraphStyle("sg",  fontName="DejaVuSans",      fontSize=8.5,leading=12, alignment=1)
    sig_b   = ParagraphStyle("sgb", fontName="DejaVuSans-Bold", fontSize=8.5,leading=12, alignment=1)

    # Şubeli : Ot.(1.4) | Saat(2.0) | Ders(7.1) | Şubeler(7.1) = 17.6 cm
    # Şubesiz: Tarih(3.5) | Ot.(1.2) | Saat(1.8) | Ders(11.1)  = 17.6 cm
    if goster_subeler:
        col_ws = [1.4 * cm, 2.0 * cm, 7.1 * cm, 7.1 * cm]
    else:
        col_ws = [3.5 * cm, 1.2 * cm, 1.8 * cm, 11.1 * cm]

    sinav = aktif_uretim.sinav
    yil = sinav.egitim_ogretim_yili if sinav else ""
    sinav_adi_str = (
        f"{yil} Eğitim-Öğretim Yılı  —  "
        f"{sinav.get_donem_display()}  {sinav.get_sinav_adi_display()}"
        if sinav else ""
    )
    ilk_tarih, son_tarih = gunler[0][0], gunler[-1][0]

    story = []

    # ── Başlık bloğu ──
    story.append(Paragraph((okul.okul_adi or "").upper() if okul else "", h_okul))
    if okul and getattr(okul, "okul_kodu", None):
        story.append(Spacer(1, 0.05 * cm))
        story.append(Paragraph(f"Okul Kodu: {okul.okul_kodu}", h_sub))
    story.append(Spacer(1, 0.15 * cm))
    story.append(Paragraph(sinav_adi_str, h_sub))
    story.append(Spacer(1, 0.1 * cm))
    story.append(Paragraph("ORTAK SINAV TAKVİMİ", h_bas))
    story.append(Spacer(1, 0.05 * cm))
    story.append(Paragraph(
        f"{_tarih_tr(ilk_tarih)} – {_tarih_tr(son_tarih)}", h_ara
    ))
    story.append(Spacer(1, 0.3 * cm))

    # ── Tablo ──
    if goster_subeler:
        tbl_data = [[
            Paragraph("<b>OT.</b>", ctr_st),
            Paragraph("<b>SAAT</b>", ctr_st),
            Paragraph("<b>SINAV / DERS</b>", ctr_st),
            Paragraph("<b>ŞUBELER</b>", ctr_st),
        ]]
    else:
        tbl_data = [[
            Paragraph("<b>TARİH</b>", ctr_st),
            Paragraph("<b>OT.</b>", ctr_st),
            Paragraph("<b>SAAT</b>", ctr_st),
            Paragraph("<b>SINAV / DERS</b>", ctr_st),
        ]]

    style_cmds = [
        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.grey),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#4a7ab5")),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
        ("FONTSIZE",      (0, 0), (-1, 0),  12),
        ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
    ]

    row_idx = 1
    _BEYAZ = colors.white
    _ACIK  = colors.HexColor("#f0f4ff")

    for tarih, satirlar in gunler:
        gun_str = _GUNLER.get(tarih.weekday(), "")

        if goster_subeler:
            # Gün başlık satırı (yalnızca şubeli versiyonda)
            tbl_data.append([
                Paragraph(f"<b>{gun_str}, {_tarih_tr(tarih)}</b>", cell_b),
                "", "", "",
            ])
            style_cmds += [
                ("SPAN",          (0, row_idx), (-1, row_idx)),
                ("BACKGROUND",    (0, row_idx), (-1, row_idx), colors.HexColor("#dbeafe")),
                ("TEXTCOLOR",     (0, row_idx), (-1, row_idx), colors.HexColor("#1d4ed8")),
                ("ALIGN",         (0, row_idx), (-1, row_idx), "LEFT"),
                ("TOPPADDING",    (0, row_idx), (-1, row_idx), 4),
                ("BOTTOMPADDING", (0, row_idx), (-1, row_idx), 4),
            ]
            row_idx += 1

        gun_row_start = row_idx
        tarih_p = Paragraph(
            f"<b>{tarih.day} {_TR_AYLAR[tarih.month - 1]}</b><br/>{gun_str}", ctr_st
        )

        for i, t in enumerate(satirlar):
            ders_k = str(t.ders) if t.ders else ""
            if t.sinav_turu:
                ders_k += f" ({t.sinav_turu})"
            if goster_subeler:
                tbl_data.append([
                    Paragraph(str(t.oturum), ctr_st),
                    Paragraph((t.saat or "")[:5], ctr_st),
                    Paragraph(ders_k, cell_st),
                    Paragraph(t.subeler or "", cell_st),
                ])
            else:
                tbl_data.append([
                    tarih_p if i == 0 else "",
                    Paragraph(str(t.oturum), ctr_st),
                    Paragraph((t.saat or "")[:5], ctr_st),
                    Paragraph(ders_k, cell_st),
                ])
            bg = _BEYAZ if i % 2 == 0 else _ACIK
            style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), bg))
            row_idx += 1

        # Aynı güne ait oturum sayısı > 1 ise tarih hücresini dikey birleştir
        if not goster_subeler and len(satirlar) > 1:
            style_cmds += [
                ("SPAN",   (0, gun_row_start), (0, row_idx - 1)),
                ("VALIGN", (0, gun_row_start), (0, row_idx - 1), "MIDDLE"),
                ("BACKGROUND", (0, gun_row_start), (0, row_idx - 1), colors.HexColor("#dbeafe")),
            ]

    tbl = Table(tbl_data, colWidths=col_ws, repeatRows=1)
    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)
    story.append(Spacer(1, 0.5 * cm))

    # ── İmza / Onay bölümü ──
    mudur = (okul.okul_muduru or "") if okul else ""
    yil_str = yil.split("-")[0] if "-" in (yil or "") else (yil or "")

    from okul.models import OkulYonetici
    mudur_yrd_obj = None
    if hazirlayan_user and getattr(hazirlayan_user, "is_authenticated", False):
        mudur_yrd_obj = (
            OkulYonetici.objects
            .filter(user=hazirlayan_user, unvan="mudur_yardimcisi", aktif=True)
            .select_related("personel", "user")
            .first()
        )
        if mudur_yrd_obj is None:
            full_name = hazirlayan_user.get_full_name().upper().strip()
            if full_name:
                for obj in OkulYonetici.objects.filter(unvan="mudur_yardimcisi", aktif=True).select_related("personel", "user"):
                    if obj.adi_soyadi.upper().strip() == full_name:
                        mudur_yrd_obj = obj
                        break
    if mudur_yrd_obj is None:
        mudur_yrd_obj = (
            OkulYonetici.objects
            .filter(unvan="mudur_yardimcisi", aktif=True)
            .select_related("personel", "user")
            .first()
        )
    mudur_yrd_adi = mudur_yrd_obj.adi_soyadi if mudur_yrd_obj else ""

    sig_data = [
        [
            Paragraph("Hazırlayan", sig_b),
            Paragraph("", sig_st),
            Paragraph(f"UYGUNDUR<br/>.../.../{ son_tarih.year}", sig_b),
        ],
        [
            Paragraph(f"<br/><br/><br/>{mudur_yrd_adi}<br/>Müdür Yardımcısı", sig_st),
            Paragraph("", sig_st),
            Paragraph(f"<br/><br/><br/>{mudur}<br/>Okul Müdürü", sig_st),
        ],
    ]
    sig_ws = [avail_w * 0.38, avail_w * 0.24, avail_w * 0.38]
    sig_tbl = Table(sig_data, colWidths=sig_ws)
    sig_tbl.setStyle(TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8.5),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TEXTCOLOR",     (2, 0), (2, 0),   colors.HexColor("#374151")),
    ]))
    story.append(sig_tbl)

    # ── Footer (her sayfada) ──
    uretim_dt = aktif_uretim.uretim_tarihi
    try:
        from django.utils import timezone as _tz
        uretim_dt = _tz.localtime(uretim_dt)
    except Exception:
        pass

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVuSans", 7)
        canvas.drawCentredString(
            doc.leftMargin + doc.width / 2, 0.4 * cm,
            f"Takvim #{aktif_uretim.pk}  ·  Üretim: {uretim_dt.strftime('%d.%m.%Y %H:%M')}"
            f"  ·  Sayfa {doc.page}",
        )
        canvas.restoreState()

    doc = BaseDocTemplate(
        out, pagesize=A4,
        leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.5 * cm, bottomMargin=1.8 * cm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="n")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=_footer)])
    doc.build(story)

# ---------------------------------------------------------------------------
# 4. MAZERET SINAV RAPORU PDF
# ---------------------------------------------------------------------------

_TR_AYLAR_MAZ = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                  "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]


def mazeret_rapor_pdf(oturumlar_veri: list, out, okul, mazeret) -> None:
    """
    oturumlar_veri: [{"oturum": MazeretOturum, "dersler": [...], "salon1": [...], "salon2": [...]}, ...]
    out: dosya yolu veya BytesIO
    Her sayfaya en fazla 36 öğrenci sığacak şekilde A4 PDF üretir.
    """
    ROWS_PER_PAGE = 36
    avail_w = 17.6 * cm

    h_okul  = _header_style(size=11, bold=True)
    h_sub   = _header_style(size=9,  bold=False)
    h_left  = _left_style(size=9)
    cell_st = ParagraphStyle("mc",  fontName="DejaVuSans",      fontSize=7.5, leading=9,  alignment=0)
    bold_st = ParagraphStyle("mb",  fontName="DejaVuSans-Bold", fontSize=7.5, leading=9,  alignment=0)
    ctr_st  = ParagraphStyle("mct", fontName="DejaVuSans",      fontSize=7.5, leading=9,  alignment=1)

    # #(0.7) OkulNo(1.8) AdSoyad(5.4) Şube(1.4) Ders(5.8) İmza(2.5) = 17.6 cm
    col_ws = [0.7*cm, 1.8*cm, 5.4*cm, 1.4*cm, 5.8*cm, 2.5*cm]

    tbl_style = TableStyle([
        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
        ("FONTNAME",      (0, 0), (-1,  0), "DejaVuSans-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("BACKGROUND",    (0, 0), (-1,  0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR",     (0, 0), (-1,  0), colors.white),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("ALIGN",         (2, 1), (2,  -1), "LEFT"),
        ("ALIGN",         (4, 1), (4,  -1), "LEFT"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
    ])

    story = []
    first_block = True  # ilk sayfa için PageBreak ekleme

    for ot_veri in oturumlar_veri:
        oturum  = ot_veri["oturum"]
        dersler = ot_veri["dersler"]
        tarih   = oturum.gun.tarih

        tarih_str = (
            f"{_GUNLER.get(tarih.weekday(), '')}  "
            f"{tarih.day} {_TR_AYLAR_MAZ[tarih.month-1]} {tarih.year}  "
            f"Saat: {oturum.saat_baslangic.strftime('%H:%M')} – "
            f"{oturum.saat_bitis.strftime('%H:%M')}"
        )
        ders_str = "  |  ".join(
            f"{od.ders.ders_adi}" + (f" ({od.sinav_turu})" if od.sinav_turu else "")
            for od in dersler
        )
        sinav_bilgi = str(mazeret.sinav)

        def _sayfa_basligi(salon_etiket):
            b = []
            b.append(Paragraph(okul.okul_adi if okul else "", h_okul))
            b.append(Spacer(1, 0.08*cm))
            b.append(Paragraph(
                f"{sinav_bilgi}  ·  Mazeret Sınavı — Salon ve Öğrenci Listesi", h_sub
            ))
            b.append(Spacer(1, 0.06*cm))
            b.append(Paragraph(
                f"{tarih_str}  |  Oturum {oturum.oturum_no}", ctr_st
            ))
            b.append(Spacer(1, 0.05*cm))
            b.append(Paragraph(ders_str, h_left))
            b.append(Spacer(1, 0.15*cm))
            b.append(Paragraph(f"<b>{salon_etiket}</b>", h_left))
            b.append(Spacer(1, 0.08*cm))
            return b

        for salon_no, kayitlar in (
            ("Mazeret 1", ot_veri.get("salon1", [])),
            ("Mazeret 2", ot_veri.get("salon2", [])),
        ):
            if not kayitlar:
                continue

            toplam = len(kayitlar)
            for chunk_start in range(0, toplam, ROWS_PER_PAGE):
                chunk = kayitlar[chunk_start:chunk_start + ROWS_PER_PAGE]
                chunk_end = chunk_start + len(chunk)
                is_last_chunk = chunk_end >= toplam

                if not first_block:
                    story.append(PageBreak())
                first_block = False

                if toplam > ROWS_PER_PAGE:
                    etiket = f"{salon_no}  ({chunk_start+1}–{chunk_end} / {toplam} öğrenci)"
                else:
                    etiket = f"{salon_no}  ({toplam} öğrenci)"

                story.extend(_sayfa_basligi(etiket))

                # ── Öğrenci tablosu ──
                data = [["#", "Okul No", "Ad Soyad", "Şube", "Ders", "İmza"]]
                for k in chunk:
                    ders_k = k.ders_adi or ""
                    if k.sinav_turu:
                        ders_k += f" ({k.sinav_turu})"
                    data.append([
                        str(k.sira_no),
                        str(k.okulno or ""),
                        Paragraph(str(k.adi_soyadi or ""), cell_st),
                        str(k.sinifsube or ""),
                        Paragraph(ders_k, cell_st),
                        "",
                    ])

                tbl = Table(data, colWidths=col_ws, repeatRows=1)
                tbl.setStyle(tbl_style)
                story.append(tbl)
                story.append(Spacer(1, 0.3*cm))

                # Gözetmen imza alanı sadece son chunk'ta
                if is_last_chunk:
                    goz_row = [[
                        Paragraph("Gözetmen Öğretmen", bold_st),
                        Paragraph("İmza / Mühür", ctr_st),
                    ]]
                    goz_t = Table(goz_row, colWidths=[avail_w * 0.6, avail_w * 0.4])
                    goz_t.setStyle(TableStyle([
                        ("TOPPADDING",    (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 20),
                        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
                        ("LINEBELOW",     (0, 0), (0,   0), 0.5, colors.black),
                        ("LINEBELOW",     (1, 0), (1,   0), 0.5, colors.black),
                        ("FONTNAME",      (0, 0), (-1, -1), "DejaVuSans"),
                        ("FONTSIZE",      (0, 0), (-1, -1), 8),
                    ]))
                    story.append(goz_t)

    okul_muduru = okul.okul_muduru if okul else ""

    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("DejaVuSans", 7.5)
        w = doc.leftMargin + doc.width
        canvas.drawRightString(
            w, 0.7 * cm, f"Okul Müdürü: {okul_muduru}"
        )
        canvas.drawString(
            doc.leftMargin, 0.7 * cm,
            f"Mazeret Plan #{mazeret.pk}  ·  "
            f"Onay: {mazeret.onay_tarihi.strftime('%d.%m.%Y %H:%M') if mazeret.onay_tarihi else '-'}"
        )
        canvas.restoreState()

    doc = BaseDocTemplate(
        out, pagesize=A4,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.2*cm,  bottomMargin=1.8*cm,
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
