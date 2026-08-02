"""Mazeret sınav planı oluşturma formu varsayılanları ve ILP dağıtım orkestrasyonu."""
from datetime import date, timedelta

from sinav.models import MazeretSinav, SinavBilgisi, Takvim, TakvimUretim
from sinav.services.mazeret_dagitim import populate_ogrenciler
from sinav.services.mazeret_ilp import MazeretILPService


def olustur_form_varsayilanlari(aktif_sinav: SinavBilgisi) -> dict:
    """Yeni mazeret planı formu için varsayılan oturum saatleri, max sınav/gün ve
    başlangıç tarihi önerisini (ana takvimin son gününden 5 iş günü sonrası) hazırlar."""
    varsayilan_saatler = "08:50,10:30,12:10,13:35,14:25"
    varsayilan_max_gun = MazeretSinav.VARSAYILAN_MAX_SINAV_PER_GUN
    try:
        varsayilan_saatler = aktif_sinav.parametreler.oturum_saatleri
        varsayilan_max_gun = aktif_sinav.parametreler.max_sinav_per_gun
    except Exception:
        pass

    aktif_uretim = TakvimUretim.objects.filter(sinav=aktif_sinav, aktif=True).first()
    oneri_tarih = None
    if aktif_uretim:
        son_gun = (
            Takvim.objects.filter(uretim=aktif_uretim)
            .values_list("tarih", flat=True)
            .order_by("tarih")
            .last()
        )
        if son_gun:
            aday = son_gun + timedelta(days=5)
            while aday.weekday() >= 5:
                aday += timedelta(days=1)
            oneri_tarih = aday

    return {
        "oturum_saatleri":   varsayilan_saatler,
        "max_sinav_per_gun": varsayilan_max_gun,
        "baslangic_tarihi":  oneri_tarih,
    }


def ogrenci_doldur_ve_dagit(
    mazeret: MazeretSinav, baslangic: date, oturum_saatleri: str,
    tatil_gunleri: str, max_gun: int,
) -> tuple[bool, str, int]:
    """Öğrenci listesini yoklama verilerinden doldurur (sureksiz_devamsiz ve muaf
    öğrenciler otomatik hariç tutulur) ve ILP ile çakışmasız takvim üretir.
    (başarılı, mesaj, hariç_tutulan_sayısı) döner."""
    eklenen, haric = populate_ogrenciler(mazeret)

    svc = MazeretILPService(
        config={"TIME_LIMIT": 120, "MAX_SINAV_PER_GUN": max_gun},
        log_fn=lambda m: None,
    )
    basarili, mesaj = svc.calistir(
        mazeret_sinav=mazeret,
        baslangic_tarih=baslangic,
        oturum_saatleri_str=oturum_saatleri,
        tatil_gunleri_str=tatil_gunleri,
    )
    return basarili, mesaj, haric
