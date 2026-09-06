"""Sorumluluk sınavı komisyon/gözetmen görevlendirmesi için otomatik dağıtım önerisi.

Üretilen öneri veritabanına YAZILMAZ. `gorevlendirme` view'ı bu modülü çağırıp
sonucu normal görevlendirme formunun (select2 dropdown'lar) ön-dolu hâli olarak
render eder; kullanıcı inceleyip mevcut "Görevlendirmeleri Kaydet" akışıyla
onaylar, dilerse dropdown'ları elle değiştirir ya da sayfayı yenileyip vazgeçer.

Kurallar:
  - Komisyon üyeleri (her iki üye de), dersin Ders Kataloğu'ndaki branş(lar)ı
    ile eşleşen personel arasından, geçmiş KOMİSYON görev sayısı en düşük
    olanlar öncelikli seçilerek adaletli dağıtılır. Branşta (Görev
    Muafiyeti hariç tutulduktan sonra) 2'den az uygun aday kalırsa —
    örn. FİZİK gibi az öğretmenli bir branşta çoğu kişi muaf olduğunda —
    eksik kalan koltuk(lar) için uyarı üretilir; branş dışından otomatik
    tamamlama YAPILMAZ, kullanıcı elle tamamlar.
  - Gözetmen ataması branştan bağımsız bir havuzdan yapılır; geçmiş TOPLAM
    (komisyon + gözetmen) görev sayısı en düşük olan personel öncelikli
    seçilir. Bu karşılaştırma branşa göre normalize EDİLMEZ (aç gözlü,
    tek-döneme özel bir branş dengelemesi yapılmaz): bir eğitim-öğretim
    yılında sırasıyla Eylül, Şubat ve Haziran dönemleri sorumluluk sınavları
    olacağından, "toplam görev sayısı" zaten bu sınav HARİÇ tüm geçmiş
    sınavları (önceki dönemler + önceki yıllar) kapsıyor; adalet tek bir
    dönemde değil, yıl genelinde birikimli olarak sağlanır.
  - Bununla birlikte, kümülatif sayısı düşük bir kişinin (ör. yeni göreve
    başlayan ya da branşının bu dönem hiç komisyon ihtiyacı doğurmadığı bir
    öğretmen) "açığını kapatmak" için TEK bir dönemde aşırı sayıda gözetmen
    görevi almasını önlemek amacıyla dönem-içi bir GÖZETMEN TAVANI uygulanır:
    `ceil(bu dönemdeki toplam gözetmen slotu / uygun personel sayısı) + 1`.
    Kümülatif açık, birkaç sonraki döneme yayılarak kapanır. Havuzdaki
    herkes tavana ulaşırsa (aksi halde slot boş kalır) tavan o slot için
    geçici olarak yok sayılır ve uyarı üretilir — hiçbir slot önerisiz
    bırakılmaz.
  - Bir personel, BU sınav döneminde (komisyon + gözetmen toplamı) en fazla
    `MAKS_GOREV_BU_DONEM` (2) görev alabilir — tek bir dönemde birkaç kişiye
    yığılmayı önlemek içindir. Bir komisyon biriminin kapladığı GÖREV SAYISI,
    o birimin kaç farklı tarihe yayıldığıdır: Yazılı+Uygulama ikilisi (ya da
    aynı slotta birleşen farklı sınıf seviyeleri, bkz. aşağıdaki kural) 2 ayrı
    tarihte olduğundan TEK BAŞINA 2 görev sayılır — yani bir öğretmen bir
    dersin yalnızca Yazılı+Uygulama'sını üstlenerek bile dönem sınırına ulaşır,
    aynı dönemde başka bir derse/sınıf seviyesine komisyon üyesi olamaz. Bu
    sınır, bir dersin komisyonu için (branş kısıtı nedeniyle) sınırı aşmamış
    yeterli aday kalmazsa YALNIZCA o ders için esnetilir (branşta az öğretmen
    olduğunda önerisiz kalan koltuk bırakmamak için) ve uyarı üretilir;
    gözetmen atamasında da aynı şekilde (dönem-içi gözetmen tavanıyla
    birlikte) uygulanır.
  - Bir personele aynı gün (tarih) yalnızca bir görev (komisyon veya gözetmen)
    verilebilir. Yazılı/Uygulama ikilisi gibi birden çok tarihe yayılan
    komisyon görevleri, her iki tarihte de bu kısıtı kilitler.
  - Aynı slotta (tarih + oturum_no) bir ders farklı sınıf seviyelerinde
    bulunuyorsa (örn. "Matematik (9. Sınıf)" ve "Matematik (10. Sınıf)" aynı
    oturumda), bu derslerin hepsine AYNI komisyon üyeleri atanır.
  - Ders Kataloğu'nda birden fazla branşa bağlı bir ders varsa (örn. "GÖRSEL
    SANATLAR/MÜZİK"), komisyonun iki üyesi FARKLI branşlardan seçilir (örn.
    biri Müzik, diğeri Görsel Sanatlar) — ikisi de aynı branştan olamaz.
  - Görev Muafiyeti listesindeki personel hiçbir göreve (komisyon/gözetmen)
    aday olarak dahil edilmez.
  - "Geçmiş" görev yükü hesaplanırken bu sınavın kendi (varsa) kayıtlı
    atamaları hariç tutulur — öneri, bu sınav için sıfırdan üretilir.
"""
import json
import math
import re
from collections import defaultdict
from itertools import groupby

