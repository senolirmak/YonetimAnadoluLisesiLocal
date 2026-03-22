from django.urls import path

from . import views

urlpatterns = [
    path("", views.dersprogrami_listesi, name="dersprogrami_listesi"),
    path("yukle/", views.dersprogrami_yukle, name="dersprogrami_yukle"),
    path("ogretmen-programi/", views.ogretmen_program, name="ogretmen_program"),
    path("sinif-programi/", views.sinif_program, name="sinif_program"),
    path("sinif-ogretmenleri/", views.sinif_ogretmenleri, name="sinif_ogretmenleri"),
]
