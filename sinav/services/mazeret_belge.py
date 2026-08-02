"""Mazeret sınavı belge teslim / özel durum (sürekli devamsız, muaf) işaretleme."""
from django.db.models import Q

from sinav.models import MazeretBelgeTeslim, MazeretOgrenci, MazeretSinav


def mazeret_belge_kaydet(request, mazeret: "MazeretSinav") -> tuple[int, int]:
    """
    POST'taki belge_teslim / sureksiz_devamsiz checkbox listelerinden MazeretOgrenci ve
    Ogrenci kayıtlarını günceller; belge_teslim değişikliklerini kalıcı MazeretBelgeTeslim
    tablosuna da yansıtır. (güncellenen_belge, güncellenen_ogr) döner.
    """
    from ogrenci.models import Ogrenci as OgrenciModel

    belge_isaretli    = set(map(int, request.POST.getlist("belge_teslim")))
    sureksiz_isaretli = set(request.POST.getlist("sureksiz_devamsiz"))
    guncellenen_belge = 0
    belge_ekle = []
    belge_sil_keys = []
    for mo in MazeretOgrenci.objects.filter(mazeret_sinav=mazeret):
        yeni_belge = mo.pk in belge_isaretli
        if mo.belge_teslim != yeni_belge:
            mo.belge_teslim = yeni_belge
            mo.save(update_fields=["belge_teslim"])
            guncellenen_belge += 1
        # Kalıcı tabloya da yansıt
        if yeni_belge:
            belge_ekle.append(
                MazeretBelgeTeslim(
                    okulno=mo.okulno,
                    ders_adi=mo.ders_adi,
                    sinav_turu=mo.sinav_turu,
                )
            )
        else:
            belge_sil_keys.append((mo.okulno, mo.ders_adi, mo.sinav_turu))

    sinav = mazeret.sinav
    if belge_ekle:
        for b in belge_ekle:
            b.sinav = sinav
        MazeretBelgeTeslim.objects.bulk_create(belge_ekle, ignore_conflicts=True)
    for okulno, ders_adi, sinav_turu in belge_sil_keys:
        MazeretBelgeTeslim.objects.filter(
            sinav=sinav, okulno=okulno, ders_adi=ders_adi, sinav_turu=sinav_turu
        ).delete()

    # Subquery yerine Python listesi: Ogrenci.okulno (int) ↔ MazeretOgrenci.okulno (varchar)
    _mo_okulno_ints = [
        int(x) for x in
        MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
        .values_list("okulno", flat=True).distinct() if x
    ]
    guncellenen_ogr = 0
    for ogr in (OgrenciModel.objects.filter(okulno__in=_mo_okulno_ints) if _mo_okulno_ints else OgrenciModel.objects.none()):
        yeni_sureksiz = str(ogr.okulno) in sureksiz_isaretli
        if ogr.sureksiz_devamsiz != yeni_sureksiz:
            ogr.sureksiz_devamsiz = yeni_sureksiz
            ogr.save(update_fields=["sureksiz_devamsiz"])
            guncellenen_ogr += 1

    return guncellenen_belge, guncellenen_ogr


def mazeret_belge_ctx(mazeret: "MazeretSinav", q: str = "") -> dict:
    """
    MazeretOgrenci tablosundan ders bazlı gruplu belge-teslim verisini (sureksiz/muaf
    bayrakları ve özet sayılarla) hazırlar. q verilirse okulno/adı-soyadı ile filtreler.
    """
    from ogrenci.models import Ogrenci as OgrenciModel
    from ogrenci.models import OgrenciMuaf
    from okul.utils import get_aktif_egitim_yili

    # Sürekli devamsız okulnoları — int → str (MazeretOgrenci.okulno CharField)
    sureksiz_okulnolari = {
        str(x) for x in
        OgrenciModel.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
    }

    # Muaf (ders bazında): subquery yerine Python listesi (int↔varchar tip uyumu)
    _mo_ok_ints = [
        int(x) for x in
        MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
        .values_list("okulno", flat=True).distinct() if x
    ]
    muaf_okulno_ders: set[tuple[str, str]] = (
        {
            (str(ok), ders)
            for ok, ders in OgrenciMuaf.objects.filter(
                ogrenci__okulno__in=_mo_ok_ints,
                egitim_yili=get_aktif_egitim_yili(),
            ).values_list("ogrenci__okulno", "ders__ders_adi")
        }
        if _mo_ok_ints else set()
    )

    qs = MazeretOgrenci.objects.filter(mazeret_sinav=mazeret)
    if q:
        qs = qs.filter(Q(okulno__icontains=q) | Q(adi_soyadi__icontains=q))
    tum_ogrenciler = list(qs.order_by("ders_adi", "sinav_turu", "sinifsube", "okulno"))

    ders_map: dict[tuple, dict] = {}
    for mo in tum_ogrenciler:
        key = (mo.ders_adi, mo.sinav_turu)
        if key not in ders_map:
            ders_map[key] = {"ders_adi": mo.ders_adi, "sinav_turu": mo.sinav_turu, "ogrenciler": []}
        sureksiz = mo.okulno in sureksiz_okulnolari
        muaf = (mo.okulno, mo.ders_adi) in muaf_okulno_ders
        ders_map[key]["ogrenciler"].append({
            "mo":       mo,
            "sureksiz": sureksiz,
            "muaf":     muaf,
        })

    toplam         = len(tum_ogrenciler)
    belge_teslim_n = sum(1 for mo in tum_ogrenciler if mo.belge_teslim)
    haric_n = sum(
        1 for mo in tum_ogrenciler
        if mo.okulno in sureksiz_okulnolari or (mo.okulno, mo.ders_adi) in muaf_okulno_ders
    )
    uygun_n = sum(
        1 for mo in tum_ogrenciler
        if mo.belge_teslim
        and mo.okulno not in sureksiz_okulnolari
        and (mo.okulno, mo.ders_adi) not in muaf_okulno_ders
    )

    return {
        "ders_gruplar":   list(ders_map.values()),
        "toplam":         toplam,
        "belge_teslim_n": belge_teslim_n,
        "haric_n":        haric_n,
        "uygun_n":        uygun_n,
    }
