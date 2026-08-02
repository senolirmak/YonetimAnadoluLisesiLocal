"""Mazeret sınavı öncesi yoklama simülasyonu ve tekil öğrenci yoklama girişi."""
import random
import re
from collections import defaultdict

from django.db.models import Q

from okul.utils import get_aktif_egitim_yili
from sinav.models import OturmaPlani, SinavSalonYoklama

_SINAV_TURU_RE = re.compile(r'^(.*?)\s+\((Yazili|Uygulama)\)$')


def _base_ders(ders_adi_full: str) -> str:
    m = _SINAV_TURU_RE.match(ders_adi_full or "")
    return m.group(1).strip() if m else (ders_adi_full or "")


def ozel_durum_siniflandirici():
    """Sürekli devamsız / muaf öğrencileri (okulno, ders_adi) bazında etiketleyen
    bir sınıflandırıcı döner: `siniflandir(okulno, ders_adi_full) -> str`
    ("sureksiz" / "muaf" / "")."""
    from ogrenci.models import Ogrenci as _Ogrenci
    from ogrenci.models import OgrenciMuaf as _OgrenciMuaf

    sureksiz_okulnolari: set[str] = set(
        _Ogrenci.objects.filter(sureksiz_devamsiz=True).values_list("okulno", flat=True)
    )
    muaf_okulno_ders: set[tuple[str, str]] = set(
        _OgrenciMuaf.objects.filter(egitim_yili=get_aktif_egitim_yili())
        .values_list("ogrenci__okulno", "ders__ders_adi")
    )

    def siniflandir(okulno: str, ders_adi_full: str) -> str:
        if okulno in sureksiz_okulnolari:
            return "sureksiz"
        if (okulno, _base_ders(ders_adi_full)) in muaf_okulno_ders:
            return "muaf"
        return ""

    return siniflandir


def oturum_istatistikleri(aktif_uretim) -> dict:
    """Aktif üretimin oturumları için öğrenci/hariç/yoklama istatistiklerini hazırlar."""
    if not aktif_uretim:
        return {
            "oturum_listesi": [], "toplam_oturum": 0, "toplam_ogrenci": 0,
            "toplam_haric": 0, "toplam_uygun": 0,
            "yoklama_kayit_sayisi": 0, "yok_sayisi": 0,
        }

    siniflandir = ozel_durum_siniflandirici()

    # (tarih, saat, salon) → {ogrenci, haric} sayıları
    oturum_ozet: dict = defaultdict(lambda: {"ogrenci": 0, "haric": 0})
    for op in (
        OturmaPlani.objects
        .filter(uretim=aktif_uretim)
        .values("tarih", "saat", "salon", "okulno", "ders_adi")
        .order_by("tarih", "saat", "salon")
    ):
        key = (str(op["tarih"]), op["saat"], op["salon"])
        oturum_ozet[key]["ogrenci"] += 1
        if siniflandir(op["okulno"], op["ders_adi"]):
            oturum_ozet[key]["haric"] += 1

    # Yoklama durumu: oturum başına kayıt ve yok sayısı
    yoklama_ozet: dict = defaultdict(lambda: {"toplam": 0, "yok": 0})
    for yk in SinavSalonYoklama.objects.filter(uretim=aktif_uretim).values(
        "tarih", "saat", "salon", "durum"
    ):
        key = (str(yk["tarih"]), yk["saat"], yk["salon"])
        yoklama_ozet[key]["toplam"] += 1
        if yk["durum"] == "yok":
            yoklama_ozet[key]["yok"] += 1

    import datetime as _dt

    oturum_listesi = []
    toplam_oturum = toplam_ogrenci = toplam_haric = 0
    yoklama_kayit_sayisi = yok_sayisi = 0
    for key, oz in sorted(oturum_ozet.items()):
        tarih_str, saat_str, salon_str = key
        yk = yoklama_ozet.get(key, {"toplam": 0, "yok": 0})
        ogrenci = oz["ogrenci"]
        haric   = oz["haric"]
        try:
            tarih_obj = _dt.date.fromisoformat(tarih_str)
        except ValueError:
            tarih_obj = tarih_str
        oturum_listesi.append({
            "tarih":       tarih_obj,
            "saat":        saat_str,
            "salon":       salon_str,
            "ogrenci":     ogrenci,
            "haric":       haric,
            "uygun":       ogrenci - haric,
            "yoklama_var": yk["toplam"] > 0,
            "yok_sayisi":  yk["yok"],
        })
        toplam_oturum += 1
        toplam_ogrenci += ogrenci
        toplam_haric   += haric
        yoklama_kayit_sayisi += yk["toplam"]
        yok_sayisi += yk["yok"]

    return {
        "oturum_listesi":       oturum_listesi,
        "toplam_oturum":        toplam_oturum,
        "toplam_ogrenci":       toplam_ogrenci,
        "toplam_haric":         toplam_haric,
        "toplam_uygun":         toplam_ogrenci - toplam_haric,
        "yoklama_kayit_sayisi": yoklama_kayit_sayisi,
        "yok_sayisi":           yok_sayisi,
    }


