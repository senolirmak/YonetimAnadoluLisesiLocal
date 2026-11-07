"""
okul.auth — Merkezi yetki yardımcıları.

Projedeki bütün rol/izin kuralları burada, bir kez yazılır; app'ler kendi
grup kontrolünü yazmaz. Kuralların tamamı `rol_bayraklari()` içindedir;
tekil kontroller (`is_mudur_yardimcisi` vb.) ve şablonlara giden rol
bayrakları (main.context_processors.kullanici_rol) ondan türetilir.

Kullanım (function-based view):
    from okul.auth import mudur_yardimcisi_required

    @mudur_yardimcisi_required
    def benim_viewim(request): ...

Kullanım (class-based view):
    from okul.auth import MudurYardimcisiMixin

    class BenimViewim(MudurYardimcisiMixin, ListView): ...

Kullanım (kod içi kontrol):
    from okul.auth import is_mudur_yardimcisi

    if is_mudur_yardimcisi(request.user):
        ...
"""

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

# ── Grup kümeleri (projede grup adlarının tek kaynağı) ─────────────────────
UST_YONETIM_GRUPLARI = frozenset({"mudur_yardimcisi", "okul_muduru"})
YONETICI_GRUPLARI = UST_YONETIM_GRUPLARI | {"rehber_ogretmen", "disiplin_kurulu"}
# Öğretmen görev sayfalarını (Görevlerim, öğretmen nöbet/sınav sayfaları) kullananlar
OGRETMEN_MENU_GRUPLARI = frozenset({"ogretmen", "rehber_ogretmen", "disiplin_kurulu"})
# Okulun bütün personel grupları
PERSONEL_GRUPLARI = UST_YONETIM_GRUPLARI | OGRETMEN_MENU_GRUPLARI

# Eski adlar
_YONETICI_GRUPLAR = YONETICI_GRUPLARI
_UST_YONETIM_GRUPLARI = UST_YONETIM_GRUPLARI

_BOS_BAYRAKLAR = {
    "mudur_yardimcisi": False,
    "ust_yonetici": False,
    "yonetici": False,
    "rehber_ogretmen": False,
    "disiplin_kurulu": False,
    "salt_ogretmen": False,
    "ogretmen_menu": False,
}


def _yonetici_profili_aktif(user) -> bool:
    """OkulYonetici profili varsa aktifliği; profil yoksa grup üyeliği yeterli sayılır."""
    try:
        return user.okul_yonetici.aktif
    except Exception:
        return True


def rol_bayraklari(user) -> dict:
    """Kullanıcının bütün rol bayrakları — tek grup sorgusuyla.

    - mudur_yardimcisi / ust_yonetici: grup üyeliği VE (varsa) aktif OkulYonetici
      profili; böylece gruba eklenmiş ama pasife alınmış kullanıcılar reddedilir.
      ust_yonetici = müdür yardımcısı veya okul müdürü (planlama modüllerinde
      bu iki rol aynı tam yetkiye sahiptir).
    - yonetici: `ogretmen` dışındaki yönetici gruplarından biri.
    - salt_ogretmen: yalnızca `ogretmen` grubunda, hiçbir yönetici grubunda değil.
    - ogretmen_menu: öğretmen görev sayfalarını kullanan (ogretmen / rehber /
      disiplin kurulu) ve üst yönetici grubunda olmayan.
    Superuser bütün yönetici bayraklarını alır, öğretmen bayraklarını almaz.
    """
    if not user.is_authenticated:
        return dict(_BOS_BAYRAKLAR)
    if user.is_superuser:
        return {**_BOS_BAYRAKLAR, "mudur_yardimcisi": True, "ust_yonetici": True,
                "yonetici": True, "rehber_ogretmen": True, "disiplin_kurulu": True}

    gruplar = set(user.groups.values_list("name", flat=True))
    ust_grubu = bool(gruplar & UST_YONETIM_GRUPLARI)
    aktif = _yonetici_profili_aktif(user) if ust_grubu else True
    yonetici = bool(gruplar & YONETICI_GRUPLARI)
    return {
        "mudur_yardimcisi": "mudur_yardimcisi" in gruplar and aktif,
        "ust_yonetici": ust_grubu and aktif,
        "yonetici": yonetici,
        "rehber_ogretmen": "rehber_ogretmen" in gruplar,
        "disiplin_kurulu": "disiplin_kurulu" in gruplar,
        "salt_ogretmen": "ogretmen" in gruplar and not yonetici,
        "ogretmen_menu": bool(gruplar & OGRETMEN_MENU_GRUPLARI) and not ust_grubu,
    }


# ── Tekil kontroller ────────────────────────────────────────────────────────

def is_mudur_yardimcisi(user) -> bool:
    return rol_bayraklari(user)["mudur_yardimcisi"]


def is_ust_yonetici(user) -> bool:
    """Müdür yardımcısı VEYA okul müdürü (bkz. rol_bayraklari)."""
    return rol_bayraklari(user)["ust_yonetici"]


def is_yonetici(user) -> bool:
    """ogretmen grubu hariç tüm yönetici grupları."""
    return rol_bayraklari(user)["yonetici"]


def is_rehber_ogretmen(user) -> bool:
    return rol_bayraklari(user)["rehber_ogretmen"]


def is_disiplin_kurulu(user) -> bool:
    return rol_bayraklari(user)["disiplin_kurulu"]


def is_salt_ogretmen(user) -> bool:
    return rol_bayraklari(user)["salt_ogretmen"]


def is_ogretmen_menu(user) -> bool:
    return rol_bayraklari(user)["ogretmen_menu"]


# ── Decorator / mixin'ler ───────────────────────────────────────────────────

def _gerektirir(kontrol):
    """Giriş yoksa ?next= ile girişe yönlendiren, kontrol geçmezse 403 veren decorator üretir."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not kontrol(request.user):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


mudur_yardimcisi_required = _gerektirir(is_mudur_yardimcisi)
yonetici_required = _gerektirir(is_yonetici)
ust_yonetici_required = _gerektirir(is_ust_yonetici)


class _KontrolMixin(LoginRequiredMixin):
    kontrol = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()  # login sayfasına yönlendir
        if not type(self).kontrol(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class MudurYardimcisiMixin(_KontrolMixin):
    """Class-based view mixin: yalnızca müdür yardımcısı."""
    kontrol = is_mudur_yardimcisi


class UstYoneticiMixin(_KontrolMixin):
    """Class-based view mixin: müdür yardımcısı veya okul müdürü."""
    kontrol = is_ust_yonetici
