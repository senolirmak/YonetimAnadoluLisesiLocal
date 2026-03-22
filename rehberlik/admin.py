from django.contrib import admin

from .models import Gorusme


@admin.register(Gorusme)
class GorusmeAdmin(admin.ModelAdmin):
    list_display = ("tarih", "tur", "ogrenci", "konu", "rehber", "gizli", "takip_tarihi")
    list_filter = ("tur", "gizli", "tarih")
    search_fields = ("konu", "aciklama", "sonuc", "ogrenci__adi", "ogrenci__soyadi")
    date_hierarchy = "tarih"
    raw_id_fields = ("ogrenci", "rehber")
