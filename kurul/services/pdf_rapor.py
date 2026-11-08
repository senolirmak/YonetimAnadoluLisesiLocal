"""Kurul ve komisyon görevlendirme listesi PDF'i (okulların yıl başında yayımladığı çizelge)."""

import io

from django.utils.html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from kurul.models import KurulTuru
from sosyalkulup.services.pdf_rapor import _fontlar

# Üyeleri listelenmeyen, herkesin kendiliğinden üyesi olduğu kurullar
_OTOMATIK_ACIKLAMA = {
    KurulTuru.OTOMATIK_TUM_PERSONEL: "Görevdeki bütün öğretmenler",
    KurulTuru.OTOMATIK_SUBE_OGRETMENLERI: "Şubeye derse giren öğretmenler ve rehber öğretmen",
    KurulTuru.OTOMATIK_BRANS_OGRETMENLERI: "Branştaki öğretmenler",
}


def gorevlendirme_listesi_pdf(egitim_yili, kurullar, okul_adi="") -> bytes:
    """Yılın kurul/komisyon görevlendirme çizelgesini A4 yatay PDF olarak üretir.

    Şube ve zümre kurulları tek satırda özetlenir (zümrelerde başkanlar yazılır);
    diğer kurulların bütün üyeleri görevleriyle listelenir."""
    font, font_kalin = _fontlar()
    stil = ParagraphStyle("normal", fontName=font, fontSize=9, leading=11.5)
    kalin = ParagraphStyle("kalin", parent=stil, fontName=font_kalin)
    baslik = ParagraphStyle("baslik", parent=stil, fontName=font_kalin, fontSize=13, leading=17, alignment=1)

    icerik = []
    if okul_adi:
        icerik.append(Paragraph(escape(okul_adi), baslik))
    icerik += [
        Paragraph(f"{escape(str(egitim_yili))} Eğitim-Öğretim Yılı Kurul ve Komisyonlar", baslik),
        Spacer(1, 10),
    ]

    satirlar = [[Paragraph("Kurul / Komisyon", kalin), Paragraph("Mevzuat Dayanağı", kalin),
                 Paragraph("Görevliler", kalin)]]
    turlere_gore = {}
    for kurul in kurullar:
        turlere_gore.setdefault(kurul.tur, []).append(kurul)

    for tur, tur_kurullari in sorted(turlere_gore.items(), key=lambda x: (x[0].sira, x[0].ad)):
        if tur.otomatik_uyelik in _OTOMATIK_ACIKLAMA:
            gorevliler = _OTOMATIK_ACIKLAMA[tur.otomatik_uyelik]
            if tur.kapsam != KurulTuru.KAPSAM_OKUL:
                gorevliler += f" ({len(tur_kurullari)} kurul)"
            baskanlar = [
                (f"{escape(k.brans.ad if k.brans_id else str(k.sinif_sube))}: " if tur.kapsam != KurulTuru.KAPSAM_OKUL else "")
                + escape(u.uye_adi)
                for k in tur_kurullari for u in k.uyeler.all() if u.gorev == "baskan"
            ]
            metin = escape(gorevliler)
            if baskanlar:
                metin += "<br/>Başkan(lar): " + "; ".join(baskanlar)
        else:
            uyeler = [u for k in tur_kurullari for u in k.uyeler.all()]
            metin = "<br/>".join(
                f"{escape(u.gorev_adi)}{'' if u.asil else ' (yedek)'}: {escape(u.uye_adi)}"
                for u in sorted(uyeler, key=lambda u: (u.kalem.sira if u.kalem_id else 999, not u.asil, u.pk))
            ) or "Üye belirlenmedi"
        satirlar.append([Paragraph(escape(tur.ad), kalin), Paragraph(escape(tur.mevzuat_dayanagi), stil),
                         Paragraph(metin, stil)])

    tablo = Table(satirlar, colWidths=[6.5 * cm, 8 * cm, 12.5 * cm], repeatRows=1)
    tablo.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    icerik.append(tablo)

    tampon = io.BytesIO()
    SimpleDocTemplate(
        tampon, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm,
        topMargin=1.2 * cm, bottomMargin=1.2 * cm, title="Kurul ve Komisyonlar",
    ).build(icerik)
    return tampon.getvalue()
