from django.contrib import admin

from kurul.models import (
    GundemMaddesi,
    Karar,
    Katilim,
    Kurul,
    KurulTuru,
    KurulUyesi,
    KurulYapiKalemi,
    Toplanti,
)


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


class GundemMaddesiInline(admin.TabularInline):
    model = GundemMaddesi
    extra = 0
    fields = ("sira", "baslik", "onceki_kararlar")


class KatilimInline(admin.TabularInline):
    model = Katilim
    extra = 0
    fields = ("ad", "gorev", "asil", "durum", "aciklama")
    readonly_fields = ("ad", "gorev")


@admin.register(Toplanti)
class ToplantiAdmin(admin.ModelAdmin):
    list_display = ("kurul", "no", "tarih", "saat", "tur", "durum")
    list_filter = ("durum", "tur", "kurul__egitim_yili")
    search_fields = ("kurul__ad", "yer")
    date_hierarchy = "tarih"
    raw_id_fields = ("kurul", "onaylayan", "olusturan")
    inlines = [GundemMaddesiInline, KatilimInline]


@admin.register(Karar)
class KararAdmin(admin.ModelAdmin):
    list_display = ("toplanti", "no", "oylama", "takip_durumu", "termin")
    list_filter = ("takip_durumu", "oylama")
    search_fields = ("metin", "toplanti__kurul__ad")
    raw_id_fields = ("toplanti", "gundem_maddesi", "sorumlu")
