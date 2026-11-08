"""Kurul üyelikleri: yapı (iskelet) üzerinden üye seçimi, otomatik üyeler, öğretmen görevleri
ve görev yükü."""

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from kurul.models import Kurul, KurulTuru, KurulUyesi, KurulYapiKalemi
from ogrenci.models import Ogrenci
from okul.models import Personel

_MUDUR_GOREVLERI = ("Okul Müdürü", "Müdür")
_REHBERLIK_GOREVI = "Rehberlik"


# ── Seçim listeleri ──────────────────────────────────────────────────────────

def personel_secenekleri(kalem):
    """Personel kalemi için seçilebilecek görevdeki personel (kalemin 'kimler arasından' kuralı)."""
    qs = Personel.objects.gorevde()
    secim = kalem.personel_secimi
    if secim == KurulYapiKalemi.SECIM_MUDUR:
        qs = qs.filter(gorev_tipi__in=_MUDUR_GOREVLERI)
    elif secim == KurulYapiKalemi.SECIM_YONETICI:
        qs = qs.filter(gorev_tipi__in=Personel.YONETICI_GOREVLERI)
    elif secim == KurulYapiKalemi.SECIM_MUDUR_YARDIMCISI:
        qs = qs.filter(gorev_tipi="Müdür Yardımcısı")
    elif secim == KurulYapiKalemi.SECIM_OGRETMEN:
        qs = qs.exclude(gorev_tipi__in=Personel.YONETICI_GOREVLERI)
    elif secim == KurulYapiKalemi.SECIM_REHBER:
        qs = qs.filter(gorev_tipi=_REHBERLIK_GOREVI)
    return qs.order_by("adi_soyadi")


def ogrenci_secenekleri():
    """Yeni görev ataması: yalnızca okulda kayıtlı (aktif) öğrenciler (bkz. CLAUDE.md)."""
    return Ogrenci.objects.filter(aktif=True).order_by("sinif", "sube", "okulno")


# ── Otomatik üyeler ──────────────────────────────────────────────────────────

def otomatik_aday_personel(kurul) -> list:
    """Kurul türünün otomatik üyelik kuralına göre üye olması gereken personel."""
    kural = kurul.tur.otomatik_uyelik
    gorevde = Personel.objects.gorevde()

    if kural == KurulTuru.OTOMATIK_TUM_PERSONEL:
        qs = gorevde
    elif kural == KurulTuru.OTOMATIK_SUBE_OGRETMENLERI:
        from dersprogrami.models import DersProgrami

        derse_girenler = (
            DersProgrami.objects.aktif()
            .filter(sinif_sube=kurul.sinif_sube)
            .values_list("ogretmen_id", flat=True)
        )
        qs = gorevde.filter(pk__in=derse_girenler) | gorevde.filter(gorev_tipi=_REHBERLIK_GOREVI)
    elif kural == KurulTuru.OTOMATIK_BRANS_OGRETMENLERI:
        qs = gorevde.filter(brans=kurul.brans).exclude(gorev_tipi__in=Personel.YONETICI_GOREVLERI)
    elif kural == KurulTuru.OTOMATIK_ZUMRE_BASKANLARI:
        baskanlar = KurulUyesi.objects.filter(
            kurul__egitim_yili=kurul.egitim_yili,
            kurul__tur__otomatik_uyelik=KurulTuru.OTOMATIK_BRANS_OGRETMENLERI,
            gorev=KurulUyesi.GOREV_BASKAN,
            personel__isnull=False,
        ).values_list("personel_id", flat=True)
        qs = gorevde.filter(pk__in=baskanlar)
    else:
        return []
    return list(qs.distinct().order_by("adi_soyadi"))


def _otomatik_kalem(tur):
    return tur.yapi.filter(otomatik=True).first()


def onerilen_baskan(kurul):
    """Mevzuata ve okulun görev dağılımına göre kurulun önerilen başkanı (yoksa None).

    - Öğretmenler kurulu: okul müdürü.
    - Sınıf/şube öğretmenler kurulu: o sınıf seviyesinden sorumlu müdür yardımcısı
      (okul/yonetim/ → Sınıf Seviyesi Sorumluları).
    """
    kural = kurul.tur.otomatik_uyelik
    if kural == KurulTuru.OTOMATIK_TUM_PERSONEL:
        return Personel.objects.gorevde().filter(gorev_tipi__in=_MUDUR_GOREVLERI).order_by("pk").first()
    if kural == KurulTuru.OTOMATIK_SUBE_OGRETMENLERI and kurul.sinif_sube_id:
        from okul.models import SinifSeviyesiSorumlusu

        sorumlu = (
            SinifSeviyesiSorumlusu.objects.filter(
                egitim_yili=kurul.egitim_yili, sinif=kurul.sinif_sube.sinif,
                personel__in=Personel.objects.gorevde(),
            ).select_related("personel").first()
        )
        return sorumlu.personel if sorumlu else None
    return None


