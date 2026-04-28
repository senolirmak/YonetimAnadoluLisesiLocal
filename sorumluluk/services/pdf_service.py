import io
from collections import defaultdict
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether, PageBreak, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.lib.fonts import addMapping

from django.conf import settings

from sorumluluk.models import SorumluOturmaPlani, SorumluKomisyonUyesi, SorumluGozetmen, SorumluTakvim, SALON_CHOICES

# --- Times New Roman — <b> etiketleri de normal ağırlıkta çizilir ---
_FONTS_DIR = settings.BASE_DIR / "static" / "fonts"
try:
    pdfmetrics.registerFont(TTFont("TNR",      str(_FONTS_DIR / "Times_New_Roman.ttf")))
    pdfmetrics.registerFont(TTFont("TNR-Bold", str(_FONTS_DIR / "Times_New_Roman_Bold.ttf")))
    registerFontFamily("TNR", normal="TNR", bold="TNR-Bold")
    addMapping("TNR", 0, 0, "TNR")
    addMapping("TNR", 1, 0, "TNR")  # bold → regular (mürekkep tasarrufu)
    _FONT = "TNR"
except Exception:
    _FONT = "Times-Roman"

_SALON_LABEL = dict(SALON_CHOICES)
_AYLAR = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
          "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]

_GRAY      = colors.HexColor("#555555")
_LIGHT     = colors.HexColor("#dddddd")
_BLACK     = colors.black


_TR_UPPER_TABLE = str.maketrans("iıüöşçğ", "İIÜÖŞÇĞ")

def _tr_upper(s: str) -> str:
    """Python'un varsayılan .upper() metodu 'i'→'I' dönüştürür; Türkçe için 'i'→'İ' gerekir."""
    return s.translate(_TR_UPPER_TABLE).upper()


def _mudur_onay_blogu(okul):
    """Müdür onay bloğunu KeepTogether olarak döndürür; müdür adı yoksa None."""
    mudur_adi = (okul.okul_muduru if okul and okul.okul_muduru else "").strip()
    if not mudur_adi:
        return None
    s = ParagraphStyle('MudurOnay', fontName=_FONT, fontSize=10, alignment=1, leading=18)
    return KeepTogether([
        Spacer(1, 36),
        Paragraph("UYGUNDUR", s),
        Spacer(1, 6),
        Paragraph("... / ... / 2026", s),
        Spacer(1, 6),
        Paragraph(_tr_upper(mudur_adi), s),
        Paragraph("Okul Müdürü", s),
    ])


def _tr_tarih(d):
    return f"{d.day} {_AYLAR[d.month - 1]} {d.year}"


# ---------------------------------------------------------------------------
# Öğrenci Sınav Takvimi PDF
# ---------------------------------------------------------------------------

