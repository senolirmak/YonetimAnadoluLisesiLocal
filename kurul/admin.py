from django.contrib import admin

from kurul.models import Kurul, KurulTuru, KurulUyesi, KurulYapiKalemi


class KurulYapiKalemiInline(admin.TabularInline):
    model = KurulYapiKalemi
    extra = 0
    fields = ("sira", "gorev", "unvan", "uye_turu", "personel_secimi", "asil_sayisi", "yedek_sayisi", "otomatik")


@admin.register(KurulTuru)
class KurulTuruAdmin(admin.ModelAdmin):
    inlines = [KurulYapiKalemiInline]
    list_display = ("ad", "kategori", "kapsam", "zorunlu", "gizli", "son_dogrulama", "aktif", "sira")
    list_filter = ("kategori", "kapsam", "zorunlu", "gizli", "aktif")
    search_fields = ("ad", "kod", "mevzuat_dayanagi")
    list_editable = ("aktif", "sira")


class KurulUyesiInline(admin.TabularInline):
    model = KurulUyesi
    extra = 0
    autocomplete_fields = ()
    raw_id_fields = ("personel", "ogrenci")
    fields = ("kalem", "personel", "ogrenci", "dis_uye", "gorev", "asil", "otomatik")


@admin.register(Kurul)
class KurulAdmin(admin.ModelAdmin):
    list_display = ("__str__", "egitim_yili")
    list_filter = ("egitim_yili", "tur__kategori")
    inlines = [KurulUyesiInline]
