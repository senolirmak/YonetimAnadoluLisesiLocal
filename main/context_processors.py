YONETICI_GRUPLAR = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
TARIH_DEGISTIREBILIR_GRUPLAR = {"mudur_yardimcisi", "okul_muduru"}


def kullanici_rol(request):
    """Tüm template'lerde kullanıcı rol bilgilerini erişilebilir kılar."""
    if request.user.is_authenticated:
        gruplar = set(request.user.groups.values_list("name", flat=True))
        superuser = request.user.is_superuser
        mudur_yardimcisi = superuser or "mudur_yardimcisi" in gruplar

        bekleyen_faaliyet = 0
        if mudur_yardimcisi:
            from faaliyet.models import Faaliyet

            bekleyen_faaliyet = Faaliyet.objects.filter(durum=Faaliyet.DURUM_BEKLEMEDE).count()

        is_yonetici = superuser or bool(gruplar & YONETICI_GRUPLAR)
        is_ust_yonetici = superuser or "mudur_yardimcisi" in gruplar or "okul_muduru" in gruplar
        return {
            "is_mudur_yardimcisi": mudur_yardimcisi,
            "is_yonetici": is_yonetici,
            "is_tarih_degistirebilir": superuser or bool(gruplar & TARIH_DEGISTIREBILIR_GRUPLAR),
            "bekleyen_faaliyet_sayisi": bekleyen_faaliyet,
            "is_rehber_ogretmen": superuser or "rehber_ogretmen" in gruplar,
            "is_disiplin_kurulu": superuser or "disiplin_kurulu" in gruplar,
            "is_ogretmen": not is_yonetici and "ogretmen" in gruplar,
            # ogretmen + rehber_ogretmen + disiplin_kurulu → nöbet okuma menüsü
            "is_ogretmen_menu": not is_ust_yonetici
            and bool(gruplar & {"ogretmen", "rehber_ogretmen", "disiplin_kurulu"}),
        }
    return {
        "is_mudur_yardimcisi": False,
        "is_yonetici": False,
        "is_tarih_degistirebilir": False,
        "bekleyen_faaliyet_sayisi": 0,
        "is_rehber_ogretmen": False,
        "is_disiplin_kurulu": False,
        "is_ogretmen": False,
        "is_ogretmen_menu": False,
    }
