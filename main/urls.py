from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("nobet/haftalik/", views.ogretmen_haftalik_nobet, name="ogretmen_haftalik_nobet"),
    path(
        "nobet/gunun-nobetcileri/",
        views.ogretmen_gunun_nobetcileri,
        name="ogretmen_gunun_nobetcileri",
    ),
    path("nobet/ders-doldurma/", views.ogretmen_ders_doldurma, name="ogretmen_ders_doldurma"),
    path("sinav/gozetim/", views.ogretmen_sinav_gozetim, name="ogretmen_sinav_gozetim"),
    path("sinav/gozetim/sinif-listesi/", views.ogretmen_gozetim_sinif_listesi, name="ogretmen_gozetim_sinif_listesi"),
]
