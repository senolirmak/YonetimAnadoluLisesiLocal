# -*- coding: utf-8 -*-
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.fonts import addMapping
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_FONTS_DIR = Path(__file__).resolve().parents[2] / "static" / "fonts"

_SARI    = colors.Color(1.0, 1.0, 0.55)
_GRI     = colors.Color(0.88, 0.88, 0.88)
_MAVİ    = colors.Color(0.22, 0.46, 0.56)
_BEYAZ   = colors.white
_SİYAH   = colors.black


_FN      = "DejaVuSans"
_FN_BOLD = "DejaVuSans-Bold"


def _register():
    try:
        pdfmetrics.registerFont(TTFont(_FN,      str(_FONTS_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont(_FN_BOLD, str(_FONTS_DIR / "DejaVuSans-Bold.ttf")))
        registerFontFamily(
            _FN,
            normal=_FN, bold=_FN_BOLD,
            italic=_FN, boldItalic=_FN_BOLD,
        )
        # Normal aile
        addMapping(_FN,      0, 0, _FN)
        addMapping(_FN,      1, 0, _FN_BOLD)
        addMapping(_FN,      0, 1, _FN)
        addMapping(_FN,      1, 1, _FN_BOLD)
        # Bold font ismi de ps2tt tablosuna girmeli
        addMapping(_FN_BOLD, 0, 0, _FN)
        addMapping(_FN_BOLD, 1, 0, _FN_BOLD)
        addMapping(_FN_BOLD, 0, 1, _FN)
        addMapping(_FN_BOLD, 1, 1, _FN_BOLD)
    except Exception:
        pass


_register()


class VertikalYazi(Flowable):
    """Grup adını 90° döndürüp (aşağıdan yukarıya) hücrede ortalar."""

    def __init__(self, text, style):
        Flowable.__init__(self)
        self.text = text
        self.style = style

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        self.height = availHeight
        return availWidth, availHeight

    def draw(self):
        c = self.canv
        c.saveState()
        c.translate(self.width / 2, self.height / 2)
        c.rotate(90)  # aşağıdan yukarıya
        p = Paragraph(self.text, self.style)
        pw, ph = p.wrap(self.height, self.width)
        p.drawOn(c, -pw / 2, -ph / 2)
        c.restoreState()


def _tr_upper(s):
    """Türkçe büyük harf: i→İ, ı→I, diğerleri Python upper()."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def _fmt_saat(saat_str):
    """'2,4' → '(2)(4)',  '6' → '6'"""
    if not saat_str:
        return ""
    parts = str(saat_str).split(",")
    return parts[0] if len(parts) == 1 else "".join(f"({p})" for p in parts)


def _ps(size=8, bold=False, align=0, leading=None, color=_SİYAH):
    return ParagraphStyle(
        "_",
        fontName=_FN_BOLD if bold else _FN,
        fontSize=size,
        leading=leading or size * 1.25,
        alignment=align,
        textColor=color,
        wordWrap="CJK",
    )


def _p(text, **kw):
    return Paragraph(str(text), _ps(**kw))


# Sütun genişlikleri (toplam 180 mm)
_CW = [72*mm, 18*mm, 8*mm, 60*mm, 16*mm, 10*mm]


def secmeli_ders_pdf(buffer, ogrenci, gelecek_sinif,
                     ortak_dersler, secmeli_gruplar,
                     secilen_ders_ids, secilen_saatler,
                     okul_bilgi, egitim_yili,
                     toplam_saat=40):
    """
    Seçmeli ders form PDF'i üretir; buffer'a yazar.
    toplam_saat: Sınıf seviyesinin haftalık toplam ders saati (SinifSeviyeToplamSaat modelinden gelir).
    """
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.2*cm, rightMargin=1.2*cm,
        topMargin=1.0*cm,  bottomMargin=1.0*cm,
    )
    els = []
    ortak_list = list(ortak_dersler)
    ortak_toplam = sum(od.haftalik_saat for od in ortak_list)
    maks_saat = toplam_saat - ortak_toplam

    okul_adi = _tr_upper(okul_bilgi.okul_adi if okul_bilgi else "OKUL ADI")

    # Bir sonraki eğitim-öğretim yılını hesapla (ör. "2024-2025" → "2025-2026")
    def _sonraki_yil(ey):
        if not ey:
            return "----"
        parts = str(ey).split("-")
        try:
            if len(parts) == 2:
                return f"{int(parts[0])+1}-{int(parts[1])+1}"
            y = int(parts[0])
            return f"{y+1}-{y+2}"
        except ValueError:
            return str(ey)

    sonraki_yil_str = _sonraki_yil(egitim_yili)
    sinif_sube      = f"{ogrenci.sinif}/{ogrenci.sube}"

    # ── Başlık ──────────────────────────────────────────────────
    els.append(_p(f"{okul_adi} MÜDÜRLÜĞÜNE", bold=True, size=10, align=1))
    els.append(Spacer(1, 3*mm))

    # ── Giriş metni ─────────────────────────────────────────────
    els.append(_p(
        f"Okulunuz <b>{sinif_sube}</b> sınıfı <b>{ogrenci.okulno}</b> nolu "
        f"<b>{ogrenci.adi} {ogrenci.soyadi}</b> T.C. Kimlik No: ........................... "
        f"öğrencisi; <b>{sonraki_yil_str}</b> eğitim-öğretim yılında <b>{gelecek_sinif}. SINIFTA</b> "
        f"okumak istediği seçmeli dersler aşağıda belirlenmiş olup, tercih ettiğimiz derslerin "
        f"okulunuzun şartlarına uygun olması halinde okutulmasını istiyorum.",
        size=8, leading=11,
    ))
    els.append(Spacer(1, 2*mm))
    els.append(_p(f"Gereğini arz ederim.   ....../...../ {date.today().year}", size=8))
    els.append(Spacer(1, 3*mm))

    # ── İmza tablosu ────────────────────────────────────────────
    def _sig(title):
        return _p(f"<b>{title}</b><br/>Adı Soyadı<br/><br/>İmzası", size=8, align=1, leading=11)

    total_w = sum(_CW)
    sig_tbl = Table(
        [[_sig("Öğrencinin"), _sig("Velinin"), _sig("Sınıf Rehber Öğretmeni")]],
        colWidths=[total_w / 3] * 3,
    )
    sig_tbl.setStyle(TableStyle([
        ("BOX",           (0, 0), (0, 0), 0.5, _SİYAH),
        ("BOX",           (1, 0), (1, 0), 0.5, _SİYAH),
        ("BOX",           (2, 0), (2, 0), 0.5, _SİYAH),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    els.append(sig_tbl)
    els.append(Spacer(1, 2*mm))

    # ── Tablo başlığı ────────────────────────────────────────────
    els.append(_p(f"{gelecek_sinif}. SINIF HAFTALIK DERS ÇİZELGESİ", bold=True, size=9, align=1))
    els.append(Spacer(1, 1*mm))

    # ── Ana tablo verisi ─────────────────────────────────────────
    # Seçmeli satırları düz listeye çevir
    secmeli_rows = []   # [(group_name_or_empty, ders_adi, saat_str, is_selected)]
    group_spans  = []   # (data_start, data_end)  veri indeksleri

    for grup in secmeli_gruplar:
        dersler = list(grup.dersler.filter(aktif=True).order_by("sira"))
        if not dersler:
            continue
        g_start = len(secmeli_rows)
        for i, ders in enumerate(dersler):
            secmeli_rows.append((
                grup.adi if i == 0 else "",
                ders.ders_adi,
                _fmt_saat(ders.saat_secenekleri),
                ders.pk in secilen_ders_ids,
                ders.pk,
            ))
        group_spans.append((g_start, len(secmeli_rows) - 1))

    # Ortak liste + toplam (açıklama ayrı satır olarak eklenir)
    # tip: False=normal, True=toplam
    ortak_rows = [(od.ders_adi, str(od.haftalik_saat), False) for od in ortak_list]
    ortak_rows.append(("ORTAK DERSLERİN TOPLAMI", str(ortak_toplam), True))

    # Açıklama metni — tablo altında tam genişlikte tek birleşik hücre
    if gelecek_sinif in (9, 10):
        _zorunlu_ac = (
            '3. Öğrencilerin 9 ve 10. sınıf seviyelerinde "İnsan, Toplum ve Bilim", '
            '"Din, Ahlak ve Değer" ile "Kültür, Sanat ve Spor" seçmeli ders gruplarından '
            'her bir gruptan en az birer ders seçmeleri zorunludur.'
        )
    else:
        _zorunlu_ac = (
            '3. Öğrencilerin 11 ve 12. sınıf seviyelerinde "İnsan, Toplum ve Bilim", '
            '"Din, Ahlak ve Değer" ile "Kültür, Sanat ve Spor" seçmeli ders gruplarının '
            'en az ikisinden birer ders seçmeleri zorunludur.'
        )

    acik_para = _p(
        f"<b>AÇIKLAMALAR</b><br/>"
        f"1. Sol taraftaki tabloda {gelecek_sinif}. SINIFTA alınması gereken zorunlu ORTAK DERSLER vardır.<br/>"
        f"2. Toplam {maks_saat} SAATİ GEÇMEMEK ŞARTI İLE seçmeli derslerden seçilebilirsiniz.<br/>"
        f"{_zorunlu_ac}<br/>"
        f"4. Spor eğitimi dersinde bireysel sporlardan halter, yüzme, güreş, kayak, tenis, masa tenisi, "
        f"badminton, oryantiring, eskrim, bisiklet ve okçuluk ile takım sporlarından basketbol, voleybol, "
        f"futbol ve hentbol eğitimi verilir. Öğrenciler spor eğitimi dersinde bireysel veya takım "
        f"sporlarının alt branşlarından birini seçer.<br/>"
        f"5. Sanat eğitimi müzik, görsel sanatlar, sahne sanatları, geleneksel Türk sanatları ve müze "
        f"eğitimi alan ve alt alanlarından oluşur. Öğrenciler müzik, görsel sanatlar, sahne sanatları, "
        f"geleneksel Türk sanatlarının alt alanlarından birini ya da müze eğitimini seçerler.",
        size=6, leading=8.5,
    )

    n_parallel = max(len(ortak_rows), len(secmeli_rows))
    n_data     = n_parallel + 1          # +1: açıklama satırı
    acik_row   = n_parallel + 2          # table_data indeksi (2 başlık + n_parallel)

    # Tablo satırları inşa et
    table_data = []

    # Satır 0 — ana başlık
    table_data.append([
        _p(f"ORTAK DERSLER ({ortak_toplam} SAAT)", bold=True, size=7, align=1),
        "", "",
        _p(f"SEÇMELİ DERSLER ({maks_saat} SAAT)", bold=True, size=7, align=1),
        "", "",
    ])
    # Satır 1 — sütun başlıkları
    table_data.append([
        _p("DERSLER", bold=True, size=7),
        _p("DERS\nSAATİ", bold=True, size=6, align=1),
        "",
        _p("DERSLER", bold=True, size=7),
        _p("DERS\nSAATİ", bold=True, size=6, align=1),
        "",
    ])

    secili_satir_idxleri = []
    toplam_satir_idx     = None

    for i in range(n_parallel):
        row = []

        # Sol (ortak)
        if i < len(ortak_rows):
            adi, saat, tip = ortak_rows[i]
            is_total = (tip is True)
            row.append(_p(adi, bold=is_total, size=7, leading=5.5))
            row.append(_p(saat, bold=is_total, size=7, leading=5.5, align=1))
            if is_total:
                toplam_satir_idx = i + 2
        else:
            row += ["", ""]

        # Orta (grup adı) — dikey metin, yalnızca grubun ilk satırına yerleştir
        if i < len(secmeli_rows):
            gn = secmeli_rows[i][0]
            row.append(VertikalYazi(gn, _ps(bold=True, size=5.5, align=1)) if gn else "")
        else:
            row.append("")

        # Sağ (seçmeli)
        if i < len(secmeli_rows):
            _, ders_adi, saat_str, is_sel, ders_pk = secmeli_rows[i]
            row.append(_p(ders_adi, size=7, leading=5.5))
            row.append(_p(saat_str, size=7, leading=5.5, align=1))
            if is_sel:
                secilen_saat = secilen_saatler.get(ders_pk, "")
                row.append(_p(f"{secilen_saat} ✓", bold=True, size=7, align=1))
                secili_satir_idxleri.append(i + 2)
            else:
                row.append(_p("(  )", size=7, align=1))
        else:
            row += ["", "", ""]

        table_data.append(row)

    # Açıklama satırı — tablo genişliğinde tek hücre
    table_data.append([acik_para, "", "", "", "", ""])

    # İçerik sınırları
    _o_son = len(ortak_rows) + 1    # son ortak tablo satırı (TOPLAM dahil)
    _s_son = len(secmeli_rows) + 1  # son seçmeli tablo satırı

    # ── Tablo stili ──────────────────────────────────────────────
    style_cmds = [
        ("FONTNAME",      (0, 0), (-1, -1), _FN),
        ("FONTSIZE",      (0, 0), (-1, -1), 7),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 2),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 2),
        # Başlık satırı (satır 0) rengi
        ("BACKGROUND",    (0, 0), (1, 0), _GRI),
        ("BACKGROUND",    (3, 0), (5, 0), _GRI),
        ("BACKGROUND",    (2, 0), (2, 0), _GRI),
        # Alt başlık satırı (satır 1)
        ("BACKGROUND",    (0, 1), (1, 1), _GRI),
        ("BACKGROUND",    (3, 1), (5, 1), _GRI),
        ("BACKGROUND",    (2, 1), (2, 1), _GRI),
        # SPAN: ortak başlık
        ("SPAN",          (0, 0), (1, 0)),
        # SPAN: seçmeli başlık
        ("SPAN",          (3, 0), (5, 0)),
        # Kenarlık: yalnızca içerik olan bölgeler
        ("BOX",           (0, 0), (5, 1),    0.3, _SİYAH),   # başlık satırları
        ("INNERGRID",     (0, 0), (5, 1),    0.3, _SİYAH),
        ("BOX",           (0, 2), (1, _o_son), 0.3, _SİYAH), # ortak içerik
        ("INNERGRID",     (0, 2), (1, _o_son), 0.3, _SİYAH),
        ("BOX",           (2, 2), (5, _s_son), 0.3, _SİYAH), # seçmeli içerik
        ("INNERGRID",     (2, 2), (5, _s_son), 0.3, _SİYAH),
    ]

    # Grup adı SPAN'ları
    for g_start, g_end in group_spans:
        tr_s = g_start + 2
        tr_e = g_end + 2
        if tr_s < tr_e:
            style_cmds.append(("SPAN",       (2, tr_s), (2, tr_e)))
        style_cmds.append(    ("VALIGN",     (2, tr_s), (2, tr_e), "MIDDLE"))
        style_cmds.append(    ("BACKGROUND", (2, tr_s), (2, tr_e), _GRI))

    # Seçili satırlar sarı
    for ri in secili_satir_idxleri:
        style_cmds.append(("BACKGROUND", (3, ri), (5, ri), _SARI))

    # Toplam satırı
    if toplam_satir_idx is not None:
        style_cmds.append(("BACKGROUND", (0, toplam_satir_idx), (1, toplam_satir_idx), _GRI))
        style_cmds.append(("FONTNAME",   (0, toplam_satir_idx), (1, toplam_satir_idx), _FN_BOLD))

    # Açıklama — tam genişlik birleşik hücre, kenarlıksız
    style_cmds.append(("SPAN",       (0, acik_row), (5, acik_row)))
    style_cmds.append(("VALIGN",     (0, acik_row), (5, acik_row), "TOP"))
    style_cmds.append(("TOPPADDING", (0, acik_row), (5, acik_row), 4))
    style_cmds.append(("BOX",        (0, acik_row), (5, acik_row), 0, _BEYAZ))
    style_cmds.append(("INNERGRID",  (0, acik_row), (5, acik_row), 0, _BEYAZ))
    style_cmds.append(("LINEABOVE",  (0, acik_row), (5, acik_row), 0, _BEYAZ))
    style_cmds.append(("LINEBELOW",  (0, acik_row), (5, acik_row), 0, _BEYAZ))
    style_cmds.append(("LINEBEFORE", (0, acik_row), (0, acik_row), 0, _BEYAZ))
    style_cmds.append(("LINEAFTER",  (5, acik_row), (5, acik_row), 0, _BEYAZ))

    _ROW_H = 12  # veri satır yüksekliği (pt) — 2 satır × 5.5pt leading + 1pt padding = 12pt
    _HDR_H = 14  # başlık satır yüksekliği (pt)
    row_heights = [_HDR_H, _HDR_H] + [_ROW_H] * n_parallel + [None]  # açıklama: otomatik
    tbl = Table(table_data, colWidths=_CW, rowHeights=row_heights)
    tbl.setStyle(TableStyle(style_cmds))
    els.append(tbl)
    els.append(Spacer(1, 2*mm))

    # ── Dipnot metni ────────────────────────────────────────────
    els.append(_p(
        "Veli, Sınıf Rehber Öğretmeni ve sorumlu Rehber Öğretmenin işbirliği ile öğrencilere "
        "derslerinin seçmeleri sağlanmıştır.",
        size=7, leading=10,
    ))

    doc.build(els)
