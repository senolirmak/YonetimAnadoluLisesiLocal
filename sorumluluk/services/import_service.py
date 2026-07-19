import re
from collections import Counter, defaultdict

import pandas as pd

from sorumluluk.models import (
    SorumluDers,
    SorumluDersHavuzu,
    SorumluDersKatalogBransOneri,
    SorumluDersKatalogOkulDersOnerisi,
    SorumluDersKatalogu,
    SorumluOgrenci,
    SorumluSinav,
)

_BASLIK_RE = re.compile(r"(\d+)\.\s*S[ıi]n[ıi]f\s*/\s*([A-Z])\s*Şubesi", re.IGNORECASE)


def _normalize(text) -> str:
    return " ".join(str(text).split())


def ders_brans_haritasi(ders_adlari: set[str]) -> dict[str, int]:
    """Haftalık Ders Programı'ndaki (aktif dönem) öğretmen atamalarından
    faydalanarak her ders adı için en sık görülen branşın id'sini bulur."""
    from dersprogrami.models import DersProgrami

    if not ders_adlari:
        return {}

    kayitlar = (
        DersProgrami.objects.aktif()
        .filter(ders__ders_adi__in=ders_adlari)
        .exclude(ogretmen__brans__isnull=True)
        .values_list("ders__ders_adi", "ogretmen__brans_id")
    )
    gruplu: dict = defaultdict(list)
    for ders_adi, brans_id in kayitlar:
        gruplu[ders_adi].append(brans_id)

    return {
        ders_adi: Counter(brans_idler).most_common(1)[0][0]
        for ders_adi, brans_idler in gruplu.items()
    }


def ders_brans_adi_haritasi(ders_adlari: set[str]) -> dict[str, str]:
    """ders_brans_haritasi ile aynı sonucu, id yerine branş adı olarak döner
    (salt-okunur görüntüleme amaçlı — örn. Ders Havuzu ekranları)."""
    from okul.models import Brans

    id_haritasi = ders_brans_haritasi(ders_adlari)
    if not id_haritasi:
        return {}

    brans_adlari = dict(Brans.objects.filter(pk__in=set(id_haritasi.values())).values_list("pk", "ad"))
    return {
        ders_adi: brans_adlari[brans_id]
        for ders_adi, brans_id in id_haritasi.items()
        if brans_id in brans_adlari
    }


def ders_brans_coklu_haritasi(ders_adlari: set[str]) -> dict[str, set[int]]:
    """Her ders adı için, Haftalık Ders Programı'nda o dersi okutan tüm öğretmenlerin
    branşlarını (tekrarsız) döner. Bir ders birden fazla branştan öğretmen tarafından
    okutulabilir (örn. GÖRSEL SANATLAR/MÜZİK → Görsel Sanatlar + Müzik)."""
    from dersprogrami.models import DersProgrami

    if not ders_adlari:
        return {}

    kayitlar = (
        DersProgrami.objects.aktif()
        .filter(ders__ders_adi__in=ders_adlari)
        .exclude(ogretmen__brans__isnull=True)
        .values_list("ders__ders_adi", "ogretmen__brans_id")
        .distinct()
    )
    sonuc: dict = defaultdict(set)
    for ders_adi, brans_id in kayitlar:
        sonuc[ders_adi].add(brans_id)
    return dict(sonuc)


def secmeli_dersler_brans_haritasi(ders_adlari: set[str]) -> dict[str, set[int]]:
    """Her ders adı için, secmelidersler.OrtakDersHavuzu/SecmeliDersHavuzu'ndaki
    (sınıf seviyesinden bağımsız, kanonik) aynı adlı kaydın branslar'ını döner.
    Bu havuz modelleri SorumluDersKatalogu ile aynı şekilde sınıf seviyesi
    taşımadığından (`OrtakDers`/`SecmeliDers`'in aksine) ders adı ek/saat
    normalizasyonu gerekmeden birebir eşleşir."""
    from secmelidersler.models import OrtakDersHavuzu, SecmeliDersHavuzu

    if not ders_adlari:
        return {}

    sonuc: dict = defaultdict(set)

    for Model in (OrtakDersHavuzu, SecmeliDersHavuzu):
        for ders_adi, brans_id in (
            Model.objects.filter(ders_adi__in=ders_adlari)
            .exclude(branslar__isnull=True)
            .values_list("ders_adi", "branslar")
            .distinct()
        ):
            sonuc[ders_adi].add(brans_id)

    return dict(sonuc)


