"""Testler için ortak, sahte veri üreten yardımcılar.

Gerçek öğrenci/personel verisi kullanılmaz; her çağrı benzersiz, uydurma bir kayıt üretir.
Dosya adı bilerek `test*.py` kalıbına uymaz — Django test keşfi bunu test modülü saymaz.

Kullanım:
    from okul.testing import kullanici_olustur, personel_olustur, ...
"""

import datetime
import itertools

from django.contrib.auth.models import Group, User

_sayac = itertools.count(1)


def _sira():
    return next(_sayac)


def kullanici_olustur(*gruplar, superuser=False, **kwargs):
    """Verilen Django gruplarına üye bir kullanıcı oluşturur (gruplar yoksa açılır)."""
    n = _sira()
    kwargs.setdefault("username", f"kullanici{n}")
    kwargs.setdefault("password", "test-sifre")
    if superuser:
        user = User.objects.create_superuser(email=f"k{n}@ornek.test", **kwargs)
    else:
        user = User.objects.create_user(**kwargs)
    for ad in gruplar:
        user.groups.add(Group.objects.get_or_create(name=ad)[0])
    return user


def personel_olustur(**kwargs):
    from okul.models import Personel

    n = _sira()
    kwargs.setdefault("kimlikno", f"{10000000000 + n}")
    kwargs.setdefault("adi_soyadi", f"Öğretmen {n:03d}")
    return Personel.objects.create(**kwargs)


def nobet_ogretmen_olustur(personel=None, **kwargs):
    from nobet.models import NobetOgretmen

    kwargs.setdefault("uygulama_tarihi", datetime.date(2025, 9, 1))
    return NobetOgretmen.objects.create(personel=personel or personel_olustur(), **kwargs)


def nobet_yeri_olustur(ad=None, **kwargs):
    from nobet.models import NobetYerleri

    return NobetYerleri.objects.create(ad=ad or f"Yer {_sira()}", **kwargs)


def nobet_gorevi_olustur(ogretmen=None, nobet_yeri=None, nobet_gun="Monday", **kwargs):
    from nobet.models import NobetGorevi

    kwargs.setdefault("uygulama_tarihi", datetime.date(2025, 9, 1))
    return NobetGorevi.objects.create(
        ogretmen=ogretmen or nobet_ogretmen_olustur(),
        nobet_yeri=nobet_yeri or nobet_yeri_olustur(),
        nobet_gun=nobet_gun,
        **kwargs,
    )


def sinif_sube_olustur(sinif=9, sube="A"):
    from okul.models import SinifSube

    return SinifSube.objects.get_or_create(sinif=sinif, sube=sube)[0]


def ders_saati_olustur(no):
    from okul.models import DersSaatleri

    baslangic = datetime.time(8 + no - 1, 0)
    bitis = datetime.time(8 + no - 1, 40)
    return DersSaatleri.objects.get_or_create(
        derssaati_no=no,
        defaults={"derssaati_baslangic": baslangic, "derssaati_bitis": bitis},
    )[0]


def ders_programi_olustur(personel, saat, sinif_sube=None, gun="Monday", **kwargs):
    from dersprogrami.models import DersProgrami

    kwargs.setdefault("uygulama_tarihi", datetime.date(2025, 9, 1))
    return DersProgrami.objects.create(
        ogretmen=personel,
        gun=gun,
        ders_saati=ders_saati_olustur(saat),
        sinif_sube=sinif_sube or sinif_sube_olustur(),
        **kwargs,
    )


def devamsizlik_olustur(ogretmen, baslangic, sure=1, **kwargs):
    from personeldevamsizlik.models import Devamsizlik

    return Devamsizlik.objects.create(
        ogretmen=ogretmen, baslangic_tarihi=baslangic, sure=sure, **kwargs
    )


def ogrenci_olustur(sinif=9, sube="A", **kwargs):
    from ogrenci.models import Ogrenci

    n = _sira()
    kwargs.setdefault("okulno", n)
    kwargs.setdefault("tckimlikno", f"{20000000000 + n}")
    kwargs.setdefault("adi", f"Öğrenci{n}")
    kwargs.setdefault("soyadi", "Örnek")
    kwargs.setdefault("dogumtarihi", datetime.date(2010, 1, 1))
    kwargs.setdefault("cinsiyet", "E")
    return Ogrenci.objects.create(sinif=sinif, sube=sube, **kwargs)


def aktif_egitim_yili_olustur(egitim_yili="2025-2026"):
    """Eğitim yılını oluşturur ve OkulBilgi'de aktif yıl yapar."""
    from okul.models import EgitimOgretimYili, OkulBilgi

    bas = int(egitim_yili[:4])
    yil, _ = EgitimOgretimYili.objects.get_or_create(
        egitim_yili=egitim_yili,
        defaults={
            "egitim_baslangic": datetime.date(bas, 9, 1),
            "egitim_bitis": datetime.date(bas + 1, 6, 20),
        },
    )
    OkulBilgi.objects.update_or_create(
        pk=1, defaults={"okul_adi": "Örnek Anadolu Lisesi", "okul_egtyil": yil}
    )
    return yil


def ders_olustur(ders_adi=None, **kwargs):
    from okul.models import DersHavuzu

    return DersHavuzu.objects.create(ders_adi=ders_adi or f"DERS {_sira()}", **kwargs)


def zamani_dondur(tarih, saat, dakika=0):
    """`timezone.localdate()` / argümansız `timezone.localtime()` sabit zamanı döndürsün.

    Kullanım: `with zamani_dondur(datetime.date(2025, 9, 8), 10, 15): ...`
    """
    from unittest import mock

    from django.utils import timezone

    sabit = timezone.make_aware(datetime.datetime.combine(tarih, datetime.time(saat, dakika)))
    gercek_localtime = timezone.localtime

    def sahte_localtime(value=None, timezone=None):
        if value is None:
            return sabit
        return gercek_localtime(value, timezone)

    return mock.patch.multiple(
        "django.utils.timezone",
        localdate=mock.Mock(return_value=tarih),
        localtime=sahte_localtime,
    )


def yetki_dogrula(testcase, urller, yasak_gruplar=(), izinli_gruplar=(), method="get"):
    """Her URL için: anonim → login sayfasına yönlenir, `yasak_gruplar` → 403,
    `izinli_gruplar` → 403 ya da login yönlendirmesi ALMAZ (sayfanın kendisi 200/302/404 dönebilir).

    `urller`: tam URL yolları listesi (reverse edilmiş)."""
    from django.conf import settings

    istek = getattr(testcase.client, method)
    testcase.client.logout()
    for url in urller:
        with testcase.subTest(kim="anonim", url=url):
            resp = istek(url)
            testcase.assertEqual(resp.status_code, 302)
            testcase.assertTrue(resp["Location"].startswith(settings.LOGIN_URL), resp["Location"])
    for grup in yasak_gruplar:
        testcase.client.force_login(kullanici_olustur(grup))
        for url in urller:
            with testcase.subTest(kim=grup, url=url):
                testcase.assertEqual(istek(url).status_code, 403)
    for grup in izinli_gruplar:
        testcase.client.force_login(kullanici_olustur(grup))
        for url in urller:
            with testcase.subTest(kim=grup, url=url):
                resp = istek(url)
                testcase.assertNotEqual(resp.status_code, 403)
                if resp.status_code == 302:
                    testcase.assertFalse(resp["Location"].startswith(settings.LOGIN_URL))
    testcase.client.logout()