def ogrenci_takvim_pdf_uret(buf, sinav, okul):
    """Her öğrenci için salon ve sıra numaralarını içeren sınav giriş belgesi üretir."""
    W, H = A4
    LR_MARGIN  = 30
    TOP_MARGIN = 65
    BOT_MARGIN = 28

    okul_adi     = _tr_upper(okul.okul_adi if okul and okul.okul_adi else "")
    sinav_baslik = f"{sinav.sinav_adi}  —  Öğrenci Sınav Takvimi"

    def _on_page(canvas, doc):
        canvas.saveState()
        y = H - 18
        if okul_adi:
            canvas.setFont(_FONT, 11)
            canvas.setFillColor(_BLACK)
            canvas.drawCentredString(W / 2, y, okul_adi)
            y -= 15
        canvas.setFont(_FONT, 10)
        canvas.setFillColor(_BLACK)
        canvas.drawCentredString(W / 2, y, sinav_baslik)
        y -= 8
        canvas.setStrokeColor(_LIGHT)
        canvas.setLineWidth(0.5)
        canvas.line(LR_MARGIN, y, W - LR_MARGIN, y)
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(_GRAY)
        canvas.drawRightString(W - LR_MARGIN, 10, f"Sayfa {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=LR_MARGIN, rightMargin=LR_MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOT_MARGIN,
    )

    info_style = ParagraphStyle(
        'OgrenciInfo', fontName=_FONT, fontSize=9, leading=13,
        spaceBefore=2, spaceAfter=5, borderPadding=5,
        borderColor=_LIGHT, borderWidth=0.5,
    )
    tbl_style = TableStyle([
        ('FONTNAME',      (0, 0), (-1, -1), _FONT),
        ('FONTSIZE',      (0, 0), (-1, -1), 9),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('ALIGN',         (2, 1), (2, -1),  'LEFT'),
        ('LINEBELOW',     (0, 0), (-1, 0),  0.5, _GRAY),
        ('GRID',          (0, 0), (-1, -1), 0.3, _LIGHT),
        ('BOTTOMPADDING', (0, 0), (-1, 0),  4),
        ('TOPPADDING',    (0, 0), (-1, 0),  4),
    ])

    planlar = (
        SorumluOturmaPlani.objects
        .filter(sinav=sinav)
        .order_by("sinifsube", "okulno", "tarih", "saat_baslangic")
    )

    student_map = defaultdict(list)
    for p in planlar:
        student_map[(p.sinifsube, p.okulno, p.adi_soyadi)].append(p)

    elements = []
    for (sinifsube, okulno, ad), kayitlar in student_map.items():
        card = []

        card.append(Paragraph(
            f"Sınıf/Şube: {sinifsube}   "
            f"Okul No: {okulno}   "
            f"Öğrenci: {ad}",
            info_style,
        ))

        data = [["Tarih", "Saat", "Ders", "Salon", "Sıra"]]
        for k in kayitlar:
            data.append([
                k.tarih.strftime("%d.%m.%Y"),
                k.saat_baslangic.strftime("%H:%M"),
                k.ders_adi or "",
                _SALON_LABEL.get(k.salon, k.salon) or k.salon,
                str(k.sira_no),
            ])
        card.append(Table(data, colWidths=[70, 45, 255, 90, 35], style=tbl_style))
        card.append(Spacer(1, 6))
        card.append(HRFlowable(width="100%", thickness=0.4, color=_LIGHT, spaceAfter=6))

        elements.append(KeepTogether(card))

    mudur = _mudur_onay_blogu(okul)
    doc.build([KeepTogether(elements + ([mudur] if mudur else []))],
              onFirstPage=_on_page, onLaterPages=_on_page)


# ---------------------------------------------------------------------------
# Okul Geneli Sınav Takvimi İlan PDF'i
# ---------------------------------------------------------------------------

