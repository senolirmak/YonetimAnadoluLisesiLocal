from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="secmeli_index"),
path("alanlar/", views.alan_listesi, name="secmeli_alan_listesi"),
    path("alanlar/yeni/", views.alan_form, name="secmeli_alan_yeni"),
    path("alanlar/<int:pk>/", views.alan_form, name="secmeli_alan_duzenle"),
    path("alanlar/<int:pk>/sil/", views.alan_sil, name="secmeli_alan_sil"),
    path("ortak-havuz/", views.ortak_havuz_listesi, name="ortak_havuz_listesi"),
    path("ortak-havuz/yeni/", views.ortak_havuz_form, name="ortak_havuz_yeni"),
    path("ortak-havuz/<int:pk>/", views.ortak_havuz_form, name="ortak_havuz_duzenle"),
    path("ortak-havuz/<int:pk>/sil/", views.ortak_havuz_sil, name="ortak_havuz_sil"),
    path("ortak-dersler/", views.ortak_ders_listesi, name="secmeli_ortak_ders_listesi"),
    path("ortak-dersler/ekle/", views.ortak_ders_havuzdan_ekle, name="secmeli_ortak_ders_ekle"),
    path("ortak-dersler/<int:pk>/sil/", views.ortak_ders_sil, name="secmeli_ortak_ders_sil"),
    path("havuz/", views.secmeli_havuz_listesi, name="secmeli_havuz_listesi"),
    path("havuz/yeni/", views.secmeli_havuz_form, name="secmeli_havuz_yeni"),
    path("havuz/<int:pk>/", views.secmeli_havuz_form, name="secmeli_havuz_duzenle"),
    path("havuz/<int:pk>/sil/", views.secmeli_havuz_sil, name="secmeli_havuz_sil"),
    path("gruplar/", views.secmeli_grup_listesi, name="secmeli_grup_listesi"),
    path("gruplar/yeni/", views.secmeli_grup_form, name="secmeli_grup_yeni"),
    path("gruplar/<int:grup_pk>/dersler/", views.secmeli_grup_ders_listesi, name="secmeli_grup_ders_listesi"),
    path("gruplar/<int:pk>/", views.secmeli_grup_form, name="secmeli_grup_duzenle"),
    path("gruplar/<int:pk>/sil/", views.secmeli_grup_sil, name="secmeli_grup_sil"),
    path("gruplar/<int:grup_pk>/ders/ekle/", views.secmeli_ders_havuzdan_ekle, name="secmeli_ders_ekle"),
    path("gruplar/<int:grup_pk>/ders/yeni/", views.secmeli_ders_form, name="secmeli_ders_yeni"),
    path("gruplar/<int:grup_pk>/ders/<int:pk>/", views.secmeli_ders_form, name="secmeli_ders_duzenle"),
    path("gruplar/<int:grup_pk>/ders/<int:pk>/sil/", views.secmeli_ders_sil, name="secmeli_ders_sil"),
    path("sinif-toplam-saat/", views.sinif_toplam_saat_listesi, name="secmeli_sinif_toplam_saat"),
]
