"""Gelecek yıl şube/alan ders paketi hesaplamaları.

`plan_sinif_dagilimi` — sinif_dagilimi view'ından taşındı; öğrencileri
seçmeli ders tercihlerine göre en uygun alana eşleyip kız/erkek dengeli
şubelere dağıtır.
"""
import math
from collections import defaultdict

MAKS_SUBE = 34
HARFLER = "ABCDEFGHİJKLMNOPQRSTUVWXYZ"


def _yf(qs, aktif_yil, alan="egitim_yili"):
    return qs.filter(**{alan: aktif_yil}) if aktif_yil else qs


def baskin_egitim_yili(sinif_seviyesi, varsayilan_yil):
    """`sinif_seviyesi` için öğrencilerin FİİLEN bağlı olduğu (en çok kullanılan)
    OgrenciSecmeliDers → grup → egitim_yili kaydını döner; hiç seçim yoksa
    `varsayilan_yil`ı döner.

    Bir denetim/eşleştirme işleminde kullanılacak Alan/AlanDers kataloğunun hangi
    yıla ait olduğunu, elle seçilen (`secili_yil`) yerine GERÇEK veriye göre
    belirlemek için kullanılır — geçiş sonrası yapılan bir alan değişikliği/
    düzeltme farklı bir yılın kataloğunu kullanmış olabilir; aksi hâlde eşleştirme
    yanlışlıkla "alan tespit edilemedi" sonucu verir (yaşandı: bkz. commit geçmişi).
    Hem `plan_sinif_dagilimi_gecmis`'in eşleştirmesi hem de alan-değiştir
    butonlarının hangi kataloğu göstereceği bu TEK fonksiyondan gelmeli — ikisi
    ayrı hesaplanırsa tutarsızlık kaçınılmaz olur.
    """
    from django.db.models import Count

    from ogrencidersleri.models import OgrenciSecmeliDers
    from okul.models import EgitimOgretimYili

    baskin = (
        OgrenciSecmeliDers.objects.filter(ders__grup__sinif_seviyesi=sinif_seviyesi)
        .values("ders__grup__egitim_yili")
        .annotate(n=Count("id"))
        .order_by("-n")
        .first()
    )
    if baskin and baskin["ders__grup__egitim_yili"]:
        return EgitimOgretimYili.objects.filter(pk=baskin["ders__grup__egitim_yili"]).first() or varsayilan_yil
    return varsayilan_yil


def _sube_dagit(ogrs, gelecek_sinif, harf_idx, maks=MAKS_SUBE):
    """Öğrencileri kız/erkek dengesi korunarak şubelere dağıtır."""
    kizlar = sorted([o for o in ogrs if o.cinsiyet == "K"], key=lambda x: x.okulno or 0)
    erkekler = sorted([o for o in ogrs if o.cinsiyet == "E"], key=lambda x: x.okulno or 0)
    toplam = len(kizlar) + len(erkekler)
    if toplam == 0:
        return [], harf_idx

    n_sube = math.ceil(toplam / maks)
    G, B = len(kizlar), len(erkekler)
    kiz_base, kiz_rem = divmod(G, n_sube)
    erk_base, erk_rem = divmod(B, n_sube)

    subeler = []
    kiz_idx = erk_idx = 0
    for i in range(n_sube):
        kiz_al = kiz_base + (1 if i < kiz_rem else 0)
        erk_al = erk_base + (1 if i < erk_rem else 0)
        sube_ogrs = kizlar[kiz_idx:kiz_idx + kiz_al] + erkekler[erk_idx:erk_idx + erk_al]
        sube_ogrs.sort(key=lambda x: x.okulno or 0)
        kiz_idx += kiz_al
        erk_idx += erk_al
        harf = HARFLER[harf_idx] if harf_idx < 26 else str(harf_idx + 1)
        subeler.append({
            "sube": harf,
            "label": f"{gelecek_sinif}/{harf}",
            "ogrenciler": sube_ogrs,
            "kiz_sayi": kiz_al,
            "erkek_sayi": erk_al,
        })
        harf_idx += 1
    return subeler, harf_idx


