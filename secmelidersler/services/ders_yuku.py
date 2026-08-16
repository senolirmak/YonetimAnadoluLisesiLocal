"""
Branş bazlı haftalık ders yükü (saat) hesaplama.

Ortak (zorunlu) dersler: `OrtakDers.haftalik_saat` × o sınıf seviyesindeki AÇIK
şube sayısı (`okul.SinifSube` / `SinifSubeYil`, verilen eğitim-öğretim yılına göre) —
tam ve kesin bir hesaptır.

Seçmeli dersler: `Alan`/`AlanDers` üzerinden, sınıf/şubeye FİİLEN ATILI olan
dersler kullanılır (SecmeliDersGrubu havuzundaki her ders değil — yalnızca bir
Alan'a eklenmiş, yani gerçekten okutulacak dersler). Her (Alan, AlanDers) çifti
için yük = `AlanDers.secilen_saat` × o Alan'ın şube sayısı:

  - 9. ve 10. sınıfta gerçek bir Alan (izlence) ayrımı yoktur — o seviyenin TÜM
    şubelerini kapsayan tek bir yer tutucu Alan ("YOK") vardır; bu Alan'ın şube
    sayısı o sınıf seviyesinin toplam açık şube sayısıdır (`sube_sayilari()`).
  - 11. ve 12. sınıfta MF/TM/DİL gibi gerçek Alanlar vardır; her Alan'ın şube
    sayısı, o Alan'a FİİLEN kayıtlı öğrencilerin GERÇEK şubelerinden türetilir
    (`secmelidersler.services.ders_dagilimi.plan_sinif_dagilimi_gecmis` — aynı
    fonksiyon "Sınıf Dağılımı" denetim ekranında da kullanılır, tek kaynak).

Branş↔ders eşleştirmesi `OrtakDers.branslar` / `SecmeliDers.branslar` M2M
alanlarından okunur (elle küratörlük yapılan, zaten "öğretmen ders yükü
dağıtımında bu derse aynı branştaki öğretmenler önerilir" amacıyla var olan
alan — bkz. secmelidersler/models.py). Bir ders birden fazla branşa atanmışsa
(örn. Görsel Sanatlar/Müzik) VARSAYILAN olarak saatler PAYLAŞTIRILMAZ — her
atanmış branşın kendi yükü altında TAM saatiyle gösterilir; bu yüzden branşlar
arası bir "genel toplam" satırı hesaplanmaz — aynı dersin saati birden fazla
branşta görünebilir. Seçmeli derslerde bu, GİZLİ BİR ÇİFT SAYIM HATASINA yol
açabilir (örn. "TÜRK SOSYAL HAYATINDA AİLE" hem Tarih hem Felsefe'ye atanmışsa
aynı şubelerin saati her ikisine de tam eklenir) — bunu düzeltmek için
`SecmeliDersBransPaylasimi` ile bir AlanDers'in gerçek şubeleri branşlar
arasında ELLE PAYLAŞTIRILABİLİR (bkz. `coklu_brans_dersleri()`, ders-yuku/
sayfasındaki "Seçmeli Ders Branş Paylaşımı" kartı — aynı ders birden fazla
Alan'da okutuluyorsa hepsi tek kart altında birleşir); paylaşım kaydı varsa o
AlanDers için VARSAYILAN (paylaştırmama) davranışın yerini alır.

Norm kadro: her branşın toplam saatinden `norm_kadro()` ile gereken öğretmen
sayısı (norm) hesaplanır — bkz. o fonksiyonun docstring'i. Norm hesaplanmadan
ÖNCE, o branştaki aktif Okul Müdürü/Müdür Yardımcısı'nın `YoneticiZorunluDersYuku`
ile kayıtlı azaltılmış ders yükü saati toplam saatten düşülür (bkz.
`yonetici_dusum_haritasi()`) — aksi hâlde yönetici "1 mevcut" sayılırken
aslında yalnızca birkaç saat okuttuğu hâlde normu yanlışlıkla dengelermiş gibi
görünür.

İstisna — `BRANS_DERS_YUKU_HARIC`: "REHBERLİK VE YÖNLENDİRME" gibi bazı dersler
branş bağımsız olarak sınıf/şube rehber öğretmenine (hangi branştan olursa olsun)
görevlendirilir; bu yüzden DB'de birçok branşa (neredeyse tüm ana branşlara)
atanmış olabilir. Bu dersleri "PAYLAŞTIRILMAZ" kuralıyla her branşın altına TAM
saatiyle eklemek yükü ciddi şekilde şişirir (örn. 11 branşın her birine aynı
saat eklenir). Bu yüzden bu dersler branş ders yükü hesabına hiç dahil edilmez
— DB'deki `branslar` ataması (başka ekranlarda kullanılıyor olabilir) korunur,
yalnızca bu rapor onu atlar.

İstisna — `BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER`: bazı ZORUNLU (Ortak) dersler
de tıpkı çok-branşlı seçmeli dersler gibi çift sayım hatasına sahiptir — örn.
12. sınıf "BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK" dersi üç branşa
(Beden Eğitimi, Görsel Sanatlar, Müzik) birden atanmıştır, ama her öğrenci
gerçekte bunlardan yalnızca birini seçer. Normalde "Seçmeli Ders Branş
Paylaşımı" kartı yalnızca `SecmeliDers`leri kapsar; bu kümede adı geçen
`OrtakDers` kayıtları da istisna olarak aynı karta (bkz.
`istisna_ortak_ders_kartlari()`) eklenir ve aynı paylaşım mekanizmasıyla
branşlara bölüştürülebilir — bir paylaşım varsa `hesapla()`nın Ortak Dersler
bölümü de artık TAM saati her branşa değil, paylaşılan gerçek şube alt
kümesini kullanır.
"""
from __future__ import annotations

