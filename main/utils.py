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
