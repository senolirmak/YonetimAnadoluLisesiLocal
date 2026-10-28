"""Öğretmenin faaliyet tarihi için geriye dönük giriş sınırı.

Öğretmen, bugünden en fazla GERIYE_DONUK_GUN gün önceki bir tarihe faaliyet
işleyebilir. Müdür yardımcısı (ve superuser) bu sınırdan muaftır.
"""

import datetime

from django.utils import timezone

from okul.auth import is_mudur_yardimcisi

GERIYE_DONUK_GUN = 7


def en_erken_tarih(bugun=None):
    """Öğretmenin seçebileceği en eski faaliyet tarihi."""
    bugun = bugun or timezone.localdate()
    return bugun - datetime.timedelta(days=GERIYE_DONUK_GUN)


def sinirdan_muaf_mi(user):
    return is_mudur_yardimcisi(user)


def tarih_hatasi(user, tarih, mevcut_tarih=None):
    """Tarih kurala uymuyorsa hata metnini, uyuyorsa None döndürür.

    `mevcut_tarih`: düzenlenen faaliyetin kayıtlı tarihi. Tarih değiştirilmeden
    yapılan düzenlemeler (örn. reddedilen eski bir faaliyeti düzeltme) engellenmez.
    """
    if sinirdan_muaf_mi(user):
        return None
    if mevcut_tarih is not None and tarih == mevcut_tarih:
        return None
    sinir = en_erken_tarih()
    if tarih < sinir:
        return (
            f"Faaliyetler en fazla {GERIYE_DONUK_GUN} gün geriye dönük işlenebilir. "
            f"Seçebileceğiniz en eski tarih: {sinir:%d.%m.%Y}. Daha eski bir faaliyet "
            "için müdür yardımcısına başvurun."
        )
    return None
