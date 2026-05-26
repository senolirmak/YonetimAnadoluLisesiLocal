from django.contrib import admin

from .models import OgrenciSecim, OrtakDers, SecmeliDers, SecmeliDersGrubu


class OrtakDersInline(admin.TabularInline):
    model = OrtakDers
    extra = 1
    fields = ("sira", "ders_adi", "haftalik_saat")


class SecmeliDersInline(admin.TabularInline):
    model = SecmeliDers
    extra = 2
    fields = ("sira", "ders_adi", "saat_secenekleri", "aktif")


@admin.register(OrtakDers)
class OrtakDersAdmin(admin.ModelAdmin):
    list_display = ("sinif_seviyesi", "sira", "ders_adi", "haftalik_saat")
    list_filter = ("sinif_seviyesi",)
    ordering = ("sinif_seviyesi", "sira")


@admin.register(SecmeliDersGrubu)
class SecmeliDersGrubuAdmin(admin.ModelAdmin):
    list_display = ("sinif_seviyesi", "sira", "adi", "zorunlu_grup")
    list_filter = ("sinif_seviyesi", "zorunlu_grup")
    ordering = ("sinif_seviyesi", "sira")
    inlines = [SecmeliDersInline]


@admin.register(SecmeliDers)
class SecmeliDersAdmin(admin.ModelAdmin):
    list_display = ("grup", "sira", "ders_adi", "saat_secenekleri", "aktif")
    list_filter = ("grup__sinif_seviyesi", "grup", "aktif")
    ordering = ("grup__sinif_seviyesi", "grup__sira", "sira")
    search_fields = ("ders_adi",)


@admin.register(OgrenciSecim)
class OgrenciSecimAdmin(admin.ModelAdmin):
    list_display = ("ogrenci", "ders", "secilen_saat", "guncelleme_tarihi")
    list_filter = ("ders__grup__sinif_seviyesi", "ders__grup")
    search_fields = ("ogrenci__adi", "ogrenci__soyadi", "ogrenci__okulno")
    autocomplete_fields = ("ogrenci",)
    raw_id_fields = ("ders",)
