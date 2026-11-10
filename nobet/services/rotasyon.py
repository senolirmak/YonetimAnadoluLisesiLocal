"""Haftalık nöbet yeri rotasyonu.

Her gün için o günün yerlerinden sabit bir döngü kurulur ve her öğretmen döngüde
bir sonraki yere geçer; öğretmenlerin nöbet günleri değişmez. Döngü ada göre
sıralıdır, ancak aynı türden yerler (adı yalnızca sondaki numarayla ayrılanlar,
örn. "BAHÇE_1", "BAHÇE_2" — ya da aynı yerde birden fazla nöbetçi) döngüye eşit
aralıklarla serpiştirilir: böylece öğretmen bu yerlere art arda haftalarda gelmez.

İsteğe bağlı kural (``bos_yer``, ``esik``): bir günde nöbetçi sayısı ``esik``'ten
azsa ``bos_yer`` o gün boş bırakılır. O gün bu yer birine verilmişse, rotasyondan
önce o gün kimsenin tutmadığı bir yerle değiştirilir; kaydırma bu yeni yer kümesi
üzerinden yapılır. Hangi yerin boş bırakılacağını kullanıcı seçer.
"""

import re
from collections import defaultdict

from okul.utils import turkce_sira_anahtari  # noqa: F401 — nobet içinden buradan da kullanılır

VARSAYILAN_ESIK = 11

def yer_anahtari(ad):
    """Büyük/küçük harf ve boşluk farkını yok sayan karşılaştırma anahtarı."""
    ad = (ad or "").replace("i", "İ").replace("ı", "I").upper()
    return " ".join(ad.split())


def yer_turu(ad):
    """Aynı tür yerleri birleştiren anahtar: sondaki numara atılır ("BAHÇE_2" → "BAHÇE")."""
    return re.sub(r"[\s_\-.]*\d+$", "", yer_anahtari(ad)) or yer_anahtari(ad)


def rotasyon_dongusu(yerler):
    """Yer adlarından (tekrar edebilir) rotasyon döngüsünü kurar.

    Kalabalık türden başlayarak her türün yerleri boş kalan sıralara eşit aralıkla
    yerleştirilir; tek yerli türler kalan sıraları ad sırasıyla doldurur.
    """
    turler = defaultdict(list)
    for y in yerler:
        turler[yer_turu(y)].append(y)
    sira = sorted(
        turler.items(), key=lambda kv: (-len(kv[1]), turkce_sira_anahtari(kv[0]))
    )
    dongu = [None] * len(yerler)
    for _, uyeler in sira:
        uyeler.sort(key=turkce_sira_anahtari)
        bos = [i for i, y in enumerate(dongu) if y is None]
        m = len(uyeler)
        for k, y in enumerate(uyeler):
            dongu[bos[(k * len(bos)) // m]] = y
    return dongu


def yeri_bosalt(gorev_yerleri, bos_yer, esik, aday_yerler):
    """Nöbetçi sayısı ``esik``'in altındaysa ``bos_yer``'deki görevi o gün boş kalan bir yere taşır.

    ``gorev_yerleri``: bir günün ``[(gorev_anahtari, yer_adi), ...]`` listesi.
    ``aday_yerler``: yerine verilebilecek yer adları; o gün kimsenin tutmadığı ve
    Türkçe alfabe sırasına göre ilki seçilir.

    Dönüş ``(yeni_gorev_yerleri, uyari)``: liste aynı sırada döner (yalnızca taşınan
    görevin yeri değişir); ``uyari`` boş yer bulunamadıysa açıklama, değilse ``None``.
    ``bos_yer`` verilmezse hiçbir şey değişmez.
    """
    gorev_yerleri = list(gorev_yerleri)
    anahtar = yer_anahtari(bos_yer)
    if (
        not anahtar
        or len(gorev_yerleri) >= esik
        or not any(yer_anahtari(y) == anahtar for _, y in gorev_yerleri)
    ):
        return gorev_yerleri, None

    dolu = {yer_anahtari(y) for _, y in gorev_yerleri}
    bos_yerler = sorted(
        {y for y in aday_yerler if yer_anahtari(y) not in dolu and yer_anahtari(y) != anahtar},
        key=turkce_sira_anahtari,
    )
    uyari = None
    for i, (gorev, yer) in enumerate(gorev_yerleri):
        if yer_anahtari(yer) != anahtar:
            continue
        if bos_yerler:
            gorev_yerleri[i] = (gorev, bos_yerler.pop(0))
        else:
            uyari = f"{bos_yer} yerine verilebilecek boş bir nöbet yeri bulunamadı"
    return gorev_yerleri, uyari


def gun_rotasyonu(gorev_yerleri, aday_yerler=(), bos_yer=None, esik=VARSAYILAN_ESIK):
    """Bir günün rotasyonunu hesaplar.

    ``gorev_yerleri``: ``[(gorev_anahtari, yer_adi), ...]`` (sırası önemsiz; aynı yerdeki
    görevler bu sırayla o yerin döngü sıralarına dağıtılır).
    ``bos_yer``/``esik``/``aday_yerler``: bkz. ``yeri_bosalt``.

    Dönüş ``({gorev_anahtari: yeni_yer_adi}, uyari)``.
    """
    # Boşaltılan yerdeki öğretmen yeni yeri tutuyormuş gibi rotasyona girer
    gorev_yerleri, uyari = yeri_bosalt(list(gorev_yerleri), bos_yer, esik, aday_yerler)
    n = len(gorev_yerleri)
    if n < 2:
        return {gorev: yer for gorev, yer in gorev_yerleri}, uyari

    dongu = rotasyon_dongusu([y for _, y in gorev_yerleri])
    # Her görevi döngüde kendi yerinin bir sırasına oturt (aynı yerde birden fazla
    # nöbetçi varsa, görev sırasına göre o yerin sıralarına dağıtılır)
    yer_siralari = defaultdict(list)
    for i, y in enumerate(dongu):
        yer_siralari[y].append(i)
    yeni = {}
    for gorev, yer in gorev_yerleri:
        konum = yer_siralari[yer].pop(0)
        yeni[gorev] = dongu[(konum + 1) % n]
    return yeni, uyari