def genel_takvim_pdf_uret(buf, sinav, okul, oturumlar_veri):
    """Okul geneli için oturum oturum, hangi salonda hangi derslerin sınavının olduğunu listeler."""
    W, _ = A4
    LR = 1.2 * cm
    TB = 0.5 * cm
    avail_w = W - 2 * LR

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=LR, rightMargin=LR,
        topMargin=TB, bottomMargin=TB,
    )

    s_okul  = ParagraphStyle('GTOkul',  fontName=_FONT, fontSize=13, alignment=1, spaceAfter=2, leading=16)
    s_donem = ParagraphStyle('GTDonem', fontName=_FONT, fontSize=9,  alignment=1, spaceAfter=2, textColor=_GRAY)
    s_sinav = ParagraphStyle('GTSinav', fontName=_FONT, fontSize=11, alignment=1, spaceAfter=5)
    s_oturum_p = ParagraphStyle('GTOtP', fontName=_FONT, fontSize=9, textColor=colors.white, leading=12)
    s_ders  = ParagraphStyle('GTDers',  fontName=_FONT, fontSize=9,  leading=13, spaceAfter=2, leftIndent=6)
    s_none  = ParagraphStyle('GTNone',  fontName=_FONT, fontSize=8,  leading=12, spaceAfter=2,
                              leftIndent=6, textColor=_GRAY)

    okul_adi    = _tr_upper(okul.okul_adi if okul and okul.okul_adi else "")
    donem_str   = sinav.get_donem_turu_display()  # type: ignore[attr-defined]
    egitim_yili = str(sinav.egitim_yili) if sinav.egitim_yili else ""

    elements = []

    if okul_adi:
        elements.append(Paragraph(okul_adi, s_okul))
    donem_bilgi = "  ·  ".join(filter(None, [egitim_yili, donem_str]))
    if donem_bilgi:
        elements.append(Paragraph(donem_bilgi, s_donem))
    elements.append(Paragraph(f"{sinav.sinav_adi}  —  Sorumluluk Sınavı Takvimi", s_sinav))
    elements.append(HRFlowable(width="100%", thickness=1, color=_GRAY, spaceAfter=5))

    _GUNLER = {0:"Pazartesi",1:"Salı",2:"Çarşamba",3:"Perşembe",4:"Cuma",5:"Cumartesi",6:"Pazar"}
    salon_keys = [(f"salon{i+1}", sc) for i, (sc, _) in enumerate(SALON_CHOICES)]

    for ot in oturumlar_veri:
        gun       = _GUNLER.get(ot["tarih"].weekday(), "")
        tarih_str = f"{gun}, {_tr_tarih(ot['tarih'])}"
        saat_str  = f"{ot['saat_baslangic'].strftime('%H:%M')} – {ot['saat_bitis'].strftime('%H:%M')}"
        baslik    = f"{tarih_str}  |  Oturum {ot['oturum_no']}  |  {saat_str}"

        hdr_tbl = Table(
            [[Paragraph(baslik, s_oturum_p)]],
            colWidths=[avail_w],
        )
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#1e3a5f")),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
        ]))

        block = [Spacer(1, 5), hdr_tbl]

        salon_found = False
        for key, slot_key in salon_keys:
            kayitlar = ot.get(key, [])
            if not kayitlar:
                continue
            salon_found = True
            dersler     = sorted({k.ders_adi for k in kayitlar})
            salon_label = _SALON_LABEL.get(slot_key, slot_key)

            etiket_tbl = Table(
                [[
                    Paragraph(salon_label, ParagraphStyle('GTEt', fontName=_FONT, fontSize=8,
                                                          textColor=colors.HexColor("#1d4ed8"))),
                    Paragraph("  ·  ".join(dersler), s_ders),
                ]],
                colWidths=[60, avail_w - 60],
            )
            etiket_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0, 0), (0, 0), colors.HexColor("#dbeafe")),
                ("TOPPADDING",    (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING",   (0, 0), (-1, -1), 6),
                ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
                ("BOX",           (0, 0), (-1, -1), 0.3, _LIGHT),
                ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ]))
            block.append(etiket_tbl)

        if not salon_found:
            block.append(Paragraph("Bu oturumda sınav bulunmamaktadır.", s_none))

        elements.append(KeepTogether(block))

    mudur = _mudur_onay_blogu(okul)
    doc.build([KeepTogether(elements + ([mudur] if mudur else []))])


# ---------------------------------------------------------------------------
# Salon Yoklama / İmza Listesi PDF  (her oturum × salon → ayrı sayfa)
# ---------------------------------------------------------------------------

