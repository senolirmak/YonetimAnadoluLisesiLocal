"""
Tamamlanmış (onaylanmış + devamsızlığı girilmiş) faaliyetlerin tarihe göre
gruplanmış toplu raporu.

Devamsızlık tespiti tekil rapordaki (``views.faaliyet_rapor``) mantığa dayanır:
faaliyetin tarihi + ders saati + öğrencisi için ``aciklama`` "Faaliyet:" ile
başlayan ve "Faaliyet: Katıldı" olmayan ``OgrenciDevamsizlik`` kaydı devamsızlıktır.
``OgrenciDevamsizlik`` faaliyete FK ile bağlı olmadığından, aynı gün aynı
öğrencilerle yapılan farklı faaliyetler karışmasın diye kayıt ayrıca
``ders_adi == "Faaliyet: {konu}"`` ile faaliyete eşlenir (bkz. ``faaliyet_devamsizlik``).
N+1 sorgudan kaçınmak için tüm tarihlerin devamsızlıkları tek sorguda çekilir.
"""

from collections import OrderedDict
from io import BytesIO

from devamsizlik.models import OgrenciDevamsizlik

from ..models import Faaliyet


def tamamlanan_faaliyetler(tarih_bas="", tarih_bit="", ogretmen_id=""):
    """Rapora girecek faaliyetleri döndürür.

    Tarih aralığı verilmediğinde Sene Sonu Geçişi ile arşivlenen kayıtlar dahil
    edilmez (``faaliyet_yonetim_listesi`` ile aynı davranış).
    """
    qs = (
        Faaliyet.objects.filter(durum=Faaliyet.DURUM_ONAYLANDI, devamsizlik_girildi=True)
        .select_related("ogretmen")
        .prefetch_related("ders_saatleri", "ogrenciler")
        .order_by("tarih", "olusturma_zamani")
    )
    if not (tarih_bas or tarih_bit):
        qs = qs.filter(arsivlendi=False)
    if tarih_bas:
        qs = qs.filter(tarih__gte=tarih_bas)
    if tarih_bit:
        qs = qs.filter(tarih__lte=tarih_bit)
    if ogretmen_id:
        qs = qs.filter(ogretmen_id=ogretmen_id)
    return qs


def _devamsizlik_kumesi(tarihler):
    """{(ogrenci_id, tarih, ders_no, ders_adi)} — faaliyet kaynaklı devamsızlıklar."""
    if not tarihler:
        return set()
    return set(
        OgrenciDevamsizlik.objects.filter(
            tarih__in=tarihler,
            aciklama__startswith="Faaliyet:",
        )
        .exclude(aciklama="Faaliyet: Katıldı")
        .values_list("ogrenci_id", "tarih", "ders_saati__derssaati_no", "ders_adi")
    )


def tarihe_gore_grupla(faaliyetler):
    """Faaliyetleri tarihe göre gruplar ve katılım özetlerini hesaplar.

    Dönüş: ``{"gunler": [...], "toplam": {...}}``. Her gün
    ``{"tarih", "faaliyetler": [satir...], "ogrenci", "devamsiz_ogrenci",
    "devamsiz_ders"}``; her satır ``{"faaliyet", "ders_saatleri", "ogrenci_sayisi",
    "ogrenciler", "devamsizlar", "devamsiz_ders"}`` içerir. ``ogrenciler`` faaliyete
    katılan tüm öğrencilerdir: ``[{"ogr", "dersler": [devamsız ders_no...]}]``
    (``dersler`` boşsa tam katılım); ``devamsizlar`` bunun ``dersler`` dolu olan alt kümesidir.
    """
    faaliyetler = list(faaliyetler)
    devamsiz = _devamsizlik_kumesi({f.tarih for f in faaliyetler})

    gunler = OrderedDict()
    toplam = {"faaliyet": 0, "ogrenci": 0, "devamsiz_ogrenci": 0, "devamsiz_ders": 0}

    for f in faaliyetler:
        ders_saatleri = sorted(f.ders_saatleri.all(), key=lambda d: d.ders_no)
        ogrenciler = sorted(
            f.ogrenciler.all(), key=lambda o: (o.sinif or 0, o.sube or "", o.soyadi, o.adi)
        )
        ders_adi = f"Faaliyet: {f.konu}"[:100]  # OgrenciDevamsizlik.ders_adi max_length
        katilim = [
            {
                "ogr": ogr,
                "dersler": [
                    ds.ders_no
                    for ds in ders_saatleri
                    if (ogr.pk, f.tarih, ds.ders_no, ders_adi) in devamsiz
                ],
            }
            for ogr in ogrenciler
        ]
        devamsizlar = [k for k in katilim if k["dersler"]]
        devamsiz_ders = sum(len(d["dersler"]) for d in devamsizlar)

        gun = gunler.setdefault(
            f.tarih,
            {
                "tarih": f.tarih,
                "faaliyetler": [],
                "ogrenci": 0,
                "devamsiz_ogrenci": 0,
                "devamsiz_ders": 0,
            },
        )
        gun["faaliyetler"].append(
            {
                "faaliyet": f,
                "ders_saatleri": ders_saatleri,
                "ogrenci_sayisi": len(ogrenciler),
                "ogrenciler": katilim,
                "devamsizlar": devamsizlar,
                "devamsiz_ders": devamsiz_ders,
            }
        )
        gun["ogrenci"] += len(ogrenciler)
        gun["devamsiz_ogrenci"] += len(devamsizlar)
        gun["devamsiz_ders"] += devamsiz_ders

        toplam["faaliyet"] += 1
        toplam["ogrenci"] += len(ogrenciler)
        toplam["devamsiz_ogrenci"] += len(devamsizlar)
        toplam["devamsiz_ders"] += devamsiz_ders

    return {"gunler": list(gunler.values()), "toplam": toplam}


