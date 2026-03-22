from django.urls import path

from . import views

app_name = "ogrenci"

urlpatterns = [
    path("", views.ogrenci_liste, name="ogrenci_liste"),
    path("<int:pk>/detay/", views.ogrenci_detay_duzenle, name="ogrenci_detay_duzenle"),
    path("excel-yukle/", views.excel_yukle, name="excel_yukle"),
]