from collections import defaultdict

from ..models import normalize_ders_adi

BRANS_DERS_YUKU_HARIC = {
    normalize_ders_adi("REHBERLİK VE YÖNLENDİRME"),
}

BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER = {
    normalize_ders_adi("BEDEN EĞİTİMİ VE SPOR/GÖRSEL SANATLAR/MÜZİK"),
}

YONETICI_GOREV_TIPLERI = ["Okul Müdürü", "Müdür Yardımcısı"]

_NORM_ILK_ESIK = 6    # bu saatin altı: 0 norm
_NORM_IKINCI_ESIK = 31   # [6, 31) aralığı: 1 norm
_NORM_UCUNCU_ESIK = 42   # [31, 42] aralığı: 2 norm (özel durum)
_NORM_DILIM = 21   # 42'den büyük saatlerde 21'lik dilim başına norm


def norm_kadro(saat):
    """Branş toplam haftalık ders saatinden (yönetici düşümünden SONRAKİ,
    yani `norm_hesap_saati`) norm kadro (gereken öğretmen sayısı) hesaplar:

      - 6 saatin altı: 0 norm
      - 6-31 saat arası: 1 norm (özel durum)
      - 31-42 saat arası (42 dahil): 2 norm (özel durum)
      - 42'den BÜYÜK saat toplamı A ise: NORM = A//21 + (A%21 >= 15 ise 1
        yoksa 0) — yani her tam 21'lik dilim 1 norm, kalan dilimde 15 ve
        üzeri saat varsa (dilimin ≥%71'i) bir norm daha yukarı yuvarlanır.

    Sınırlar dahil-hariç: [6,31) → 1, [31,42] → 2, (42,∞) → A//21 + (A%21>=15).
    """
    if saat < _NORM_ILK_ESIK:
        return 0
    if saat < _NORM_IKINCI_ESIK:
        return 1
    if saat <= _NORM_UCUNCU_ESIK:
        return 2
    return saat // _NORM_DILIM + (1 if saat % _NORM_DILIM >= 15 else 0)


def normalize_sube_metni(metin):
    """Virgülle ayrılmış şube harflerini büyük harfe çevirip sırasız kümeye
    indirger — elle girilen bir değerin o anki OTOMATİK tespitle GERÇEKTEN
    farklı olup olmadığını anlamak için kullanılır (boşluk/sıra farkı bir
    "değişiklik" sayılmaz). Bkz. views.alan_sube_toplu_kaydet."""
    return tuple(sorted({s.strip().upper() for s in metin.split(",") if s.strip()}))


def sube_sayilari(egitim_yili):
    """{sinif_seviyesi: açık şube sayısı} — o yıl için SinifSubeYil.acik=False
    olanlar hariç tutulur (egitim_yili verilmezse hiçbiri hariç tutulmaz)."""
    from okul.models import SinifSube, SinifSubeYil

    kapali_kume = set()
    if egitim_yili is not None:
        kapali_kume = set(
            SinifSubeYil.objects.filter(egitim_yili=egitim_yili, acik=False).values_list(
                "sinif_sube__sinif", "sinif_sube__sube"
            )
        )

    sayilar: dict[int, int] = defaultdict(int)
    for sinif, sube in SinifSube.objects.values_list("sinif", "sube"):
        if (sinif, sube) in kapali_kume:
            continue
        sayilar[sinif] += 1
    return dict(sayilar)


def acik_sube_harfleri(egitim_yili, sinif_seviyesi):
    """O sınıf seviyesindeki AÇIK şube harflerini (SinifSube/SinifSubeYil,
    verilen eğitim-öğretim yılına göre `acik=False` olanlar hariç) sıralı
    döner — `sube_sayilari()`nin tek tek harf listesi hâli. `istisna_ortak_
    ders_kartlari()` Alan ayrımı olmayan "Tüm Şubeler" havuzunu bununla kurar."""
    from okul.models import SinifSube, SinifSubeYil

    kapali_kume = set()
    if egitim_yili is not None:
        kapali_kume = set(
            SinifSubeYil.objects.filter(egitim_yili=egitim_yili, acik=False).values_list(
                "sinif_sube__sinif", "sinif_sube__sube"
            )
        )
    return [
        sube
        for sinif, sube in SinifSube.objects.order_by("sube").values_list("sinif", "sube")
        if sinif == sinif_seviyesi and (sinif, sube) not in kapali_kume
    ]


# ---------------------------------------------------------------------------
# Şube Bölme — bkz. SecmeliDersSubeBolunmesi docstring'i
# ---------------------------------------------------------------------------
# Normal (bölünmemiş) bir şube, rozet/paylaşım sistemi içinde DÜZ HARFİ ("A")
# ile temsil edilir ve tüm ders saatini taşır. Bölünmüş bir şube, her biri
# KENDİ saatini taşıyan birden fazla "parça token"ına ("A#1#1", "A#2#2" gibi
# — harf#parça_no#saat) genişletilir; her parça ayrı bir branşa sürüklenip
# bırakılabilir. Token'lar `SecmeliDersBransPaylasimi.subeler`de DÜZ METİN
# olarak saklanır (o alan zaten opak virgüllü bir liste); bu modülün
# `_sube_token_*` yardımcıları eski (düz harf) ve yeni (parça) biçimleri
# tek bir arayüzde ele alır.

def _sube_token_ayikla(token):
    """'A#1#2' gibi bir parça token'ını (harf, saat) olarak ayıklar; düz bir
    şube harfiyse (örn. 'A') (harf, None) döner (bölünmemiş — saat çağıran
    tarafından, genelde dersin `secilen_saat`/`haftalik_saat`ından alınır)."""
    parcalar = token.split("#")
    if len(parcalar) == 3:
        harf, _sira, saat_metni = parcalar
        try:
            return harf, int(saat_metni)
        except ValueError:
            return harf, None
    return token, None


