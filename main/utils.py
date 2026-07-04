def _only_ogretmen(user):
    """Sadece ogretmen grubunda olup yönetici gruplarında olmayan kullanıcı."""
    if user.is_superuser:
        return False
    gruplar = set(user.groups.values_list("name", flat=True))
    yonetici = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    return "ogretmen" in gruplar and not (gruplar & yonetici)


def _ogretmen_menu_gorumu(user):
    """ogretmen + rehber_ogretmen + disiplin_kurulu → nöbet okuma sayfalarına erişim."""
    if user.is_superuser:
        return False
    gruplar = set(user.groups.values_list("name", flat=True))
    ust_yonetici = {"mudur_yardimcisi", "okul_muduru"}
    return bool(gruplar & {"ogretmen", "rehber_ogretmen", "disiplin_kurulu"}) and not (
        gruplar & ust_yonetici
    )


_DAYS_MAP = {
    0: "Monday",
    1: "Tuesday",
    2: "Wednesday",
    3: "Thursday",
    4: "Friday",
    5: "Saturday",
    6: "Sunday",
}

_GUN_TR = {
    "Monday": "Pazartesi",
    "Tuesday": "Salı",
    "Wednesday": "Çarşamba",
    "Thursday": "Perşembe",
    "Friday": "Cuma",
}

_TR_GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]


def get_ogretmen_gorev_verileri(user, today):
    """
    Öğretmenin nöbet / ders doldurma / sınav gözetim / sorumluluk görev özetini döner.

    main/views.py:index() ve main/views.py:gorevlerim() tarafından ortak kullanılır.
    """
    from django.db.models import Q
    from dersprogrami.models import DersProgrami
    from nobet.models import NobetGecmisi, NobetGorevi
    from okul.utils import get_aktif_dp_tarihi

    _gruplar = set(user.groups.values_list("name", flat=True))
    _yonetici_gruplar = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}
    _salt_ogretmen = not user.is_superuser and "ogretmen" in _gruplar and not bool(_gruplar & _yonetici_gruplar)
    personel_bagli = _salt_ogretmen and hasattr(user, "personel")

    rehberlik_sinif_sube = None
    ogretmen_nobetleri = []
    atanan_dersler = []
    if personel_bagli:
        _aktif_tarih = get_aktif_dp_tarihi()
        _dp_f = {"uygulama_tarihi": _aktif_tarih} if _aktif_tarih else {}
        rehberlik_ders = (
            DersProgrami.objects.filter(
                ogretmen=user.personel,
                ders__ders_adi__iexact="rehberlik ve yönlendirme",
                **_dp_f,
            )
            .select_related("sinif_sube", "ders")
            .first()
        )
        if rehberlik_ders and rehberlik_ders.sinif_sube:
            rehberlik_sinif_sube = str(rehberlik_ders.sinif_sube)

        try:
            nobet_ogretmen = user.personel.ogretmen
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

    sinav_gozetim_var = False
    sinav_aktif_var = False
    if hasattr(user, "personel") and user.personel:
        try:
            from sinav.models import (
                OturmaPlani as _OturmaPlani,
                SinavBilgisi as _SinavBilgisi,
                TakvimUretim as _TakvimUretim,
            )
            _personel = user.personel
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
    if hasattr(user, "personel") and user.personel:
        try:
            from sorumluluk.models import SorumluGozetmen as _SGZ, SorumluKomisyonUyesi as _SKU
            _p = user.personel
            sorumluluk_gorev_var = (
                _SKU.objects.filter(Q(uye1=_p) | Q(uye2=_p)).exists()
                or _SGZ.objects.filter(gozetmen=_p).exists()
            )
        except Exception:
            pass

    return {
        "personel_bagli": personel_bagli,
        "rehberlik_sinif_sube": rehberlik_sinif_sube,
        "ogretmen_nobetleri": ogretmen_nobetleri,
        "atanan_dersler": atanan_dersler,
        "sinav_gozetim_var": sinav_gozetim_var,
        "sinav_aktif_var": sinav_aktif_var,
        "sorumluluk_gorev_var": sorumluluk_gorev_var,
        "sorumluluk_takvim_var": sorumluluk_takvim_var,
    }
