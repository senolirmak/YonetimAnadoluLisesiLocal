from django.urls import path

from . import views

urlpatterns = [
    path("", views.ogrenci_listesi, name="ogrdrs_listesi"),
    path("toplu-zorunlu-ata/", views.sinif_toplu_zorunlu_ata, name="ogrdrs_toplu_zorunlu_ata"),
    path("toplu-zorunlu-ata-mevcut/", views.sube_zorunlu_ata_mevcut, name="ogrdrs_toplu_zorunlu_ata_mevcut"),
    path("sube/<int:sinif>/<str:sube>/secmeli/", views.sube_secmeli_form, name="ogrdrs_sube_secmeli_form"),
    path("sube/<int:sinif>/<str:sube>/secmeli-mevcut/", views.sube_secmeli_form_mevcut, name="ogrdrs_sube_secmeli_form_mevcut"),
    path("<int:ogrenci_pk>/", views.ogrenci_detay, name="ogrdrs_detay"),
    path("<int:ogrenci_pk>/alan/<int:alan_pk>/ata/", views.ogrenci_alan_ata, name="ogrdrs_alan_ata"),
    path("<int:ogrenci_pk>/secmeli/", views.ogrenci_secmeli_form, name="ogrdrs_secmeli_form"),
    path("<int:ogrenci_pk>/secmeli/pdf/", views.ogrenci_secmeli_pdf, name="ogrdrs_secmeli_pdf"),
    path(
        "<int:ogrenci_pk>/secmeli/seviye/<int:sinif_seviyesi>/",
        views.ogrenci_secmeli_form_seviye,
        name="ogrdrs_secmeli_form_seviye",
    ),
    path("<int:ogrenci_pk>/zorunlu/ata/", views.ogrenci_zorunlu_ata, name="ogrdrs_zorunlu_ata"),
    path("<int:ogrenci_pk>/zorunlu/<int:ders_pk>/sil/", views.ogrenci_zorunlu_sil, name="ogrdrs_zorunlu_sil"),
]