def _sube_token_etiket(token):
    """Rozet üzerinde gösterilecek okunur etiket: bölünmemişse düz harf
    ('A'), bölünmüşse 'A·2s' gibi saat eki ile."""
    harf, saat = _sube_token_ayikla(token)
    return f"{harf}·{saat}s" if saat is not None else harf


def _sube_token_saat(token, varsayilan_saat):
    """Token'ın taşıdığı saati döner — bölünmemiş bir token için dersin TAM
    saatini (`varsayilan_saat`), bölünmüş bir parça için KENDİ saatini."""
    _harf, saat = _sube_token_ayikla(token)
    return saat if saat is not None else varsayilan_saat


def _sube_tokenlari_genislet(subeler, bolunme_map):
    """Düz şube harfi listesini (`['A','B']`), bölünme tanımı olan şubeleri
    parça token'larına açarak genişletir. `bolunme_map`: {harf: [saat, ...]}
    (bkz. `SecmeliDersSubeBolunmesi.parca_listesi`). Bölünmesi olmayan
    harfler DEĞİŞMEDEN kalır (eski davranışla tam uyumlu)."""
    sonuc = []
    for harf in subeler:
        parcalar = bolunme_map.get(harf)
        if parcalar:
            sonuc.extend(f"{harf}#{sira}#{saat}" for sira, saat in enumerate(parcalar, start=1))
        else:
            sonuc.append(harf)
    return sonuc


def alan_sube_sayilari(egitim_yili, sube_map=None):
    """{Alan: şube_sayısı} — 9-10. sınıfın tek "YOK" Alan'ı için o seviyenin
    toplam açık şube sayısı; 11-12. sınıfın MF/TM/DİL Alanları için Alan'a
    fiilen kayıtlı öğrencilerin gerçek şube sayısı (bkz. modül docstring'i).

    ÖNEMLİ: 11-12. sınıf için döndürülen `Alan` nesneleri `egitim_yili`
    parametresine değil, `plan_sinif_dagilimi_gecmis`in kullandığı
    `baskin_egitim_yili`ye (kohort_yili) ait olabilir — öğrencilerin GERÇEK
    seçimlerinin hangi Alan/AlanDers kataloğuna bağlı olduğu `egitim_yili`den
    farklı bir yıl olabilir (örn. 11. sınıf öğrencileri seçimlerini bir önceki
    yılın kataloğuyla yapmış olabilir). Bu yüzden `hesapla()`/`atanmamis_dersler()`
    bu fonksiyonun döndürdüğü Alan nesnelerini DOĞRUDAN kullanmalı — ayrıca
    `egitim_yili` ile yeniden filtrelenmemelidir, aksi hâlde AlanDers eşleşmesi
    sessizce boş (0 şube) çıkar (bkz. commit geçmişi).

    `AlanSubeAtama` ile elle atanmış bir şube listesi varsa (bkz. ders-yuku/
    sayfasındaki "Alan Şube Ataması" kartı), otomatik tespitin ÜZERİNE YAZAR.
    """
    from ..models import Alan, AlanSubeAtama
    from .ders_dagilimi import plan_sinif_dagilimi_gecmis

    if sube_map is None:
        sube_map = sube_sayilari(egitim_yili)

    sonuc: dict = {}

    for sv in (9, 10):
        for alan in Alan.objects.filter(egitim_yili=egitim_yili, sinif_seviyesi=sv):
            sonuc[alan] = sube_map.get(sv, 0)

    for sv in (11, 12):
        plan = plan_sinif_dagilimi_gecmis(sv, egitim_yili)
        for grup in plan["alan_gruplari"]:
            sonuc[grup["alan"]] = grup["sube_sayisi"]

    manuel_map = {
        a.alan_id: a.sube_sayisi
        for a in AlanSubeAtama.objects.filter(alan__in=[alan.pk for alan in sonuc])
    }
    for alan in list(sonuc):
        if alan.pk in manuel_map:
            sonuc[alan] = manuel_map[alan.pk]

    return sonuc


def alan_sube_detaylari(egitim_yili):
    """Sınıf seviyesi bazında gruplu, her Alan için otomatik tespit edilen şube
    listesini ve varsa elle atanmış override'ı bir arada döner — ders-yuku/
    sayfasındaki "Alan Şube Ataması" kartı için.

    Döner: [{"sinif_seviyesi": int, "alanlar": [
        {"alan": Alan, "auto_subeler": [harf, ...], "manuel": AlanSubeAtama|None,
         "kullanilan_sayi": int},
        ...
    ]}, ...]
    """
    from okul.models import SinifSube, SinifSubeYil

    from ..models import Alan, AlanSubeAtama
    from .ders_dagilimi import plan_sinif_dagilimi_gecmis

    kapali_kume = set()
    if egitim_yili is not None:
        kapali_kume = set(
            SinifSubeYil.objects.filter(egitim_yili=egitim_yili, acik=False).values_list(
                "sinif_sube__sinif", "sinif_sube__sube"
            )
        )
    acik_subeler_by_seviye: dict = defaultdict(list)
    for sinif, sube in SinifSube.objects.order_by("sinif", "sube").values_list("sinif", "sube"):
        if (sinif, sube) in kapali_kume:
            continue
        acik_subeler_by_seviye[sinif].append(sube)

    manuel_map = {a.alan_id: a for a in AlanSubeAtama.objects.select_related("alan")}

    gruplar = []
    for sv in (9, 10, 11, 12):
        alan_satirlari = []
        if sv in (9, 10):
            for alan in Alan.objects.filter(egitim_yili=egitim_yili, sinif_seviyesi=sv).order_by("sira"):
                auto = acik_subeler_by_seviye.get(sv, [])
                manuel = manuel_map.get(alan.pk)
                alan_satirlari.append({
                    "alan": alan, "auto_subeler": auto, "manuel": manuel,
                    "kullanilan_sayi": manuel.sube_sayisi if manuel else len(auto),
                })
        else:
            plan = plan_sinif_dagilimi_gecmis(sv, egitim_yili)
            for grup in plan["alan_gruplari"]:
                alan = grup["alan"]
                auto = [s["sube"] for s in grup["subeler"]]
                manuel = manuel_map.get(alan.pk)
                alan_satirlari.append({
                    "alan": alan, "auto_subeler": auto, "manuel": manuel,
                    "kullanilan_sayi": manuel.sube_sayisi if manuel else len(auto),
                })
        gruplar.append({"sinif_seviyesi": sv, "alanlar": alan_satirlari})
    return gruplar


