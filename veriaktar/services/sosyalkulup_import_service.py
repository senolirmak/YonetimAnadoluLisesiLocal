"""Okul sosyal kulüpleri ve danışman öğretmenlerini Excel'den içe aktarır.

Beklenen sayfa düzeni (ilk sayfa okunur; başlık satırı ilk 10 satır içinde aranır):

    Sıra NO | Sosyal Kulüp | Danışman Öğretmen(1) | Danışman Öğretmen(2) | ...

- Başlığında "KULÜP" geçen sütun kulüp adıdır; "DANIŞMAN" geçen tüm sütunlar danışman
  öğretmendir (sayısı serbesttir).
- Kulüpler `SosyalKulup` tablosuna eklenir (adı aynı olan kulüp varsa yeniden kullanılır
  ve aktif yapılır).
- Danışmanlar verilen eğitim yılına yazılır: dosyadaki her kulübün o yılki danışman listesi
  dosyadakiyle değiştirilir. Dosyada olmayan kulüplere dokunulmaz.
- Öğretmen adı personel listesiyle (büyük/küçük harf ve fazla boşluk farkı gözetmeden)
  eşleştirilir; bulunamayan adlar atlanır ve raporda listelenir.
"""

import re
from dataclasses import dataclass, field

from django.db import transaction
from openpyxl import load_workbook


def _buyuk_harf(metin):
    """Türkçe kurallarına göre büyük harf + tek boşluk."""
    metin = str(metin or "").replace("i", "İ").replace("ı", "I").upper()
    return re.sub(r"\s+", " ", metin).strip()


def _temiz(deger):
    return re.sub(r"\s+", " ", str(deger)).strip() if deger is not None else ""


@dataclass
class SosyalKulupImportSonucu:
    yeni_kulup: int = 0
    mevcut_kulup: int = 0
    danisman_atanan: int = 0
    danisman_kaldirilan: int = 0
    bulunamayan_ogretmenler: list = field(default_factory=list)  # [(kulüp, ad)]


class SosyalKulupExcelHatasi(ValueError):
    pass


def _satirlari_oku(dosya):
    """[(kulüp_adı, [danışman_adı, ...]), ...] döner."""
    try:
        wb = load_workbook(dosya, read_only=True, data_only=True)
    except Exception as exc:
        raise SosyalKulupExcelHatasi("Dosya okunamadı; geçerli bir .xlsx dosyası seçin.") from exc
    try:
        satirlar = list(wb.worksheets[0].iter_rows(values_only=True))
    finally:
        wb.close()

    for i, satir in enumerate(satirlar[:10]):
        basliklar = [_buyuk_harf(h) for h in satir]
        kulup_sutunu = next((j for j, b in enumerate(basliklar) if "KULÜP" in b), None)
        danisman_sutunlari = [j for j, b in enumerate(basliklar) if "DANIŞMAN" in b]
        if kulup_sutunu is not None and danisman_sutunlari:
            break
    else:
        raise SosyalKulupExcelHatasi(
            "Başlık satırı bulunamadı: 'Sosyal Kulüp' ve 'Danışman Öğretmen' sütunları olmalı."
        )

    sonuc = []
    for satir in satirlar[i + 1:]:
        satir = list(satir) + [None] * (len(basliklar) - len(satir))
        ad = _temiz(satir[kulup_sutunu])
        if not ad:
            continue
        danismanlar = [_temiz(satir[j]) for j in danisman_sutunlari if _temiz(satir[j])]
        sonuc.append((ad, danismanlar))
    if not sonuc:
        raise SosyalKulupExcelHatasi("Dosyada kulüp satırı bulunamadı.")
    return sonuc


@transaction.atomic
def sosyal_kulupleri_ice_aktar(dosya, egitim_yili):
    from okul.models import Personel
    from sosyalkulup.models import KulupDanisman, SosyalKulup

    satirlar = _satirlari_oku(dosya)
    sonuc = SosyalKulupImportSonucu()

    kulupler = {_buyuk_harf(k.ad): k for k in SosyalKulup.objects.all()}
    personeller = {_buyuk_harf(p.adi_soyadi): p for p in Personel.objects.all()}

    for kulup_adi, danisman_adlari in satirlar:
        kulup = kulupler.get(_buyuk_harf(kulup_adi))
        if kulup is None:
            kulup = SosyalKulup.objects.create(ad=kulup_adi)
            kulupler[_buyuk_harf(kulup_adi)] = kulup
            sonuc.yeni_kulup += 1
        else:
            sonuc.mevcut_kulup += 1
            if not kulup.aktif:
                kulup.aktif = True
                kulup.save(update_fields=["aktif"])

        istenen = set()
        for ad in danisman_adlari:
            personel = personeller.get(_buyuk_harf(ad))
            if personel is None:
                sonuc.bulunamayan_ogretmenler.append((kulup.ad, ad))
            else:
                istenen.add(personel.pk)

        mevcut = set(
            KulupDanisman.objects.filter(egitim_yili=egitim_yili, kulup=kulup).values_list(
                "ogretmen_id", flat=True
            )
        )
        kaldirilacak = mevcut - istenen
        if kaldirilacak:
            KulupDanisman.objects.filter(
                egitim_yili=egitim_yili, kulup=kulup, ogretmen_id__in=kaldirilacak
            ).delete()
            sonuc.danisman_kaldirilan += len(kaldirilacak)
        for ogretmen_id in istenen - mevcut:
            KulupDanisman.objects.create(
                egitim_yili=egitim_yili, kulup=kulup, ogretmen_id=ogretmen_id
            )
            sonuc.danisman_atanan += 1

    return sonuc