from okul.models import Personel
from sorumluluk.models import (
    OncekiDonemGorev,
    SorumluDersKatalogu,
    SorumluGorevMuafPersonel,
    SorumluGozetmen,
    SorumluKomisyonUyesi,
    salon_choices,
)

_SINIF_SUFFIX_RE = re.compile(r" \(\d+\. Sınıf\)$")

# Bir personelin BU sınav döneminde alabileceği toplam (komisyon + gözetmen)
# görev sayısının üst sınırı — bkz. modül docstring'i. Branşta yeterli aday
# kalmazsa yalnızca ilgili ders/slot için esnetilir (oner_gorevlendirme).
MAKS_GOREV_BU_DONEM = 2


def gercek_ders_adi(ders_adi: str) -> str:
    """Ders Kataloğu ile eşleştirme için sınıf/Grup/Yazılı-Uygulama eklerini temizler."""
    base = ders_adi.split(" (Grup ")[0] if " (Grup " in ders_adi else ders_adi
    base = base.replace(" (Uygulama)", "").replace(" (Yazılı)", "")
    m = _SINIF_SUFFIX_RE.search(base)
    return (base[: m.start()] if m else base).strip()


def pair_base(ders_adi: str) -> str:
    """Yazılı/Uygulama eşleşmesi için taban ad (Grup ve Sınıf bilgisi korunur)."""
    if ders_adi.endswith(" (Yazılı)"):
        return ders_adi[: -len(" (Yazılı)")]
    if ders_adi.endswith(" (Uygulama)"):
        return ders_adi[: -len(" (Uygulama)")]
    return ders_adi


def komisyon_birimleri(takvim_rows):
    """Aynı komisyon üyelerini paylaşması GEREKEN takvim satırlarını gruplar (union-find).

    İki kural aynı birime (=aynı komisyon üyeleri) zorlar:
      (a) Yazılı/Uygulama eşleşmesi: aynı ders+sınıf, farklı tarihte olabilir.
      (b) Aynı slot (tarih+oturum_no) + aynı gerçek ders adı: farklı sınıf
          seviyeleri aynı oturumdaysa (örn. Matematik 9 ve Matematik 10).
    Her iki bağıntı da aynı gerçek ders adını koruduğu için, oluşan her
    bileşendeki tüm satırlar aynı gerçek ders adına (dolayısıyla aynı branş
    kümesine) sahiptir.

    `gorevlendirme_oneri.oner_gorevlendirme()` bu gruplamayı öneri üretirken,
    `sorumluluk.views.gorevlendirme()` ise kaydetme sırasında (kullanıcı bir
    satırı doldurup diğerini boş bırakırsa kardeş satırlara senkronize etmek
    için) kullanır — iki yer AYNI fonksiyonu çağırmalı, aksi halde öneri ile
    kayıt davranışı birbirinden sapar.

    Returns: list[list[SorumluTakvim]] — her alt liste bir birimin satırları.
    """
    n = len(takvim_rows)
    parent = list(range(n))

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a, b):
        ra, rb = _find(a), _find(b)
        if ra != rb:
            parent[ra] = rb

    pair_index = defaultdict(list)
    slot_index = defaultdict(list)
    for i, row in enumerate(takvim_rows):
        pair_index[pair_base(row.ders_adi)].append(i)
        slot_index[(row.tarih, row.oturum_no, gercek_ders_adi(row.ders_adi))].append(i)
    for idxs in pair_index.values():
        for i in idxs[1:]:
            _union(idxs[0], i)
    for idxs in slot_index.values():
        for i in idxs[1:]:
            _union(idxs[0], i)

    bilesenler = defaultdict(list)
    for i, row in enumerate(takvim_rows):
        bilesenler[_find(i)].append(row)
    return list(bilesenler.values())


