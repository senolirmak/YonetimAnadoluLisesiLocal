import re
import pandas as pd

from sorumluluk.models import (
    SorumluDers,
    SorumluDersHavuzu,
    SorumluOgrenci,
    SorumluSinav,
)

_BASLIK_RE = re.compile(r"(\d+)\.\s*S[ıi]n[ıi]f\s*/\s*([A-Z])\s*Şubesi", re.IGNORECASE)


def _normalize(text) -> str:
    return " ".join(str(text).split())


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
            for col_idx in range(8, min(12, len(cols) - 1)):
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

    havuz_kayitlari = [
        SorumluDersHavuzu(sinav=sinav, ders_adi=d_adi, onceki_sinif=d_sinif)
        for d_adi, d_sinif in ders_havuzu_set
    ]
    SorumluDersHavuzu.objects.bulk_create(havuz_kayitlari, ignore_conflicts=True)

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