def plan_sinif_dagilimi(sinif_no, gelecek_sinif, aktif_yil, maks_sube=MAKS_SUBE):
    """Mevcut `sinif_no` öğrencilerini `gelecek_sinif` seviyesi alanlarına/şubelerine dağıtır."""
    from ogrenci.models import Ogrenci
    from ogrencidersleri.models import OgrenciSecmeliDers

    from ..models import Alan, AlanDers, OgrenciSinifTekrari, OgrenciTasdikname

    alanlar = list(
        _yf(Alan.objects.filter(sinif_seviyesi=gelecek_sinif), aktif_yil)
        .order_by("sira", "adi")
    )
    alan_ders_map = {
        a.pk: set(AlanDers.objects.filter(alan=a).values_list("ders_id", flat=True))
        for a in alanlar
    }

    ogrenciler = list(Ogrenci.objects.filter(sinif=sinif_no).order_by("okulno"))
    ogr_ids = [o.pk for o in ogrenciler]

    # `aktif_yil`a göre kapsamlanır — aksi hâlde geçmiş bir yılda sınıfta kalmış ama
    # o yılı zaten tamamlayıp normal terfi eden bir öğrenci de kalıcı olarak
    # sınıf-tekrarı kabul edilip yanlışlıkla planın dışında bırakılır (bkz. commit
    # geçmişi).
    sinif_tekrari_ids = set(
        _yf(OgrenciSinifTekrari.objects.filter(ogrenci_id__in=ogr_ids), aktif_yil)
        .values_list("ogrenci_id", flat=True)
    )
    tasdikname_ids = set(
        OgrenciTasdikname.objects.filter(ogrenci_id__in=ogr_ids).values_list("ogrenci_id", flat=True)
    )

    ogr_secim = defaultdict(set)
    for ogr_id, ders_id in OgrenciSecmeliDers.objects.filter(
        ogrenci_id__in=ogr_ids
    ).values_list("ogrenci_id", "ders_id"):
        ogr_secim[ogr_id].add(ders_id)

    alan_ogr = defaultdict(list)
    alan_yok = []
    sinif_tekrari_liste = []
    tasdikname_liste = []
    for ogr in ogrenciler:
        if ogr.pk in tasdikname_ids:
            tasdikname_liste.append(ogr)
            continue
        if ogr.pk in sinif_tekrari_ids:
            sinif_tekrari_liste.append(ogr)
            continue
        secimler = ogr_secim.get(ogr.pk, set())
        if not secimler:
            alan_yok.append(ogr)
            continue
        en_iyi_pk, en_iyi_skor = None, 0
        for a_pk, d_ids in alan_ders_map.items():
            skor = len(secimler & d_ids)
            if skor > en_iyi_skor:
                en_iyi_skor, en_iyi_pk = skor, a_pk
        (alan_ogr[en_iyi_pk] if en_iyi_pk else alan_yok).append(ogr)

    harf_idx = 0
    alan_gruplari = []
    for a in alanlar:
        ogrs = alan_ogr.get(a.pk, [])
        subeler, harf_idx = _sube_dagit(ogrs, gelecek_sinif, harf_idx, maks_sube)
        toplam_kiz = sum(1 for o in ogrs if o.cinsiyet == "K")
        toplam_erkek = sum(1 for o in ogrs if o.cinsiyet == "E")
        alan_gruplari.append({
            "alan": a,
            "ogrenci_sayisi": len(ogrs),
            "toplam_kiz": toplam_kiz,
            "toplam_erkek": toplam_erkek,
            "sube_sayisi": len(subeler),
            "subeler": subeler,
        })

    return {
        "sinif": sinif_no,
        "gelecek_sinif": gelecek_sinif,
        "alan_gruplari": alan_gruplari,
        "alan_yok": alan_yok,
        "sinif_tekrari": sinif_tekrari_liste,
        "tasdikname": tasdikname_liste,
        "toplam_ogr": sum(g["ogrenci_sayisi"] for g in alan_gruplari),
        "toplam_sube": sum(g["sube_sayisi"] for g in alan_gruplari),
    }