def rapor_pdf_uret(buf, sinav, okul, oturumlar_veri, imza_sirkusu=False):
    """Her oturum-salon için ayrı sayfa içeren oturma planı veya imza listesi PDF'i üretir."""
    W, _ = A4
    LR_MARGIN = 1.5 * cm
    TB_MARGIN = 1.0 * cm

    COL_WIDTHS = [25, 55, 140, 210, 80] if imza_sirkusu else [25, 65, 170, 250]

    okul_adi  = _tr_upper(okul.okul_adi if okul and okul.okul_adi else "")
    sinav_str = sinav.sinav_adi
    if sinav.egitim_yili:
        sinav_str += f"  ·  {sinav.egitim_yili}"
    sinav_str += f"  ·  {sinav.get_donem_turu_display()}"  # type: ignore[attr-defined]

    _TBL_HDR_H = 16

    def _style(name, **kw):
        s = ParagraphStyle(name, fontName=_FONT, fontSize=9, leading=13)
        for k, v in kw.items():
            setattr(s, k, v)
        return s

    s_okul   = _style("okul",   fontSize=11, alignment=1, spaceAfter=2)
    s_baslik = _style("baslik", fontSize=10, alignment=1, spaceAfter=4)
    s_sinav  = _style("sinav",  fontSize=8,  alignment=1, spaceAfter=4, textColor=_GRAY)
    s_info   = _style("info",   fontSize=8,  leading=12)
    s_ders   = _style("ders",   fontSize=8,  leading=11)
    s_imzaln = _style("imzaln", fontSize=8,  leading=14)

    def _tablo_stili(n_rows, pad=None):
        base_style = [
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("ALIGN",         (0, 1), (0, -1),  "CENTER"),
            ("ALIGN",         (1, 1), (1, -1),  "CENTER"),
            ("BOTTOMPADDING", (0, 0), (-1, 0),  4),
            ("TOPPADDING",    (0, 0), (-1, 0),  4),
            ("LINEBELOW",     (0, 0), (-1, 0),  0.5, _GRAY),
            ("GRID",          (0, 0), (-1, -1), 0.3, _LIGHT),
        ]
        if pad is None:
            calc_pad = ((640.0 / max(1, n_rows)) - 10) / 2.0
            pad = max(1.0, min(3.5, calc_pad))
        base_style.extend([
            ("TOPPADDING",    (0, 1), (-1, -1), pad),
            ("BOTTOMPADDING", (0, 1), (-1, -1), pad),
        ])
        return TableStyle(base_style)

    def _sayfa_basligi(elements):
        if okul_adi:
            elements.append(Paragraph(okul_adi, s_okul))
        baslik_text = "SORUMLULUK SINAVI — ÖĞRENCİ İMZA LİSTESİ" if imza_sirkusu \
                      else "SORUMLULUK SINAVI — SALON OTURMA PLANI"
        elements.append(Paragraph(baslik_text, s_baslik))
        elements.append(Paragraph(sinav_str, s_sinav))
        elements.append(HRFlowable(width="100%", thickness=0.5, color=_GRAY, spaceAfter=5))

    def _info_kutusu(elements, ot, salon_goster, toplam, sayfa_no, toplam_sayfa):
        dersler_str = ",  ".join(ot["dersler"])
        sayfa_bilgi = f"  ({sayfa_no}/{toplam_sayfa})" if toplam_sayfa > 1 else ""
        info_data = [[
            Paragraph(f"Tarih: {_tr_tarih(ot['tarih'])}", s_info),
            Paragraph(f"Oturum: {ot['oturum_no']}", s_info),
            Paragraph(f"Saat: {ot['saat_baslangic'].strftime('%H:%M')} – {ot['saat_bitis'].strftime('%H:%M')}", s_info),
            Paragraph(f"Salon: {salon_goster}{sayfa_bilgi}  ({toplam} öğrenci)", s_info),
        ]]
        info_tbl = Table(info_data, colWidths=[130, 70, 110, 200])
        info_tbl.setStyle(TableStyle([
            ("BOX",           (0, 0), (-1, -1), 0.4, _LIGHT),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ]))
        elements.append(info_tbl)
        elements.append(Spacer(1, 3))
        elements.append(Paragraph(f"Ders(ler): {dersler_str}", s_ders))
        elements.append(Spacer(1, 4))

    def _gozetmen_satiri(elements):
        elements.append(Spacer(1, 8))
        elements.append(HRFlowable(width="100%", thickness=0.4, color=_LIGHT))
        elements.append(Spacer(1, 4))
        imza_tbl = Table([[
            Paragraph("Gözetmen:  ___________________________________", s_imzaln),
            Paragraph("İmza:  ____________________", s_imzaln),
        ]], colWidths=[340, 170])
        imza_tbl.setStyle(TableStyle([
            ("TOPPADDING",    (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("LEFTPADDING",   (0, 0), (-1, -1), 0),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
        ]))
        elements.append(imza_tbl)

    _state = {"page": 0}

    def on_page(canvas, doc):
        _state["page"] += 1
        canvas.saveState()
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(_GRAY)
        canvas.drawRightString(W - LR_MARGIN, TB_MARGIN * 0.6, f"Sayfa {_state['page']}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=LR_MARGIN, rightMargin=LR_MARGIN,
        topMargin=TB_MARGIN,  bottomMargin=TB_MARGIN,
    )

    salon_keys = [(f"salon{i+1}", sc) for i, (sc, _) in enumerate(SALON_CHOICES)]
    elements = []
    first_page = True

    for ot in oturumlar_veri:
        for key, slot_key in salon_keys:
            kayitlar = ot.get(key, [])
            if not kayitlar:
                continue

            salon_goster = _SALON_LABEL.get(slot_key, slot_key)
            toplam       = len(kayitlar)

            if not first_page:
                elements.append(PageBreak())
            first_page = False

            _sayfa_basligi(elements)
            _info_kutusu(elements, ot, salon_goster, toplam, 1, 1)

            header_row = ["#", "Okul No", "Adı Soyadı", "Ders"]
            if imza_sirkusu:
                header_row.append("İmza")
            data = [header_row]

            for k in kayitlar:
                ad  = k.adi_soyadi[:27] + "..." if len(k.adi_soyadi) > 30 else k.adi_soyadi
                row = [str(k.sira_no), k.okulno, ad, k.ders_adi or ""]
                if imza_sirkusu:
                    row.append("")
                data.append(row)

            if imza_sirkusu:
                n_data      = len(data) - 1
                row_h       = 21.0
                pad         = max(0.0, (row_h - 10.0) / 2.0)
                row_heights = [float(_TBL_HDR_H)] + [row_h] * n_data
                tbl = Table(data, colWidths=COL_WIDTHS, rowHeights=row_heights)
            else:
                tbl = Table(data, colWidths=COL_WIDTHS, repeatRows=1)
                pad = None

            tbl.setStyle(_tablo_stili(len(data), pad=pad))
            elements.append(tbl)

            _gozetmen_satiri(elements)

    mudur = _mudur_onay_blogu(okul)
    if mudur:
        elements.append(mudur)
    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)


# ---------------------------------------------------------------------------
# Komisyon & Gözetmen Görevlendirme PDF
# ---------------------------------------------------------------------------

def gorevlendirme_pdf_uret(buf, sinav, okul):
    """Her oturum için komisyon üyeleri ve gözetmen atamalarını listeleyen PDF üretir."""
    from itertools import groupby

    W, _ = A4
    LR = 1.5 * cm
    TB = 1.0 * cm
    avail_w = W - 2 * LR

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=LR, rightMargin=LR,
        topMargin=TB, bottomMargin=TB,
    )

    s_okul    = ParagraphStyle('GROkul',    fontName=_FONT, fontSize=12, alignment=1, spaceAfter=2, leading=16)
    s_sinav   = ParagraphStyle('GRSinav',   fontName=_FONT, fontSize=9,  alignment=1, spaceAfter=2, textColor=_GRAY)
    s_baslik  = ParagraphStyle('GRBaslik',  fontName=_FONT, fontSize=10, alignment=1, spaceAfter=5, leading=14)
    s_oturum  = ParagraphStyle('GROturum',  fontName=_FONT, fontSize=9,  textColor=colors.white, leading=12)
    s_bolum   = ParagraphStyle('GRBolum',   fontName=_FONT, fontSize=8,  leading=11)
    s_hucre   = ParagraphStyle('GRHucre',   fontName=_FONT, fontSize=8.5, leading=12)
    s_bos     = ParagraphStyle('GRBos',     fontName=_FONT, fontSize=8,  textColor=_GRAY, leading=11)

    okul_adi    = _tr_upper(okul.okul_adi if okul and okul.okul_adi else "")
    donem_str   = sinav.get_donem_turu_display()   # type: ignore[attr-defined]
    egitim_yili = str(sinav.egitim_yili) if sinav.egitim_yili else ""
    _GUNLER = {0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
               4: "Cuma", 5: "Cumartesi", 6: "Pazar"}

    # --- Veri ---
    takvim_saatler = {
        (t.tarih, t.oturum_no): (t.saat_baslangic, t.saat_bitis)
        for t in SorumluTakvim.objects.filter(sinav=sinav).order_by("tarih", "oturum_no")
    }
    kom_by_oturum: dict = defaultdict(list)
    for k in SorumluKomisyonUyesi.objects.filter(sinav=sinav).select_related("uye1", "uye2").order_by("tarih", "oturum_no", "ders_adi"):
        kom_by_oturum[(k.tarih, k.oturum_no)].append(k)

    goz_by_oturum: dict = defaultdict(list)
    for g in SorumluGozetmen.objects.filter(sinav=sinav).select_related("gozetmen").order_by("tarih", "oturum_no", "salon"):
        goz_by_oturum[(g.tarih, g.oturum_no)].append(g)

    oturum_keys = sorted(set(list(kom_by_oturum.keys()) + list(goz_by_oturum.keys())))

    # --- Tablo stilleri ---
    def _hdr_style(bg):
        return TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), bg),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("FONTSIZE",      (0, 1), (-1, -1), 8.5),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING",   (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
            ("GRID",          (0, 0), (-1, -1), 0.3, _LIGHT),
            ("LINEBELOW",     (0, 0), (-1, 0),  0.6, _GRAY),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ])

    _KOM_BG  = colors.HexColor("#fef9ec")
    _GOZ_BG  = colors.HexColor("#f0fdf4")
    _HDR_KOM = colors.HexColor("#fde68a")
    _HDR_GOZ = colors.HexColor("#a7f3d0")

    # --- Elementler ---
    elements = []

    if okul_adi:
        elements.append(Paragraph(okul_adi, s_okul))
    donem_bilgi = "  ·  ".join(filter(None, [egitim_yili, donem_str]))
    if donem_bilgi:
        elements.append(Paragraph(donem_bilgi, s_sinav))
    elements.append(Paragraph(f"{sinav.sinav_adi}  —  Komisyon & Gözetmen Görevlendirme Çizelgesi", s_baslik))
    elements.append(HRFlowable(width="100%", thickness=1, color=_GRAY, spaceAfter=6))

    for (tarih, oturum_no) in oturum_keys:
        saatler = takvim_saatler.get((tarih, oturum_no))
        if saatler:
            saat_str = f"{saatler[0].strftime('%H:%M')} – {saatler[1].strftime('%H:%M')}"
        else:
            saat_str = ""
        gun       = _GUNLER.get(tarih.weekday(), "")
        tarih_str = f"{gun}, {_tr_tarih(tarih)}"
        baslik    = f"{tarih_str}  |  Oturum {oturum_no}  |  {saat_str}"

        hdr_tbl = Table([[Paragraph(baslik, s_oturum)]], colWidths=[avail_w])
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#1e3a5f")),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 8),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
        ]))

        block = [Spacer(1, 6), hdr_tbl]

        # Komisyon tablosu
        komisyonlar = kom_by_oturum.get((tarih, oturum_no), [])
        if komisyonlar:
            kom_data = [
                [
                    Paragraph("Ders", s_bolum),
                    Paragraph("1. Komisyon Üyesi", s_bolum),
                    Paragraph("2. Komisyon Üyesi", s_bolum),
                ]
            ]
            for k in komisyonlar:
                uye1_str = k.uye1.adi_soyadi if k.uye1 else "—"
                uye2_str = k.uye2.adi_soyadi if k.uye2 else "—"
                kom_data.append([
                    Paragraph(k.ders_adi, s_hucre),
                    Paragraph(uye1_str,   s_hucre),
                    Paragraph(uye2_str,   s_hucre),
                ])
            kom_tbl = Table(kom_data, colWidths=[avail_w * 0.38, avail_w * 0.31, avail_w * 0.31])
            style = _hdr_style(_HDR_KOM)
            for i in range(1, len(kom_data)):
                style.add("BACKGROUND", (0, i), (-1, i), _KOM_BG)
            kom_tbl.setStyle(style)
            block.append(kom_tbl)

        # Gözetmen tablosu
        gozetmenler = goz_by_oturum.get((tarih, oturum_no), [])
        if gozetmenler:
            goz_data = [
                [
                    Paragraph("Salon", s_bolum),
                    Paragraph("Gözetmen", s_bolum),
                ]
            ]
            for g in gozetmenler:
                salon_label = _SALON_LABEL.get(g.salon, g.salon)
                goz_str     = g.gozetmen.adi_soyadi if g.gozetmen else "—"
                goz_data.append([
                    Paragraph(salon_label, s_hucre),
                    Paragraph(goz_str,     s_hucre),
                ])
            goz_tbl = Table(goz_data, colWidths=[avail_w * 0.3, avail_w * 0.7])
            style = _hdr_style(_HDR_GOZ)
            for i in range(1, len(goz_data)):
                style.add("BACKGROUND", (0, i), (-1, i), _GOZ_BG)
            goz_tbl.setStyle(style)
            block.append(goz_tbl)

        if not komisyonlar and not gozetmenler:
            block.append(Paragraph("Bu oturumda görevlendirme bulunmamaktadır.", s_bos))

        elements.append(KeepTogether(block))

    mudur = _mudur_onay_blogu(okul)
    if mudur:
        elements.append(mudur)

    _state = {"page": 0}

    def on_page(canvas, doc):
        _state["page"] += 1
        canvas.saveState()
        canvas.setFont(_FONT, 7.5)
        canvas.setFillColor(_GRAY)
        canvas.drawRightString(W - LR, TB * 0.6, f"Sayfa {_state['page']}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=on_page, onLaterPages=on_page)
