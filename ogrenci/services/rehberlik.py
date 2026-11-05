"""Sınıf rehber öğretmeni bilgisi.

Rehber öğretmenin tek kaynağı `okul.SinifRehberOgretmeni` tablosudur. Haftalık ders
programında bir sınıfa "REHBERLİK VE YÖNLENDİRME" dersini veren öğretmen yalnızca
öneri olarak sunulur; yönetici kabul ederse tabloya işlenir.
"""

from django.db import transaction
from django.db.models import Q

from dersprogrami.models import DersProgrami
from okul.models import SinifRehberOgretmeni, SinifSube
from okul.utils import get_aktif_egitim_yili

REHBERLIK_DERS_ADI = "REHBERLİK VE YÖNLENDİRME"

GUN_TR = {
    "Monday": "Pazartesi",
    "Tuesday": "Salı",
    "Wednesday": "Çarşamba",
    "Thursday": "Perşembe",
    "Friday": "Cuma",
    "Saturday": "Cumartesi",
    "Sunday": "Pazar",
}
GUN_SIRA = {g: i for i, g in enumerate(GUN_TR)}

# Tablo satırı durumları
UYUMLU = "uyumlu"            # kayıt var, ders programı önerisiyle aynı
FARKLI = "farkli"            # kayıt var, öneri başka bir öğretmeni gösteriyor
ATANMAMIS = "atanmamis"      # kayıt yok, öneri var
ONERI_YOK = "oneri_yok"      # kayıt yok, öneri de yok
ELLE = "elle"                # kayıt var, ders programında öneri yok


def rehberlik_dersi_q(alan="ders__ders_adi"):
    """Rehberlik dersini adının yazımından bağımsız eşleyen filtre.

    `iexact` büyük/küçük harf dönüşümünü veritabanının locale'ine bırakır: Türkçe
    olmayan bir locale'de "i" → "I" olur, "İ" ile eşleşmez. Bu yüzden ad hem noktalı
    büyük İ ile ("REHBERLİK VE YÖNLENDİRME") hem de noktasız i ile
    ("Rehberlik ve Yönlendirme") aranır. Yalnızca öneri üretmek için kullanılır.
    """
    return Q(**{f"{alan}__iexact": REHBERLIK_DERS_ADI}) | Q(
        **{f"{alan}__iexact": "rehberlik ve yönlendirme"}
    )


# ─────────────────────────────────────────────
# Okuma — tüm uygulama bu iki fonksiyonu kullanır
# ─────────────────────────────────────────────

def rehberlik_sinif_sube(user, egitim_yili=None):
    """Kullanıcının aktif yılda rehber öğretmeni olduğu SinifSube; yoksa None.
    Birden fazla sınıfı varsa sınıf/şube sırasına göre ilki döner."""
    personel = getattr(user, "personel", None)
    yil = egitim_yili or get_aktif_egitim_yili()
    if personel is None or yil is None:
        return None
    kayit = (
        SinifRehberOgretmeni.objects.filter(egitim_yili=yil, personel=personel)
        .select_related("sinif_sube")
        .order_by("sinif_sube__sinif", "sinif_sube__sube")
        .first()
    )
    return kayit.sinif_sube if kayit else None


def sinif_rehber_ogretmeni(sinif_sube, egitim_yili=None):
    """`sinif_sube`'nin aktif yıldaki rehber öğretmeni (Personel); yoksa None."""
    yil = egitim_yili or get_aktif_egitim_yili()
    if yil is None:
        return None
    kayit = (
        SinifRehberOgretmeni.objects.filter(egitim_yili=yil, sinif_sube=sinif_sube)
        .select_related("personel")
        .first()
    )
    return kayit.personel if kayit else None


# ─────────────────────────────────────────────
# Ders programından öneri ve yönetim
# ─────────────────────────────────────────────