def komisyon_gorev_sayisi(kayitlar: list[tuple]) -> int:
    """Union-find: bir personelin komisyon kayıtları arasında aynı slotta
    (tarih + oturum_no eşit) VEYA aynı ders_adi'na sahip olanlar tek görev sayılır
    (Yazılı/Uygulama ikilisi ya da çok günlü sınav gibi durumlarda tekrar saymayı
    önler). Sonuç, oluşan bağlı bileşen sayısıdır.

    `kayitlar` elemanları `(ders_adi, tarih, oturum_no)` (tek sınav bağlamı) ya da
    `(sinav_id, ders_adi, tarih, oturum_no)` (sınavlar arası kümülatif bağlam)
    biçiminde olabilir — sinav_id varsa ayrıca eşitlik şartı aranır.
    """
    n = len(kayitlar)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(n):
        for j in range(i + 1, n):
            *sinav_i, ders_i, tarih_i, oturum_i = kayitlar[i]
            *sinav_j, ders_j, tarih_j, oturum_j = kayitlar[j]
            if sinav_i != sinav_j:
                continue
            if (tarih_i == tarih_j and oturum_i == oturum_j) or ders_i == ders_j:
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[ri] = rj

    return len({find(i) for i in range(n)})


def _kumulatif_komisyon_baseline(sinav):
    """Bu sınav HARİÇ tüm sınavlardaki komisyon görev sayıları (aynı ders_adi veya
    aynı slotta birleşen atamalar tek görev sayılır — mevcut gorevlendirme() view'ı
    ile aynı union-find mantığı)."""
    kayitlar_by_pid = defaultdict(list)
    for ku in SorumluKomisyonUyesi.objects.exclude(sinav=sinav):
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid:
                kayitlar_by_pid[pid].append((ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no))

    return defaultdict(int, {
        pid: komisyon_gorev_sayisi(kayitlar) for pid, kayitlar in kayitlar_by_pid.items()
    })


