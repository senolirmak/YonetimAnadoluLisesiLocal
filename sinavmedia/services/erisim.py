"""Sınav medyası (dinleme/izleme sınavı dosyaları) erişim kuralları.

Dosyalar önceden Nginx tarafından /media/ altından kontrolsüz sunuluyordu: oynatıcı sayfası
saat kısıtı uygulasa da dosya adresini bilen (tahmin eden) herkes, sınavdan önce bile,
giriş yapmadan indirebiliyordu. Artık dosya yalnızca `sinavmedia:dosya` view'ı üzerinden,
aşağıdaki kurala göre verilir (bkz. sinavmedia/views.py: dosya).

İki pencere vardır:
  - Oynatıcı sayfası: sınav saatinden itibaren `TOLERANS_DAKIKA` (öğretmen sayfayı açar).
  - Dosyanın kendisi: sınav saatinden itibaren `DOSYA_PENCERESI_DAKIKA`. Tarayıcı ses/videoyu
    parça parça indirir; dosya 5. dakikada kapanırsa uzun bir dinleme metni yarıda kesilirdi.
"""

from datetime import datetime, timedelta

from django.utils import timezone

TOLERANS_DAKIKA = 5
DOSYA_PENCERESI_DAKIKA = 60


def sinav_baslangici(medya):
    saat = datetime.strptime(medya.takvim.saat, "%H:%M").time()
    return timezone.make_aware(datetime.combine(medya.takvim.tarih, saat))


def kontrolden_muaf_mi(user):
    from okul.auth import is_mudur_yardimcisi

    return user.is_superuser or user.is_staff or is_mudur_yardimcisi(user)


def oynatma_acik_mi(medya, simdi=None):
    """Oynatıcı sayfası / öğretmen medya listesi için (yönetici kontrolü çağıranda)."""
    if medya.serbest:
        return True
    simdi = simdi or timezone.now()
    bas = sinav_baslangici(medya)
    return bas <= simdi <= bas + timedelta(minutes=TOLERANS_DAKIKA)


def dosya_erisimi_var_mi(user, medya, simdi=None):
    if not user.is_authenticated:
        return False
    if medya.serbest or kontrolden_muaf_mi(user):
        return True
    simdi = simdi or timezone.now()
    bas = sinav_baslangici(medya)
    return bas <= simdi <= bas + timedelta(minutes=DOSYA_PENCERESI_DAKIKA)
