from django.urls import path

from . import views

app_name = "devamsizlik"

urlpatterns = [
    path("yoklama/", views.ogretmen_devamsizlik, name="ogretmen_devamsizlik"),
    path("yoklama/<int:ders_saati>/", views.ogretmen_devamsizlik, name="ogretmen_devamsizlik_ders"),
    path("yoklama-listesi/", views.ogrenci_devamsizlik_listesi, name="ogrenci_devamsizlik_listesi"),
    path("yoklama-pdf/", views.ogrenci_devamsizlik_pdf, name="ogrenci_devamsizlik_pdf"),
]
