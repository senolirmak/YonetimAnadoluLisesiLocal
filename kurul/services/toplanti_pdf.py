"""Toplantı çıktıları: gündem duyurusu, toplantı tutanağı ve yıllık karar defteri (A4 PDF)."""

import io

from django.utils.html import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from kurul.models import Karar, Katilim, KurulUyesi, Toplanti
from kurul.services.toplanti import onceki_toplanti, sirali_katilimlar
from sosyalkulup.services.pdf_rapor import _fontlar

_GUNLER = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def _stiller():
    font, kalin = _fontlar()
    s = ParagraphStyle("n", fontName=font, fontSize=10, leading=13)
    return {
        "n": s,
        "k": ParagraphStyle("k", parent=s, fontName=kalin),
        "kucuk": ParagraphStyle("kucuk", parent=s, fontSize=8.5, leading=11),
        "baslik": ParagraphStyle("b", parent=s, fontName=kalin, fontSize=13, leading=17, alignment=1),
        "alt": ParagraphStyle("a", parent=s, alignment=1),
        "bolum": ParagraphStyle("bo", parent=s, fontName=kalin, fontSize=11, leading=15, spaceBefore=10, spaceAfter=4),
        "sag": ParagraphStyle("sag", parent=s, alignment=2),
        "font": font,
        "kalin": kalin,
    }


def _tarih(t):
    return f"{t:%d.%m.%Y} {_GUNLER[t.weekday()]}"


