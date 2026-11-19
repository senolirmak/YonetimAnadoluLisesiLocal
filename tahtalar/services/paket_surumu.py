"""akal-eta-yonetim paketinin sürüm denetimi.

Tahtalar yeni sürümü yalnızca `SURUM` artınca çeker; paket içeriği değişip
sürüm aynı kalırsa güncelleme sessizce tahtalara ulaşmaz. Bunu önlemek için
pakete giren içeriğin özeti sürümüyle birlikte `paket-ozeti.txt`'de tutulur:

    1.2.0 <sha256>

`test_paket_surumu` içerik değişip kayıt güncellenmediyse başarısız olur ve
yeni sürümü önerir; `python manage.py tahta_surum_artir` SURUM'u ve kaydı
birlikte günceller. Sunucuya özgü olanlar (kayıt anahtarı, CA, depo imza
anahtarı) özete girmez.
"""

import hashlib
import re

from tahtalar.services import kurulum_paketi

OZET_DOSYA_ADI = "paket-ozeti.txt"
_SURUM_SATIRI = re.compile(r'^SURUM = "[^"\n]*"$', re.MULTILINE)
SEVIYELER = ("yama", "kucuk", "buyuk")


class SurumHatasi(Exception):
    pass


def _ozet_dosyasi():
    return kurulum_paketi.UYGULAMA_KLASORU / OZET_DOSYA_ADI


def _uygulama_dosyasi():
    return kurulum_paketi.UYGULAMA_KLASORU / kurulum_paketi.UYGULAMA_DOSYASI


def icerik_ozeti():
    """Pakete giren içeriğin özeti (SURUM satırı hariç)."""
    klasor = kurulum_paketi.UYGULAMA_KLASORU
    uygulama = _uygulama_dosyasi().read_text(encoding="utf-8")
    parcalar = [
        ("uygulama", _SURUM_SATIRI.sub('SURUM = ""', uygulama).encode("utf-8")),
        ("service", (klasor / f"{kurulum_paketi.PAKET_ADI}.service").read_bytes()),
        ("conf.ornek", (klasor / f"{kurulum_paketi.PAKET_ADI}.conf.ornek").read_bytes()),
        ("eski-kurulumu-tasi.sh", (klasor / "eski-kurulumu-tasi.sh").read_bytes()),
        ("postinst", kurulum_paketi._POSTINST.encode("utf-8")),
        ("prerm", kurulum_paketi._PRERM.encode("utf-8")),
        ("postrm", kurulum_paketi._POSTRM.encode("utf-8")),
        ("control", kurulum_paketi._control("", 0).encode("utf-8")),
    ]
    ozet = hashlib.sha256()
    for ad, icerik in parcalar:
        ozet.update(f"{ad}\0{len(icerik)}\0".encode())
        ozet.update(icerik)
    return ozet.hexdigest()


def surum_parcalari(surum):
    eslesme = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", surum or "")
    if not eslesme:
        raise SurumHatasi(f"Sürüm X.Y.Z biçiminde olmalı: {surum!r}")
    return tuple(int(p) for p in eslesme.groups())


def sonraki_surum(surum, seviye="yama"):
    buyuk, kucuk, yama = surum_parcalari(surum)
    if seviye == "buyuk":
        return f"{buyuk + 1}.0.0"
    if seviye == "kucuk":
        return f"{buyuk}.{kucuk + 1}.0"
    if seviye == "yama":
        return f"{buyuk}.{kucuk}.{yama + 1}"
    raise SurumHatasi(f"Bilinmeyen seviye: {seviye}")


def kayitli():
    """(sürüm, özet) ya da kayıt yoksa (None, None)."""
    try:
        metin = _ozet_dosyasi().read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, None
    satirlar = [s for s in metin.splitlines() if s.strip() and not s.startswith("#")]
    parca = satirlar[0].split() if satirlar else []
    if len(parca) != 2:
        raise SurumHatasi(f"{OZET_DOSYA_ADI} bozuk.")
    return parca[0], parca[1]


def denetle():
    """Sorun yoksa None, varsa açıklayıcı mesaj."""
    surum = kurulum_paketi.uygulama_surumu()
    kayitli_surum, kayitli_ozet = kayitli()
    ozet = icerik_ozeti()
    komut = "python manage.py tahta_surum_artir"
    if kayitli_surum is None:
        return f"{OZET_DOSYA_ADI} yok. Oluşturmak için: {komut} --kaydet"
    if ozet == kayitli_ozet and surum == kayitli_surum:
        return None
    if ozet == kayitli_ozet:
        return (
            f"SURUM {kayitli_surum} → {surum} olmuş ama paket içeriği değişmemiş; "
            f"tahtalar boşuna güncellenir. SURUM'u {kayitli_surum} yapın."
        )
    if surum == kayitli_surum:
        return (
            f"Tahta paketi değişti ama SURUM hâlâ {surum}; tahtalar bu değişikliği almaz. "
            f"Önerilen: {sonraki_surum(surum)} (yeni özellikse {sonraki_surum(surum, 'kucuk')}) "
            f"→ {komut} [--kucuk | --buyuk]"
        )
    return f"SURUM {surum} olmuş ama {OZET_DOSYA_ADI} güncellenmemiş → {komut}"


def kaydet(surum=None):
    """SURUM'u (verildiyse) yazar ve özet kaydını günceller → yazılan sürüm."""
    if surum is not None:
        surum_parcalari(surum)
        yol = _uygulama_dosyasi()
        metin = yol.read_text(encoding="utf-8")
        yeni, adet = _SURUM_SATIRI.subn(f'SURUM = "{surum}"', metin, count=1)
        if adet != 1:
            raise SurumHatasi(f"{yol.name} içinde SURUM satırı bulunamadı.")
        yol.write_text(yeni, encoding="utf-8")
    surum = kurulum_paketi.uygulama_surumu()
    _ozet_dosyasi().write_text(
        "# akal-eta-yonetim paket içeriğinin özeti; elle değiştirmeyin.\n"
        "# Güncellemek için: python manage.py tahta_surum_artir\n"
        f"{surum} {icerik_ozeti()}\n",
        encoding="utf-8",
    )
    return surum


def artir(seviye="yama"):
    """İçerik değiştiyse SURUM'u artırıp kaydeder. Döner: (eski, yeni) ya da
    içerik değişmediyse (eski, None). SURUM elle artırılmışsa olduğu gibi kaydedilir."""
    surum = kurulum_paketi.uygulama_surumu()
    kayitli_surum, kayitli_ozet = kayitli()
    if kayitli_surum is None:
        raise SurumHatasi(f"{OZET_DOSYA_ADI} yok; önce --kaydet ile oluşturun.")
    if icerik_ozeti() == kayitli_ozet:
        return kayitli_surum, None
    if surum_parcalari(surum) > surum_parcalari(kayitli_surum):
        return kayitli_surum, kaydet()
    return kayitli_surum, kaydet(sonraki_surum(kayitli_surum, seviye))
