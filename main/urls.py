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
    path("sinav/medya/", views.ogretmen_sinav_medya, name="ogretmen_sinav_medya"),
    path("sinav/gozetim/sinif-listesi/", views.ogretmen_gozetim_sinif_listesi, name="ogretmen_gozetim_sinif_listesi"),
    path("sinav/gozetim/salon-yoklama/", views.sinav_salon_yoklama, name="sinav_salon_yoklama"),
    path("sinav/istatistik/", views.sinav_oturum_istatistik, name="sinav_oturum_istatistik"),
    path("sinav/yoklama-raporum/", views.ogretmen_yoklama_raporum, name="ogretmen_yoklama_raporum"),
    path("okul-ayarlari/", views.okul_ayarlari, name="okul_ayarlari"),
    path("sinif/oturma-plani/", views.sinif_oturma_plani, name="sinif_oturma_plani"),
]
