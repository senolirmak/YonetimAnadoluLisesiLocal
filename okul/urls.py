# -*- coding: utf-8 -*-
from django.urls import path

from okul import crud, views

app_name = "okul"

urlpatterns = [
    path("ders-havuzu/", views.ders_havuzu_ayarlari, name="ders_havuzu_ayarlari"),
    path("ders-havuzu/kaydet/", views.ders_havuzu_ayarlari_kaydet, name="ders_havuzu_ayarlari_kaydet"),

    path("yonetim/", crud.yonetim_index, name="yonetim_index"),
    path("yonetim/<slug:slug>/", crud.yonetim_list, name="yonetim_list"),
    path("yonetim/<slug:slug>/ekle/", crud.yonetim_create, name="yonetim_create"),
    path("yonetim/<slug:slug>/<int:pk>/duzenle/", crud.yonetim_update, name="yonetim_update"),
    path("yonetim/<slug:slug>/<int:pk>/sil/", crud.yonetim_delete, name="yonetim_delete"),

    path("yonetim/sinif-sube/<int:pk>/yil/ata/", crud.sinif_sube_yil_ata, name="sinif_sube_yil_ata"),
    path("yonetim/sinif-sube/<int:pk>/yil/<int:yil_pk>/sil/", crud.sinif_sube_yil_sil, name="sinif_sube_yil_sil"),

    path(
        "yonetim/personel/<int:pk>/okutma-yetkisi/",
        crud.personel_okutma_yetkisi_ata,
        name="personel_okutma_yetkisi_ata",
    ),
]
