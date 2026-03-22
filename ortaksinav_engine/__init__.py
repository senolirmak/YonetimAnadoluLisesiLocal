# -*- coding: utf-8 -*-
"""
ortaksinav_engine – public API

views.py bu modul uzerinden servislere erisir.
Her fonksiyon CONFIG'i inject ederek ilgili servisi cagirir.
"""

from ortaksinav_engine.config import CONFIG
from ortaksinav_engine.services.veri_import import VeriImportService
from ortaksinav_engine.services.ders_analiz import DersAnalizService
from ortaksinav_engine.services.takvim import TakvimService
from ortaksinav_engine.services.oturma import OturmaPlanService
def temel_verileri_olustur():
    """DersHavuzu + SinifSube: DB'de olmayan kayitlari ekler."""
    VeriImportService(CONFIG).temel_verileri_olustur()


def verileri_aktar():
    """DersProgram + Ogrenci: Aktif sinav icin FK referanslari kullanarak aktarim yapar."""
    from sinav.models import SinavBilgisi
    aktif = SinavBilgisi.objects.filter(aktif=True).first()
    VeriImportService(CONFIG).verileri_aktar(aktif)


def subeders_guncelle():
    """SubeDers: Aktif sinav derslerinden sinav yapilmayacaklar filtrelenerek eksik kayitlar eklenir."""
    from sinav.models import SinavBilgisi
    aktif = SinavBilgisi.objects.filter(aktif=True).first()
    DersAnalizService(CONFIG).subeders_guncelle(aktif)


def takvim_olustur():
    """Takvim: ILP ile catismasiz sinav takvimi olusturur."""
    TakvimService(CONFIG).adim4()


def oturma_planlarini_olustur():
    """OturmaPlani: Ogrencileri salon ve sira numarasina gore yerlestirir."""
    OturmaPlanService(CONFIG).generate_all()


__all__ = [
    "CONFIG",
    "temel_verileri_olustur",
    "verileri_aktar",
    "subeders_guncelle",
    "takvim_olustur",
    "oturma_planlarini_olustur",
]
