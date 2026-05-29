from django.urls import path

from . import views

urlpatterns = [
    path("", views.ogrenci_listesi, name="ogrdrs_listesi"),
    path("toplu-ders-ata/", views.sinif_toplu_ders_ata, name="ogrdrs_toplu_ders_ata"),
    path("toplu-zorunlu-ata/", views.sinif_toplu_zorunlu_ata, name="ogrdrs_toplu_zorunlu_ata"),
    path("<int:ogrenci_pk>/", views.ogrenci_detay, name="ogrdrs_detay"),
    path("<int:ogrenci_pk>/secmeli/", views.ogrenci_secmeli_form, name="ogrdrs_secmeli_form"),
    path("<int:ogrenci_pk>/secmeli/pdf/", views.ogrenci_secmeli_pdf, name="ogrdrs_secmeli_pdf"),
    path("<int:ogrenci_pk>/mevcut/ata/", views.ogrenci_mevcutyil_ata, name="ogrdrs_mevcut_ata"),
    path("<int:ogrenci_pk>/mevcut/<int:ders_pk>/sil/", views.ogrenci_mevcutyil_sil, name="ogrdrs_mevcut_sil"),
    path("<int:ogrenci_pk>/zorunlu/ata/", views.ogrenci_zorunlu_ata, name="ogrdrs_zorunlu_ata"),
    path("<int:ogrenci_pk>/zorunlu/<int:ders_pk>/sil/", views.ogrenci_zorunlu_sil, name="ogrdrs_zorunlu_sil"),
]