def oner_gorevlendirme(sinav, takvim_rows, active_salons):
    """Verilen takvim satırları ve aktif salon bilgisine göre öneri üretir.

    Args:
        sinav: SorumluSinav
        takvim_rows: SorumluTakvim listesi (tarih, oturum_no, ders_adi sıralı)
        active_salons: {(tarih, oturum_no): {salon, ...}}

    Returns:
        {
          "komisyon": {(tarih, oturum_no, ders_adi): SorumluKomisyonUyesi(kaydedilmemiş)},
          "gozetmen": {(tarih, oturum_no, salon): SorumluGozetmen(kaydedilmemiş)},
          "uyarilar": [str, ...],
        }
    """
    uyarilar = []

    muaf_ids = set(SorumluGorevMuafPersonel.objects.values_list("personel_id", flat=True))
    personel_listesi = list(
        Personel.objects.gorevde().select_related("brans").exclude(pk__in=muaf_ids)
    )

    katalog_brans = {
        k.ders_adi: set(k.branslar.values_list("pk", flat=True))
        for k in SorumluDersKatalogu.objects.filter(sinav=sinav).prefetch_related("branslar")
    }

    running_komisyon = defaultdict(int, _kumulatif_komisyon_baseline(sinav))
    running_gozetmen = defaultdict(int)
    for gz in SorumluGozetmen.objects.exclude(sinav=sinav).filter(gozetmen__isnull=False):
        running_gozetmen[gz.gozetmen_id] += 1
    for og in OncekiDonemGorev.objects.all():
        running_komisyon[og.personel_id] += og.komisyon
        running_gozetmen[og.personel_id] += og.gozetmen

    def running_total(pid):
        return running_komisyon[pid] + running_gozetmen[pid]

    used_on_date = defaultdict(set)  # tarih -> {personel_id}
    bu_donem_toplam = defaultdict(int)  # personel_id -> bu sınavda şu ana kadar atanan görev sayısı

    units = []
    for rows in komisyon_birimleri(takvim_rows):
        dates = {r.tarih for r in rows}
        gercek = gercek_ders_adi(rows[0].ders_adi)
        brans_ids = katalog_brans.get(gercek) or None
        units.append({"rows": rows, "dates": dates, "brans_ids": brans_ids, "gercek": gercek})

    def komisyon_pool(brans_ids, dates, sinirla=True):
        # Bir birim (`dates`) Yazılı+Uygulama ikilisi gibi birden çok tarihe
        # yayılıyorsa, o birimden alınacak görev de o kadar (len(dates)) sayılır —
        # ör. bir dersin hem Yazılı hem Uygulama'sında görev almak, tek bir dönemde
        # 2 görev almış saymaya yeter. Bu yüzden burada "zaten tavanda mı" değil,
        # "bu birim eklenince tavanı AŞAR MI" kontrol edilir.
        pool = []
        for p in personel_listesi:
            if brans_ids and p.brans_id not in brans_ids:
                continue
            if any(p.pk in used_on_date[d] for d in dates):
                continue
            if sinirla and bu_donem_toplam[p.pk] + len(dates) > MAKS_GOREV_BU_DONEM:
                continue
            pool.append(p)
        return pool

    # En kısıtlı (aday havuzu küçük / gün sayısı fazla) birimler önce işlenir
    units.sort(key=lambda u: (len(komisyon_pool(u["brans_ids"], u["dates"])), -len(u["dates"])))

    komisyon_sonuc = {}
    for u in units:
        if not u["brans_ids"]:
            uyarilar.append(
                f"\"{u['gercek']}\" dersi için Ders Kataloğu'nda branş bilgisi bulunamadı; "
                f"komisyon üyeleri tüm personel arasından seçildi, lütfen kontrol edin."
            )
        karma_gerekli = bool(u["brans_ids"]) and len(u["brans_ids"]) >= 2
        pool = komisyon_pool(u["brans_ids"], u["dates"])

        # Dönem-içi görev sınırı (MAKS_GOREV_BU_DONEM) bu ders için yeterli aday
        # bırakmıyorsa (branşta az öğretmen olduğunda sık görülür) sınır bu ders
        # özelinde esnetilir — hiçbir koltuk salt bu sınır yüzünden boş kalmasın.
        yeterli = (
            len({p.brans_id for p in pool}) >= 2 if karma_gerekli else len(pool) >= 2
        )
        if not yeterli:
            pool_gevsek = komisyon_pool(u["brans_ids"], u["dates"], sinirla=False)
            if len(pool_gevsek) > len(pool):
                uyarilar.append(
                    f"\"{u['gercek']}\" için dönem içi kişi başı {MAKS_GOREV_BU_DONEM} görev "
                    f"sınırı, branşta yeterli sayıda uygun aday kalmadığından bu ders için "
                    f"esnetildi — lütfen kontrol edin."
                )
                pool = pool_gevsek

        secilenler = []

        if karma_gerekli:
            # Ders birden fazla branşa bağlı (örn. Görsel Sanatlar/Müzik): komisyonun
            # iki üyesi FARKLI branşlardan olmalı — her branştan en az yüklü aday seçilir.
            brans_havuzu = defaultdict(list)
            for p in pool:
                brans_havuzu[p.brans_id].append(p)
            for adaylar in brans_havuzu.values():
                adaylar.sort(key=lambda p: (running_komisyon[p.pk], running_total(p.pk), p.adi_soyadi))
            mevcut_branslar = sorted(
                brans_havuzu.keys(),
                key=lambda bid: (running_komisyon[brans_havuzu[bid][0].pk], running_total(brans_havuzu[bid][0].pk)),
            )
            if len(mevcut_branslar) >= 2:
                secilenler = [brans_havuzu[bid][0] for bid in mevcut_branslar[:2]]
            else:
                uyarilar.append(
                    f"\"{u['gercek']}\" farklı branşlardan birer komisyon üyesi gerektiriyor, "
                    f"ancak yalnızca bir branştan uygun aday bulunabildi — lütfen elle kontrol edin."
                )

        if not secilenler:
            pool.sort(key=lambda p: (running_komisyon[p.pk], running_total(p.pk), p.adi_soyadi))
            secilenler = pool[:2]

        if len(secilenler) < 2:
            uyarilar.append(
                f"\"{u['gercek']}\" için yeterli komisyon üyesi bulunamadı "
                f"({len(secilenler)}/2 kişi atanabildi) — lütfen elle tamamlayın."
            )
        uye1 = secilenler[0] if len(secilenler) > 0 else None
        uye2 = secilenler[1] if len(secilenler) > 1 else None
        for p in secilenler:
            running_komisyon[p.pk] += 1
            # Yazılı+Uygulama gibi birden çok tarihe yayılan bir birim, kişi başına
            # tek değil o kadar (len(dates)) görev sayılır — bkz. komisyon_pool().
            bu_donem_toplam[p.pk] += len(u["dates"])
            for d in u["dates"]:
                used_on_date[d].add(p.pk)
        for row in u["rows"]:
            komisyon_sonuc[(row.tarih, row.oturum_no, row.ders_adi)] = SorumluKomisyonUyesi(
                sinav=sinav, tarih=row.tarih, oturum_no=row.oturum_no, ders_adi=row.ders_adi,
                uye1=uye1, uye2=uye2,
            )

    # --- Gözetmen birimleri: her (tarih, oturum_no, salon) bağımsız ---
    gozetmen_sonuc = {}
    gozetmen_units = sorted(
        ((t, o, s) for (t, o), salons in active_salons.items() for s in salons),
        key=lambda x: (x[0], x[1], x[2]),
    )

    # Dönem-içi gözetmen tavanı: kümülatif sayısı düşük biri (ör. branşı bu
    # dönem hiç komisyon ihtiyacı doğurmayan bir öğretmen), sadece "en ucuz
    # aday" olduğu için TEK dönemde orantısız çok gözetmen görevi almasın —
    # açığı birkaç sonraki döneme yayılarak kapansın (bkz. modül docstring'i).
    bu_donem_gozetmen = defaultdict(int)
    gozetmen_tavani = (
        math.ceil(len(gozetmen_units) / len(personel_listesi)) + 1 if personel_listesi else 0
    )

    for tarih, oturum_no, salon in gozetmen_units:
        pool = [p for p in personel_listesi if p.pk not in used_on_date[tarih]]
        secilen = None
        if not pool:
            uyarilar.append(
                f"{tarih:%d.%m.%Y} Oturum {oturum_no} – {salon} için uygun gözetmen bulunamadı "
                f"(herkes o gün başka bir görevde) — lütfen elle tamamlayın."
            )
        else:
            # Hem gözetmen-özel tavan hem de genel dönem-içi görev sınırı (MAKS_GOREV_BU_DONEM)
            # aynı anda uygulanır; ikisinden biri havuzu boşaltırsa (aksi halde slot
            # önerisiz kalır) her iki sınır da bu slot için geçici olarak yok sayılır.
            tavan_alti = [
                p for p in pool
                if bu_donem_gozetmen[p.pk] < gozetmen_tavani
                and bu_donem_toplam[p.pk] < MAKS_GOREV_BU_DONEM
            ]
            secim_havuzu = tavan_alti or pool
            if not tavan_alti:
                uyarilar.append(
                    f"{tarih:%d.%m.%Y} Oturum {oturum_no} – {salon}: uygun personelin tamamı bu "
                    f"dönem için gözetmen tavanına (kişi başı {gozetmen_tavani}) ya da genel "
                    f"{MAKS_GOREV_BU_DONEM} görev sınırına ulaştığından, sınırlar bu slot için "
                    f"geçici olarak uygulanmadı — lütfen kontrol edin."
                )
            secim_havuzu.sort(key=lambda p: (running_total(p.pk), running_gozetmen[p.pk], p.adi_soyadi))
            secilen = secim_havuzu[0]
            running_gozetmen[secilen.pk] += 1
            bu_donem_gozetmen[secilen.pk] += 1
            bu_donem_toplam[secilen.pk] += 1
            used_on_date[tarih].add(secilen.pk)
        gozetmen_sonuc[(tarih, oturum_no, salon)] = SorumluGozetmen(
            sinav=sinav, tarih=tarih, oturum_no=oturum_no, salon=salon, gozetmen=secilen,
        )

    return {"komisyon": komisyon_sonuc, "gozetmen": gozetmen_sonuc, "uyarilar": uyarilar}


