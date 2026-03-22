from django.contrib import admin
from .models import OkulBilgileri, SinifSube, DersHavuzu, DisVeri


@admin.register(OkulBilgileri)
class OkulBilgileriAdmin(admin.ModelAdmin):
    list_display = ["okul_adi", "okul_kodu", "okul_muduru"]


@admin.register(SinifSube)
class SinifSubeAdmin(admin.ModelAdmin):
    list_display = ["sinif", "sube", "sinifsube", "salon"]
    list_filter = ["sinif"]
    ordering = ["sinif", "sube"]
    readonly_fields = ["sinifsube", "salon"]


@admin.register(DersHavuzu)
class DersHavuzuAdmin(admin.ModelAdmin):
    list_display = ["ders_adi"]
    search_fields = ["ders_adi"]
    ordering = ["ders_adi"]


@admin.register(DisVeri)
class DisVeriAdmin(admin.ModelAdmin):
    list_display = ["sinav", "dosya_etiketi", "gecerlilik_tarihi", "yukleme_tarihi", "dosya"]
    list_filter = ["sinav", "dosya_etiketi"]
    readonly_fields = ["yukleme_tarihi"]
