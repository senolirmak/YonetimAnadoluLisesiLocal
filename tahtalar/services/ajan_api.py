"""Tahtadaki ajanın (tahtalar/ajan/okul_ajan.py) sunucu tarafı.

Ajan iki uç nokta kullanır:
  - kayıt: ortak kayıt anahtarıyla bir kez kaydolur, tahtaya özel token alır.
  - durum: 60 sn'de bir durumunu bildirir, önceki komutların sonucunu iletir
    ve bekleyen komutları alır.

Token veritabanında yalnızca SHA-256 özeti olarak tutulur.
"""

import datetime
import hashlib
import hmac
import re
import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address
from django.db import transaction
from django.utils import timezone

from tahtalar.models import KOMUT_GECERLILIK, Tahta, TahtaEnvanteri, TahtaKomutu

GECERLI_AHENK_DURUMLARI = {k for k, _ in Tahta.AHENK_SECENEKLERI}
AJAN_SONUC_DURUMLARI = {TahtaKomutu.TAMAMLANDI, TahtaKomutu.BASARISIZ}


class KayitHatasi(Exception):
    pass


def token_ozeti(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _secenek(deger, gecerliler):
    """Ajandan gelen değer izin verilen metinlerden biriyse onu, değilse "" döner.
    (Liste/sözlük gibi değerler kümede aranırken TypeError vermesin.)"""
    return deger if isinstance(deger, str) and deger in gecerliler else ""


def _metin(veri, alan, uzunluk):
    deger = veri.get(alan)
    if not isinstance(deger, str):
        return ""
    return deger.strip()[:uzunluk]


def kayit_anahtari_dogru_mu(anahtar):
    beklenen = getattr(settings, "TAHTA_KAYIT_ANAHTARI", "")
    if not beklenen or not isinstance(anahtar, str):
        return False
    return hmac.compare_digest(anahtar.encode(), beklenen.encode())


def tahta_kaydet(veri):
    """Tahtayı kaydeder (ya da yeniden kurulmuşsa token'ını yeniler).

    Döner: (tahta, düz token). Düz token yalnızca bu yanıtta verilir.
    """
    if not kayit_anahtari_dogru_mu(veri.get("kayit_anahtari")):
        raise KayitHatasi("Kayıt anahtarı geçersiz.")
    makine_kimligi = _metin(veri, "makine_kimligi", 64)
    if not makine_kimligi:
        raise KayitHatasi("Makine kimliği eksik.")

    token = secrets.token_urlsafe(32)
    hostname = _metin(veri, "hostname", 100)
    tahta = Tahta.objects.filter(makine_kimligi=makine_kimligi).first()
    if tahta is None:
        tahta = Tahta(makine_kimligi=makine_kimligi, ad=hostname or makine_kimligi[:12])
    elif not tahta.aktif:
        raise KayitHatasi("Bu tahta pasife alınmış.")
    tahta.token_ozeti = token_ozeti(token)
    tahta.save()
    return tahta, token


def token_ile_tahta(token):
    if not token:
        return None
    return Tahta.objects.filter(token_ozeti=token_ozeti(token), aktif=True).first()


def durum_guncelle(tahta, veri):
    tahta.hostname = _metin(veri, "hostname", 100)
    tahta.isletim_sistemi = _metin(veri, "isletim_sistemi", 150)
    tahta.ajan_surumu = _metin(veri, "ajan_surumu", 20)

    ip = _metin(veri, "ip_adresi", 45)
    try:
        validate_ipv46_address(ip)
        tahta.ip_adresi = ip
    except ValidationError:
        tahta.ip_adresi = None

    sure = veri.get("acik_kalma_suresi")
    tahta.acik_kalma_suresi = sure if isinstance(sure, int) and sure >= 0 else None

    ahenk = veri.get("ahenk_servisi")
    tahta.ahenk_servisi = _secenek(ahenk, GECERLI_AHENK_DURUMLARI) or Tahta.AHENK_BILINMIYOR

    kayitli = veri.get("meb_kayitli")
    tahta.meb_kayitli = kayitli if isinstance(kayitli, bool) else None

    guncelleme_bilgisini_isle(tahta, veri.get("guncelleme"))
    tahta.oturumlar = oturum_listesi(veri.get("oturumlar"))

    macler = mac_listesi(veri.get("mac_adresleri"))
    tahta.mac_adresleri = ", ".join(macler)[:255]
    if tahta.envanter_id is None:
        envanteri_bagla(tahta, macler)

    tahta.son_gorulme = timezone.now()
    tahta.save()


OTURUM_TURLERI = {"x11", "wayland", "tty", "mir", "unspecified"}


EBA_OZETI = re.compile(r"^[0-9a-f]{32}$")


def eba_personelleri(ozetler):
    """{md5(eba_id): Personel} — EBA hesabını bağlamış personel için.

    Tahta, ETAP'ın EBA girişinin GECOS'a yazdığı md5(eba_id) değerini gönderir;
    EbaHesap düz eba_id tuttuğundan eşleştirme burada özet üzerinden yapılır.
    """
    if not ozetler:
        return {}
    from ebagiris.models import EbaHesap

    eslesme = {}
    for hesap in EbaHesap.objects.select_related("personel"):
        ozet = hashlib.md5(hesap.eba_id.encode()).hexdigest()
        if ozet in ozetler:
            eslesme[ozet] = hesap.personel
    return eslesme


def oturum_listesi(degerler):
    """Ajanın bildirdiği oturumları doğrular; yalnızca bilinen alanlar saklanır.

    EBA özeti saklanmaz (KVKK: gereğinden fazla veri tutulmaz); yalnızca EBA
    girişi olup olmadığı ve eşleşen personel kaydedilir.
    """
    if not isinstance(degerler, list):
        return []
    degerler = [o for o in degerler[:10] if isinstance(o, dict)]
    ozet_listesi = [_eba_ozeti(o) for o in degerler]
    personeller = eba_personelleri({oz for oz in ozet_listesi if oz})
    liste = []
    for oturum, ozet in zip(degerler, ozet_listesi):
        kullanici = _metin(oturum, "kullanici", 64)
        if not kullanici:
            continue
        baslangic = oturum.get("baslangic")
        liste.append(
            {
                "kullanici": kullanici,
                "ad": _metin(oturum, "ad", 100),
                "aktif": oturum.get("aktif") is True,
                "tur": _secenek(oturum.get("tur"), OTURUM_TURLERI),
                "baslangic": baslangic if isinstance(baslangic, int) and baslangic > 0 else None,
                "eba": bool(ozet),
                **_personel_alanlari(personeller.get(ozet)),
            }
        )
    return liste


def _eba_ozeti(oturum):
    deger = oturum.get("eba_ozeti")
    return deger if isinstance(deger, str) and EBA_OZETI.match(deger) else ""


def _personel_alanlari(personel):
    if personel is None:
        return {"personel_id": None, "personel": ""}
    return {"personel_id": personel.pk, "personel": personel.adi_soyadi}


GECERLI_GUNCELLEME_DURUMLARI = {k for k, _ in Tahta.GUNCELLEME_SECENEKLERI}


def guncelleme_bilgisini_isle(tahta, bilgi):
    """Ajanın bildirdiği son güncelleme: {'durum': ..., 'zaman': epoch sn}.
    Bilgi yoksa (hiç güncellenmemiş) önceki kayıt korunur."""
    if not isinstance(bilgi, dict) or not _secenek(
        bilgi.get("durum"), GECERLI_GUNCELLEME_DURUMLARI
    ):
        return
    zaman = bilgi.get("zaman")
    if not isinstance(zaman, int) or zaman <= 0:
        return
    try:
        tahta.guncelleme_zamani = datetime.datetime.fromtimestamp(zaman, tz=datetime.UTC)
    except (OverflowError, OSError, ValueError):
        return
    tahta.guncelleme_durumu = bilgi["durum"]


def mac_normalize(deger):
    """'AA-BB-CC-11-22-33' → 'aa:bb:cc:11:22:33'; geçersizse boş metin."""
    if not isinstance(deger, str):
        return ""
    onaltilik = re.sub(r"[^0-9a-fA-F]", "", deger).lower()
    if len(onaltilik) != 12 or onaltilik == "0" * 12:
        return ""
    return ":".join(onaltilik[i : i + 2] for i in range(0, 12, 2))


def mac_listesi(degerler):
    if not isinstance(degerler, list):
        return []
    macler = []
    for deger in degerler[:10]:
        mac = mac_normalize(deger)
        if mac and mac not in macler:
            macler.append(mac)
    return macler


def envanteri_bagla(tahta, macler):
    """Tahtayı MAC adresi eşleşen ve henüz bağlanmamış envanter kaydına bağlar.
    Tahtanın adı hâlâ ajanın verdiği bilgisayar adıysa şube adıyla değiştirilir."""
    if not macler:
        return
    envanter = TahtaEnvanteri.objects.filter(mac_adresi__in=macler, tahta__isnull=True).first()
    if envanter is None:
        return
    tahta.envanter = envanter
    if tahta.ad in ("", tahta.hostname, tahta.makine_kimligi[:12]):
        tahta.ad = envanter.sube_adi
    if not tahta.konum:
        tahta.konum = envanter.sube_adi


def sonuclari_isle(tahta, sonuclar):
    """Ajanın bildirdiği komut sonuçlarını kaydeder. Yalnızca bu tahtaya ait
    ve tahtaya gönderilmiş komutlar güncellenir."""
    if not isinstance(sonuclar, list):
        return
    for sonuc in sonuclar[:20]:
        if not isinstance(sonuc, dict):
            continue
        durum = sonuc.get("durum")
        komut_id = sonuc.get("id")
        if not _secenek(durum, AJAN_SONUC_DURUMLARI) or not isinstance(komut_id, int):
            continue
        TahtaKomutu.objects.filter(pk=komut_id, tahta=tahta, durum=TahtaKomutu.GONDERILDI).update(
            durum=durum,
            sonuc_mesaji=_metin(sonuc, "mesaj", 255),
            tamamlanma=timezone.now(),
        )


def suresi_dolanlari_iptal_et(tahta=None):
    komutlar = TahtaKomutu.objects.filter(
        durum=TahtaKomutu.BEKLIYOR, olusturma__lt=timezone.now() - KOMUT_GECERLILIK
    )
    if tahta is not None:
        komutlar = komutlar.filter(tahta=tahta)
    return komutlar.update(durum=TahtaKomutu.IPTAL, sonuc_mesaji="Süresi doldu, tahtaya ulaşmadı.")


@transaction.atomic
def bekleyen_komutlari_teslim_et(tahta):
    suresi_dolanlari_iptal_et(tahta)
    komutlar = list(
        TahtaKomutu.objects.select_for_update()
        .filter(tahta=tahta, durum=TahtaKomutu.BEKLIYOR)
        .order_by("olusturma")
    )
    simdi = timezone.now()
    for komut in komutlar:
        komut.durum = TahtaKomutu.GONDERILDI
        komut.gonderilme = simdi
        komut.save(update_fields=["durum", "gonderilme"])
    return [{"id": k.pk, "komut": k.komut} for k in komutlar]


def komut_olustur(tahtalar, komut, kullanici=None):
    """Seçilen tahtalara komut ekler. Aynı komut tahtada zaten bekliyorsa
    yenisi eklenmez. Döner: oluşturulan komut sayısı."""
    if komut not in {k for k, _ in TahtaKomutu.KOMUT_SECENEKLERI}:
        raise ValueError(f"Bilinmeyen komut: {komut}")
    suresi_dolanlari_iptal_et()
    bekleyenler = set(
        TahtaKomutu.objects.filter(
            tahta__in=tahtalar, komut=komut, durum=TahtaKomutu.BEKLIYOR
        ).values_list("tahta_id", flat=True)
    )
    yeni = [
        TahtaKomutu(tahta=t, komut=komut, olusturan=kullanici)
        for t in tahtalar
        if t.pk not in bekleyenler
    ]
    TahtaKomutu.objects.bulk_create(yeni)
    return len(yeni)
