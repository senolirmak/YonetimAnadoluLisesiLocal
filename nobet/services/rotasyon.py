"""Haftalık nöbet yeri rotasyonu.

Her gün için o günün görevleri nöbet yeri adına göre sıralanır ve yerler bir adım
kaydırılır (her öğretmen listedeki bir sonraki yere geçer); öğretmenlerin nöbet
günleri değişmez.

Kural: Bir günde nöbetçi öğretmen sayısı ``GIRIS_ORTA_ESIGI``'nden azsa
``GIRIS_ORTA`` yeri boş bırakılır. O gün bu yer birine verilmişse, rotasyondan önce
o gün kimsenin tutmadığı aktif bir nöbet yeriyle değiştirilir; kaydırma bu yeni yer
kümesi üzerinden yapılır.
"""

GIRIS_ORTA = "GİRİŞ ORTA"
GIRIS_ORTA_ESIGI = 11

_ALFABE = "ABCÇDEFGĞHIİJKLMNOÖPRSŞTUÜVYZ"


def yer_anahtari(ad):
    """Büyük/küçük harf ve boşluk farkını yok sayan karşılaştırma anahtarı."""
    ad = (ad or "").replace("i", "İ").replace("ı", "I").upper()
    return " ".join(ad.split())


def turkce_sira_anahtari(ad):
    """Türkçe alfabe sırasına göre sıralama anahtarı."""
    return [(_ALFABE.index(h) if h in _ALFABE else 100 + ord(h)) for h in yer_anahtari(ad)]


def _giris_orta_mi(ad):
    return yer_anahtari(ad) == yer_anahtari(GIRIS_ORTA)


def giris_orta_bosalt(gorev_yerleri, aktif_yerler):
    """Nöbetçi sayısı eşiğin altındaysa GİRİŞ ORTA'daki görevi o gün boş kalan bir yere taşır.

    ``gorev_yerleri``: bir günün ``[(gorev_anahtari, yer_adi), ...]`` listesi.
    ``aktif_yerler``: otomatik dağıtıma açık nöbet yeri adları; boş yer bunlardan,
    Türkçe alfabe sırasına göre ilki seçilir.

    Dönüş ``(yeni_gorev_yerleri, uyari)``: liste aynı sırada döner (yalnızca taşınan
    görevin yeri değişir); ``uyari`` boş yer bulunamadıysa açıklama, değilse ``None``.
    """
    gorev_yerleri = list(gorev_yerleri)
    if len(gorev_yerleri) >= GIRIS_ORTA_ESIGI or not any(
        _giris_orta_mi(y) for _, y in gorev_yerleri
    ):
        return gorev_yerleri, None

    dolu = {yer_anahtari(y) for _, y in gorev_yerleri}
    bos_yerler = sorted(
        (y for y in aktif_yerler if yer_anahtari(y) not in dolu and not _giris_orta_mi(y)),
        key=turkce_sira_anahtari,
    )
    uyari = None
    for i, (anahtar, yer) in enumerate(gorev_yerleri):
        if not _giris_orta_mi(yer):
            continue
        if bos_yerler:
            gorev_yerleri[i] = (anahtar, bos_yerler.pop(0))
        else:
            uyari = "GİRİŞ ORTA yerine verilebilecek boş bir nöbet yeri bulunamadı"
    return gorev_yerleri, uyari


def gun_rotasyonu(gorev_yerleri, aktif_yerler):
    """Bir günün rotasyonunu hesaplar.

    ``gorev_yerleri``: ``[(gorev_anahtari, yer_adi), ...]``, nöbet yeri adına göre sıralı.
    ``aktif_yerler``: otomatik dağıtıma açık nöbet yeri adları.

    Dönüş ``({gorev_anahtari: yeni_yer_adi}, uyari)``; ``uyari`` GİRİŞ ORTA
    boşaltılamadıysa açıklama, değilse ``None``.
    """
    gorev_yerleri = list(gorev_yerleri)
    bosaltilmis, uyari = giris_orta_bosalt(gorev_yerleri, aktif_yerler)
    if bosaltilmis != gorev_yerleri:
        # GİRİŞ ORTA'daki öğretmen yeni yeri tutuyormuş gibi rotasyona girer
        gorev_yerleri = sorted(bosaltilmis, key=lambda gy: turkce_sira_anahtari(gy[1]))

    if len(gorev_yerleri) < 2:
        return {anahtar: yer for anahtar, yer in gorev_yerleri}, uyari

    yerler = [y for _, y in gorev_yerleri]
    yeni_yerler = yerler[1:] + yerler[:1]
    return {anahtar: yeni for (anahtar, _), yeni in zip(gorev_yerleri, yeni_yerler)}, uyari
