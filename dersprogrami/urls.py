from django.urls import path

from . import views

urlpatterns = [
    path("", views.dersprogrami_listesi, name="dersprogrami_listesi"),
    path("yukle/", views.dersprogrami_yukle, name="dersprogrami_yukle"),
    path("ogretmen-programi/", views.ogretmen_program, name="ogretmen_program"),
    path("sinif-programi/", views.sinif_program, name="sinif_program"),
    path("sinif-ogretmenleri/", views.sinif_ogretmenleri, name="sinif_ogretmenleri"),
    path("haftalik-program/", views.haftalik_ders_programi, name="haftalik_ders_programi"),
    path("rehber-ogretmenler/", views.rehber_ogretmenler, name="rehber_ogretmenler"),
    path("ogretmen-ders-listesi/", views.ogretmen_ders_listesi, name="ogretmen_ders_listesi"),
    path("fet/", views.fet_kopru, name="fet_kopru"),
    path("fet/indir/", views.fet_indir, name="fet_indir"),
    path("fet/aktif-yap/", views.fet_aktif_yap, name="fet_aktif_yap"),
    path("fet/yayin/gelen/", views.fet_yayin_al, name="fet_yayin_al"),
    path("fet/gelen/yukle/", views.fet_paket_yukle, name="fet_paket_yukle"),
    path("fet/gelen/<int:pk>/", views.fet_gelen_detay, name="fet_gelen_detay"),
    path("fet/gelen/<int:pk>/<str:islem>/", views.fet_gelen_islem, name="fet_gelen_islem"),
]
