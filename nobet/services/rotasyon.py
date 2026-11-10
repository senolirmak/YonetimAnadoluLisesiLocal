"""Haftalık nöbet yeri rotasyonu.

Her gün için o günün görevleri nöbet yeri adına göre sıralanır ve yerler bir adım
kaydırılır (her öğretmen listedeki bir sonraki yere geçer); öğretmenlerin nöbet
günleri değişmez.

İsteğe bağlı kural (``bos_yer``, ``esik``): bir günde nöbetçi sayısı ``esik``'ten
azsa ``bos_yer`` o gün boş bırakılır. O gün bu yer birine verilmişse, rotasyondan
önce o gün kimsenin tutmadığı bir yerle değiştirilir; kaydırma bu yeni yer kümesi
üzerinden yapılır. Hangi yerin boş bırakılacağını kullanıcı seçer.
"""

VARSAYILAN_ESIK = 11

_ALFABE = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"


def yer_anahtari(ad):
    """Büyük/küçük harf ve boşluk farkını yok sayan karşılaştırma anahtarı."""
    ad = (ad or "").replace("i", "İ").replace("ı", "I").upper()
    return " ".join(ad.split())


def turkce_sira_anahtari(ad):
    """Türkçe alfabe sırasına göre sıralama anahtarı."""
    return [(_ALFABE.index(h) if h in _ALFABE else 100 + ord(h)) for h in yer_anahtari(ad)]


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

    ``gorev_yerleri``: ``[(gorev_anahtari, yer_adi), ...]``, nöbet yeri adına göre sıralı.
    ``bos_yer``/``esik``/``aday_yerler``: bkz. ``yeri_bosalt``.

    Dönüş ``({gorev_anahtari: yeni_yer_adi}, uyari)``.
    """
    gorev_yerleri = list(gorev_yerleri)
    bosaltilmis, uyari = yeri_bosalt(gorev_yerleri, bos_yer, esik, aday_yerler)
    if bosaltilmis != gorev_yerleri:
        # Boşaltılan yerdeki öğretmen yeni yeri tutuyormuş gibi rotasyona girer
        gorev_yerleri = sorted(bosaltilmis, key=lambda gy: turkce_sira_anahtari(gy[1]))

    if len(gorev_yerleri) < 2:
        return {gorev: yer for gorev, yer in gorev_yerleri}, uyari

    yerler = [y for _, y in gorev_yerleri]
    yeni_yerler = yerler[1:] + yerler[:1]
    return {gorev: yeni for (gorev, _), yeni in zip(gorev_yerleri, yeni_yerler)}, uyari
