from django.contrib import admin

from .models import OgrenciDevamsizlik


@admin.register(OgrenciDevamsizlik)
class OgrenciDevamsizlikAdmin(admin.ModelAdmin):
    list_display = ("ogrenci", "tarih", "ders_saati", "ders_adi", "ogretmen_adi", "aciklama")
    list_filter = ("tarih", "ders_saati")
    search_fields = (
        "ogrenci__adi",
        "ogrenci__soyadi",
        "ogrenci__okulno",
        "ders_adi",
        "ogretmen_adi",
        "aciklama",
    )
    date_hierarchy = "tarih"
    ordering = ("-tarih", "ders_saati")
