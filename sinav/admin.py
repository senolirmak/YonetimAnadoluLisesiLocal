from django.contrib import admin
from .models import DersHavuzu, DisVeri


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