def coklu_brans_dersleri(egitim_yili):
    """"Seçmeli Ders Branş Paylaşımı" kartında gösterilecek SecmeliDers'leri
    DERS bazında GRUPLU döner — aynı ders birden fazla Alan'da okutuluyorsa
    (örn. 11. sınıfta "TÜRK SOSYAL HAYATINDA AİLE" hem DİL hem MF hem TM'de
    varsa) hepsi TEK kart altında birleşir; her Alan'ın kendi AlanDers'i ve
    gerçek şubeleri korunur (bir SecmeliDers zaten tek bir sınıf seviyesine
    ait olduğundan — SecmeliDersGrubu.sinif_seviyesi — bu gruplama farklı
    sınıf seviyelerini asla karıştırmaz).

    İki kaynaktan gelir (bkz. `SecmeliDersBransPaylasimi` docstring'i — çift
    sayım hatasını önlemek için):
      1. OTOMATİK: birden fazla branşa atanmış (`SecmeliDers.branslar.count() > 1`)
         VE fiilen en az bir Alan'a atılı olan dersler.
      2. ELLE EKLENMİŞ: yukarıdaki kritere uymasa bile (örn. tek branşlı bir
         ders) kullanıcının "Ders Ekle" formuyla en az bir
         `SecmeliDersBransPaylasimi` kaydı oluşturduğu dersler.

    Bir dersin `brans_satirlari`si, dersin `SecmeliDers.branslar`daki "resmî"
    branşlarını VE varsa bunların dışında elle eklenmiş branş paylaşımlarını
    birlikte içerir. Her branş satırının `hucreler`i, bu dersin HER Alan'ı
    için bir hücre içerir (o Alan'da paylaşım kaydı olmasa bile) — böylece
    sürükle-bırakla herhangi bir Alan'ın şubesi ilk kez oraya bırakılabilir.

    Döner: [{"ders": SecmeliDers, "sinif_seviyesi": int,
             "alan_dersler": [AlanDers, ...],
             "havuz_rozetleri": [{"alan_ders": AlanDers, "sube": token, "etiket": str}, ...],
             "brans_satirlari": [{"brans": Brans,
                 "hucreler": [{"alan_ders": AlanDers,
                               "paylasim": SecmeliDersBransPaylasimi|None}, ...]},
                ...]},
            ...] — sınıf seviyesi, ders adına göre sıralı. `havuz_rozetleri`
    ve `paylasim.sube_listesi`deki "sube" değerleri düz bir harf ("A") ya da
    — o (AlanDers, şube) çiftinde bir `SecmeliDersSubeBolunmesi` varsa — bir
    parça token'ı ("A#1#1") olabilir; bkz. modülün "Şube Bölme" bölümü.
    """
    from ..models import AlanDers, SecmeliDersBransPaylasimi, SecmeliDersSubeBolunmesi

    sube_map = sube_sayilari(egitim_yili)
    alan_sube_map = alan_sube_sayilari(egitim_yili, sube_map)

    efektif_sube_harfleri: dict = {}
    for grup in alan_sube_detaylari(egitim_yili):
        for satir in grup["alanlar"]:
            manuel = satir["manuel"]
            efektif_sube_harfleri[satir["alan"].pk] = (
                manuel.sube_listesi if manuel else satir["auto_subeler"]
            )

    alanders_qs = (
        AlanDers.objects.filter(alan__in=alan_sube_map.keys())
        .select_related("alan", "ders")
        .prefetch_related("ders__branslar")
    )

    paylasim_map: dict = defaultdict(dict)
    for p in SecmeliDersBransPaylasimi.objects.select_related("brans"):
        paylasim_map[p.alan_ders_id][p.brans_id] = p

    bolunme_by_alanders: dict = defaultdict(dict)
    for b in SecmeliDersSubeBolunmesi.objects.filter(alan_ders__isnull=False):
        bolunme_by_alanders[b.alan_ders_id][b.sube] = b.parca_listesi

    ders_alanders: dict = defaultdict(list)
    ders_obj_map: dict = {}
    for ad in alanders_qs:
        ders_alanders[ad.ders_id].append(ad)
        ders_obj_map[ad.ders_id] = ad.ders

    sonuc = []
    for ders_id, alan_dersler in ders_alanders.items():
        ders = ders_obj_map[ders_id]
        resmi_branslar = list(ders.branslar.all())
        resmi_brans_idler = {b.pk for b in resmi_branslar}

        ekstra_branslar = {}
        for ad in alan_dersler:
            for brans_id, p in paylasim_map.get(ad.pk, {}).items():
                if brans_id not in resmi_brans_idler:
                    ekstra_branslar[brans_id] = p.brans

        if len(resmi_branslar) < 2 and not ekstra_branslar:
            continue

        alan_dersler = sorted(alan_dersler, key=lambda a: a.alan.adi)
        tum_branslar = resmi_branslar + list(ekstra_branslar.values())

        brans_satirlari = []
        atanmis_by_alanders: dict = defaultdict(set)
        for brans in tum_branslar:
            hucreler = []
            for ad in alan_dersler:
                p = paylasim_map.get(ad.pk, {}).get(brans.pk)
                hucreler.append({"alan_ders": ad, "paylasim": p})
                if p:
                    atanmis_by_alanders[ad.pk].update(p.sube_listesi)
            brans_satirlari.append({"brans": brans, "hucreler": hucreler})

        havuz_rozetleri = []
        for ad in alan_dersler:
            sube_listesi = efektif_sube_harfleri.get(ad.alan.pk, [])
            genisletilmis = _sube_tokenlari_genislet(sube_listesi, bolunme_by_alanders.get(ad.pk, {}))
            atanmis = atanmis_by_alanders.get(ad.pk, set())
            havuz_rozetleri.extend(
                {"alan_ders": ad, "sube": token, "etiket": _sube_token_etiket(token), "bolunmus": "#" in token}
                for token in genisletilmis if token not in atanmis
            )

        sonuc.append({
            "ders": ders,
            "sinif_seviyesi": alan_dersler[0].alan.sinif_seviyesi,
            "alan_dersler": alan_dersler,
            "havuz_rozetleri": havuz_rozetleri,
            "brans_satirlari": brans_satirlari,
            "kaynak_tur": "secmeli",
        })

    sonuc.sort(key=lambda s: (s["sinif_seviyesi"], s["ders"].ders_adi))
    return sonuc


