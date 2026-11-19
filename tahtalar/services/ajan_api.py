"""Tahtadaki akal-eta-yonetim uygulamasının
(tahtalar/akal-eta-yonetim/akal_eta_yonetim.py) sunucu tarafı.

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
    kendini_guncelleme_bilgisini_isle(tahta, veri.get("kendini_guncelleme"))
    eta_bilgisini_isle(tahta, veri.get("eta"))
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


GECERLI_OTO_GUNCELLEME_DURUMLARI = {k for k, _ in Tahta.OTO_GUNCELLEME_SECENEKLERI}
SURUM_KALIBI = re.compile(r"^\d+\.\d+\.\d+$")


def kendini_guncelleme_bilgisini_isle(tahta, bilgi):
    """{'durum', 'zaman', 'hedef'}: tahtanın APT deposundan kendini güncellemesi.
    Bilgi yoksa önceki kayıt korunur."""
    if not isinstance(bilgi, dict):
        return
    durum = _secenek(bilgi.get("durum"), GECERLI_OTO_GUNCELLEME_DURUMLARI)
    hedef = bilgi.get("hedef")
    zaman = _epoch(bilgi.get("zaman"))
    if not durum or zaman is None or not isinstance(hedef, str) or not SURUM_KALIBI.match(hedef):
        return
    tahta.oto_guncelleme_durumu = durum
    tahta.oto_guncelleme_hedef = hedef
    tahta.oto_guncelleme_zamani = zaman


def _epoch(deger):
    if not isinstance(deger, int) or isinstance(deger, bool) or deger <= 0:
        return None
    try:
        return datetime.datetime.fromtimestamp(deger, tz=datetime.UTC)
    except (OverflowError, OSError, ValueError):
        return None


def eta_bilgisini_isle(tahta, bilgi):
    """Ajanın son ETA envanter sorgusu:
    {'kayitli': bool|None, 'okul_kodu', 'okul_adi', 'birim_adi', 'hata', 'zaman': epoch}.
    Bilgi yoksa (eski ajan ya da henüz sorgulanmamış) önceki kayıt korunur.
    Sorgu başarısızsa (kayitli None) son bilinen kayıt bilgisi korunur, yalnızca
    hata ve zaman güncellenir."""
    if not isinstance(bilgi, dict):
        return
    zaman = _epoch(bilgi.get("zaman"))
    if zaman is None:
        return
    tahta.eta_kontrol_zamani = zaman
    tahta.eta_hata = _metin(bilgi, "hata", 255)
    kayitli = bilgi.get("kayitli")
    if not isinstance(kayitli, bool):
        return
    tahta.eta_kayitli = kayitli
    if kayitli:
        tahta.eta_okul_kodu = _metin(bilgi, "okul_kodu", 20)
        tahta.eta_okul_adi = _metin(bilgi, "okul_adi", 200)
        birim = _metin(bilgi, "birim_adi", 20)
        # Birim adı ETA'da değiştiyse (panelden ya da tahtadaki eta-register ile)
        # tahtanın adı da ETA'daki ada uyar. Değişmediyse elle verilen ada dokunulmaz.
        if birim and birim != tahta.eta_birim_adi:
            _eta_birim_adini_tahta_adi_yap(tahta, {"birim_adi": birim})
        tahta.eta_birim_adi = birim
    else:
        tahta.eta_okul_kodu = tahta.eta_okul_adi = tahta.eta_birim_adi = ""


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
        komut = TahtaKomutu.objects.filter(
            pk=komut_id, tahta=tahta, durum=TahtaKomutu.GONDERILDI
        ).first()
        if komut is None:
            continue
        komut.durum = durum
        komut.sonuc_mesaji = _metin(sonuc, "mesaj", 255)
        komut.tamamlanma = timezone.now()
        komut.save(update_fields=["durum", "sonuc_mesaji", "tamamlanma"])
        if komut.komut == TahtaKomutu.ETA_KAYDET and durum == TahtaKomutu.TAMAMLANDI:
            _eta_birim_adini_tahta_adi_yap(tahta, komut.parametreler)


def _eta_birim_adini_tahta_adi_yap(tahta, parametreler):
    """ETA'ya kayıt/güncelleme başarılıysa tahtanın adı verilen birim adı olur;
    böylece paneldeki tahta adı ETA'daki adla aynı kalır. Tahta, çağıran
    (durum_guncelle) tarafından kaydedilir."""
    birim = parametreler.get("birim_adi") if isinstance(parametreler, dict) else None
    birim = " ".join(birim.split()) if isinstance(birim, str) else ""
    if birim:
        tahta.ad = birim[: Tahta._meta.get_field("ad").max_length]


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
    return [
        {"id": k.pk, "komut": k.komut, **({"parametreler": k.parametreler} if k.parametreler else {})}
        for k in komutlar
    ]


def komut_olustur(tahtalar, komut, kullanici=None):
    """Seçilen tahtalara parametresiz komut ekler. Aynı komut tahtada zaten
    bekliyorsa yenisi eklenmez. Döner: oluşturulan komut sayısı."""
    if komut not in {k for k, _ in TahtaKomutu.PANEL_KOMUTLARI}:
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


ETA_OKUL_KODU = re.compile(r"^[0-9]{1,12}$")
ETA_BIRIM_EN_AZ, ETA_BIRIM_EN_COK = 2, 12  # eta-register'ın sınırı


def eta_okul_kodu_dogrula(kod):
    kod = (kod or "").strip()
    if not ETA_OKUL_KODU.match(kod):
        raise ValueError("Okul (tesis) kodu yalnızca rakamlardan oluşmalı.")
    return kod


def eta_birim_adi_dogrula(ad):
    ad = " ".join((ad or "").split())
    if not ETA_BIRIM_EN_AZ <= len(ad) <= ETA_BIRIM_EN_COK:
        raise ValueError(
            f"Birim adı {ETA_BIRIM_EN_AZ}-{ETA_BIRIM_EN_COK} karakter olmalı: “{ad}”."
        )
    return ad


def eta_birim_onerisi(tahta):
    """Birim adı için öneri: ETA'daki mevcut ad, yoksa Lider'deki şube adı, yoksa tahta adı."""
    for aday in (
        tahta.eta_birim_adi,
        tahta.envanter.sube_adi if tahta.envanter_id else "",
        tahta.ad,
    ):
        aday = " ".join((aday or "").split())
        if aday:
            return aday[:ETA_BIRIM_EN_COK].strip()
    return ""


@transaction.atomic
def eta_kayit_komutu_olustur(tahta_birimleri, okul_kodu, kullanici=None):
    """[(tahta, birim_adi)] için eta_kaydet komutu ekler. Tahtada bekleyen eski
    eta_kaydet komutu varsa iptal edilir (son verilen geçerlidir).
    Döner: oluşturulan komut sayısı. Değerler önceden doğrulanmış olmalı."""
    suresi_dolanlari_iptal_et()
    tahtalar = [t for t, _ in tahta_birimleri]
    TahtaKomutu.objects.filter(
        tahta__in=tahtalar, komut=TahtaKomutu.ETA_KAYDET, durum=TahtaKomutu.BEKLIYOR
    ).update(durum=TahtaKomutu.IPTAL, sonuc_mesaji="Yerine yeni kayıt komutu verildi.")
    TahtaKomutu.objects.bulk_create(
        [
            TahtaKomutu(
                tahta=t,
                komut=TahtaKomutu.ETA_KAYDET,
                parametreler={"okul_kodu": okul_kodu, "birim_adi": birim},
                olusturan=kullanici,
            )
            for t, birim in tahta_birimleri
        ]
    )
    return len(tahta_birimleri)
