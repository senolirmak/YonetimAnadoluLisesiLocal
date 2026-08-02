"""Mazeret sınavı takvim/rapor sayfaları için ortak veri hazırlama."""
from sinav.models import MazeretOgrenci, MazeretOturum, MazeretOturumDers, Takvim
from sinav.services.mazeret_takvim import mazeret_salon_gruplari


def mazeret_oturumlar_verisi(mazeret) -> list[dict]:
    """`mazeret_takvim_detay`, `mazeret_rapor`, `mazeret_rapor_pdf_view` tarafından
    paylaşılan oturum → ders → salon verisini hazırlar."""
    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .prefetch_related("oturma_plani")
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )

    oturumlar_veri = []
    for oturum in oturumlar_qs:
        kayitlar = list(oturum.oturma_plani.order_by("salon", "sira_no"))
        dersler = list(
            MazeretOturumDers.objects
            .filter(oturum=oturum)
            .select_related("ders")
            .order_by("ders__ders_adi")
        )
        oturumlar_veri.append({
            "oturum": oturum,
            "dersler": dersler,
            "salonlar": mazeret_salon_gruplari(mazeret, kayitlar),
            "toplam": len(kayitlar),
        })
    return oturumlar_veri


def mazeret_ilan_oturumlar_veri(mazeret) -> list[dict]:
    """İlan takvimi için gün/oturum/ders verisini (öğrenci/salon detayı olmadan) hazırlar."""
    oturumlar_qs = (
        MazeretOturum.objects
        .filter(gun__mazeret_sinav=mazeret)
        .select_related("gun")
        .order_by("gun__tarih", "oturum_no")
    )
    return [
        {
            "oturum": oturum,
            "dersler": list(
                MazeretOturumDers.objects
                .filter(oturum=oturum)
                .select_related("ders")
                .order_by("ders__ders_adi")
            ),
        }
        for oturum in oturumlar_qs
    ]


def mazeret_detay_verisi(mazeret, aktif_uretim) -> list[dict]:
    """`mazeret_sinav_detay` view'ı için gün → oturum → ders → öğrenci hiyerarşisini hazırlar."""
    # {(ders_id, sinav_turu): [{"okulno", "adi_soyadi", "sinifsube"}, ...]}
    # MazeretOgrenci zaten sureksiz_devamsiz filtreli ve tekildir.
    ogrenci_map: dict[tuple, list] = {}
    if aktif_uretim:
        # ders_adi → ders_id çözümlemesi için cache
        ders_id_cache: dict[tuple[str, str], int | None] = {}

        for mo in MazeretOgrenci.objects.filter(mazeret_sinav=mazeret).order_by("sinifsube", "okulno"):
            cache_key = (mo.ders_adi, mo.sinav_turu)
            if cache_key not in ders_id_cache:
                tk = Takvim.objects.filter(
                    uretim=aktif_uretim,
                    ders__ders_adi=mo.ders_adi,
                    sinav_turu=mo.sinav_turu,
                ).values("ders_id").first()
                ders_id_cache[cache_key] = tk["ders_id"] if tk else None

            ders_id = ders_id_cache[cache_key]
            if ders_id is None:
                continue
            key = (ders_id, mo.sinav_turu)
            ogrenci_map.setdefault(key, []).append({
                "okulno":     mo.okulno,
                "adi_soyadi": mo.adi_soyadi,
                "sinifsube":  mo.sinifsube,
            })

    gunler = (
        mazeret.gunler
        .prefetch_related("oturumlar__dersler__ders")
        .order_by("tarih")
    )

    # Oturum bazında ders + öğrenci listesini hazırla
    gunler_veri = []
    for gun in gunler:
        oturumlar_veri = []
        for oturum in gun.oturumlar.order_by("oturum_no"):
            dersler_veri = []
            for od in oturum.dersler.select_related("ders").order_by("ders__ders_adi"):
                key = (od.ders_id, od.sinav_turu)
                dersler_veri.append({
                    "od":        od,
                    "ogrenciler": ogrenci_map.get(key, []),
                })
            oturumlar_veri.append({"oturum": oturum, "dersler": dersler_veri})
        gunler_veri.append({"gun": gun, "oturumlar": oturumlar_veri})

    return gunler_veri