class _OrtakDersSutunu:
    """`coklu_brans_dersleri()` şablonunun beklediği `AlanDers` arayüzünü
    (`.pk`, `.alan.adi`, `.secilen_saat`) taklit eden hafif bir sarmalayıcı.
    İstisna bir Ortak Ders'te Alan ayrımı olmadığından tek bir sanal "sütun"
    olarak temsil edilir — bu sayede şablon/JS/view kodu AlanDers'e özel
    yazılmadan tek bir hücre soyutlamasıyla çalışabilir. `.pk` metin
    ("o<pk>") olduğundan gerçek (tam sayı) AlanDers pk'leriyle asla çakışmaz."""

    class _AlanShim:
        def __init__(self, adi):
            self.adi = adi

    def __init__(self, ortak_ders):
        self.ortak_ders = ortak_ders
        self.pk = f"o{ortak_ders.pk}"
        self.alan = self._AlanShim("Tüm Şubeler")
        self.secilen_saat = ortak_ders.haftalik_saat


def istisna_ortak_ders_kartlari(egitim_yili):
    """`coklu_brans_dersleri()` ile AYNI kart şemasını, `BRANS_PAYLASIM_
    ISTISNA_ORTAK_DERSLER`de adı geçen `OrtakDers` kayıtları için üretir —
    bu dersler Zorunlu (Ortak) olduğundan normalde bu karta hiç girmezler
    (bkz. modül docstring'i). Alan ayrımı olmadığından her kartın TEK bir
    sanal sütunu (`_OrtakDersSutunu`) vardır; `kaynak_tur` alanı view'ların
    (kaydet/ekle/kaldır) `SecmeliDersBransPaylasimi.alan_ders` yerine
    `.ortak_ders` alanını kullanması gerektiğini ayırt eder."""
    from ..models import OrtakDers, SecmeliDersBransPaylasimi, SecmeliDersSubeBolunmesi

    istisnalar = [
        d
        for d in OrtakDers.objects.filter(egitim_yili=egitim_yili).prefetch_related("branslar")
        if normalize_ders_adi(d.ders_adi) in BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER
    ]
    if not istisnalar:
        return []

    paylasim_map: dict = defaultdict(dict)
    for p in SecmeliDersBransPaylasimi.objects.filter(ortak_ders__in=istisnalar).select_related("brans"):
        paylasim_map[p.ortak_ders_id][p.brans_id] = p

    bolunme_by_ortakders: dict = defaultdict(dict)
    for b in SecmeliDersSubeBolunmesi.objects.filter(ortak_ders__in=istisnalar):
        bolunme_by_ortakders[b.ortak_ders_id][b.sube] = b.parca_listesi

    sonuc = []
    for ders in istisnalar:
        sutun = _OrtakDersSutunu(ders)
        resmi_branslar = list(ders.branslar.all())
        resmi_brans_idler = {b.pk for b in resmi_branslar}

        ekstra_branslar = {
            brans_id: p.brans
            for brans_id, p in paylasim_map.get(ders.pk, {}).items()
            if brans_id not in resmi_brans_idler
        }
        tum_branslar = resmi_branslar + list(ekstra_branslar.values())

        brans_satirlari = []
        atanmis: set = set()
        for brans in tum_branslar:
            p = paylasim_map.get(ders.pk, {}).get(brans.pk)
            brans_satirlari.append({"brans": brans, "hucreler": [{"alan_ders": sutun, "paylasim": p}]})
            if p:
                atanmis.update(p.sube_listesi)

        tum_subeler = acik_sube_harfleri(egitim_yili, ders.sinif_seviyesi)
        genisletilmis = _sube_tokenlari_genislet(tum_subeler, bolunme_by_ortakders.get(ders.pk, {}))
        havuz_rozetleri = [
            {"alan_ders": sutun, "sube": token, "etiket": _sube_token_etiket(token), "bolunmus": "#" in token}
            for token in genisletilmis if token not in atanmis
        ]

        sonuc.append({
            "ders": ders,
            "sinif_seviyesi": ders.sinif_seviyesi,
            "alan_dersler": [sutun],
            "havuz_rozetleri": havuz_rozetleri,
            "brans_satirlari": brans_satirlari,
            "kaynak_tur": "ortak",
        })
    return sonuc


