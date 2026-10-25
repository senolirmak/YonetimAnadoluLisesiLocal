"""Arka plan görevlerinin (takvim / oturma planı üretimi) durumu.

Görev, onu başlatan Gunicorn worker'ında bir thread olarak çalışır; ama sayfanın
durum sorguları (`gorev_durumu`) ve "Durdur" isteği (`gorev_iptal`) başka bir
worker'a düşebilir. Bu yüzden durum, tüm worker'ların okuyabildiği paylaşılan
"gorevler" önbelleğinde tutulur (bkz. config/settings/base.py: CACHES).

Yarış durumu olmasın diye her anahtarın tek bir yazarı vardır:
  - `sinav_gorev:<id>`       → yalnızca görevi çalıştıran thread yazar (log, done, error ...)
  - `sinav_gorev_iptal:<id>` → yalnızca iptal isteği yazar
"""

import threading
import time

from django.core.cache import caches

SURE_SN = 6 * 60 * 60  # tamamlanan görevin durumu 6 saat saklanır
_IPTAL_KONTROL_ARALIGI_SN = 1.0
IPTAL_MESAJI = "! Durdurma istegi alindi. Mevcut adim/oturum tamamlaninca durulacak..."
_YAZMA_ARALIGI_SN = 0.5  # log satırları en fazla bu sıklıkta depoya yazılır

_yerel: dict = {}  # bu worker'da çalışan görevler: {id: durum}
_kilit = threading.Lock()
_iptal_onbellek: dict = {}  # {id: (son_kontrol_zamani, deger)}
_son_yazma: dict = {}  # {id: zaman}


def _depo():
    return caches["gorevler"]


def _anahtar(gorev_id):
    return f"sinav_gorev:{gorev_id}"


def _iptal_anahtari(gorev_id):
    return f"sinav_gorev_iptal:{gorev_id}"


def _yaz(gorev_id, zorla=True):
    """Yerel durumu paylaşılan depoya yazar. `_kilit` tutulurken çağrılır.
    `zorla=False` iken son yazmadan bu yana `_YAZMA_ARALIGI_SN` geçmediyse yazmaz
    (GA çok sayıda log satırı üretir; her satırda tüm listeyi yazmak pahalıdır)."""
    simdi = time.monotonic()
    if not zorla and simdi - _son_yazma.get(gorev_id, 0) < _YAZMA_ARALIGI_SN:
        return
    _son_yazma[gorev_id] = simdi
    kayit = dict(_yerel[gorev_id])
    kayit["logs"] = list(kayit["logs"])
    _depo().set(_anahtar(gorev_id), kayit, SURE_SN)


def olustur(gorev_id):
    with _kilit:
        _yerel[gorev_id] = {"logs": [], "done": False, "error": False, "tamamlanan": []}
        _yaz(gorev_id)


def log_ekle(gorev_id, mesaj):
    with _kilit:
        _yerel[gorev_id]["logs"].append(mesaj)
        _yaz(gorev_id, zorla=False)


def loglar(gorev_id):
    with _kilit:
        return list(_yerel.get(gorev_id, {}).get("logs", []))


def guncelle(gorev_id, **alanlar):
    with _kilit:
        _yerel[gorev_id].update(alanlar)
        _yaz(gorev_id)


def bitir(gorev_id, hata=False):
    with _kilit:
        _yerel[gorev_id].update(done=True, error=hata)
        _yaz(gorev_id)
        _yerel.pop(gorev_id, None)
        _son_yazma.pop(gorev_id, None)
    _iptal_onbellek.pop(gorev_id, None)


def iptal_iste(gorev_id):
    """Durdur isteği. Görev bulunamazsa ya da zaten bittiyse False döner."""
    durum = _depo().get(_anahtar(gorev_id))
    if not durum or durum.get("done"):
        return False
    _depo().set(_iptal_anahtari(gorev_id), True, SURE_SN)
    return True


def iptal_istendi_mi(gorev_id):
    """GA döngüsü bunu sık çağırır; paylaşılan depo en fazla saniyede bir okunur."""
    simdi = time.monotonic()
    son = _iptal_onbellek.get(gorev_id)
    if son and simdi - son[0] < _IPTAL_KONTROL_ARALIGI_SN:
        return son[1]
    deger = bool(_depo().get(_iptal_anahtari(gorev_id)))
    _iptal_onbellek[gorev_id] = (simdi, deger)
    # Görev bir süre log yazmadıysa bekleyen son satırlar burada depoya aktarılır.
    with _kilit:
        if gorev_id in _yerel:
            _yaz(gorev_id, zorla=False)
    return deger


def durum(gorev_id):
    """Sayfanın sorguladığı durum; görev yoksa None. Hangi worker'dan çağrıldığı fark etmez."""
    kayit = _depo().get(_anahtar(gorev_id))
    if kayit is None:
        return None
    iptal = bool(_depo().get(_iptal_anahtari(gorev_id)))
    logs = list(kayit.get("logs", []))
    if iptal and not kayit.get("done"):
        logs.append(IPTAL_MESAJI)
    return {
        "logs": logs,
        "done": kayit.get("done", False),
        "error": kayit.get("error", False),
        "cancelled": iptal,
        "tamamlanan": kayit.get("tamamlanan", []),
    }
