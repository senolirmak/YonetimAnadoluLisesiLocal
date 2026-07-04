from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from okul.auth import (  # noqa: F401 — re-export
    _UST_YONETIM_GRUPLARI as TARIH_DEGISTIREBILIR_GRUPLAR,
    is_mudur_yardimcisi,
    is_ust_yonetici,
    ust_yonetici_required,
)

YONETICI_GRUPLAR = {"mudur_yardimcisi", "okul_muduru", "rehber_ogretmen", "disiplin_kurulu"}


def is_yonetici(user):
    return user.is_superuser or user.groups.filter(name__in=YONETICI_GRUPLAR).exists()


def is_tarih_degistirebilir(user):
    return is_ust_yonetici(user)


def mudur_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_tarih_degistirebilir(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def mudur_yardimcisi_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def yonetici_required(view_func):
    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_yonetici(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


class MudurYardimcisiMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
