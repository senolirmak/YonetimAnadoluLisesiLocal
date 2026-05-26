from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import render
from django.utils import timezone

from cagri.models import OgrenciCagri
from dersprogrami.models import DersProgrami
from devamsizlik.models import OgrenciDevamsizlik
from faaliyet.models import Faaliyet
from nobet.models import (
    GunlukNobetCizelgesi,
    NobetGecmisi,
    NobetGorevi,
    NobetPersonel,
    OkulBilgi,
)
from ogrencinobet.models import OgrenciNobetGorevi
from personeldevamsizlik.models import Devamsizlik
from okul.utils import get_aktif_dp_tarihi
from main.utils import _GUN_TR
from utility.constants import WEEKDAY_TO_DB as _WEEKDAY_TO_DB


@login_required
def index(request):
    okul_bilgi = OkulBilgi.objects.select_related("okul_donem", "okul_donem__egitim_yili", "okul_egtyil").first()

    today = timezone.localdate()
    day_name_en = _WEEKDAY_TO_DB.get(today.weekday(), "Monday")

    toplam_ogretmen = NobetPersonel.objects.count()
    ucretli_ogretmen = NobetPersonel.objects.filter(gorev_tipi__icontains="Ücretli").count()

    devamsiz_ogretmen = (
        Devamsizlik.objects.filter(baslangic_tarihi__lte=today)
        .filter(Q(bitis_tarihi__gte=today) | Q(bitis_tarihi__isnull=True))
        .values("ogretmen")
        .distinct()
        .count()
    )

    gorev_date = (
        NobetGorevi.objects.filter(uygulama_tarihi__lte=today)
        .order_by("-uygulama_tarihi")
        .values_list("uygulama_tarihi", flat=True)
        .first()
    )
    nobetci_ogretmen = (
        NobetGorevi.objects.filter(uygulama_tarihi=gorev_date, nobet_gun=day_name_en)
        .values("ogretmen")
        .distinct()
        .count()
        if gorev_date
        else 0
    )

    brans_dagilimi = (
        NobetPersonel.objects.values("brans").annotate(sayi=Count("id")).order_by("-sayi")
    )

    gunun_nobetci_ogretmenleri = (
        GunlukNobetCizelgesi.objects.filter(tarih=today)
        .select_related("ogretmen__personel")
        .order_by("nobet_yeri", "ogretmen__personel__adi_soyadi")
    )

    devamsiz_kiz = (
        OgrenciDevamsizlik.objects.filter(tarih=today, ogrenci__cinsiyet="K")
        .values("ogrenci")
        .distinct()
        .count()
    )
    devamsiz_erkek = (
        OgrenciDevamsizlik.objects.filter(tarih=today, ogrenci__cinsiyet="E")
        .values("ogrenci")
        .distinct()
        .count()
    )
    faaliyet_ogrenci = (
        Faaliyet.objects.filter(tarih=today, durum=Faaliyet.DURUM_ONAYLANDI).aggregate(
            sayi=Count("ogrenciler", distinct=True)
        )["sayi"]
        or 0
    )
    rehberlik_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_REHBERLIK
    ).count()
    disiplin_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_DISIPLIN
    ).count()
    muduriyetcagri_cagri = OgrenciCagri.objects.filter(
        tarih=today, servis=OgrenciCagri.SERVIS_MUDURIYETCAGRI
    ).count()

    _gruplar = set(request.user.groups.values_list("name", flat=True))
    _yonetici_gruplar = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    _salt_ogretmen = not request.user.is_superuser and "ogretmen" in _gruplar and not bool(_gruplar & _yonetici_gruplar)
    personel_bagli = _salt_ogretmen and hasattr(request.user, "personel")

    rehberlik_sinif_sube = None
    ogretmen_nobetleri = []
    atanan_dersler = []
    if personel_bagli:
        _aktif_tarih = get_aktif_dp_tarihi()
        _dp_f = {"uygulama_tarihi": _aktif_tarih} if _aktif_tarih else {}
        rehberlik_ders = (
            DersProgrami.objects.filter(
                ogretmen=request.user.personel,
                ders__ders_adi__iexact="rehberlik ve yönlendirme",
                **_dp_f,
            )
            .select_related("sinif_sube", "ders")
            .first()
        )
        if rehberlik_ders and rehberlik_ders.sinif_sube:
            rehberlik_sinif_sube = str(rehberlik_ders.sinif_sube)

        try:
            nobet_ogretmen = request.user.personel.ogretmen
            son_uygulama = (
                NobetGorevi.objects.filter(ogretmen=nobet_ogretmen)
                .order_by("-uygulama_tarihi")
                .values_list("uygulama_tarihi", flat=True)
                .first()
            )
            if son_uygulama:
                ogretmen_nobetleri = [
                    {
                        "gun": _GUN_TR.get(n.nobet_gun, n.nobet_gun),
                        "yer": n.nobet_yeri,
                    }
                    for n in NobetGorevi.objects.filter(
                        ogretmen=nobet_ogretmen, uygulama_tarihi=son_uygulama
                    ).order_by("nobet_gun")
                ]

            atanan_dersler = list(
                NobetGecmisi.objects.filter(ogretmen=nobet_ogretmen, tarih__date=today).order_by(
                    "saat"
                )
            )
        except Exception:
            pass

    from ogrenci.models import Ogrenci as _Ogrenci
    _sube_qs = (
        _Ogrenci.objects
        .values("sinif", "sube", "cinsiyet")
        .annotate(sayi=Count("id"))
        .order_by("sinif", "sube", "cinsiyet")
    )
    _sinif_map = {}
    _sube_map = {}
    for r in _sube_qs:
        s, sb, cins = r["sinif"], r["sube"], r["cinsiyet"]
        _sinif_map.setdefault(s, {"sinif": s, "kiz": 0, "erkek": 0})
        _sube_map.setdefault(s, {}).setdefault(sb, {"sube": sb, "kiz": 0, "erkek": 0})
        if cins == "K":
            _sinif_map[s]["kiz"] += r["sayi"]
            _sube_map[s][sb]["kiz"] = r["sayi"]
        elif cins == "E":
            _sinif_map[s]["erkek"] += r["sayi"]
            _sube_map[s][sb]["erkek"] = r["sayi"]
    ogrenci_seviye_listesi = []
    for v in sorted(_sinif_map.values(), key=lambda x: x["sinif"]):
        s = v["sinif"]
        subeler = [
            {**sb, "toplam": sb["kiz"] + sb["erkek"]}
            for sb in sorted(_sube_map.get(s, {}).values(), key=lambda x: x["sube"])
        ]
        ogrenci_seviye_listesi.append({**v, "toplam": v["kiz"] + v["erkek"], "subeler": subeler})
    ogrenci_genel_toplam = {
        "kiz":    sum(v["kiz"]  for v in _sinif_map.values()),
        "erkek":  sum(v["erkek"] for v in _sinif_map.values()),
        "toplam": sum(v["kiz"] + v["erkek"] for v in _sinif_map.values()),
    }

    gunun_nobetci_ogrencileri = list(
        OgrenciNobetGorevi.objects.filter(tarih=today)
        .select_related("ogrenci")
        .order_by("ogrenci__sinif", "ogrenci__sube", "ogrenci__okulno")
    )

    sinav_gozetim_var = False
    sinav_aktif_var   = False
    if hasattr(request.user, "personel") and request.user.personel:
        try:
            from sinav.models import (
                SinavBilgisi as _SinavBilgisi,
                TakvimUretim as _TakvimUretim,
                OturmaPlani as _OturmaPlani,
            )
            _personel = request.user.personel
            _aktif_sinav = _SinavBilgisi.objects.filter(aktif=True).first()
            if _aktif_sinav:
                _aktif_uretim = _TakvimUretim.objects.filter(
                    sinav=_aktif_sinav, aktif=True
                ).first()
                if _aktif_uretim:
                    sinav_aktif_var = True
                    sinav_gozetim_var = _OturmaPlani.objects.filter(
                        uretim=_aktif_uretim,
                        gozetmen_fk=_personel,
                    ).exists()
        except Exception:
            pass

    sorumluluk_takvim_var = False
    if rehberlik_sinif_sube:
        try:
            from sorumluluk.models import SorumluOturmaPlani as _SOP
            sorumluluk_takvim_var = _SOP.objects.filter(sinifsube=rehberlik_sinif_sube).exists()
        except Exception:
            pass

    sorumluluk_gorev_var = False
    if hasattr(request.user, "personel") and request.user.personel:
        try:
            from sorumluluk.models import SorumluKomisyonUyesi as _SKU, SorumluGozetmen as _SGZ
            _p = request.user.personel
            sorumluluk_gorev_var = (
                _SKU.objects.filter(Q(uye1=_p) | Q(uye2=_p)).exists()
                or _SGZ.objects.filter(gozetmen=_p).exists()
            )
        except Exception:
            pass

    return render(
        request,
        "main/index.html",
        {
            "title": "Anasayfa",
            "okul_bilgi": okul_bilgi,
            "gunun_nobetci_ogrencileri": gunun_nobetci_ogrencileri,
            "gunun_nobetci_ogretmenleri": gunun_nobetci_ogretmenleri,
            "personel_bagli": personel_bagli,
            "rehberlik_sinif_sube": rehberlik_sinif_sube,
            "ogretmen_nobetleri": ogretmen_nobetleri,
            "atanan_dersler": atanan_dersler,
            "sinav_gozetim_var":      sinav_gozetim_var,
            "sinav_aktif_var":        sinav_aktif_var,
            "sorumluluk_gorev_var":   sorumluluk_gorev_var,
            "sorumluluk_takvim_var":  sorumluluk_takvim_var,
            "personel_istatistik": {
                "toplam": toplam_ogretmen,
                "ucretli": ucretli_ogretmen,
                "devamsiz": devamsiz_ogretmen,
                "nobetci": nobetci_ogretmen,
                "brans_dagilimi": brans_dagilimi,
            },
            "ogrenci_istatistik": {
                "devamsiz_kiz": devamsiz_kiz,
                "devamsiz_erkek": devamsiz_erkek,
                "faaliyet": faaliyet_ogrenci,
                "rehberlik_cagri": rehberlik_cagri,
                "disiplin_cagri": disiplin_cagri,
                "muduriyetcagri_cagri": muduriyetcagri_cagri,
            },
            "ogrenci_seviye_listesi": ogrenci_seviye_listesi,
            "ogrenci_genel_toplam":   ogrenci_genel_toplam,
        },
    )
