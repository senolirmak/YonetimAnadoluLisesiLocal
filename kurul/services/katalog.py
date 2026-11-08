"""Varsayılan kurul/komisyon kataloğunun yüklenmesi (kurul/fixtures/kurul_katalogu.json)."""

import datetime
import json
from pathlib import Path

from django.db import transaction

from kurul.models import KurulTuru, KurulYapiKalemi

KATALOG_DOSYASI = Path(__file__).resolve().parent.parent / "fixtures" / "kurul_katalogu.json"

ALANLAR = (
    "ad", "kategori", "kapsam", "otomatik_uyelik", "mevzuat_dayanagi", "mevzuat_url",
    "olusum", "toplanma", "gorev_suresi", "zorunlu", "gizli", "son_dogrulama", "sira",
    "gundem_onerileri",
)


def _kayitlar():
    for kayit in json.loads(KATALOG_DOSYASI.read_text(encoding="utf-8")):
        alanlar = {k: kayit.get(k) for k in ALANLAR if k in kayit}
        if alanlar.get("son_dogrulama"):
            alanlar["son_dogrulama"] = datetime.date.fromisoformat(alanlar["son_dogrulama"])
        yield kayit["kod"], alanlar, kayit.get("yapi", [])


def _yapiyi_yaz(tur, yapi):
    for sira, kalem in enumerate(yapi, 1):
        KurulYapiKalemi.objects.create(tur=tur, sira=sira, **kalem)


@transaction.atomic
def katalogu_yukle(guncelle=False) -> dict:
    """Katalogdaki türleri yapılarıyla birlikte `kod` ile ekler.

    Var olan türler `guncelle=True` değilse korunur (okulun yaptığı düzenlemeler ezilmez);
    yalnızca yapısı hiç tanımlanmamış türlere katalogdaki yapı eklenir. `guncelle=True`
    türü ve yapısını katalogla değiştirir — eski kalemlere bağlı üyeler silinmez, yapı
    dışı (ek) üye olarak kalır. Eklenen/güncellenen/atlanan sayılarını döner."""
    sonuc = {"eklenen": 0, "guncellenen": 0, "atlanan": 0}
    for kod, alanlar, yapi in _kayitlar():
        tur = KurulTuru.objects.filter(kod=kod).first()
        if tur is None:
            _yapiyi_yaz(KurulTuru.objects.create(kod=kod, **alanlar), yapi)
            sonuc["eklenen"] += 1
        elif guncelle:
            for alan, deger in alanlar.items():
                setattr(tur, alan, deger)
            tur.save()
            tur.yapi.all().delete()
            _yapiyi_yaz(tur, yapi)
            sonuc["guncellenen"] += 1
        else:
            if not tur.yapi.exists():
                _yapiyi_yaz(tur, yapi)
            # Sonradan eklenen katalog alanları boşsa doldurulur (okulun girdiği değer ezilmez)
            if not tur.gundem_onerileri and alanlar.get("gundem_onerileri"):
                tur.gundem_onerileri = alanlar["gundem_onerileri"]
                tur.save(update_fields=["gundem_onerileri"])
            sonuc["atlanan"] += 1
    return sonuc


def katalog_bossa_yukle() -> bool:
    """Hiç tür tanımlı değilse varsayılan kataloğu yükler (ilk kullanım) ve True döner.

    Katalog daha önce yüklendiyse, sonradan eklenen alanlardan (gündem önerileri) eksik
    kalanlar sessizce tamamlanır; okulun girdiği değerler ezilmez."""
    if not KurulTuru.objects.exists():
        katalogu_yukle()
        return True
    if KurulTuru.objects.filter(kod="ogretmenler-kurulu", gundem_onerileri="").exists():
        katalogu_yukle()
    return False
