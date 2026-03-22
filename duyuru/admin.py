from django.contrib import admin

from .models import Duyuru


@admin.register(Duyuru)
class DuyuruAdmin(admin.ModelAdmin):
    list_display = ("sinif", "tarih", "ders_saati", "mesaj_ozeti", "olusturan", "olusturulma_zaman")
    list_filter = ("tarih", "sinif", "ders_saati")
    search_fields = ("mesaj", "sinif__sinif", "sinif__sube")

    def mesaj_ozeti(self, obj):
        return obj.mesaj[:50] + "..." if len(obj.mesaj) > 50 else obj.mesaj

    mesaj_ozeti.short_description = "Mesaj Özeti"