def brans_paylasimi_kartlari(egitim_yili):
    """`coklu_brans_dersleri()` (çok branşlı Seçmeli Dersler) ile
    `istisna_ortak_ders_kartlari()` (istisna Zorunlu Dersler) kartlarını TEK,
    sınıf seviyesi + ders adına göre sıralı listede birleştirir — "Seçmeli
    Ders Branş Paylaşımı" sayfasının (view + kaydet/ekle/kaldır) tek kaynağı
    budur."""
    kartlar = coklu_brans_dersleri(egitim_yili) + istisna_ortak_ders_kartlari(egitim_yili)
    kartlar.sort(key=lambda s: (s["sinif_seviyesi"], s["ders"].ders_adi))
    return kartlar


def tum_secmeli_dersler(egitim_yili):
    """Bu yıl fiilen atılı (en az bir Alan'a eklenmiş) TÜM SecmeliDers'leri
    TEKİL (Alan'a göre tekrarsız) döner — "Seçmeli Ders Branş Paylaşımı"
    kartındaki "Ders Ekle" seçim kutusunun kaynağı. `coklu_brans_dersleri()`den
    farkı: yalnızca çoklu branşlı olanları değil, hepsini listeler — kullanıcı
    tek branşlı (hatta hiç branşı olmayan) bir derse de elle paylaşım
    ekleyebilsin diye. Aynı ders birden fazla Alan'da okutuluyorsa listede TEK
    satır olarak görünür (dropdown'da yalnızca ders adı gösterilir)."""
    from ..models import SecmeliDers

    sube_map = sube_sayilari(egitim_yili)
    alan_sube_map = alan_sube_sayilari(egitim_yili, sube_map)
    return list(
        SecmeliDers.objects.filter(alan_dersler__alan__in=alan_sube_map.keys())
        .select_related("grup")
        .distinct()
        .order_by("grup__sinif_seviyesi", "ders_adi")
    )


_MEVCUT_DURUM_SABIT = {"Görevde", "Dış Görevde"}


def _mevcut_durumlar():
    """Norm kadro karşılaştırmasında "Mevcut" sayılan `Personel.durum` değerleri:
    Görevde + Dış Görevde + adında "İzin" geçen tüm izin türleri (örn. Aylıksız
    İzinli, Analık İzinli) — kadrosu hâlâ o branşa ait sayılır, izinliyken
    branşın normundan düşülmez. Yalnızca fiilen ayrılmış olanlar (Emekli,
    Ayrıldı-Tayin, Açığa Alındı, Görevlendirme Sona Erdi) hariç tutulur.

    NOT: bu, `Personel.objects.gorevde()` (durum="Görevde", "yeni bir göreve
    şu an atanabilir mi" anlamında — rehberlik/sorumluluk/kullanıcı hesabı
    gibi ekranlarda kullanılır) ile KARIŞTIRILMAMALI; "Mevcut" burada "kadrosu
    bu branşa ait mi" anlamındadır, bilerek daha geniş bir küme kullanır.
    """
    from okul.models import Personel

    # NOT: Python'da "İ".lower() -> "i̇" (noktalı, iki karakterli) olduğundan
    # "izin" in deger.lower() SESSİZCE False döner ("İzinli" hiç eşleşmez).
    # Bu yüzden "İzin" büyük/küçük harf DUYARLI aranır — DURUM_CHOICES'taki
    # tüm izin türleri gerçekte hep "İzin" (büyük İ) ile başlıyor.
    return _MEVCUT_DURUM_SABIT | {
        deger for deger, _ in Personel.DURUM_CHOICES if "İzin" in deger
    }


def mevcut_ogretmenler():
    """{brans_id: [Personel, ...]} — "Mevcut" sayılan öğretmenler (bkz.
    `_mevcut_durumlar`), branş bazlı gruplu ve isme göre sıralı. Sayaç
    (`mevcut`) burada `len()` ile türetilir; ders-yuku/ sayfasındaki "Mevcut"
    etiketine tıklanınca açılan öğretmen listesi de aynı veriden gelir.

    Okul Müdürü / Müdür Yardımcısı (`YONETICI_GOREV_TIPLERI`) burada SAYILMAZ —
    onlar zaten ayrı bir yolla (bkz. `yonetici_dusum_haritasi`) branşın toplam
    ders yükünden düşülüyor; hem "1 mevcut öğretmen" hem de "yükten düşülen
    kişi" olarak sayılırlarsa aynı kişi iki farklı yönde norm hesabını
    etkilemiş (ve mevcut'u yanlış şişirmiş) olurdu.
    """
    from okul.models import Personel

    sonuc: dict = defaultdict(list)
    qs = (
        Personel.objects.filter(durum__in=_mevcut_durumlar())
        .exclude(brans__isnull=True)
        .exclude(gorev_tipi__in=YONETICI_GOREV_TIPLERI)
        .order_by("brans_id", "adi_soyadi")
    )
    for p in qs:
        sonuc[p.brans_id].append(p)
    return dict(sonuc)


def yonetici_ders_yuku_detaylari():
    """Aktif (durum="Görevde") Okul Müdürü / Müdür Yardımcısı listesini,
    branşları ve varsa kayıtlı `YoneticiZorunluDersYuku.saat` değerleriyle
    birlikte döner — ders-yuku/ sayfasındaki "Yönetici Zorunlu Ders Yükü"
    formunun kaynağı. Kayıt yoksa saat 0 varsayılır (henüz elle girilmemiş).

    Döner: [{"personel": Personel, "saat": int}, ...] — adı soyadına göre sıralı.
    """
    from okul.models import Personel

    from ..models import YoneticiZorunluDersYuku

    kayitli = dict(YoneticiZorunluDersYuku.objects.values_list("personel_id", "saat"))
    yoneticiler = (
        Personel.objects.gorevde()
        .filter(gorev_tipi__in=YONETICI_GOREV_TIPLERI)
        .select_related("brans")
        .order_by("adi_soyadi")
    )
    return [{"personel": p, "saat": kayitli.get(p.pk, 0)} for p in yoneticiler]


