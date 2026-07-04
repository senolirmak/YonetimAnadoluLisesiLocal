from django.contrib import admin

from sorumluluk.models import (
    OncekiDonem,
    OncekiDonemGorev,
    SorumluDers,
    SorumluDersHavuzu,
    SorumluOgrenci,
    SorumluOturmaPlani,
    SorumluSinav,
    SorumluSinavParametre,
    SorumluTakvim,
)


class SorumluDersInline(admin.TabularInline):
    model = SorumluDers
    extra = 0


@admin.register(SorumluOgrenci)
class SorumluOgrenciAdmin(admin.ModelAdmin):
    list_display  = ["okulno", "adi_soyadi", "sinif", "sube", "aktif"]
    list_filter   = ["sinif", "sube", "aktif"]
    search_fields = ["okulno", "adi_soyadi"]
    inlines       = [SorumluDersInline]


@admin.register(SorumluSinav)
class SorumluSinavAdmin(admin.ModelAdmin):
    list_display = ["sinav_adi", "onaylandi", "olusturma_tarihi"]


@admin.register(SorumluTakvim)
class SorumluTakvimAdmin(admin.ModelAdmin):
    list_display  = ["sinav", "tarih", "oturum_no", "saat_baslangic", "sinav_turu", "ders_adi"]
    list_filter   = ["sinav", "tarih", "sinav_turu"]
    search_fields = ["ders_adi"]


admin.site.register(SorumluSinavParametre)
admin.site.register(SorumluOturmaPlani)
admin.site.register(SorumluDersHavuzu)


class OncekiDonemGorevInline(admin.TabularInline):
    model    = OncekiDonemGorev
    extra    = 0
    fields   = ["personel", "komisyon", "gozetmen"]
    ordering = ["personel__brans__ad", "personel__adi_soyadi"]


@admin.register(OncekiDonem)
class OncekiDonemAdmin(admin.ModelAdmin):
    list_display  = ["sinav_adi", "egitim_yili", "get_donem_turu_display", "gorev_sayisi", "olusturma_tarihi"]
    list_filter   = ["donem_turu", "egitim_yili"]
    search_fields = ["sinav_adi", "aciklama"]
    inlines       = [OncekiDonemGorevInline]

    @admin.display(description="Görev Kaydı")
    def gorev_sayisi(self, obj):
        return f"{obj.gorevler.count()} öğretmen"