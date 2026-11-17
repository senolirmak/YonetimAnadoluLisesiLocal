"""MEB Lider'den dışa aktarılan tahta listesini (Excel) TahtaEnvanteri'ne yükler.

Lider Id'ye göre ekler ya da günceller; tekrar çalıştırmak güvenlidir.
Excel'de olmayan kayıtlar silinmez.
"""

import datetime
from dataclasses import dataclass, field

import openpyxl
from django.db import transaction
from django.utils import timezone

from tahtalar.models import Tahta, TahtaEnvanteri
from tahtalar.services.ajan_api import envanteri_bagla, mac_normalize

# Excel başlığı → model alanı
SUTUNLAR = {
    "Lider Id": "lider_id",
    "MAC": "mac_adresi",
    "Okul Kodu": "okul_kodu",
    "Şube Adı": "sube_adi",
    "Faz": "faz",
    "Durumu": "lider_cevrimici",
    "Aktif/Pasif": "lider_aktif",
    "IP Adresi 1": "ip_adresi",
    "Oluşturulma Tarihi": "lider_olusturulma",
    "Durum Değişim Tarihi": "lider_durum_degisim",
    "İşletim Sistemi Versiyonu": "isletim_sistemi",
    "Ahenk Versiyonu": "ahenk_surumu",
    "Marka": "marka",
    "Model": "model",
    "İşlemci": "islemci",
    "RAM(GB)": "ram_gb",
    "Toplam Disk Alanı(GB)": "disk_toplam_gb",
    "Kullanılan Disk Alanı(GB)": "disk_kullanilan_gb",
    "Boş Disk Alanı(GB)": "disk_bos_gb",
}
ZORUNLU = {"Lider Id", "MAC", "Şube Adı"}
TARIH_ALANLARI = {"lider_olusturulma", "lider_durum_degisim"}
SAYI_ALANLARI = {"ram_gb", "disk_toplam_gb", "disk_kullanilan_gb", "disk_bos_gb"}


class EnvanterHatasi(Exception):
    pass


@dataclass
class AktarimSonucu:
    eklenen: int = 0
    guncellenen: int = 0
    baglanan: int = 0
    hatalar: list = field(default_factory=list)


def _metin(deger):
    return "" if deger is None else str(deger).strip()


def _sayi(deger):
    try:
        return int(float(_metin(deger)))
    except ValueError:
        return None


def _tarih(deger):
    if isinstance(deger, datetime.datetime):
        tarih = deger
    else:
        try:
            tarih = datetime.datetime.strptime(_metin(deger), "%d/%m/%Y %H:%M:%S")
        except ValueError:
            return None
    return timezone.make_aware(tarih) if timezone.is_naive(tarih) else tarih


def _evet_hayir(deger, evet, hayir):
    metin = _metin(deger)
    if metin == evet:
        return True
    if metin == hayir:
        return False
    return None


def satiri_donustur(satir):
    """{Excel başlığı: değer} → TahtaEnvanteri alanları. Geçersizse EnvanterHatasi."""
    lider_id = _sayi(satir.get("Lider Id"))
    mac = mac_normalize(_metin(satir.get("MAC")))
    sube = _metin(satir.get("Şube Adı"))[:100]
    if lider_id is None or lider_id <= 0:
        raise EnvanterHatasi("Lider Id geçersiz")
    if not mac:
        raise EnvanterHatasi("MAC adresi geçersiz")
    if not sube:
        raise EnvanterHatasi("Şube adı boş")

    alanlar = {"mac_adresi": mac, "sube_adi": sube}
    for baslik, alan in SUTUNLAR.items():
        if baslik in ZORUNLU or baslik not in satir:
            continue
        deger = satir[baslik]
        if alan in TARIH_ALANLARI:
            alanlar[alan] = _tarih(deger)
        elif alan in SAYI_ALANLARI:
            sayi = _sayi(deger)
            alanlar[alan] = sayi if sayi is not None and sayi >= 0 else None
        elif alan == "lider_cevrimici":
            alanlar[alan] = _evet_hayir(deger, "Çevrimiçi", "Çevrimdışı")
        elif alan == "lider_aktif":
            alanlar[alan] = _evet_hayir(deger, "Aktif", "Pasif")
        elif alan == "ip_adresi":
            alanlar[alan] = _metin(deger) or None
        else:
            uzunluk = TahtaEnvanteri._meta.get_field(alan).max_length
            alanlar[alan] = _metin(deger)[:uzunluk]
    return lider_id, alanlar


def excel_satirlari(dosya):
    try:
        kitap = openpyxl.load_workbook(dosya, read_only=True, data_only=True)
    except Exception as hata:  # openpyxl çok çeşitli hata türleri fırlatır
        raise EnvanterHatasi(f"Excel dosyası açılamadı: {hata}") from hata
    try:
        satirlar = kitap.active.iter_rows(values_only=True)
        basliklar = [_metin(b) for b in next(satirlar, ())]
        eksik = ZORUNLU - set(basliklar)
        if eksik:
            raise EnvanterHatasi(f"Eksik sütun(lar): {', '.join(sorted(eksik))}")
        for satir in satirlar:
            if any(d not in (None, "") for d in satir):
                yield dict(zip(basliklar, satir))
    finally:
        kitap.close()


@transaction.atomic
def envanteri_yukle(dosya):
    sonuc = AktarimSonucu()
    for sira, satir in enumerate(excel_satirlari(dosya), start=2):
        try:
            lider_id, alanlar = satiri_donustur(satir)
        except EnvanterHatasi as hata:
            sonuc.hatalar.append(f"{sira}. satır: {hata}")
            continue
        cakisan = (
            TahtaEnvanteri.objects.filter(mac_adresi=alanlar["mac_adresi"])
            .exclude(lider_id=lider_id)
            .exists()
        )
        if cakisan:
            sonuc.hatalar.append(f"{sira}. satır: MAC başka bir Lider kaydında var")
            continue
        _, yeni = TahtaEnvanteri.objects.update_or_create(lider_id=lider_id, defaults=alanlar)
        if yeni:
            sonuc.eklenen += 1
        else:
            sonuc.guncellenen += 1

    # Envanterden önce kaydolmuş tahtaları da bağla.
    for tahta in Tahta.objects.filter(envanter__isnull=True).exclude(mac_adresleri=""):
        envanteri_bagla(tahta, tahta.mac_adresleri.split(", "))
        if tahta.envanter_id:
            tahta.save()
            sonuc.baglanan += 1
    return sonuc