def otomatik_uyeleri_uygula(kurul) -> int:
    """Kurulu önerilerle tamamlar: eksik otomatik üyeleri yapının otomatik kalemine ekler ve
    başkanı boşsa önerilen başkanı (bkz. `onerilen_baskan`) başkan kalemine yerleştirir.
    Elle seçilmiş üyelere ve başkana dokunmaz. Eklenen/görevi değişen üye sayısını döner."""
    mevcut = set(kurul.uyeler.filter(personel__isnull=False).values_list("personel_id", flat=True))
    otomatik_kalem = _otomatik_kalem(kurul.tur)
    eklenen = 0
    for personel in otomatik_aday_personel(kurul):
        if personel.pk in mevcut:
            continue
        KurulUyesi.objects.create(
            kurul=kurul, personel=personel, gorev=KurulUyesi.GOREV_UYE, kalem=otomatik_kalem, otomatik=True
        )
        eklenen += 1

    baskan = None if kurul.uyeler.filter(gorev=KurulUyesi.GOREV_BASKAN).exists() else onerilen_baskan(kurul)
    if baskan is not None:
        baskan_kalemi = kurul.tur.yapi.filter(gorev=KurulUyesi.GOREV_BASKAN, otomatik=False).first()
        uye = kurul.uyeler.filter(personel=baskan).first() or KurulUyesi(kurul=kurul, personel=baskan)
        uye.gorev, uye.kalem, uye.asil, uye.otomatik = KurulUyesi.GOREV_BASKAN, baskan_kalemi, True, True
        uye.save()
        eklenen += 1
    return eklenen


# ── Yapı (iskelet) üzerinden seçim ───────────────────────────────────────────

def kalem_uyeleri(kurul, kalem):
    """Kalemdeki üyeler: önce asiller, sonra yedekler (eklenme sırasıyla)."""
    return list(
        kurul.uyeler.filter(kalem=kalem).select_related("personel", "ogrenci").order_by("-asil", "id")
    )


def yapi_doluluk(kurul) -> dict:
    """Seçimle doldurulan kalemlerde dolu/gereken asil sayısı (otomatik kalemler hariç)."""
    gereken = dolu = 0
    asil_sayilari = {}
    for u in kurul.uyeler.filter(kalem__isnull=False, kalem__otomatik=False, asil=True):
        asil_sayilari[u.kalem_id] = asil_sayilari.get(u.kalem_id, 0) + 1
    for kalem in kurul.tur.yapi.filter(otomatik=False):
        gereken += kalem.asil_sayisi
        dolu += min(asil_sayilari.get(kalem.pk, 0), kalem.asil_sayisi)
    return {"dolu": dolu, "gereken": gereken}


def _anahtar(deger):
    if isinstance(deger, Personel):
        return ("p", deger.pk)
    if isinstance(deger, Ogrenci):
        return ("o", deger.pk)
    return None  # dış üye metinleri tekrarlanabilir (ör. iki ayrı veli)


@transaction.atomic
def yapiyi_kaydet(kurul, secimler: dict) -> None:
    """Yapı formundaki seçimleri kaydeder.

    `secimler`: {kalem: {"asil": [değer, ...], "yedek": [değer, ...]}} — değer bir Personel,
    Ogrenci, dış üye unvanı (str) ya da boştur (None/""). Seçilmeyen yerler boş kalır.

    - Aynı kişi formda iki görev yerine seçilemez (ValidationError).
    - Kurulda zaten (ör. otomatik ya da ek üye olarak) bulunan kişi seçilirse ikinci kayıt
      açılmaz; mevcut üyeliği bu kaleme taşınır.
    - Kalemden çıkarılan kişi, türün otomatik üyeleri arasındaysa otomatik kaleme döner;
      değilse kuruldan çıkarılır.
    """
    gorulen = {}
    for kalem, liste in secimler.items():
        for deger in liste["asil"] + liste["yedek"]:
            anahtar = _anahtar(deger)
            if anahtar is None:
                continue
            if anahtar in gorulen:
                raise ValidationError(
                    f"{deger} hem '{gorulen[anahtar]}' hem '{kalem.unvan}' için seçildi; "
                    "bir kişi bir görev yerinde bulunabilir."
                )
            gorulen[anahtar] = kalem.unvan

    otomatik_kalem = _otomatik_kalem(kurul.tur)
    otomatik_adaylar = {p.pk for p in otomatik_aday_personel(kurul)} if otomatik_kalem else set()

    for kalem, liste in secimler.items():
        eski = {u.pk: u for u in kurul.uyeler.filter(kalem=kalem)}
        tutulan = set()
        for asil, degerler in ((True, liste["asil"]), (False, liste["yedek"])):
            for deger in degerler:
                if deger in (None, ""):
                    continue
                alanlar = {"kalem": kalem, "gorev": kalem.gorev, "asil": asil}
                if isinstance(deger, Personel):
                    uye = kurul.uyeler.filter(personel=deger).first() or KurulUyesi(kurul=kurul, personel=deger)
                elif isinstance(deger, Ogrenci):
                    uye = kurul.uyeler.filter(ogrenci=deger).first() or KurulUyesi(kurul=kurul, ogrenci=deger)
                else:
                    metin = str(deger).strip()
                    uye = next(
                        (u for u in eski.values() if u.dis_uye == metin and u.pk not in tutulan),
                        None,
                    ) or KurulUyesi(kurul=kurul, dis_uye=metin)
                for alan, d in alanlar.items():
                    setattr(uye, alan, d)
                uye.otomatik = False
                uye.save()
                tutulan.add(uye.pk)
        for pk, uye in eski.items():
            if pk in tutulan:
                continue
            if uye.personel_id and uye.personel_id in otomatik_adaylar:
                uye.kalem, uye.gorev, uye.asil, uye.otomatik = otomatik_kalem, KurulUyesi.GOREV_UYE, True, True
                uye.save()
            else:
                uye.delete()


