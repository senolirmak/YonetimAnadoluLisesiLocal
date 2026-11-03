from django.contrib import admin

from ogrenci.models import Ogrenci
from okul.models import Personel

from .models import KulupDanisman, KulupUyelik, SosyalKulup


class YeniKayittaAktifleriListele:
    """Yeni kayıt eklerken seçim listelerini güncel adaylarla sınırlar (aktif kulüp,
    görevdeki öğretmen, aktif öğrenci). Var olan kayıt düzenlenirken sınır uygulanmaz;
    arşivlenmiş öğrenci/personelin geçmiş kayıtları açılabilmelidir."""

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is None:
            alanlar = form.base_fields
            if "kulup" in alanlar:
                alanlar["kulup"].queryset = SosyalKulup.objects.filter(aktif=True)
            if "ogretmen" in alanlar:
                alanlar["ogretmen"].queryset = Personel.objects.gorevde()
            if "ogrenci" in alanlar:
                alanlar["ogrenci"].queryset = Ogrenci.objects.filter(aktif=True)
        return form


@admin.register(SosyalKulup)
class SosyalKulupAdmin(admin.ModelAdmin):
    list_display = ("ad", "aktif")
    list_filter = ("aktif",)
    search_fields = ("ad",)


@admin.register(KulupDanisman)
class KulupDanismanAdmin(YeniKayittaAktifleriListele, admin.ModelAdmin):
    list_display = ("kulup", "ogretmen", "egitim_yili")
    list_filter = ("egitim_yili", "kulup")
    search_fields = ("kulup__ad", "ogretmen__adi_soyadi")
    list_select_related = ("kulup", "ogretmen", "egitim_yili")


@admin.register(KulupUyelik)
class KulupUyelikAdmin(YeniKayittaAktifleriListele, admin.ModelAdmin):
    list_display = ("ogrenci", "kulup", "gorev", "egitim_yili")
    list_filter = ("egitim_yili", "kulup", "gorev")
    search_fields = ("kulup__ad", "ogrenci__adi", "ogrenci__soyadi", "ogrenci__okulno")
    list_select_related = ("kulup", "ogrenci", "egitim_yili")