def sorumluluk_katalog_branslarini_oner(sinav: SorumluSinav) -> int:
    """Katalogdaki (elle bir Ortak/Seçmeli Ders Havuzu kaydına bağlanmamış)
    derslere, secmelidersler.OrtakDersHavuzu/SecmeliDersHavuzu'ndan ders adı
    eşleşmesiyle tespit edilen ve henüz atanmamış/önerilmemiş branşlar için
    onay bekleyen SorumluDersKatalogBransOneri kaydı oluşturur. Elle bağlanmış
    kataloglar bu fonksiyonu atlar — onların branşı `katalog_baglantidan_brans_uygula`
    ile onay gerekmeden doğrudan uygulanır (kullanıcı zaten bağlantıyı elle
    seçerek onaylamış sayılır). Oluşturulan yeni öneri sayısını döner."""
    katalog = list(
        SorumluDersKatalogu.objects.filter(sinav=sinav, ortak_ders__isnull=True, secmeli_ders__isnull=True)
        .prefetch_related("branslar", "brans_onerileri")
    )
    harita = secmeli_dersler_brans_haritasi({k.ders_adi for k in katalog})

    yeni_oneriler = []
    for k in katalog:
        onerilen = harita.get(k.ders_adi)
        if not onerilen:
            continue
        mevcut_brans_id = {b.pk for b in k.branslar.all()}
        mevcut_oneri_id = {o.brans_id for o in k.brans_onerileri.all()}
        eksik = onerilen - mevcut_brans_id - mevcut_oneri_id
        for brans_id in eksik:
            yeni_oneriler.append(SorumluDersKatalogBransOneri(katalog=k, brans_id=brans_id))

    if yeni_oneriler:
        SorumluDersKatalogBransOneri.objects.bulk_create(yeni_oneriler, ignore_conflicts=True)
    return len(yeni_oneriler)


def katalog_baglantidan_brans_uygula(katalog: SorumluDersKatalogu) -> int:
    """Katalog satırı elle bir Ortak/Seçmeli Ders'e bağlıysa (`ortak_ders`/
    `secmeli_ders`), o kaydın branşlarını onay gerekmeden doğrudan
    `katalog.branslar`'a ekler (kullanıcı bağlantıyı elle seçerek zaten
    onaylamış sayılır). Eklenen yeni branş sayısını döner."""
    ders = katalog.ortak_ders or katalog.secmeli_ders
    if ders is None:
        return 0
    yeni_brans_id = set(ders.branslar.values_list("pk", flat=True)) - {
        b.pk for b in katalog.branslar.all()
    }
    if yeni_brans_id:
        katalog.branslar.add(*yeni_brans_id)
    return len(yeni_brans_id)


def okul_dersi_haritasi(ders_adlari: set[str]) -> dict[str, int]:
    """Ders adına göre Okul Ders Havuzu'ndaki (okul.DersHavuzu) kaydın id'sini bulur."""
    from okul.models import DersHavuzu

    if not ders_adlari:
        return {}
    return dict(DersHavuzu.objects.filter(ders_adi__in=ders_adlari).values_list("ders_adi", "pk"))


