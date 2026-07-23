from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from devamsizlik.models import OgrenciDevamsizlik
from faaliyet.models import Faaliyet
from main.utils import get_ogretmen_gorev_verileri
from nobet.models import GunlukNobetCizelgesi, OkulBilgi
from ogrencinobet.models import OgrenciNobetGorevi


@login_required
def index(request):
    okul_bilgi = OkulBilgi.objects.select_related("okul_donem", "okul_donem__egitim_yili", "okul_egtyil").first()

    today = timezone.localdate()

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
    _gorev = get_ogretmen_gorev_verileri(request.user, today)
    personel_bagli = _gorev["personel_bagli"]
    rehberlik_sinif_sube = _gorev["rehberlik_sinif_sube"]
    ogretmen_nobetleri = _gorev["ogretmen_nobetleri"]
    atanan_dersler = _gorev["atanan_dersler"]
    sinav_gozetim_var = _gorev["sinav_gozetim_var"]
    sinav_aktif_var = _gorev["sinav_aktif_var"]
    sorumluluk_gorev_var = _gorev["sorumluluk_gorev_var"]
    sorumluluk_takvim_var = _gorev["sorumluluk_takvim_var"]

    from ogrenci.models import Ogrenci as _Ogrenci
    _sube_qs = (
        _Ogrenci.objects
        .filter(aktif=True)
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
            "ogrenci_istatistik": {
                "devamsiz_kiz": devamsiz_kiz,
                "devamsiz_erkek": devamsiz_erkek,
                "faaliyet": faaliyet_ogrenci,
            },
            "ogrenci_seviye_listesi": ogrenci_seviye_listesi,
            "ogrenci_genel_toplam":   ogrenci_genel_toplam,
        },
    )


@login_required
def gorevlerim(request):
    """Öğretmenin nöbet, ders doldurma, sınav gözetim ve sorumluluk görevlerini tek sayfada toplar."""
    today = timezone.localdate()
    gorev = get_ogretmen_gorev_verileri(request.user, today)

    return render(
        request,
        "main/gorevlerim.html",
        {
            "title": "Görevlerim",
            **gorev,
        },
    )