def yonetici_dusum_haritasi():
    """{brans_id: toplam Zorunlu Ders Yükü saati} — norm hesabından önce ilgili
    branşın toplam ders yükünden düşülecek tutar (bkz. modül docstring'i)."""
    sonuc: dict = defaultdict(int)
    for satir in yonetici_ders_yuku_detaylari():
        p = satir["personel"]
        if p.brans_id:
            sonuc[p.brans_id] += satir["saat"]
    return dict(sonuc)


def hesapla(egitim_yili):
    """Branş bazlı ders yükünü (ve norm/mevcut/fazla/eksik karşılaştırmasını) hesaplar.

    Döner: [{"brans": Brans, "ortak_saat": int, "secmeli_saat": int,
             "toplam_saat": int, "yonetici_dusum_saat": int,
             "norm_hesap_saati": int, "norm_kadro": int, "mevcut": int,
             "ogretmenler": [Personel, ...], "fazla": int, "eksik": int,
             "dersler": [...]}, ...] — brans adına göre sıralı. `toplam_saat`
    HAM (yönetici düşümü uygulanmamış) ders yüküdür; `norm_hesap_saati` =
    `toplam_saat - yonetici_dusum_saat` (0'ın altına inmez) — `norm_kadro` bu
    düşülmüş saat üzerinden hesaplanır (bkz. `yonetici_dusum_haritasi`). `mevcut`
    o branştaki "Mevcut" sayılan öğretmen sayısıdır (`len(ogretmenler)`);
    `ogretmenler` ders-yuku/ sayfasında "Mevcut" etiketine tıklanınca açılan
    listeyi besler. `fazla`/`eksik`, (norm_kadro - mevcut) negatifse/pozitifse
    mutlak değeridir (ikisinden yalnızca biri 0'dan farklı olabilir).
    """
    from ..models import AlanDers, OrtakDers, SecmeliDersBransPaylasimi

    sube_map = sube_sayilari(egitim_yili)
    alan_sube_map = alan_sube_sayilari(egitim_yili, sube_map)

    sonuc: dict = defaultdict(lambda: {"ortak_saat": 0, "secmeli_saat": 0, "dersler": []})

    # ── Ortak Dersler ──────────────────────────────────────────────
    # İstisna dersler (bkz. BRANS_PAYLASIM_ISTISNA_ORTAK_DERSLER) için elle
    # girilmiş bir SecmeliDersBransPaylasimi.ortak_ders paylaşımı varsa TAM
    # saat yerine bu paylaşımlar kullanılır (Seçmeli Dersler bölümündeki
    # paylasim_by_alanders ile aynı mantık — bkz. modül docstring'i).
    ortak_paylasim_by_ders: dict = defaultdict(list)
    for p in SecmeliDersBransPaylasimi.objects.filter(ortak_ders__isnull=False).select_related("brans"):
        ortak_paylasim_by_ders[p.ortak_ders_id].append(p)

    ortak_qs = OrtakDers.objects.filter(egitim_yili=egitim_yili).prefetch_related("branslar")
    for ders in ortak_qs:
        if normalize_ders_adi(ders.ders_adi) in BRANS_DERS_YUKU_HARIC:
            continue
        sube_n = sube_map.get(ders.sinif_seviyesi, 0)
        saat = ders.haftalik_saat * sube_n

        paylasimlar = ortak_paylasim_by_ders.get(ders.pk)
        if paylasimlar:
            for p in paylasimlar:
                p_saat = sum(_sube_token_saat(t, ders.haftalik_saat) for t in p.sube_listesi)
                sonuc[p.brans]["ortak_saat"] += p_saat
                sonuc[p.brans]["dersler"].append({
                    "tur": "ortak", "sinif_seviyesi": ders.sinif_seviyesi,
                    "ders_adi": f"{ders.ders_adi} ({p.brans.ad} payı)", "saat": p_saat,
                    "detay": f"{ders.haftalik_saat} saat × {p.sube_sayisi} şube ({', '.join(p.etiket_listesi)})",
                })
        else:
            for brans in ders.branslar.all():
                sonuc[brans]["ortak_saat"] += saat
                sonuc[brans]["dersler"].append({
                    "tur": "ortak", "sinif_seviyesi": ders.sinif_seviyesi,
                    "ders_adi": ders.ders_adi, "saat": saat,
                    "detay": f"{ders.haftalik_saat} saat × {sube_n} şube",
                })

    # ── Seçmeli Dersler (Alan/AlanDers üzerinden — fiilen atılı olanlar) ────
    # alan_sube_map.keys() kullanılır (alan__egitim_yili=egitim_yili DEĞİL) —
    # bkz. alan_sube_sayilari() docstring'i: 11-12. sınıfta gerçek Alan nesnesi
    # farklı bir yılın kataloğuna ait olabilir.
    alanders_qs = (
        AlanDers.objects.filter(alan__in=alan_sube_map.keys())
        .select_related("alan", "ders")
        .prefetch_related("ders__branslar")
    )

    # Birden fazla branşa atanmış derslerde (bkz. SecmeliDersBransPaylasimi
    # docstring'i — çift sayım hatası) elle girilmiş paylaşım varsa TAM saat
    # yerine bu paylaşımlar kullanılır.
    paylasim_by_alanders: dict = defaultdict(list)
    for p in SecmeliDersBransPaylasimi.objects.select_related("brans"):
        paylasim_by_alanders[p.alan_ders_id].append(p)

    for ad in alanders_qs:
        ders = ad.ders
        if normalize_ders_adi(ders.ders_adi) in BRANS_DERS_YUKU_HARIC:
            continue
        sube_n = alan_sube_map.get(ad.alan, 0)
        saat = ad.secilen_saat * sube_n

        paylasimlar = paylasim_by_alanders.get(ad.pk)
        if paylasimlar:
            for p in paylasimlar:
                p_saat = sum(_sube_token_saat(t, ad.secilen_saat) for t in p.sube_listesi)
                sonuc[p.brans]["secmeli_saat"] += p_saat
                sonuc[p.brans]["dersler"].append({
                    "tur": "secmeli", "sinif_seviyesi": ad.alan.sinif_seviyesi,
                    "ders_adi": f"{ders.ders_adi} ({ad.alan.adi} — {p.brans.ad} payı)", "saat": p_saat,
                    "detay": f"{ad.secilen_saat} saat × {p.sube_sayisi} şube ({', '.join(p.etiket_listesi)})",
                })
        else:
            for brans in ders.branslar.all():
                sonuc[brans]["secmeli_saat"] += saat
                sonuc[brans]["dersler"].append({
                    "tur": "secmeli", "sinif_seviyesi": ad.alan.sinif_seviyesi,
                    "ders_adi": f"{ders.ders_adi} ({ad.alan.adi})", "saat": saat,
                    "detay": f"{ad.secilen_saat} saat × {sube_n} şube ({ad.alan.adi})",
                })

    ogretmen_map = mevcut_ogretmenler()
    dusum_map = yonetici_dusum_haritasi()

    satirlar = []
    for brans, veri in sonuc.items():
        veri["toplam_saat"] = veri["ortak_saat"] + veri["secmeli_saat"]
        veri["yonetici_dusum_saat"] = dusum_map.get(brans.pk, 0)
        veri["norm_hesap_saati"] = max(0, veri["toplam_saat"] - veri["yonetici_dusum_saat"])
        veri["norm_kadro"] = norm_kadro(veri["norm_hesap_saati"])
        veri["ogretmenler"] = ogretmen_map.get(brans.pk, [])
        veri["mevcut"] = len(veri["ogretmenler"])
        fark = veri["norm_kadro"] - veri["mevcut"]
        veri["fazla"] = abs(fark) if fark < 0 else 0
        veri["eksik"] = fark if fark > 0 else 0
        veri["brans"] = brans
        veri["dersler"].sort(key=lambda d: (d["sinif_seviyesi"], d["tur"], d["ders_adi"]))
        satirlar.append(veri)
    satirlar.sort(key=lambda s: s["brans"].ad)
    return satirlar