def sorumluluk_katalog_okul_dersini_esle(sinav: SorumluSinav) -> int:
    """Ders Kataloğu'ndaki, henüz Okul Ders Havuzu'na bağlanmamış derslerden adı
    Okul Ders Havuzu'nda birebir bulunanları doğrudan bağlar (isim eşleşmesi net
    olduğu için onay gerektirmez). Bağlanan ders sayısını döner."""
    bagsiz = list(SorumluDersKatalogu.objects.filter(sinav=sinav, okul_dersi__isnull=True))
    if not bagsiz:
        return 0

    harita = okul_dersi_haritasi({k.ders_adi for k in bagsiz})
    guncellenecek = []
    for k in bagsiz:
        okul_dersi_id = harita.get(k.ders_adi)
        if okul_dersi_id:
            k.okul_dersi_id = okul_dersi_id
            guncellenecek.append(k)

    if guncellenecek:
        SorumluDersKatalogu.objects.bulk_update(guncellenecek, ["okul_dersi_id"])
    return len(guncellenecek)


def sorumluluk_katalog_secmeli_dersini_esle(sinav: SorumluSinav) -> int:
    """Ders Kataloğu'ndaki, henüz bir Ortak/Seçmeli Ders Havuzu kaydına
    bağlanmamış derslerden adı OrtakDersHavuzu/SecmeliDersHavuzu'nda birebir
    bulunanları doğrudan bağlar (isim eşleşmesi net olduğu için onay
    gerektirmez — `sorumluluk_katalog_okul_dersini_esle` ile aynı mantık).
    Aynı ad hem Ortak hem Seçmeli Ders Havuzu'nda birden varsa (belirsiz durum)
    atlanır, kullanıcı `havuz_duzenle`'den elle seçer. Bağlanan ders sayısını döner."""
    from secmelidersler.models import OrtakDersHavuzu, SecmeliDersHavuzu

    bagsiz = list(
        SorumluDersKatalogu.objects.filter(sinav=sinav, ortak_ders__isnull=True, secmeli_ders__isnull=True)
    )
    if not bagsiz:
        return 0

    ders_adlari = {k.ders_adi for k in bagsiz}
    ortak_harita = dict(OrtakDersHavuzu.objects.filter(ders_adi__in=ders_adlari).values_list("ders_adi", "pk"))
    secmeli_harita = dict(SecmeliDersHavuzu.objects.filter(ders_adi__in=ders_adlari).values_list("ders_adi", "pk"))

    guncellenecek = []
    for k in bagsiz:
        ortak_id = ortak_harita.get(k.ders_adi)
        secmeli_id = secmeli_harita.get(k.ders_adi)
        if ortak_id and secmeli_id:
            continue
        if ortak_id:
            k.ortak_ders_id = ortak_id
            guncellenecek.append(k)
        elif secmeli_id:
            k.secmeli_ders_id = secmeli_id
            guncellenecek.append(k)

    if guncellenecek:
        SorumluDersKatalogu.objects.bulk_update(guncellenecek, ["ortak_ders_id", "secmeli_ders_id"])
    return len(guncellenecek)


def sorumluluk_katalog_okul_dersi_onerilerini_olustur(sinav: SorumluSinav) -> int:
    """Ders Kataloğu'ndaki, Okul Ders Havuzu'nda karşılığı bulunamayan (örn. nakil
    öğrenci) dersler için, Okul Ders Havuzu'na yeni kayıt açılması amacıyla onay
    bekleyen SorumluDersKatalogOkulDersOnerisi kaydı oluşturur. Okul Ders Havuzu'na
    doğrudan ekleme yapılmaz. Oluşturulan yeni öneri sayısını döner."""
    adaylar = (
        SorumluDersKatalogu.objects.filter(sinav=sinav, okul_dersi__isnull=True)
        .exclude(okul_dersi_onerisi__isnull=False)
    )
    yeni_oneriler = [SorumluDersKatalogOkulDersOnerisi(katalog=k) for k in adaylar]
    if yeni_oneriler:
        SorumluDersKatalogOkulDersOnerisi.objects.bulk_create(yeni_oneriler, ignore_conflicts=True)
    return len(yeni_oneriler)


