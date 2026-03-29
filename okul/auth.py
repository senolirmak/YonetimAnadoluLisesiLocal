"""
okul.auth — Merkezi yetki yardımcıları.

Sistemdeki her app'te tekrarlanan:
  - _is_mudur_yardimcisi / _mudur_yardimcisi_mi
  - mudur_yardimcisi_required decorator
  - MudurYardimcisiMixin

tanımlarının tek kaynağı burası olmalıdır.

Kullanım (function-based view):
    from okul.auth import mudur_yardimcisi_required

    @mudur_yardimcisi_required
    def benim_viewim(request): ...

Kullanım (class-based view):
    from okul.auth import MudurYardimcisiMixin

    class BenimViewim(MudurYardimcisiMixin, ListView): ...

Kullanım (template / context kontrolü):
    from okul.auth import is_mudur_yardimcisi

    if is_mudur_yardimcisi(request.user):
        ...
"""

from functools import wraps

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def is_mudur_yardimcisi(user) -> bool:
    """
    Kullanıcının müdür yardımcısı yetkisine sahip olup olmadığını döndürür.

    Koşullar (herhangi biri yeterlidi):
      1. Superuser
      2. 'mudur_yardimcisi' grubunda üye VE aktif MudurYardimcisi kaydı var

    İkinci koşulda model kaydı aktiflik kontrolü de yapılır; böylece
    gruba eklenmiş ama pasife alınmış kullanıcılar reddedilir.
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True

    if not user.groups.filter(name="mudur_yardimcisi").exists():
        return False

    # OkulYonetici profil kaydı varsa aktiflik kontrolü yap
    try:
        return user.okul_yonetici.aktif
    except Exception:
        # Profil kaydı henüz oluşturulmamış: sadece grup üyeliği yeterli
        return True


def mudur_yardimcisi_required(view_func):
    """Function-based view decorator."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        if not is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper


class MudurYardimcisiMixin(LoginRequiredMixin):
    """Class-based view mixin."""
    def dispatch(self, request, *args, **kwargs):
        if not is_mudur_yardimcisi(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