# ── Yapı dışı (ek) üye ───────────────────────────────────────────────────────

def uye_ekle(kurul, *, personel=None, ogrenci=None, dis_uye="", gorev=KurulUyesi.GOREV_UYE, asil=True):
    """Kurula yapı dışında ek üye ekler; aynı kişi iki kez eklenemez. Hata durumunda ValidationError."""
    uye = KurulUyesi(
        kurul=kurul, personel=personel, ogrenci=ogrenci, dis_uye=(dis_uye or "").strip(),
        gorev=gorev, asil=asil,
    )
    uye.full_clean(validate_constraints=False)
    try:
        with transaction.atomic():
            uye.save()
    except IntegrityError:
        raise ValidationError("Bu kişi kurulda zaten üye.")
    return uye


# ── Öğretmen görevleri ve görev yükü ─────────────────────────────────────────

def personel_uyelikleri(personel, egitim_yili):
    """Personelin yıldaki kurul/komisyon üyelikleri."""
    if personel is None or egitim_yili is None:
        return KurulUyesi.objects.none()
    return (
        KurulUyesi.objects.filter(personel=personel, kurul__egitim_yili=egitim_yili)
        .select_related("kurul__tur", "kurul__sinif_sube", "kurul__brans", "kalem")
        .order_by("kurul__tur__sira", "kurul__tur__ad")
    )


def gorev_yuku(egitim_yili) -> list:
    """Öğretmen başına seçimle/görevlendirmeyle aldığı kurul ve komisyon görevleri.

    Herkesin kendiliğinden üyesi olduğu kurullar (öğretmenler, şube, zümre kurulları)
    sayılmaz; başkanlıklar ayrıca gösterilir. Görev sayısına göre çoktan aza sıralı."""
    uyelikler = (
        KurulUyesi.objects.filter(kurul__egitim_yili=egitim_yili, personel__isnull=False)
        .select_related("personel", "kurul__tur", "kurul__sinif_sube", "kurul__brans")
    )
    satirlar = {}
    for u in uyelikler:
        satir = satirlar.setdefault(
            u.personel_id, {"personel": u.personel, "gorevler": [], "baskanliklar": []}
        )
        if u.gorev == KurulUyesi.GOREV_BASKAN:
            satir["baskanliklar"].append(u)
        if u.kurul.tur.otomatik_uyelik == KurulTuru.OTOMATIK_YOK:
            satir["gorevler"].append(u)
    sonuc = [s for s in satirlar.values() if s["gorevler"] or s["baskanliklar"]]
    # Seçimle görevi olmayanlar (yalnızca otomatik kurullarda üye olanlar dahil) sona eklenir
    gorevsiz = (
        Personel.objects.gorevde().exclude(pk__in=[s["personel"].pk for s in sonuc])
        .exclude(gorev_tipi__in=Personel.YONETICI_GOREVLERI).order_by("adi_soyadi")
    )
    sonuc.sort(key=lambda s: (-len(s["gorevler"]), s["personel"].adi_soyadi))
    sonuc += [{"personel": p, "gorevler": [], "baskanliklar": []} for p in gorevsiz]
    return sonuc


def kurullar(egitim_yili):
    return (
        Kurul.objects.filter(egitim_yili=egitim_yili)
        .select_related("tur", "sinif_sube", "brans")
    )
