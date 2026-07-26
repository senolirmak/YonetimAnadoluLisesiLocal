from django.contrib import admin

from senesonu.models import SeneSonuGecisi, SeneSonuOgrenciGecisi


class SeneSonuOgrenciGecisiInline(admin.TabularInline):
    model = SeneSonuOgrenciGecisi
    extra = 0


@admin.register(SeneSonuGecisi)
class SeneSonuGecisiAdmin(admin.ModelAdmin):
    list_display = ("eski_egitim_yili", "yeni_egitim_yili", "uygulandi", "olusturulma_zamani")
    list_filter = ("uygulandi",)
    inlines = [SeneSonuOgrenciGecisiInline]


@admin.register(SeneSonuOgrenciGecisi)
class SeneSonuOgrenciGecisiAdmin(admin.ModelAdmin):
    list_display = ("gecis", "ogrenci", "eski_sinif", "eski_sube", "yeni_sinif", "yeni_sube", "durum")
    list_filter = ("durum", "eski_sinif")
    search_fields = ("ogrenci__adi", "ogrenci__soyadi", "ogrenci__okulno")
