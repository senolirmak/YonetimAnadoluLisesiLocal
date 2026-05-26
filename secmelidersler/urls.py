from django.urls import path

from . import views

urlpatterns = [
    path("", views.ogrenci_listesi, name="secmeli_ogrenci_listesi"),
    path("<int:ogrenci_pk>/", views.ogrenci_secim_formu, name="secmeli_ogrenci_formu"),
    path("<int:ogrenci_pk>/pdf/", views.ogrenci_secim_pdf, name="secmeli_ogrenci_pdf"),
    path("alanlar/", views.alan_listesi, name="secmeli_alan_listesi"),
    path("alanlar/yeni/", views.alan_form, name="secmeli_alan_yeni"),
    path("alanlar/<int:pk>/", views.alan_form, name="secmeli_alan_duzenle"),
    path("alanlar/<int:pk>/sil/", views.alan_sil, name="secmeli_alan_sil"),
]