def _tablo(satirlar, genislikler, baslik_satiri=True):
    t = Table(satirlar, colWidths=genislikler, repeatRows=1 if baslik_satiri else 0)
    stil = [("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    if baslik_satiri:
        stil.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9ecef")))
    t.setStyle(TableStyle(stil))
    return t


def _p(metin, stil):
    return Paragraph(escape(metin or "").replace("\n", "<br/>"), stil)


def _ust_bilgi(st, okul_adi, toplanti, baslik):
    icerik = []
    if okul_adi:
        icerik.append(_p(okul_adi, st["baslik"]))
    icerik += [
        _p(f"{toplanti.kurul.egitim_yili} Eğitim-Öğretim Yılı", st["alt"]),
        Spacer(1, 4),
        _p(f"{toplanti.kurul.ad}", st["baslik"]),
        _p(baslik, st["baslik"]),
        Spacer(1, 10),
    ]
    return icerik


def _bilgi_tablosu(st, toplanti, baskan_adi):
    satirlar = [
        [_p("Toplantı No", st["k"]), _p(str(toplanti.no), st["n"]),
         _p("Türü", st["k"]), _p(toplanti.get_tur_display(), st["n"])],
        [_p("Tarih", st["k"]), _p(_tarih(toplanti.tarih), st["n"]),
         _p("Saat", st["k"]), _p(f"{toplanti.saat:%H:%M}", st["n"])],
        [_p("Yer", st["k"]), _p(toplanti.yer, st["n"]),
         _p("Kurul Başkanı", st["k"]), _p(baskan_adi or "-", st["n"])],
    ]
    return _tablo(satirlar, [3 * cm, 5.5 * cm, 3 * cm, 5.5 * cm], baslik_satiri=False)


def _baskan_adi(toplanti):
    u = toplanti.kurul.uyeler.filter(gorev=KurulUyesi.GOREV_BASKAN).select_related("personel").first()
    return u.uye_adi if u else ""


def _belge(icerik, yatay=False, baslik="Toplantı"):
    tampon = io.BytesIO()
    SimpleDocTemplate(
        tampon, pagesize=landscape(A4) if yatay else A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
        topMargin=1.4 * cm, bottomMargin=1.4 * cm, title=baslik,
    ).build(icerik)
    return tampon.getvalue()


def duyuru_pdf(toplanti, okul_adi="") -> bytes:
    """Toplantı duyurusu ve gündem (öğretmenler odasına asılmak üzere)."""
    st = _stiller()
    baskan = _baskan_adi(toplanti)
    icerik = _ust_bilgi(st, okul_adi, toplanti, "Toplantı Duyurusu")
    icerik.append(_bilgi_tablosu(st, toplanti, baskan))
    icerik.append(Spacer(1, 10))
    icerik.append(_p(
        f"{toplanti.kurul.ad} aşağıdaki gündemle {toplanti.tarih:%d.%m.%Y} tarihinde saat "
        f"{toplanti.saat:%H:%M}'de {toplanti.yer} yerinde toplanacaktır. Üyelerin katılımları rica olunur.",
        st["n"],
    ))
    if toplanti.kurul.tur.gizli:
        icerik.append(Spacer(1, 6))
        icerik.append(_p("Gündem, kurul üyelerine ayrıca bildirilir.", st["n"]))
    else:
        icerik.append(_p("GÜNDEM", st["bolum"]))
        for m in toplanti.gundem.all():
            icerik.append(_p(f"{m.sira}. {m.baslik}", st["n"]))
    if toplanti.aciklama:
        icerik += [Spacer(1, 6), _p(toplanti.aciklama, st["kucuk"])]
    icerik += [Spacer(1, 24), _imza_blogu(st, toplanti.duyuru_tarihi, baskan, "Kurul Başkanı")]
    return _belge(icerik, baslik="Toplantı Duyurusu")


def _imza_blogu(st, tarih, ad, unvan):
    metin = f"{tarih:%d.%m.%Y}<br/><br/>{escape(ad or '')}<br/>{escape(unvan)}" if tarih else \
        f"..../..../........<br/><br/>{escape(ad or '')}<br/>{escape(unvan)}"
    return Table([["", Paragraph(metin, ParagraphStyle("imza", parent=st["n"], alignment=1))]],
                 colWidths=[10 * cm, 7 * cm])


def tutanak_pdf(toplanti, okul_adi="", okul_muduru="") -> bytes:
    """Toplantı tutanağı: katılım, gündem, görüşmeler, kararlar, imzalar ve müdür onayı."""
    st = _stiller()
    gizli = toplanti.kurul.tur.gizli
    icerik = _ust_bilgi(st, okul_adi, toplanti, f"{toplanti.no} Nolu Toplantı Tutanağı")
    icerik.append(_bilgi_tablosu(st, toplanti, _baskan_adi(toplanti)))

    katilimlar = sirali_katilimlar(toplanti)
    gruplar = {d: [k for k in katilimlar if k.durum == d] for d, _ in Katilim.DURUM_CHOICES}
    icerik.append(_p("KATILIM", st["bolum"]))
    for durum, ad in Katilim.DURUM_CHOICES:
        kisiler = gruplar[durum]
        if kisiler:
            icerik.append(_p(f"{ad} ({len(kisiler)}): " + ", ".join(k.ad for k in kisiler), st["n"]))

    if gizli:
        icerik.append(Spacer(1, 6))
        icerik.append(_p("Bu kurulun görüşme ve kararları, öğrenci kişisel verisi içerdiğinden ilgili "
                         "uygulamada/kayıtta tutulur.", st["kucuk"]))
    else:
        maddeler = list(toplanti.gundem.all())
        icerik.append(_p("GÜNDEM", st["bolum"]))
        for m in maddeler:
            icerik.append(_p(f"{m.sira}. {m.baslik}", st["n"]))
        icerik.append(_p("GÖRÜŞMELER", st["bolum"]))
        onceki = onceki_toplanti(toplanti)
        for m in maddeler:
            blok = [_p(f"{m.sira}. {m.baslik}", st["k"])]
            if m.onceki_kararlar and onceki:
                for k in onceki.kararlar.all():
                    blok.append(_p(f"• {onceki.no} nolu toplantının {k.no}. kararı: {k.metin} — "
                                   f"{k.get_takip_durumu_display()}", st["kucuk"]))
            if m.gorusme:
                blok.append(_p(m.gorusme, st["n"]))
            blok.append(Spacer(1, 4))
            icerik.append(KeepTogether(blok))

        kararlar = list(toplanti.kararlar.select_related("sorumlu", "gundem_maddesi"))
        icerik.append(_p("KARARLAR", st["bolum"]))
        if kararlar:
            satirlar = [[_p("No", st["k"]), _p("Karar", st["k"]), _p("Oylama", st["k"]),
                         _p("Sorumlu / Termin", st["k"])]]
            for k in kararlar:
                sorumlu = k.sorumlu.adi_soyadi if k.sorumlu_id else ""
                termin = f"{k.termin:%d.%m.%Y}" if k.termin else ""
                satirlar.append([_p(str(k.no), st["n"]), _p(k.metin, st["n"]), _p(k.oylama_metni, st["kucuk"]),
                                 _p(" / ".join(x for x in (sorumlu, termin) if x) or "-", st["kucuk"])])
            icerik.append(_tablo(satirlar, [1.2 * cm, 9.3 * cm, 3 * cm, 3.5 * cm]))
        else:
            icerik.append(_p("Karar alınmamıştır.", st["n"]))

    # Yönerge: tutanak, toplantıya katılmayanlar dahil üyeler tarafından imzalanır
    icerik.append(_p("İMZALAR", st["bolum"]))
    satirlar = [[_p("#", st["k"]), _p("Adı Soyadı / Unvanı", st["k"]), _p("Görevi", st["k"]),
                 _p("Durum", st["k"]), _p("İmza", st["k"])]]
    for i, k in enumerate(katilimlar, 1):
        satirlar.append([_p(str(i), st["kucuk"]), _p(k.ad, st["n"]),
                         _p(k.gorev + ("" if k.asil else " (yedek)"), st["kucuk"]),
                         _p(k.get_durum_display(), st["kucuk"]), ""])
    t = _tablo(satirlar, [0.9 * cm, 5.6 * cm, 5 * cm, 2.3 * cm, 3.2 * cm])
    t.setStyle(TableStyle([("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
                           ("TOPPADDING", (0, 1), (-1, -1), 7), ("BOTTOMPADDING", (0, 1), (-1, -1), 7)]))
    icerik.append(t)

    icerik.append(Spacer(1, 20))
    if toplanti.durum == Toplanti.DURUM_ONAYLANDI and toplanti.onay_tarihi:
        onay_metni = f"UYGUNDUR<br/>{toplanti.onay_tarihi:%d.%m.%Y}"
    else:
        onay_metni = "UYGUNDUR<br/>..../..../........"
    onay_metni += f"<br/><br/>{escape(okul_muduru or '')}<br/>Okul Müdürü"
    icerik.append(KeepTogether([Table(
        [["", Paragraph(onay_metni, ParagraphStyle("onay", parent=st["n"], alignment=1))]],
        colWidths=[10 * cm, 7 * cm],
    )]))
    return _belge(icerik, baslik="Toplantı Tutanağı")


def karar_defteri_pdf(kurul, okul_adi="") -> bytes:
    """Kurulun yıl içindeki bütün kararları ve takip durumları (A4 yatay)."""
    st = _stiller()
    icerik = []
    if okul_adi:
        icerik.append(_p(okul_adi, st["baslik"]))
    icerik += [
        _p(f"{kurul.egitim_yili} Eğitim-Öğretim Yılı", st["alt"]),
        _p(f"{kurul.ad} — Karar Defteri", st["baslik"]),
        Spacer(1, 10),
    ]
    kararlar = (
        Karar.objects.filter(toplanti__kurul=kurul).exclude(toplanti__durum=Toplanti.DURUM_IPTAL)
        .select_related("toplanti", "sorumlu").order_by("toplanti__no", "no")
    )
    satirlar = [[_p(b, st["k"]) for b in ("Toplantı", "No", "Karar", "Oylama", "Sorumlu", "Termin", "Takip")]]
    for k in kararlar:
        t = k.toplanti
        toplanti_metni = f"{t.no}. toplantı<br/>{t.tarih:%d.%m.%Y}"
        if t.durum != Toplanti.DURUM_ONAYLANDI:
            toplanti_metni += "<br/>(onaysız)"
        satirlar.append([
            Paragraph(toplanti_metni, st["kucuk"]), _p(str(k.no), st["n"]), _p(k.metin, st["n"]),
            _p(k.oylama_metni, st["kucuk"]), _p(k.sorumlu.adi_soyadi if k.sorumlu_id else "-", st["kucuk"]),
            _p(f"{k.termin:%d.%m.%Y}" if k.termin else "-", st["kucuk"]),
            _p(k.get_takip_durumu_display() + (f" — {k.takip_notu}" if k.takip_notu else ""), st["kucuk"]),
        ])
    if len(satirlar) == 1:
        satirlar.append(["", "", _p("Henüz karar yok.", st["n"]), "", "", "", ""])
    icerik.append(_tablo(satirlar, [2.6 * cm, 1.1 * cm, 11.5 * cm, 3 * cm, 3.5 * cm, 2.2 * cm, 3 * cm]))
    return _belge(icerik, yatay=True, baslik="Karar Defteri")
