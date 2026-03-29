from django.contrib import admin

from .models import BildirimLog, SinifTahta


@admin.register(SinifTahta)
class SinifTahtaAdmin(admin.ModelAdmin):
    list_display = ["sinif_sube", "ip_adresi", "port", "aktif"]
    list_filter = ["aktif"]
    search_fields = ["ip_adresi", "sinif_sube__sinif", "sinif_sube__sube"]


@admin.register(BildirimLog)
class BildirimLogAdmin(admin.ModelAdmin):
    list_display = ["gonderim_zamani", "tur", "tahta", "baslik", "durum", "gonderen"]
    list_filter = ["tur", "durum"]
    search_fields = ["baslik", "mesaj"]
    readonly_fields = ["gonderim_zamani"]