def plan_sinif_dagilimi_gecmis(gelecek_sinif, secili_yil):
    """`plan_sinif_dagilimi` ile aynı çıktı biçimini, zaten uygulanmış bir geçişi
    denetlemek için üretir: `secili_yil`in (uygulanmış) sene sonu geçişiyle
    `gelecek_sinif` seviyesine ULAŞMIŞ öğrencileri, kohortun fiilen bağlı olduğu
    (bkz. `baskin_egitim_yili`) Alan/AlanDers kayıtlarıyla (kendi seviyelerindeki
    seçimleri üzerinden) eşleştirir ve gerçek (hipotetik değil) mevcut şubelerine
    göre gruplar. Hiçbir kayıt değiştirmez, salt okunur denetim amaçlıdır — bkz.
    `secmelidersler.views.sinif_dagilimi`.

    Not: eşleştirme `secili_yil` (denetim ekranında seçilen yıl) yerine
    `baskin_egitim_yili` kullanır — kohortun gerçek seçimleri `secili_yil`den
    farklı bir yılın kataloğuna bağlıysa (örn. geçiş sonrası yapılan bir alan
    düzeltmesi), `secili_yil`i kullanmak tüm öğrencileri yanlışlıkla "alan tespit
    edilemedi" bucket'ına düşürür.

    Nüfus kaynağı: `Ogrenci.sinif=gelecek_sinif` (GÜNCEL/fiilî sınıf seviyesi) VE
    `SeneSonuGecisi(eski_egitim_yili=secili_yil, uygulandı=True)` geçişine dahil
    olma (geçişin herhangi bir satırında `ogrenci` olarak geçme) — ikisi birden
    aranır. Geçişin kendi `yeni_sinif` değeri TEK BAŞINA yeterli sayılmaz: geçiş
    kaydı bir ANLIK GÖRÜNTÜdür (dondurulmuştur) ve geçiş uygulandıktan SONRA
    yapılan bir düzeltme (örn. "normal" terfi kaydedilmiş bir öğrencinin sonradan
    sınıf tekrarına çevrilmesiyle `Ogrenci.sinif`in geri alınması) bu anlık
    görüntüye yansımaz; yalnızca `yeni_sinif`e güvenmek böyle bir öğrenciyi hâlâ
    (artık doğru olmayan) eski seviyesinde gösterir (bkz. commit geçmişi —
    3903/YASEMİN YALINSU geçişte "10→11 normal" görünüyor ama `Ogrenci.sinif`
    sonradan 10'a düzeltilmiş, gerçek sınıf tekrarı 10. sınıfta). Yalnızca
    `Ogrenci.sinif=gelecek_sinif` kullanmak da tek başına yeterli değildir; aksi
    hâlde (özellikle 9./10. sınıfta) `secili_yil`den SONRA doğrudan o seviyeye
    yeni kayıt olmuş öğrenciler (bu geçişle hiç ilgisi olmayanlar) yanlışlıkla
    denetime dahil olur (bkz. commit geçmişi — 9. sınıfta 237 "yeni kayıt"
    öğrencisi 2025-2026 denetiminde görünüyordu). `secili_yil` için henüz
    uygulanmış bir çıkış geçişi yoksa (tipik olarak `secili_yil` = aktif/güncel
    yıl olduğunda — o yılın geçişi henüz yapılmadı) yalnızca mevcut fiilî nüfusa
    (`Ogrenci.sinif=gelecek_sinif`) düşülür.
    """
    from ogrenci.models import Ogrenci
    from ogrencidersleri.models import OgrenciSecmeliDers
    from senesonu.models import SeneSonuGecisi

    from ..models import Alan, AlanDers

    kohort_yili = baskin_egitim_yili(gelecek_sinif, secili_yil)
    alanlar = list(
        _yf(Alan.objects.filter(sinif_seviyesi=gelecek_sinif), kohort_yili)
        .order_by("sira", "adi")
    )
    alan_ders_map = {
        a.pk: set(AlanDers.objects.filter(alan=a).values_list("ders_id", flat=True))
        for a in alanlar
    }

    gecis = (
        SeneSonuGecisi.objects.filter(eski_egitim_yili=secili_yil, uygulandi=True)
        .order_by("-uygulama_zamani")
        .first()
    )

    if gecis:
        # Öğrencinin bu geçişteki KENDİ satırı (hangi `yeni_sinif`e yazıldığından
        # bağımsız) — yalnızca "secili_yil kohortuna dahildi mi" ve varsa "önceki
        # sınıf/şube" bilgisi için kullanılır; gerçek seviye kararı `Ogrenci.sinif`e
        # bırakılır (bkz. yukarıdaki docstring notu).
        onceki_map = {
            ogr_id: (eski_sinif, eski_sube)
            for ogr_id, eski_sinif, eski_sube in gecis.ogrenci_gecisleri
            .order_by("gecis_id")
            .values_list("ogrenci_id", "eski_sinif", "eski_sube")
        }
        ogrenciler = list(
            Ogrenci.objects.filter(
                pk__in=onceki_map.keys(), sinif=gelecek_sinif, aktif=True
            ).order_by("sube", "okulno")
        )
    else:
        # secili_yil için henüz uygulanmış bir çıkış geçişi yok (örn. secili_yil aktif
        # yılın kendisi) — bu durumda "kohorta dahil miydi" bilgisi sorgulanamaz,
        # mevcut fiilî nüfus kullanılır.
        onceki_map = {}
        ogrenciler = list(
            Ogrenci.objects.filter(sinif=gelecek_sinif, aktif=True).order_by("sube", "okulno")
        )

    ogr_ids = [o.pk for o in ogrenciler]
    for ogr in ogrenciler:
        eski = onceki_map.get(ogr.pk)
        ogr.onceki_sinif = eski[0] if eski else None
        ogr.onceki_sube = eski[1] if eski else None

    # `kohort_yili`ya göre kapsamlanır — aksi hâlde sınıf tekrarı yapan bir öğrencinin
    # (mevcut sinif seviyesi = gelecek_sinif) hem geçmiş hem güncel yıla etiketli
    # seçimleri birlikte sayılır ve eşleştirme yanlış çıkar (bkz. ogrencidersleri'ndeki
    # aynı sınıf hatası — commit geçmişi).
    ogr_secim = defaultdict(set)
    for ogr_id, ders_id in _yf(
        OgrenciSecmeliDers.objects.filter(ogrenci_id__in=ogr_ids, ders__grup__sinif_seviyesi=gelecek_sinif),
        kohort_yili, "ders__grup__egitim_yili",
    ).values_list("ogrenci_id", "ders_id"):
        ogr_secim[ogr_id].add(ders_id)

    alan_ogr = defaultdict(list)
    alan_yok = []
    for ogr in ogrenciler:
        secimler = ogr_secim.get(ogr.pk, set())
        if not secimler:
            alan_yok.append(ogr)
            continue
        en_iyi_pk, en_iyi_skor = None, 0
        for a_pk, d_ids in alan_ders_map.items():
            skor = len(secimler & d_ids)
            if skor > en_iyi_skor:
                en_iyi_skor, en_iyi_pk = skor, a_pk
        (alan_ogr[en_iyi_pk] if en_iyi_pk else alan_yok).append(ogr)

    alan_gruplari = []
    for a in alanlar:
        ogrs = alan_ogr.get(a.pk, [])
        sube_ogr_map = defaultdict(list)
        for o in ogrs:
            sube_ogr_map[o.sube].append(o)
        subeler = []
        for harf in sorted(sube_ogr_map):
            grup_ogrenciler = sorted(sube_ogr_map[harf], key=lambda x: x.okulno or 0)
            subeler.append({
                "sube": harf,
                "label": f"{gelecek_sinif}/{harf}",
                "ogrenciler": grup_ogrenciler,
                "kiz_sayi": sum(1 for o in grup_ogrenciler if o.cinsiyet == "K"),
                "erkek_sayi": sum(1 for o in grup_ogrenciler if o.cinsiyet == "E"),
            })
        alan_gruplari.append({
            "alan": a,
            "ogrenci_sayisi": len(ogrs),
            "toplam_kiz": sum(1 for o in ogrs if o.cinsiyet == "K"),
            "toplam_erkek": sum(1 for o in ogrs if o.cinsiyet == "E"),
            "sube_sayisi": len(subeler),
            "subeler": subeler,
        })

    return {
        "sinif": None,
        "gelecek_sinif": gelecek_sinif,
        "alan_gruplari": alan_gruplari,
        "alan_yok": alan_yok,
        "tum_alanlar": alanlar,
        "sinif_tekrari": [],
        "tasdikname": [],
        "toplam_ogr": sum(g["ogrenci_sayisi"] for g in alan_gruplari),
        "toplam_sube": sum(g["sube_sayisi"] for g in alan_gruplari),
    }
