from django.contrib import admin

from .models import AktifVeriKonfigurasyonu, OkulYonetici, VeriAktarimGecmisi


@admin.register(OkulYonetici)
class OkulYoneticiAdmin(admin.ModelAdmin):
    list_display = ("user", "unvan", "personel", "aktif")
    list_filter = ("unvan", "aktif")
    search_fields = ("user__username", "user__first_name", "user__last_name",
                     "personel__adi_soyadi")
    raw_id_fields = ("user", "personel")


@admin.register(VeriAktarimGecmisi)
class VeriAktarimGecmisiAdmin(admin.ModelAdmin):
    list_display = (
        "dosya_turu", "dosya_adi", "uygulama_tarihi",
        "dosya_tarihi", "yukleme_tarihi", "kullanici",
        "kayit_sayisi", "hata_sayisi", "otomatik_eklenen", "durum",
    )
    list_filter = ("dosya_turu", "durum", "yukleme_tarihi")
    search_fields = ("dosya_adi", "kullanici__username", "notlar")
    readonly_fields = (
        "yukleme_tarihi", "kayit_sayisi", "hata_sayisi",
        "otomatik_eklenen", "durum", "notlar",
    )
    date_hierarchy = "yukleme_tarihi"


@admin.register(AktifVeriKonfigurasyonu)
class AktifVeriKonfigurasyonuAdmin(admin.ModelAdmin):
    list_display = ("veri_turu", "uygulama_tarihi", "guncelleme_tarihi")
    readonly_fields = ("guncelleme_tarihi",)