def sorumluluk_brans_bilgisi_guncelle(sinav: SorumluSinav) -> int:
    """Var olan SorumluDersHavuzu kayıtları için branş bilgisini Haftalık Ders
    Programı'ndan yeniden hesaplar (ders programı güncellendiğinde tekrar
    çalıştırılabilir). Güncellenen kayıt sayısını döner."""
    havuzlar = list(SorumluDersHavuzu.objects.filter(sinav=sinav))
    harita = ders_brans_haritasi({h.ders_adi for h in havuzlar})

    guncellenecek = []
    for h in havuzlar:
        yeni_brans_id = harita.get(h.ders_adi)
        if h.brans_id != yeni_brans_id:
            h.brans_id = yeni_brans_id
            guncellenecek.append(h)

    if guncellenecek:
        SorumluDersHavuzu.objects.bulk_update(guncellenecek, ["brans_id"])
    return len(guncellenecek)


def sorumluluk_excel_aktar(dosya_yolu: str, sinav: SorumluSinav) -> dict:
    """XLS dosyasından belirtilen sınava ait SorumluOgrenci + SorumluDers yükler.

    Sınava ait mevcut öğrenci ve ders kayıtları silinerek yeniden oluşturulur.
    Returns: {"ogrenci": int, "ders": int, "hatalar": list}
    """
    df = pd.read_excel(dosya_yolu, header=None, dtype=str)
    df = df.fillna("")

    ogrenciler: dict[str, dict] = {}   # okulno → {adi_soyadi, sinif, sube, dersler:[]}
    mevcut_sinif = None
    mevcut_sube  = None
    son_okulno   = None

    for _, row in df.iterrows():
        cols = list(row)

        # Section header — col[0] ya da col[1]'de sınıf/şube başlığı
        baslik_bulundu = False
        for ci in (0, 1):
            m = _BASLIK_RE.search(str(cols[ci]))
            if m:
                mevcut_sinif = int(m.group(1))
                mevcut_sube  = m.group(2).upper()
                baslik_bulundu = True
                break

        if baslik_bulundu or mevcut_sinif is None:
            continue

        # Öğrenci satırı: col[0] tam sayı (sıra no), col[1] okul no
        col0 = _normalize(cols[0])
        try:
            int(float(col0))
            is_ogr_satiri = True
        except (ValueError, TypeError):
            is_ogr_satiri = False

        if is_ogr_satiri:
            okulno = _normalize(cols[1])
            if not okulno or okulno == "nan":
                continue
            son_okulno = okulno

            adi_soyadi = _normalize(cols[3]) if len(cols) > 3 else ""

            if okulno not in ogrenciler:
                ogrenciler[okulno] = {
                    "adi_soyadi": adi_soyadi,
                    "sinif": mevcut_sinif,
                    "sube":  mevcut_sube,
                    "dersler": [],
                }

        # İster ana öğrenci satırı olsun, ister alt satır (ek ders) olsun;
        # Gönderdiğiniz algoritmada olduğu gibi 8. ve 11. sütunlar arasını
        # Sınıf -> Ders eşleşmesi şeklinde dinamik olarak tarıyoruz.
        if son_okulno and son_okulno in ogrenciler:
            for col_idx in range(8, len(cols) - 1):
                cell_value = str(cols[col_idx]).strip()
                if not cell_value or cell_value == "nan":
                    continue
                try:
                    # Eğer hücre sayısal bir değerse (sınıf numarası)
                    onceki_sinif = int(float(cell_value))
                    # Bir sağındaki sütun ders adıdır
                    ders_adi = _normalize(cols[col_idx + 1])
                    if ders_adi and ders_adi != "nan":
                        mevcut = ogrenciler[son_okulno]["dersler"]
                        if (ders_adi, onceki_sinif) not in mevcut:
                            mevcut.append((ders_adi, onceki_sinif))
                except (ValueError, TypeError):
                    # Sayısal bir değer değilse diğer sütuna geç
                    continue

    # Sınava ait önceki verileri temizle
    SorumluOgrenci.objects.filter(sinav=sinav).delete()
    SorumluDersHavuzu.objects.filter(sinav=sinav).delete()

    toplam_ogrenci = 0
    toplam_ders    = 0
    hatalar        = []

    # 1. Excel'deki benzersiz dersleri bulup havuza topluca ekleyelim
    ders_havuzu_set = set()
    for veri in ogrenciler.values():
        for d in veri["dersler"]:
            ders_havuzu_set.add(d)

    brans_harita = ders_brans_haritasi({d_adi for d_adi, _ in ders_havuzu_set})
    havuz_kayitlari = [
        SorumluDersHavuzu(
            sinav=sinav, ders_adi=d_adi, onceki_sinif=d_sinif,
            brans_id=brans_harita.get(d_adi),
        )
        for d_adi, d_sinif in ders_havuzu_set
    ]
    SorumluDersHavuzu.objects.bulk_create(havuz_kayitlari, ignore_conflicts=True)

    # Bilgilendirme amaçlı ders kataloğu: sınıf seviyesinden bağımsız, sadece
    # ekleme yapılır (mevcut/elle silinmiş kayıtlar korunur; takvim algoritmasını etkilemez).
    katalog_ders_adlari = {d_adi for d_adi, _ in ders_havuzu_set}
    mevcut_katalog_adlari = set(
        SorumluDersKatalogu.objects.filter(sinav=sinav).values_list("ders_adi", flat=True)
    )
    eksik_katalog_adlari = katalog_ders_adlari - mevcut_katalog_adlari
    okul_dersi_harita = okul_dersi_haritasi(eksik_katalog_adlari)
    yeni_katalog_kayitlari = [
        SorumluDersKatalogu(sinav=sinav, ders_adi=d_adi, okul_dersi_id=okul_dersi_harita.get(d_adi))
        for d_adi in eksik_katalog_adlari
    ]
    if yeni_katalog_kayitlari:
        SorumluDersKatalogu.objects.bulk_create(yeni_katalog_kayitlari, ignore_conflicts=True)

    # Ders adı Okul Ders Havuzu'nda birebir varsa doğrudan bağla (net eşleşme, onay gerekmez);
    # bulunamayan (örn. nakil öğrenci) dersler için Okul Ders Havuzu'na ekleme önerisi oluştur.
    sorumluluk_katalog_okul_dersini_esle(sinav)
    sorumluluk_katalog_okul_dersi_onerilerini_olustur(sinav)
    # Aynı şekilde Ortak/Seçmeli Ders Havuzu'nda birebir ad eşleşmesi varsa doğrudan bağla.
    sorumluluk_katalog_secmeli_dersini_esle(sinav)
    sorumluluk_katalog_branslarini_oner(sinav)

    # 2. Eklenen havuz derslerini daha sonra ForeignKey olarak atamak için DB'den çekelim
    havuz_dict = {
        (hd.ders_adi, hd.onceki_sinif): hd
        for hd in SorumluDersHavuzu.objects.filter(sinav=sinav)
    }

    # 3. Öğrencileri ve havuza bağlanan SorumluDers kayıtlarını oluşturalım
    for okulno, veri in ogrenciler.items():
        try:
            ogr = SorumluOgrenci.objects.create(
                sinav=sinav,
                okulno=okulno,
                adi_soyadi=veri["adi_soyadi"],
                sinif=veri["sinif"],
                sube=veri["sube"],
            )
            toplam_ogrenci += 1
            
            ogr_dersler = []
            for ders_adi, onceki_sinif in veri["dersler"]:
                hd = havuz_dict.get((ders_adi, onceki_sinif))
                if hd:
                    ogr_dersler.append(SorumluDers(ogrenci=ogr, havuz_dersi=hd))
                    toplam_ders += 1
            
            if ogr_dersler:
                SorumluDers.objects.bulk_create(ogr_dersler, ignore_conflicts=True)

        except Exception as e:
            hatalar.append(f"{okulno}: {e}")

    return {"ogrenci": toplam_ogrenci, "ders": toplam_ders, "hatalar": hatalar}