def _secili_slot_filtresi(secili_keys) -> Q:
    filtre = Q()
    for key in secili_keys:
        parcalar = key.split("_", 2)
        if len(parcalar) == 3:
            t_str, saat_str, salon_str = parcalar
            filtre |= Q(tarih=t_str, saat=saat_str, salon=salon_str)
    return filtre


def yoklama_simulasyonu_calistir(
    aktif_uretim, secili_keys, tumu_sec: bool, devamsizlik_yuzdesi: int,
    mevcut_de_kaydet: bool, sifirla_once: bool, kaydeden,
) -> dict:
    """Seçili oturumlar için rastgele devamsızlık simülasyonu üretip
    SinavSalonYoklama'ya yazar. Sonuç, mesaj oluşturmak için sayaçları içerir."""
    op_qs = OturmaPlani.objects.filter(uretim=aktif_uretim)
    if not tumu_sec:
        op_qs = op_qs.filter(_secili_slot_filtresi(secili_keys))

    kayitlar = list(
        op_qs.values(
            "tarih", "saat", "salon", "okulno",
            "adi_soyadi", "sinifsube", "sira_no", "ders_adi",
        ).order_by("tarih", "saat", "salon", "sira_no")
    )

    if sifirla_once:
        sil_qs = SinavSalonYoklama.objects.filter(uretim=aktif_uretim)
        if not tumu_sec:
            sil_qs = sil_qs.filter(_secili_slot_filtresi(secili_keys))
        sil_qs.delete()

    siniflandir = ozel_durum_siniflandirici()
    rng = random.Random()
    yeni_kayitlar = []
    yok_count = mevcut_count = haric_count = 0

    for r in kayitlar:
        if siniflandir(r["okulno"], r["ders_adi"]):
            # Sürekli devamsız / muaf → sınava girmez; mevcut kaydı da oluşturma
            haric_count += 1
            continue

        is_absent = rng.random() * 100 < devamsizlik_yuzdesi
        if is_absent:
            durum = "yok"
            yok_count += 1
        elif mevcut_de_kaydet:
            durum = "mevcut"
            mevcut_count += 1
        else:
            continue

        yeni_kayitlar.append(SinavSalonYoklama(
            uretim=aktif_uretim,
            tarih=r["tarih"],
            saat=r["saat"],
            salon=r["salon"],
            okulno=r["okulno"],
            adi_soyadi=r["adi_soyadi"],
            sinifsube=r["sinifsube"],
            sira_no=r["sira_no"],
            durum=durum,
            kaydeden=kaydeden,
        ))

    SinavSalonYoklama.objects.bulk_create(yeni_kayitlar, ignore_conflicts=True)

    return {
        "toplam":       len(kayitlar),
        "haric_count":  haric_count,
        "yok_count":    yok_count,
        "mevcut_count": mevcut_count,
    }


def yoklama_getir(aktif_uretim, okulno: str) -> list[dict]:
    """Bir öğrencinin aktif üretimdeki tüm oturumlarının mevcut yoklama durumunu döner."""
    qs = (
        OturmaPlani.objects
        .filter(uretim=aktif_uretim, okulno=okulno)
        .order_by("tarih", "saat")
    )
    mevcut_yoklama = {
        (y.tarih, y.saat, y.salon): y.durum
        for y in SinavSalonYoklama.objects.filter(uretim=aktif_uretim, okulno=okulno)
    }
    return [
        {
            "tarih":    o.tarih,
            "saat":     o.saat,
            "salon":    o.salon,
            "ders_adi": o.ders_adi,
            "durum":    mevcut_yoklama.get((o.tarih, o.saat, o.salon), "mevcut"),
        }
        for o in qs
    ]


def yoklama_kaydet(aktif_uretim, okulno: str, satirlar: list[dict], kaydeden) -> str:
    """`satirlar`: [{"tarih": date, "saat": str, "salon": str, "durum": str}, ...].
    Döndürülen değer kaydedilen öğrencinin adı soyadıdır (mesaj için); eşleşen
    satır yoksa boş string döner."""
    op_lookup = {
        (o.tarih, o.saat, o.salon): o
        for o in OturmaPlani.objects.filter(uretim=aktif_uretim, okulno=okulno)
    }
    adi_soyadi = ""
    for satir in satirlar:
        o = op_lookup.get((satir["tarih"], satir["saat"], satir["salon"]))
        if not o:
            continue
        adi_soyadi = o.adi_soyadi
        SinavSalonYoklama.objects.update_or_create(
            uretim=aktif_uretim, tarih=satir["tarih"], saat=satir["saat"],
            salon=satir["salon"], okulno=okulno,
            defaults={
                "adi_soyadi": o.adi_soyadi,
                "sinifsube":  o.sinifsube,
                "sira_no":    o.sira_no,
                "durum":      satir["durum"],
                "kaydeden":   kaydeden,
            },
        )
    return adi_soyadi
