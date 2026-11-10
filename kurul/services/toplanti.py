"""Kurul toplantıları: oluşturma, gündem, katılım, kararlar, durum akışı ve yetki.

Kurallar Eğitim Kurulları ve Zümreleri Yönergesi'nden: tarih/yer/gündem en az 5 gün
önceden duyurulur; ilk gündem maddesi bir önceki toplantının kararlarıdır; kararlar oy
çokluğuyla alınır ve müdür onayından sonra uygulanır; tutanağı katılmayanlar dahil üyeler
imzalar. Gizli kurullarda (disiplin, onur) yalnızca tarih, yer ve katılım tutulur.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from kurul.models import GundemMaddesi, Karar, Katilim, KurulUyesi, Toplanti
from okul.auth import is_mudur_yardimcisi, is_ust_yonetici
from okul.utils import turkce_sira_anahtari

ACILIS_MADDESI = "Açılış ve yoklama"
ONCEKI_KARARLAR_MADDESI = "Bir önceki toplantıda alınan kararların değerlendirilmesi"
DILEK_MADDESI = "Dilek ve temenniler"


# ── Yetki ────────────────────────────────────────────────────────────────────

def _personel(user):
    return getattr(user, "personel", None) if user.is_authenticated else None


def toplanti_yonetebilir(user, kurul) -> bool:
    """Müdür yardımcısı ya da kurulun başkanı/raportörü toplantı yönetir.
    Okul müdürü toplantıları görür ve kararları onaylar (bkz. onaylayabilir)."""
    if is_mudur_yardimcisi(user):
        return True
    personel = _personel(user)
    return personel is not None and kurul.uyeler.filter(
        personel=personel, gorev__in=(KurulUyesi.GOREV_BASKAN, "raportor")
    ).exists()


def toplanti_gorebilir(user, kurul) -> bool:
    """Yönetebilenler, üst yöneticiler ve kurul üyeleri toplantıları görür."""
    if toplanti_yonetebilir(user, kurul) or is_ust_yonetici(user):
        return True
    personel = _personel(user)
    return personel is not None and kurul.uyeler.filter(personel=personel).exists()


def onaylayabilir(user) -> bool:
    """Kararları müdür (ya da yetkilendirdiği müdür yardımcısı) onaylar."""
    return is_ust_yonetici(user)


# ── Oluşturma ────────────────────────────────────────────────────────────────

def onceki_toplanti(toplanti):
    """Aynı kurulun bu toplantıdan önceki (iptal edilmemiş) son toplantısı."""
    return (
        Toplanti.objects.filter(kurul=toplanti.kurul)
        .exclude(pk=toplanti.pk).exclude(durum=Toplanti.DURUM_IPTAL)
        .filter(no__lt=toplanti.no).order_by("-no").first()
    )


def _katilim_sira_anahtari(k):
    """Okul Müdürü ve kurul başkanı, müdür yardımcıları, öğretmenler (branşa göre),
    öğrenciler, dış üyeler; her grupta ada göre. Yedekler asillerden sonra gelir."""
    uye = k.uye
    personel = uye.personel if uye and uye.personel_id else None
    baskan = bool(uye and uye.gorev == KurulUyesi.GOREV_BASKAN) or "(Başkan)" in k.gorev
    if personel is not None:
        unvan = personel.unvan
        if unvan == "Okul Müdürü":
            grup, alt = 0, ""
        elif baskan:
            grup, alt = 0, "~"  # müdürden sonra
        elif unvan == "Müdür Yardımcısı":
            grup, alt = 1, ""
        else:
            grup, alt = 2, personel.brans.ad if personel.brans_id else "~"
    elif baskan:
        grup, alt = 0, "~"
    elif uye and uye.ogrenci_id:
        grup, alt = 3, ""
    elif uye:
        grup, alt = 4, ""
    else:  # üye sonradan kuruldan çıkarılmış: tutanaktaki görev metnine göre
        grup = 0 if k.gorev.startswith("Okul Müdürü") else 1 if k.gorev.startswith("Müdür Yardımcısı") else 2
        alt = k.gorev
    return (not k.asil, grup, turkce_sira_anahtari(alt), turkce_sira_anahtari(k.ad))


def sirali_katilimlar(toplanti):
    """Katılım listesi, sayfa ve tutanakta kullanılan sırayla (bkz. _katilim_sira_anahtari)."""
    return sorted(
        toplanti.katilimlar.select_related("uye__personel__brans"),
        key=_katilim_sira_anahtari,
    )


def _uyeleri_katilima_yaz(toplanti, uyeler):
    for u in uyeler:
        Katilim.objects.create(
            toplanti=toplanti, uye=u, ad=u.uye_adi[:200], gorev=u.katilim_gorevi[:200], asil=u.asil,
        )


@transaction.atomic
def toplanti_olustur(kurul, *, tarih, saat, yer, tur=Toplanti.TUR_OLAGAN, aciklama="", olusturan=None):
    """Toplantıyı bir sonraki numarayla açar; katılım listesini kurul üyelerinden, gündemin
    sabit maddelerini (açılış, önceki kararlar, dilek ve temenniler) kendiliğinden oluşturur."""
    no = (kurul.toplantilar.aggregate(m=Max("no"))["m"] or 0) + 1
    toplanti = Toplanti.objects.create(
        kurul=kurul, no=no, tarih=tarih, saat=saat, yer=yer, tur=tur, aciklama=aciklama,
        olusturan=olusturan,
    )
    _uyeleri_katilima_yaz(toplanti, kurul.uyeler.select_related("personel__brans", "ogrenci", "kalem"))
    if not kurul.tur.gizli:
        maddeler = [(ACILIS_MADDESI, False)]
        if onceki_toplanti(toplanti):
            maddeler.append((ONCEKI_KARARLAR_MADDESI, True))
        maddeler.append((DILEK_MADDESI, False))
        for sira, (baslik, onceki) in enumerate(maddeler, 1):
            GundemMaddesi.objects.create(toplanti=toplanti, sira=sira, baslik=baslik, onceki_kararlar=onceki)
    return toplanti


def katilimi_esitle(toplanti) -> tuple[int, int]:
    """Toplantı açıldıktan sonra kurula eklenen üyeleri katılım listesine ekler; listede
    olanların görevini güncel kurul/personel bilgisinden yeniler (onaylanmış ya da iptal
    edilmiş toplantıda tutanak bozulmasın diye hiçbir şey değişmez).

    Dönüş ``(eklenen, guncellenen)``.
    """
    if not toplanti.duzenlenebilir:
        return 0, 0
    guncellenen = 0
    for k in toplanti.katilimlar.exclude(uye=None).select_related("uye__personel__brans"):
        gorev = k.uye.katilim_gorevi[:200]
        if k.gorev != gorev:
            k.gorev = gorev
            k.save(update_fields=["gorev"])
            guncellenen += 1
    var = set(toplanti.katilimlar.exclude(uye=None).values_list("uye_id", flat=True))
    yeni = list(
        toplanti.kurul.uyeler.exclude(pk__in=var).select_related("personel__brans", "ogrenci", "kalem")
    )
    _uyeleri_katilima_yaz(toplanti, yeni)
    return len(yeni), guncellenen


# ── Gündem ───────────────────────────────────────────────────────────────────

def _duzenlenebilir(toplanti):
    if not toplanti.duzenlenebilir:
        raise ValidationError("Onaylanmış ya da iptal edilmiş toplantı düzenlenemez.")
    if toplanti.kurul.tur.gizli:
        raise ValidationError("Gizli kurullarda gündem ve karar bu uygulamada tutulmaz.")


def _yeniden_sirala(toplanti):
    for sira, madde in enumerate(toplanti.gundem.order_by("sira", "id"), 1):
        if madde.sira != sira:
            madde.sira = sira
            madde.save(update_fields=["sira"])


@transaction.atomic
def gundem_ekle(toplanti, basliklar) -> int:
    """Maddeleri 'Dilek ve temenniler'den önceye ekler. Eklenen sayısını döner."""
    _duzenlenebilir(toplanti)
    mevcut = set(toplanti.gundem.values_list("baslik", flat=True))
    dilek = toplanti.gundem.filter(baslik=DILEK_MADDESI).first()
    sira = dilek.sira if dilek else (toplanti.gundem.aggregate(m=Max("sira"))["m"] or 0) + 1
    eklenen = 0
    for baslik in basliklar:
        baslik = (baslik or "").strip()[:300]
        if not baslik or baslik in mevcut:
            continue
        GundemMaddesi.objects.create(toplanti=toplanti, sira=sira, baslik=baslik)
        mevcut.add(baslik)
        sira += 1
        eklenen += 1
    if dilek and eklenen:
        dilek.sira = sira
        dilek.save(update_fields=["sira"])
    _yeniden_sirala(toplanti)
    return eklenen


@transaction.atomic
def gundem_onerileri(toplanti) -> list:
    """Kurul türünün mevzuattaki gündem konularından bu toplantıda henüz olmayanlar.
    Önceki kararlar maddesi kendiliğinden eklendiği için önerilmez."""
    var = set(toplanti.gundem.values_list("baslik", flat=True))
    return [
        o for o in toplanti.kurul.tur.gundem_onerisi_listesi
        if o not in var and not o.casefold().startswith("bir önceki toplantı")
    ]


def gundem_tasi(madde, yon):
    """Maddeyi bir yukarı (yon=-1) ya da aşağı (yon=1) taşır."""
    _duzenlenebilir(madde.toplanti)
    komsu = (
        madde.toplanti.gundem.filter(sira__lt=madde.sira).order_by("-sira").first() if yon < 0
        else madde.toplanti.gundem.filter(sira__gt=madde.sira).order_by("sira").first()
    )
    if komsu:
        madde.sira, komsu.sira = komsu.sira, madde.sira
        madde.save(update_fields=["sira"])
        komsu.save(update_fields=["sira"])


@transaction.atomic
def gundem_sil(madde):
    toplanti = madde.toplanti
    _duzenlenebilir(toplanti)
    madde.delete()
    _yeniden_sirala(toplanti)


def gorusmeleri_kaydet(toplanti, ozetler: dict):
    """{madde_pk: görüşme özeti} ile gündem maddelerinin görüşme özetlerini kaydeder."""
    _duzenlenebilir(toplanti)
    for madde in toplanti.gundem.all():
        if madde.pk in ozetler and madde.gorusme != ozetler[madde.pk]:
            madde.gorusme = ozetler[madde.pk]
            madde.save(update_fields=["gorusme"])


# ── Katılım ve kararlar ──────────────────────────────────────────────────────

def katilimi_kaydet(toplanti, durumlar: dict):
    """{katilim_pk: (durum, açıklama)} ile katılım durumlarını kaydeder."""
    if not toplanti.duzenlenebilir:
        raise ValidationError("Onaylanmış ya da iptal edilmiş toplantı düzenlenemez.")
    gecerli = dict(Katilim.DURUM_CHOICES)
    for k in toplanti.katilimlar.all():
        if k.pk in durumlar:
            durum, aciklama = durumlar[k.pk]
            if durum in gecerli:
                k.durum, k.aciklama = durum, (aciklama or "")[:200]
                k.save(update_fields=["durum", "aciklama"])


def karar_ekle(toplanti, **alanlar):
    _duzenlenebilir(toplanti)
    alanlar["no"] = (toplanti.kararlar.aggregate(m=Max("no"))["m"] or 0) + 1
    karar = Karar(toplanti=toplanti, **alanlar)
    karar.full_clean()
    karar.save()
    return karar


def karar_sil(karar):
    _duzenlenebilir(karar.toplanti)
    karar.delete()


def karar_takibi(karar, takip_durumu, takip_notu=""):
    """Karar takibi onaydan sonra da güncellenebilir (uygulamanın izlenmesi)."""
    if takip_durumu not in dict(Karar.TAKIP_CHOICES):
        raise ValidationError("Geçersiz takip durumu.")
    karar.takip_durumu, karar.takip_notu = takip_durumu, (takip_notu or "")[:300]
    karar.save(update_fields=["takip_durumu", "takip_notu"])


# ── Durum akışı ──────────────────────────────────────────────────────────────

_GECISLER = {
    "duyur": ({Toplanti.DURUM_TASLAK}, Toplanti.DURUM_DUYURULDU),
    "yapildi": ({Toplanti.DURUM_TASLAK, Toplanti.DURUM_DUYURULDU}, Toplanti.DURUM_YAPILDI),
    "onayla": ({Toplanti.DURUM_YAPILDI}, Toplanti.DURUM_ONAYLANDI),
    "onayi_kaldir": ({Toplanti.DURUM_ONAYLANDI}, Toplanti.DURUM_YAPILDI),
    "iptal": ({Toplanti.DURUM_TASLAK, Toplanti.DURUM_DUYURULDU}, Toplanti.DURUM_IPTAL),
}


def durum_degistir(toplanti, islem, user):
    """Durum akışındaki bir adımı uygular. Onay ve onay kaldırma üst yöneticiye aittir.
    Geçersiz adımda ValidationError, yetkisizlikte PermissionDenied."""
    if islem not in _GECISLER:
        raise ValidationError("Geçersiz işlem.")
    kaynaklar, hedef = _GECISLER[islem]
    if toplanti.durum not in kaynaklar:
        raise ValidationError(f"Toplantı '{toplanti.get_durum_display()}' durumundayken bu işlem yapılamaz.")
    if islem in ("onayla", "onayi_kaldir") and not onaylayabilir(user):
        raise PermissionDenied
    bugun = timezone.localdate()
    if islem == "duyur":
        toplanti.duyuru_tarihi = bugun
    if islem == "yapildi" and toplanti.tarih > bugun:
        raise ValidationError("Tarihi gelmemiş toplantı 'yapıldı' olarak işaretlenemez.")
    if islem == "onayla":
        toplanti.onaylayan, toplanti.onay_tarihi = user, bugun
    if islem == "onayi_kaldir":
        toplanti.onaylayan, toplanti.onay_tarihi = None, None
    toplanti.durum = hedef
    toplanti.save()
    return toplanti


# ── Listeler ─────────────────────────────────────────────────────────────────

def personel_toplantilari(personel, egitim_yili, yalnizca_yaklasan=True):
    """Personelin üyesi olduğu kurulların yıldaki toplantıları."""
    if personel is None or egitim_yili is None:
        return Toplanti.objects.none()
    qs = (
        Toplanti.objects.filter(kurul__egitim_yili=egitim_yili, kurul__uyeler__personel=personel)
        .exclude(durum=Toplanti.DURUM_IPTAL)
        .select_related("kurul__tur", "kurul__sinif_sube", "kurul__brans").distinct()
    )
    if yalnizca_yaklasan:
        qs = qs.filter(tarih__gte=timezone.localdate())
    return qs.order_by("tarih", "saat")