def toplu_rapor_pdf(rapor, baslik_alt=""):
    """``tarihe_gore_grupla`` çıktısından PDF üretir, bytes döndürür."""
    from django.conf import settings
    from django.utils import timezone
    from django.utils.html import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        CondPageBreak,
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    fonts_dir = settings.BASE_DIR / "static" / "fonts"
    try:
        pdfmetrics.registerFont(TTFont("DejaVu", str(fonts_dir / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(fonts_dir / "DejaVuSans-Bold.ttf")))
        base_font, bold_font = "DejaVu", "DejaVu-Bold"
    except Exception:
        base_font, bold_font = "Helvetica", "Helvetica-Bold"

    HDR_BG = colors.HexColor("#417690")
    GUN_BG = colors.HexColor("#e67e22")
    DEVAMSIZ = colors.HexColor("#c0392b")
    KATILDI = colors.HexColor("#1a7f37")
    BILGI_BG = colors.HexColor("#eef3f7")
    ROW2 = colors.HexColor("#f4f8fb")

    def ps(name, bold=False, size=8, center=False, color=colors.black):
        return ParagraphStyle(
            name,
            fontName=bold_font if bold else base_font,
            fontSize=size,
            leading=size + 3,
            alignment=TA_CENTER if center else TA_LEFT,
            textColor=color,
        )

    s_normal = ps("n")
    s_center = ps("c", center=True)
    s_title = ps("t", bold=True, size=13, center=True)
    s_sub = ps("s", size=9, center=True, color=colors.HexColor("#555555"))
    s_hdr = ps("h", bold=True, color=colors.white)
    s_hdr_c = ps("hc", bold=True, center=True, color=colors.white)
    s_gun = ps("g", bold=True, size=10, color=colors.white)
    s_bilgi = ps("b", size=8.5)
    s_katildi = ps("k", bold=True, color=KATILDI)
    s_devamsiz = ps("d", bold=True, color=DEVAMSIZ)

    buffer = BytesIO()
    margin = 1.2 * cm
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title="Faaliyet Toplu Raporu",
    )

    story = [Paragraph("FAALİYET TOPLU KATILIM RAPORU", s_title)]
    if baslik_alt:
        story += [Spacer(1, 0.1 * cm), Paragraph(baslik_alt, s_sub)]
    story += [
        Spacer(1, 0.2 * cm),
        HRFlowable(width="100%", thickness=1.5, color=HDR_BG),
        Spacer(1, 0.3 * cm),
    ]

    # Her faaliyet ayrı bir tablodur: ilk satır faaliyet bilgisi, ikinci satır sütun
    # başlıkları (ikisi de sayfa geçişlerinde tekrarlanır), ardından her öğrenci bir satır.
    # Öğrenciler tek hücrede toplanmaz — satırlar sayfalar arasında bölünemediği için
    # kalabalık faaliyetlerde reportlab LayoutError verir.
    # Sütunlar: Sn | Okul No | Adı Soyadı | Sınıf/Şube | Katılım
    w = doc.width
    col_widths = [1.0 * cm, 1.7 * cm, w - 1.0 * cm - 1.7 * cm - 2.3 * cm - 5.0 * cm, 2.3 * cm, 5.0 * cm]
    cizgi = colors.HexColor("#c0c8d0")

    for gun in rapor["gunler"]:
        gun_baslik = Table(
            [
                [
                    Paragraph(
                        f"{gun['tarih'].strftime('%d.%m.%Y')} — {len(gun['faaliyetler'])} faaliyet, "
                        f"{gun['ogrenci']} öğrenci, {gun['devamsiz_ogrenci']} devamsız öğrenci "
                        f"({gun['devamsiz_ders']} ders saati)",
                        s_gun,
                    )
                ]
            ],
            colWidths=[w],
        )
        gun_baslik.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), GUN_BG),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        # Gün başlığı sayfa sonunda tek başına kalmasın
        story += [CondPageBreak(4 * cm), gun_baslik, Spacer(1, 0.2 * cm)]

        for satir in gun["faaliyetler"]:
            f = satir["faaliyet"]
            ders_str = ", ".join(f"{ds.ders_no}." for ds in satir["ders_saatleri"]) or "—"
            # Paragraph işaretleme dili kullandığından kullanıcı metinleri kaçışlanır;
            # DejaVu için <b> font ailesi kayıtlı olmadığından kalın font adıyla verilir.
            bilgi = (
                f'<font name="{bold_font}">{escape(f.konu)}</font><br/>'
                f"Yer: {escape(f.yer)} &nbsp;·&nbsp; "
                f"Öğretmen: {escape(f.ogretmen.adi_soyadi or '')} "
                f"&nbsp;·&nbsp; Ders: {ders_str} &nbsp;·&nbsp; "
                f"{satir['ogrenci_sayisi']} öğrenci, {len(satir['devamsizlar'])} devamsız"
            )
            data = [
                [Paragraph(bilgi, s_bilgi), "", "", "", ""],
                [
                    Paragraph("Sn", s_hdr_c),
                    Paragraph("Okul No", s_hdr_c),
                    Paragraph("Adı Soyadı", s_hdr),
                    Paragraph("Sınıf/Şube", s_hdr_c),
                    Paragraph("Katılım", s_hdr),
                ],
            ]
            for sira, k in enumerate(satir["ogrenciler"], start=1):
                ogr = k["ogr"]
                if k["dersler"]:
                    durum = Paragraph(
                        "✗ Devamsız: " + ", ".join(f"{n}." for n in k["dersler"]) + " ders",
                        s_devamsiz,
                    )
                else:
                    durum = Paragraph("✓ Katıldı", s_katildi)
                data.append(
                    [
                        Paragraph(str(sira), s_center),
                        Paragraph(str(ogr.okulno or ""), s_center),
                        Paragraph(escape(f"{ogr.adi} {ogr.soyadi}"), s_normal),
                        Paragraph(f"{ogr.sinif}/{ogr.sube}", s_center),
                        durum,
                    ]
                )
            if not satir["ogrenciler"]:
                data.append(["", "", Paragraph("Katılımcı öğrenci yok.", s_normal), "", ""])

            stil = [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), BILGI_BG),
                ("BACKGROUND", (0, 1), (-1, 1), HDR_BG),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.3, cizgi),
                ("LINEBELOW", (0, 1), (-1, 1), 1, HDR_BG),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            ]
            for i in range(3, len(data), 2):
                stil.append(("BACKGROUND", (0, i), (-1, i), ROW2))

            tbl = Table(data, colWidths=col_widths, repeatRows=2)
            tbl.setStyle(TableStyle(stil))
            story += [CondPageBreak(3 * cm), tbl, Spacer(1, 0.35 * cm)]

        story.append(Spacer(1, 0.2 * cm))

    t = rapor["toplam"]
    story += [
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cccccc")),
        Spacer(1, 0.15 * cm),
        Paragraph(
            f'<font name="{bold_font}">Genel Toplam:</font> '
            f"{len(rapor['gunler'])} gün, {t['faaliyet']} faaliyet, "
            f"{t['ogrenci']} öğrenci katılımı, {t['devamsiz_ogrenci']} devamsız öğrenci "
            f"({t['devamsiz_ders']} ders saati)",
            s_normal,
        ),
        Spacer(1, 0.1 * cm),
        Paragraph(
            f"Rapor Tarihi: {timezone.localdate().strftime('%d.%m.%Y')}",
            ps("alt", size=7, color=colors.HexColor("#666666")),
        ),
    ]

    doc.build(story)
    return buffer.getvalue()
