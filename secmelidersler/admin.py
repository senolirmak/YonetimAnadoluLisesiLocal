from django.contrib import admin

from .models import OrtakDers, SecmeliDers, SecmeliDersGrubu, SinifSeviyeToplamSaat


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
    list_display = ("egitim_yili", "sinif_seviyesi", "sira", "ders_adi", "haftalik_saat")
    list_filter = ("egitim_yili", "sinif_seviyesi")
    ordering = ("-egitim_yili__egitim_yili", "sinif_seviyesi", "sira")


@admin.register(SecmeliDersGrubu)
class SecmeliDersGrubuAdmin(admin.ModelAdmin):
    list_display = ("egitim_yili", "sinif_seviyesi", "sira", "adi", "zorunlu_grup")
    list_filter = ("egitim_yili", "sinif_seviyesi", "zorunlu_grup")
    ordering = ("-egitim_yili__egitim_yili", "sinif_seviyesi", "sira")
    inlines = [SecmeliDersInline]


@admin.register(SecmeliDers)
class SecmeliDersAdmin(admin.ModelAdmin):
    list_display = ("grup", "sira", "ders_adi", "saat_secenekleri", "aktif")
    list_filter = ("grup__egitim_yili", "grup__sinif_seviyesi", "grup", "aktif")
    ordering = ("grup__sinif_seviyesi", "grup__sira", "sira")
    search_fields = ("ders_adi",)


@admin.register(SinifSeviyeToplamSaat)
class SinifSeviyeToplamSaatAdmin(admin.ModelAdmin):
    list_display = ("egitim_yili", "sinif_seviyesi", "haftalik_toplam_saat")
    list_filter = ("egitim_yili",)
    ordering = ("-egitim_yili__egitim_yili", "sinif_seviyesi")
