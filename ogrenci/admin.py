from django.contrib import admin

from .models import Ogrenci, OgrenciAdres, OgrenciAyrilma, OgrenciDetay


class OgrenciDetayInline(admin.StackedInline):
    model = OgrenciDetay
    can_delete = False
    verbose_name = "Aile / Veli Bilgileri"


class OgrenciAdresInline(admin.StackedInline):
    model = OgrenciAdres
    can_delete = False
    verbose_name = "Adres Bilgileri"


@admin.register(Ogrenci)
class OgrenciAdmin(admin.ModelAdmin):
    list_display = ("okulno", "sinif", "sube", "adi", "soyadi", "tckimlikno", "cinsiyet")
    list_filter = ("sinif", "sube", "cinsiyet")
    search_fields = ("okulno", "tckimlikno", "adi", "soyadi")
    inlines = [OgrenciDetayInline, OgrenciAdresInline]


@admin.register(OgrenciAyrilma)
class OgrenciAyrilmaAdmin(admin.ModelAdmin):
    list_display = ("ogrenci", "sebep", "tarih", "egitim_yili", "olusturma")
    list_filter = ("sebep", "egitim_yili")
    search_fields = ("ogrenci__okulno", "ogrenci__adi", "ogrenci__soyadi")
    autocomplete_fields = ["ogrenci"]