def gorevlendirme_baglami_olustur(sinav, takvim_rows, active_salons, komisyon_dict, gozetmen_dict):
    """`sorumluluk.views.gorevlendirme` (DB'den yüklü) ve `gorevlendirme_oner`
    (öneri, kaydedilmemiş) view'larının ortak render bağlamını üretir."""
    muaf_ids = SorumluGorevMuafPersonel.objects.values_list("personel_id", flat=True)
    personel_listesi = list(
        Personel.objects.gorevde().select_related("brans").exclude(pk__in=muaf_ids).order_by("adi_soyadi")
    )

    oturumlar = []
    for (tarih, oturum_no), rows in groupby(takvim_rows, key=lambda r: (r.tarih, r.oturum_no)):
        rows = list(rows)
        dersler_data = [
            {"takvim": row, "komisyon": komisyon_dict.get((row.tarih, row.oturum_no, row.ders_adi))}
            for row in rows
        ]
        _salon_label_map = dict(salon_choices())
        salons_data = [
            {
                "salon": salon,
                "salon_label": _salon_label_map.get(salon, salon),
                "gozetmen": gozetmen_dict.get((tarih, oturum_no, salon)),
            }
            for salon in sorted(active_salons.get((tarih, oturum_no), []))
        ]
        oturumlar.append({
            "tarih": tarih,
            "oturum_no": oturum_no,
            "saat_baslangic": rows[0].saat_baslangic,
            "saat_bitis": rows[0].saat_bitis,
            "dersler_data": dersler_data,
            "ders_sayisi": len(rows),
            "salons_data": salons_data,
        })

    # Görev sayısı özeti — tüm personel dahil, branş bazında gruplu
    gorev_sayac: dict = {
        p.pk: {"adi_soyadi": p.adi_soyadi, "brans": p.brans.ad if p.brans else "", "komisyon": 0, "gozetmen": 0}
        for p in personel_listesi
    }

    # Komisyon sayımı: aynı slotta farklı dersler ya da farklı slotlarda aynı
    # ders (çok günlü sınav) → 1 görev (bkz. komisyon_gorev_sayisi).
    komisyon_kayitlar: dict = {}  # personel_pk → [(ders_adi, tarih, oturum_no), ...]
    for ku in komisyon_dict.values():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in gorev_sayac:
                komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in komisyon_kayitlar.items():
        gorev_sayac[pid]["komisyon"] = komisyon_gorev_sayisi(kayitlar)

    for gz in gozetmen_dict.values():
        if gz.gozetmen_id and gz.gozetmen_id in gorev_sayac:
            gorev_sayac[gz.gozetmen_id]["gozetmen"] += 1

    # Kümülatif görev sayısı — tüm SorumluSinav kayıtları
    kumulatif_sayac = {p.pk: {"komisyon": 0, "gozetmen": 0} for p in personel_listesi}

    kum_komisyon_kayitlar: dict = {}  # personel_pk → [(sinav_id, ders_adi, tarih, oturum_no)]
    for ku in SorumluKomisyonUyesi.objects.all():
        for pid in (ku.uye1_id, ku.uye2_id):
            if pid and pid in kumulatif_sayac:
                kum_komisyon_kayitlar.setdefault(pid, []).append(
                    (ku.sinav_id, ku.ders_adi, ku.tarih, ku.oturum_no)
                )
    for pid, kayitlar in kum_komisyon_kayitlar.items():
        kumulatif_sayac[pid]["komisyon"] = komisyon_gorev_sayisi(kayitlar)

    for gz in SorumluGozetmen.objects.all():
        if gz.gozetmen_id and gz.gozetmen_id in kumulatif_sayac:
            kumulatif_sayac[gz.gozetmen_id]["gozetmen"] += 1

    # Geçmiş dönem (OncekiDonemGorev) kümülatife ekle
    for og in OncekiDonemGorev.objects.filter(personel_id__in=kumulatif_sayac):
        kumulatif_sayac[og.personel_id]["komisyon"] += og.komisyon
        kumulatif_sayac[og.personel_id]["gozetmen"] += og.gozetmen

    sinav_toplam_komisyon = sum(v["komisyon"] for v in gorev_sayac.values())
    sinav_toplam_gozetmen = sum(v["gozetmen"] for v in gorev_sayac.values())
    sinav_toplam_gorev    = sinav_toplam_komisyon + sinav_toplam_gozetmen
    sinav_kbs_saat        = sinav_toplam_gorev * 5

    personel_kum_json = json.dumps({
        str(p.pk): {
            "k": kumulatif_sayac[p.pk]["komisyon"],
            "g": kumulatif_sayac[p.pk]["gozetmen"],
            "t": kumulatif_sayac[p.pk]["komisyon"] + kumulatif_sayac[p.pk]["gozetmen"],
        }
        for p in personel_listesi
    })

    return {
        "sinav": sinav,
        "oturumlar": oturumlar,
        "personel_listesi": personel_listesi,
        "personel_kum_json": personel_kum_json,
        "sinav_toplam_komisyon": sinav_toplam_komisyon,
        "sinav_toplam_gozetmen": sinav_toplam_gozetmen,
        "sinav_toplam_gorev":    sinav_toplam_gorev,
        "sinav_kbs_saat":        sinav_kbs_saat,
    }
