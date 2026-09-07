from django.contrib import admin

from .models import EbaHesap, EbaOturum


@admin.register(EbaHesap)
class EbaHesapAdmin(admin.ModelAdmin):
    list_display = ("personel", "eba_id", "eba_adi_soyadi", "baglanma_zamani")
    search_fields = ("personel__adi_soyadi", "eba_id", "eba_adi_soyadi")
    autocomplete_fields = ["personel"]


@admin.register(EbaOturum)
class EbaOturumAdmin(admin.ModelAdmin):
    list_display = (
        "token", "amac", "durum", "eba_id", "eslesen_personel", "olusturma_zamani",
    )
    list_filter = ("amac", "durum")
    search_fields = ("token", "eba_id", "eba_adi_soyadi")
    readonly_fields = [f.name for f in EbaOturum._meta.fields]

    def has_add_permission(self, request):
        # Bu kayıtlar yalnızca view/worker akışıyla oluşturulur; admin'den
        # elle yeni bir oturum eklemenin bir anlamı yok.
        return False