def atanmamis_dersler(egitim_yili):
    """Branş atanmamış (branslar M2M boş) — ama fiilen bir Alan'a ATILI OLAN —
    Ortak/Seçmeli dersleri döner. Ders yükü raporunda bu dersler hiçbir branşın
    altında görünmez; kullanıcı bu listedeki dersler için branş ataması
    yapmalıdır. BRANS_DERS_YUKU_HARIC listesindeki dersler (branşsız olsa da)
    bu uyarıya dahil edilmez — onlar zaten hesaba hiç katılmadığı için
    branşsız olmaları bir veri eksikliği değildir. SecmeliDersGrubu havuzunda
    olup hiçbir Alan'a atanmamış (bu yıl fiilen okutulmayacak) dersler de bu
    listeye dahil edilmez.
    """
    from ..models import OrtakDers, SecmeliDers

    ortak = [
        d for d in OrtakDers.objects.filter(egitim_yili=egitim_yili, branslar__isnull=True)
        .order_by("sinif_seviyesi", "sira")
        if normalize_ders_adi(d.ders_adi) not in BRANS_DERS_YUKU_HARIC
    ]
    # alan_dersler__alan__in=... kullanılır (alan__egitim_yili=egitim_yili DEĞİL) —
    # bkz. alan_sube_sayilari() docstring'i.
    secmeli = [
        d for d in SecmeliDers.objects.filter(
            alan_dersler__alan__in=alan_sube_sayilari(egitim_yili).keys(), branslar__isnull=True
        ).select_related("grup").distinct().order_by("grup__sinif_seviyesi", "sira")
        if normalize_ders_adi(d.ders_adi) not in BRANS_DERS_YUKU_HARIC
    ]
    return ortak, secmeli


def arsivle(egitim_yili, kullanici=None):
    """Şu anki branş norm kadro hesabının (bkz. `hesapla()`) DEĞİŞMEZ bir anlık
    görüntüsünü `NormKadroArsivi` + `NormKadroArsiviSatiri` olarak kaydeder.

    Norm ile ilgili güncellemeler (Alan Şube Ataması, Yönetici Zorunlu Ders
    Yükü, branş atamaları) tamamlandığında çağrılır — sonrasında alttaki veri
    değişse de bu arşiv satırları sabit kalır. Döner: oluşturulan
    `NormKadroArsivi` nesnesi.
    """
    from ..models import NormKadroArsivi, NormKadroArsiviSatiri

    satirlar = hesapla(egitim_yili)
    arsiv = NormKadroArsivi.objects.create(egitim_yili=egitim_yili, olusturan=kullanici)
    NormKadroArsiviSatiri.objects.bulk_create([
        NormKadroArsiviSatiri(
            arsiv=arsiv,
            brans=s["brans"],
            ortak_saat=s["ortak_saat"],
            secmeli_saat=s["secmeli_saat"],
            toplam_saat=s["toplam_saat"],
            yonetici_dusum_saat=s["yonetici_dusum_saat"],
            norm_hesap_saati=s["norm_hesap_saati"],
            norm_kadro=s["norm_kadro"],
            mevcut=s["mevcut"],
            fazla=s["fazla"],
            eksik=s["eksik"],
        )
        for s in satirlar
    ])
    return arsiv
