from collections import defaultdict
from datetime import datetime as dt

from sinav.models import Takvim as TakvimModel


def _oturum_atamalarini_hesapla(items: list[tuple]) -> list[int]:
    """`items`: [(tarih, saat), ...] — girdiyle aynı sırada, her kayıt için günlük
    (aynı tarih içinde) saat sırasına göre 1'den başlayan oturum numarasını döner."""
    gun_map: dict = defaultdict(list)
    for idx, (tarih, saat) in enumerate(items):
        gun_map[tarih].append((idx, saat))

    sonuc: list = [None] * len(items)
    for gun_kayitlari in gun_map.values():
        gun_kayitlari.sort(key=lambda x: x[1])
        slot_to_oturum: dict = {}
        oturum_no = 1
        for idx, saat in gun_kayitlari:
            if saat not in slot_to_oturum:
                slot_to_oturum[saat] = oturum_no
                oturum_no += 1
            sonuc[idx] = slot_to_oturum[saat]
    return sonuc


def onizleme_oturumlarini_yeniden_numarala(kayitlar: list[dict]) -> None:
    """Önizleme (henüz onaylanmamış) kayıt listesindeki 'Oturum' alanını
    'Tarih'+'Saat' sırasına göre günlük olarak yeniden numaralar (yerinde değişir)."""
    items = [(r["Tarih"], r.get("Saat", "")) for r in kayitlar]
    for r, oturum_no in zip(kayitlar, _oturum_atamalarini_hesapla(items)):
        r["Oturum"] = oturum_no


def takvim_oturumlarini_yeniden_numarala(aktif_uretim) -> None:
    """Takvim tablosundaki kayıtları tarih+saat sırasına göre günlük olarak
    1'den yeniden numaralar ve DB'ye yazar."""
    kayitlar = list(
        TakvimModel.objects.filter(uretim=aktif_uretim).order_by("tarih", "saat")
    )
    items = [(t.tarih, t.saat) for t in kayitlar]
    for t, oturum_no in zip(kayitlar, _oturum_atamalarini_hesapla(items)):
        t.oturum = oturum_no
        t.save(update_fields=["oturum"])


def takvimi_onayla(aktif_sinav, uretim) -> int:
    """Bir TakvimUretim'in `onizleme_verisi` JSON'unu gerçek Takvim kayıtlarına
    çevirir (bulk_create), önizleme verisini temizler. Döndürülen değer
    oluşturulan kayıt sayısıdır."""
    from okul.models import DersHavuzu, DersSaatleri

    kayitlar = uretim.onizleme_verisi
    # Takvim.ders FK için ders adı → DersHavuzu eşlemesi
    # Çift oturumlu dersler " (Yazili)"/" (Uygulama)" ekiyle gelir; base adı dene.
    ders_map = {d.ders_adi: d for d in DersHavuzu.objects.all()}

    def _ders_fk(ders_adi_str):
        obj = ders_map.get(ders_adi_str)
        if obj is None:
            base = ders_adi_str.rsplit(" (", 1)[0].strip()
            obj = ders_map.get(base)
        return obj

    def _sinav_turu(ders_adi_str):
        if ders_adi_str.endswith(" (Uygulama)"):
            return "Uygulama"
        if ders_adi_str.endswith(" (Yazili)"):
            return "Yazili"
        return ""

    # Takvim.ders_saati FK için saat string → DersSaatleri eşlemesi
    saatler_map = {
        str(ds.derssaati_baslangic)[:5]: ds
        for ds in DersSaatleri.objects.all()
    }

    # Yalnızca bu uretim'e ait eski Takvim kayıtlarını temizle (yeniden onaylama durumu)
    TakvimModel.objects.filter(uretim=uretim).delete()
    TakvimModel.objects.bulk_create([
        TakvimModel(
            sinav      = aktif_sinav,
            uretim     = uretim,
            tarih      = dt.strptime(r["Tarih"], "%Y-%m-%d").date(),
            saat       = r["Saat"],
            ders_saati = saatler_map.get(r["Saat"]),
            oturum     = int(r["Oturum"]),
            ders       = _ders_fk(r["Ders"]),
            sinav_turu = _sinav_turu(r["Ders"]),
            subeler    = r["Subeler"],
        )
        for r in kayitlar
    ])
    # Önizleme verisini temizle
    uretim.onizleme_verisi = None
    uretim.save(update_fields=["onizleme_verisi"])

    return len(kayitlar)