def ders_programi_onerileri():
    """Aktif ders programına göre {sinif_sube_id: [{"personel", "saatler"}, ...]}.

    `saatler`: ["Pazartesi 3. ders", ...] — rehberlik dersinin programdaki yerleri.
    """
    kayitlar = (
        DersProgrami.objects.aktif()
        .filter(rehberlik_dersi_q(), sinif_sube__isnull=False)
        .select_related("ogretmen", "ders_saati")
    )
    gruplar = {}
    for k in kayitlar:
        oneri = gruplar.setdefault(k.sinif_sube_id, {}).setdefault(
            k.ogretmen_id, {"personel": k.ogretmen, "_saatler": []}
        )
        no = k.ders_saati.derssaati_no if k.ders_saati else 0
        oneri["_saatler"].append((GUN_SIRA.get(k.gun, 9), no, k.gun))
    sonuc = {}
    for ss_id, ogretmenler in gruplar.items():
        liste = []
        for o in ogretmenler.values():
            o["saatler"] = [
                f"{GUN_TR.get(gun, gun)} {no}. ders" if no else GUN_TR.get(gun, gun)
                for _, no, gun in sorted(o.pop("_saatler"))
            ]
            liste.append(o)
        sonuc[ss_id] = sorted(liste, key=lambda o: o["personel"].adi_soyadi)
    return sonuc


def rehber_tablosu(egitim_yili):
    """Yönetim ekranı satırları: her sınıf için kayıtlı rehber, öneri ve durum.

    Aktif yılda açık olan sınıflar ile kaydı ya da önerisi olan sınıflar listelenir.
    """
    kayitlar = {
        k.sinif_sube_id: k
        for k in SinifRehberOgretmeni.objects.filter(egitim_yili=egitim_yili)
        .select_related("personel", "guncelleyen")
    }
    oneriler = ders_programi_onerileri()
    satirlar = []
    for ss in SinifSube.objects.order_by("sinif", "sube"):
        kayit = kayitlar.get(ss.pk)
        oneri = oneriler.get(ss.pk, [])
        if not (kayit or oneri or ss.acik_mi(egitim_yili)):
            continue
        oneri_pkler = {o["personel"].pk for o in oneri}
        if kayit:
            durum = ELLE if not oneri else (UYUMLU if kayit.personel_id in oneri_pkler else FARKLI)
        else:
            durum = ATANMAMIS if oneri else ONERI_YOK
        satirlar.append({"sinif_sube": ss, "kayit": kayit, "oneriler": oneri, "durum": durum})
    return satirlar


def rehber_ata(sinif_sube, personel, egitim_yili, user):
    """Sınıfın rehber öğretmenini kaydeder ya da değiştirir."""
    kayit, _ = SinifRehberOgretmeni.objects.update_or_create(
        egitim_yili=egitim_yili,
        sinif_sube=sinif_sube,
        defaults={"personel": personel, "guncelleyen": user},
    )
    return kayit


def rehber_kaldir(sinif_sube, egitim_yili):
    """Sınıfın rehber öğretmeni kaydını siler; silinen kayıt sayısını döner."""
    silinen, _ = SinifRehberOgretmeni.objects.filter(
        egitim_yili=egitim_yili, sinif_sube=sinif_sube
    ).delete()
    return silinen


@transaction.atomic
def onerileri_toplu_kabul_et(egitim_yili, user):
    """Rehberi atanmamış ve ders programında tek önerisi olan sınıflara öneriyi işler.

    Kayıtlı rehberi olan sınıflara dokunulmaz; birden fazla öğretmen önerilen sınıflar
    atlanır (yönetici elle seçer). İşlenen sınıf sayısını döner.
    """
    sayi = 0
    for satir in rehber_tablosu(egitim_yili):
        if satir["durum"] == ATANMAMIS and len(satir["oneriler"]) == 1:
            rehber_ata(satir["sinif_sube"], satir["oneriler"][0]["personel"], egitim_yili, user)
            sayi += 1
    return sayi


def atanmamis_sinif_sayisi(egitim_yili):
    """Aktif yılda açık olup rehber öğretmeni kaydedilmemiş sınıf sayısı."""
    if egitim_yili is None:
        return 0
    atanmis = set(
        SinifRehberOgretmeni.objects.filter(egitim_yili=egitim_yili).values_list(
            "sinif_sube_id", flat=True
        )
    )
    return sum(
        1
        for ss in SinifSube.objects.exclude(pk__in=atanmis)
        if ss.acik_mi(egitim_yili)
    )
